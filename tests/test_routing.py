"""Smoke test guarding against accidentally dropping a route on refactor.

Reads the paths straight out of the generated OpenAPI schema rather than
walking `app.routes` directly: included sub-routers are represented lazily
there, so inspecting the schema is the stable, documented way to see the
final, effective route set.
"""
from app import main


def _registered_paths() -> set[str]:
    return set(main.app.openapi()["paths"].keys())


def test_generate_route_is_registered_and_legacy_chat_route_is_gone():
    paths = _registered_paths()
    assert "/v1/generate" in paths
    assert "/v1/chat" not in paths


def test_generate_route_documents_chat_turn_contract():
    op = main.app.openapi()["paths"]["/v1/generate"]["post"]
    request_ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    response_ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/ChatRequest")
    assert response_ref.endswith("/ChatTurnResponse")


def test_info_route_is_registered():
    assert "/v1/info" in _registered_paths()


def test_conversation_crud_and_sub_resource_routes_are_registered():
    paths = _registered_paths()
    assert "/v1/conversations" in paths
    assert "/v1/conversations/{conversation_id}" in paths
    assert "/v1/conversations/{conversation_id}/messages" in paths
    assert "/v1/conversations/{conversation_id}/export" in paths


def test_openapi_documents_the_search_and_pagination_query_params():
    """Guards against the query-param docs silently going stale on a refactor."""
    schema = main.app.openapi()

    list_params = {p["name"]: p for p in schema["paths"]["/v1/conversations"]["get"]["parameters"]}
    assert "case-insensitive" in list_params["q"]["description"].lower()

    message_params = {
        p["name"]: p
        for p in schema["paths"]["/v1/conversations/{conversation_id}/messages"]["get"]["parameters"]
    }
    assert "cap" in message_params["limit"]["description"].lower()
    assert "cursor" in message_params["before"]["description"].lower()
