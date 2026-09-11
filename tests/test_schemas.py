import pytest
from pydantic import ValidationError

from app.schemas import (
    ChatRequest,
    ChatTurnResponse,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    GenerateRequest,
    InfoResponse,
    MessageOut,
)


def test_generate_request_defaults():
    req = GenerateRequest(prompt="hi")
    assert req.max_tokens == 64


def test_chat_request_defaults_and_required():
    req = ChatRequest(conversation_id="c1", message="hello")
    assert req.max_tokens == 64
    assert req.model is None
    with pytest.raises(ValidationError):
        ChatRequest(message="no conversation id")


def test_conversation_schemas():
    assert ConversationCreate().title is None
    assert ConversationUpdate(title="t").title == "t"


def test_conversation_update_requires_at_least_one_field():
    with pytest.raises(ValidationError):
        ConversationUpdate()


def test_conversation_update_accepts_pinned_alone():
    update = ConversationUpdate(pinned=True)
    assert update.title is None
    assert update.pinned is True


def test_conversation_update_accepts_title_and_pinned_together():
    update = ConversationUpdate(title="t", pinned=False)
    assert update.title == "t"
    assert update.pinned is False


def test_conversation_out_requires_all_fields():
    out = ConversationOut(id="c1", title="T", created_at=1.0, updated_at=2.0, pinned=False)
    assert out.model_dump() == {
        "id": "c1", "title": "T", "created_at": 1.0, "updated_at": 2.0, "pinned": False,
    }
    with pytest.raises(ValidationError):
        ConversationOut(id="c1", title="T", created_at=1.0)


def test_message_out_allows_null_latency():
    out = MessageOut(id="m1", conversation_id="c1", role="user", content="hi", created_at=1.0)
    assert out.latency_ms is None


def test_chat_turn_response_usage_is_passthrough_dict():
    resp = ChatTurnResponse(
        message=MessageOut(
            id="m1", conversation_id="c1", role="assistant", content="hi",
            latency_ms=10, created_at=1.0,
        ),
        latency_ms=10,
        model="mock-large",
        usage={"prompt_tokens": 3, "completion_tokens": 4, "some_future_field": True},
    )
    assert resp.usage == {"prompt_tokens": 3, "completion_tokens": 4, "some_future_field": True}


def test_info_response_shape():
    info = InfoResponse(name="llm-router", version="0.1.0", models=["default"], uptime_s=1.5)
    assert info.models == ["default"]
    with pytest.raises(ValidationError):
        InfoResponse(name="llm-router", version="0.1.0", uptime_s=1.5)
