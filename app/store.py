"""SQLite persistence for conversations and messages."""
import os
import sqlite3
import time
import uuid

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    latency_ms INTEGER,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);
"""


def _row_to_dict(row: sqlite3.Row, drop: tuple[str, ...] = ()) -> dict:
    return {k: row[k] for k in row.keys() if k not in drop}


class Store:
    def __init__(self, path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- conversations -----------------------------------------------------

    def create_conversation(self, title: str = "New conversation") -> dict:
        now = time.time()
        conversation = {
            "id": uuid.uuid4().hex,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }
        self._conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conversation["id"], title, now, now),
        )
        self._conn.commit()
        return conversation

    def list_conversations(self, q: str | None = None) -> list[dict]:
        if q:
            # Escape SQL LIKE wildcards in the query itself, so searching for
            # e.g. a title containing a literal "%" or "_" does a plain
            # substring match instead of an unintended wildcard match.
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = self._conn.execute(
                "SELECT * FROM conversations WHERE LOWER(title) LIKE LOWER(?) ESCAPE '\\'"
                " ORDER BY updated_at DESC",
                (f"%{escaped}%",),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_conversation(self, conversation_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None

    def rename_conversation(self, conversation_id: str, title: str) -> dict | None:
        cur = self._conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), conversation_id),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # -- messages ----------------------------------------------------------

    def add_message(self, conversation_id: str, role: str, content: str,
                    latency_ms: int | None = None) -> dict:
        now = time.time()
        message = {
            "id": uuid.uuid4().hex,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "latency_ms": latency_ms,
            "created_at": now,
        }
        self._conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, latency_ms, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (message["id"], conversation_id, role, content, latency_ms, now),
        )
        self._conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        self._conn.commit()
        return message

    def list_messages(self, conversation_id: str, limit: int | None = None,
                      before: str | None = None) -> list[dict]:
        """List a conversation's messages in chronological order.

        With no arguments, returns the full history (unchanged behavior).
        `limit` caps how many are returned; `before` is a message id cursor —
        only messages that happened strictly before it are considered. The
        combination lets a caller page backwards through history: e.g.
        `limit=20` returns the most recent 20 turns, and passing the id of
        the oldest one back in as `before` fetches the 20 before that.
        """
        # Tie-break on the implicit sqlite rowid (insertion order), not the
        # message id: ids are random uuids, so using them to break ties
        # between same-timestamp rows would not reliably preserve the order
        # messages were actually written in.
        query = "SELECT *, rowid FROM messages WHERE conversation_id = ?"
        params: list = [conversation_id]
        if before:
            anchor = self._conn.execute(
                "SELECT created_at, rowid FROM messages WHERE id = ? AND conversation_id = ?",
                (before, conversation_id),
            ).fetchone()
            if anchor is not None:
                query += " AND (created_at, rowid) < (?, ?)"
                params += [anchor["created_at"], anchor["rowid"]]
        query += " ORDER BY created_at DESC, rowid DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_dict(r, drop=("rowid",)) for r in reversed(rows)]

    def close(self) -> None:
        self._conn.close()
