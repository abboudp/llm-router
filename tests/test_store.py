from app.store import Store


def make_store(tmp_path):
    return Store(str(tmp_path / "test.db"))


def test_conversation_crud(tmp_path):
    s = make_store(tmp_path)
    c = s.create_conversation()
    assert c["title"] == "New conversation"
    assert s.get_conversation(c["id"])["id"] == c["id"]

    renamed = s.rename_conversation(c["id"], "Renamed")
    assert renamed["title"] == "Renamed"
    assert s.rename_conversation("nope", "x") is None

    c2 = s.create_conversation(title="Second")
    ids = [row["id"] for row in s.list_conversations()]
    assert set(ids) == {c["id"], c2["id"]}

    assert s.delete_conversation(c["id"]) is True
    assert s.delete_conversation(c["id"]) is False
    assert s.get_conversation(c["id"]) is None
    s.close()


def test_messages_roundtrip_and_order(tmp_path):
    s = make_store(tmp_path)
    c = s.create_conversation()
    m1 = s.add_message(c["id"], "user", "hello")
    m2 = s.add_message(c["id"], "assistant", "hi there", latency_ms=1234)
    msgs = s.list_messages(c["id"])
    assert [m["id"] for m in msgs] == [m1["id"], m2["id"]]
    assert msgs[0]["latency_ms"] is None
    assert msgs[1]["latency_ms"] == 1234
    s.close()


def test_delete_cascades_messages(tmp_path):
    s = make_store(tmp_path)
    c = s.create_conversation()
    s.add_message(c["id"], "user", "hello")
    s.delete_conversation(c["id"])
    assert s.list_messages(c["id"]) == []
    s.close()


def test_creates_parent_directory(tmp_path):
    s = Store(str(tmp_path / "nested" / "dir" / "app.db"))
    assert s.create_conversation()["id"]
    s.close()


def test_list_conversations_search_is_case_insensitive_substring(tmp_path):
    s = make_store(tmp_path)
    match = s.create_conversation(title="Kubernetes migration plan")
    s.create_conversation(title="Weekend recipe ideas")

    assert [c["id"] for c in s.list_conversations(q="kubernetes")] == [match["id"]]
    assert [c["id"] for c in s.list_conversations(q="MIGRATION")] == [match["id"]]
    assert s.list_conversations(q="no such thing") == []
    assert len(s.list_conversations(q=None)) == 2
    assert len(s.list_conversations(q="")) == 2
    s.close()


def test_list_conversations_search_case_folding_is_ascii_only(tmp_path):
    # SQLite's LOWER()/LIKE case-folding only covers ASCII A-Z without the
    # ICU extension. This documents that real, current limitation (matching
    # accented letters case-insensitively is out of scope) rather than
    # leaving it as an untested assumption.
    s = make_store(tmp_path)
    s.create_conversation(title="café notes")
    assert [c["title"] for c in s.list_conversations(q="café")] == ["café notes"]
    assert s.list_conversations(q="CAFÉ") == []
    s.close()


def test_list_conversations_search_escapes_sql_wildcards(tmp_path):
    s = make_store(tmp_path)
    percent_title = s.create_conversation(title="50% done")
    s.create_conversation(title="anything at all")

    # A literal "%" in the query should match only titles containing that
    # literal character, not act as a SQL wildcard matching everything.
    assert [c["id"] for c in s.list_conversations(q="50%")] == [percent_title["id"]]
    assert [c["id"] for c in s.list_conversations(q="%")] == [percent_title["id"]]
    s.close()


def test_list_messages_limit_returns_most_recent(tmp_path):
    s = make_store(tmp_path)
    c = s.create_conversation()
    ids = [s.add_message(c["id"], "user", f"turn {n}")["id"] for n in range(4)]

    assert [m["id"] for m in s.list_messages(c["id"], limit=2)] == ids[-2:]
    assert [m["id"] for m in s.list_messages(c["id"])] == ids
    s.close()


def test_list_messages_before_cursor_pages_backwards(tmp_path):
    s = make_store(tmp_path)
    c = s.create_conversation()
    ids = [s.add_message(c["id"], "user", f"turn {n}")["id"] for n in range(5)]

    newest_two = s.list_messages(c["id"], limit=2)
    assert [m["id"] for m in newest_two] == ids[-2:]

    older_two = s.list_messages(c["id"], limit=2, before=newest_two[0]["id"])
    assert [m["id"] for m in older_two] == ids[-4:-2]

    # an unknown cursor is ignored rather than erroring
    assert [m["id"] for m in s.list_messages(c["id"], before="nope")] == ids
    s.close()


def test_list_messages_before_cursor_from_another_conversation_is_ignored(tmp_path):
    s = make_store(tmp_path)
    c1 = s.create_conversation()
    c2 = s.create_conversation()
    other_id = s.add_message(c2["id"], "user", "from another conversation")["id"]
    mine = [s.add_message(c1["id"], "user", f"turn {n}")["id"] for n in range(3)]

    # a cursor id that exists, but belongs to a different conversation,
    # must not leak that conversation's position into this one's results
    assert [m["id"] for m in s.list_messages(c1["id"], before=other_id)] == mine
    s.close()
