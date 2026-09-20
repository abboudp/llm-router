from fastapi.testclient import TestClient

from app import main


def client():
    return TestClient(main.app)


def test_create_list_rename_delete():
    with client() as c:
        created = c.post("/v1/conversations", json={"title": "My chat"})
        assert created.status_code == 201
        cid = created.json()["id"]
        assert created.json()["title"] == "My chat"

        default = c.post("/v1/conversations", json={})
        assert default.json()["title"] == "New conversation"

        listing = c.get("/v1/conversations")
        assert listing.status_code == 200
        assert {row["id"] for row in listing.json()} >= {cid}

        renamed = c.patch(f"/v1/conversations/{cid}", json={"title": "Renamed"})
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Renamed"
        assert c.patch("/v1/conversations/nope", json={"title": "x"}).status_code == 404

        assert c.delete(f"/v1/conversations/{cid}").status_code == 204
        assert c.delete(f"/v1/conversations/{cid}").status_code == 404


def test_messages_listing_and_404():
    with client() as c:
        cid = c.post("/v1/conversations", json={}).json()["id"]
        assert c.get(f"/v1/conversations/{cid}/messages").json() == []
        assert c.get("/v1/conversations/nope/messages").status_code == 404


def test_search_filters_by_title_case_insensitively():
    with client() as c:
        cid = c.post("/v1/conversations", json={"title": "Kubernetes migration plan"}).json()["id"]
        c.post("/v1/conversations", json={"title": "Weekend recipe ideas"})

        matched = c.get("/v1/conversations", params={"q": "KUBERNETES"}).json()
        assert [row["id"] for row in matched] == [cid]

        unmatched = c.get("/v1/conversations", params={"q": "no such title"}).json()
        assert unmatched == []


def test_search_blank_query_returns_everything():
    with client() as c:
        c.post("/v1/conversations", json={"title": "One"})
        c.post("/v1/conversations", json={"title": "Two"})
        assert len(c.get("/v1/conversations").json()) == 2
        assert len(c.get("/v1/conversations", params={"q": ""}).json()) == 2


def test_search_rejects_overly_long_query():
    with client() as c:
        resp = c.get("/v1/conversations", params={"q": "x" * 201})
        assert resp.status_code == 422


def test_search_query_at_max_length_is_accepted():
    with client() as c:
        resp = c.get("/v1/conversations", params={"q": "x" * 200})
        assert resp.status_code == 200


def test_search_results_stay_ordered_by_most_recently_updated():
    with client() as c:
        old_id = c.post("/v1/conversations", json={"title": "Kubernetes setup"}).json()["id"]
        new_id = c.post("/v1/conversations", json={"title": "Kubernetes migration"}).json()["id"]
        # Bump `old_id` back to the top by renaming it after `new_id` was created.
        c.patch(f"/v1/conversations/{old_id}", json={"title": "Kubernetes setup (updated)"})

        results = c.get("/v1/conversations", params={"q": "kubernetes"}).json()
        assert [r["id"] for r in results] == [old_id, new_id]


def test_create_conversation_with_empty_title_falls_back_to_default():
    with client() as c:
        resp = c.post("/v1/conversations", json={"title": ""})
        assert resp.json()["title"] == "New conversation"


def test_messages_pagination_limit_and_before_cursor():
    with client() as c:
        cid = c.post("/v1/conversations", json={}).json()["id"]
        store = main.app.state.store
        ids = [store.add_message(cid, "user", f"turn {n}")["id"] for n in range(5)]

        page = c.get(f"/v1/conversations/{cid}/messages", params={"limit": 2}).json()
        assert [m["id"] for m in page] == ids[-2:]

        earlier = c.get(
            f"/v1/conversations/{cid}/messages",
            params={"limit": 2, "before": ids[-2]},
        ).json()
        assert [m["id"] for m in earlier] == ids[-4:-2]


def test_messages_pagination_rejects_non_positive_limit():
    with client() as c:
        cid = c.post("/v1/conversations", json={}).json()["id"]
        assert c.get(f"/v1/conversations/{cid}/messages", params={"limit": 0}).status_code == 422


def test_messages_pagination_rejects_limit_above_max():
    with client() as c:
        cid = c.post("/v1/conversations", json={}).json()["id"]
        resp = c.get(f"/v1/conversations/{cid}/messages", params={"limit": 10_000})
        assert resp.status_code == 422


def test_messages_pagination_at_the_max_limit_is_accepted():
    with client() as c:
        cid = c.post("/v1/conversations", json={}).json()["id"]
        resp = c.get(f"/v1/conversations/{cid}/messages", params={"limit": 200})
        assert resp.status_code == 200


def test_messages_before_empty_string_behaves_like_no_cursor():
    with client() as c:
        cid = c.post("/v1/conversations", json={}).json()["id"]
        store = main.app.state.store
        ids = [store.add_message(cid, "user", f"turn {n}")["id"] for n in range(3)]

        without_cursor = c.get(f"/v1/conversations/{cid}/messages").json()
        with_empty_cursor = c.get(
            f"/v1/conversations/{cid}/messages", params={"before": ""}
        ).json()
        assert [m["id"] for m in without_cursor] == ids
        assert [m["id"] for m in with_empty_cursor] == ids


def test_export_returns_markdown_attachment():
    with client() as c:
        cid = c.post("/v1/conversations", json={"title": "Export me"}).json()["id"]
        store = main.app.state.store
        store.add_message(cid, "user", "hello")
        store.add_message(cid, "assistant", "hi there")

        resp = c.get(f"/v1/conversations/{cid}/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert 'filename="export-me.md"' in resp.headers["content-disposition"]
        assert resp.text.startswith("# Export me\n")
        assert "## User" in resp.text
        assert "## Assistant" in resp.text


def test_export_unknown_conversation_404():
    with client() as c:
        assert c.get("/v1/conversations/nope/export").status_code == 404


def test_export_filename_is_safe_for_titles_with_quotes_and_punctuation():
    # slugify() strips anything but [a-z0-9], so the Content-Disposition
    # header can never end up with a title-controlled quote/newline that
    # would break out of the filename="..." value.
    with client() as c:
        cid = c.post("/v1/conversations", json={"title": 'Say "hi" / bye'}).json()["id"]
        resp = c.get(f"/v1/conversations/{cid}/export")
        assert resp.status_code == 200
        assert resp.headers["content-disposition"] == 'attachment; filename="say-hi-bye.md"'
