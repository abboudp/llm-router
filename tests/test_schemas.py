import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest, ConversationCreate, ConversationRename, GenerateRequest


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
    assert ConversationRename(title="t").title == "t"
    with pytest.raises(ValidationError):
        ConversationRename()
