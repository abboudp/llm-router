from pydantic import BaseModel


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 64


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    max_tokens: int = 64
    model: str | None = None


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationRename(BaseModel):
    title: str
