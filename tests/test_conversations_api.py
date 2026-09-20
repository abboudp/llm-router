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
