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
