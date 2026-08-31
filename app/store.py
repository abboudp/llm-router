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


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


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

    def list_conversations(self) -> list[dict]:
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

    def list_messages(self, conversation_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, id",
            (conversation_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
