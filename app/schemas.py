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


# -- response models ---------------------------------------------------------
# These describe the shape of what the store already returns; wiring them in
# as `response_model=` gets us request-time validation plus accurate OpenAPI
# docs for the conversation/chat/info surface without changing any payloads.


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    latency_ms: int | None = None
    created_at: float


class ChatTurnResponse(BaseModel):
    message: MessageOut
    latency_ms: int
    model: str | None = None
    # `usage` is passed through opaquely: it comes straight from the upstream
    # backend, whose exact field set this service doesn't own, so it isn't
    # worth (or safe) pinning to a strict shape here.
    usage: dict | None = None


class InfoResponse(BaseModel):
    name: str
    version: str
    models: list[str]
    uptime_s: float
