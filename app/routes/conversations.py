from fastapi import APIRouter, HTTPException, Request, Response

from ..schemas import ConversationCreate, ConversationRename

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(request: Request):
    return request.app.state.store.list_conversations()


@router.post("", status_code=201)
async def create_conversation(body: ConversationCreate, request: Request):
    title = body.title or "New conversation"
    return request.app.state.store.create_conversation(title=title)


@router.patch("/{conversation_id}")
async def rename_conversation(conversation_id: str, body: ConversationRename, request: Request):
    conversation = request.app.state.store.rename_conversation(conversation_id, body.title)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, request: Request):
    if not request.app.state.store.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    return Response(status_code=204)


@router.get("/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request):
    store = request.app.state.store
    if store.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return store.list_messages(conversation_id)
