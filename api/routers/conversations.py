"""List/rename/delete conversations, and fetch one conversation's full thread.
Starting a NEW conversation happens through POST /api/chat instead (see
api/routers/chat.py) — a conversation is created lazily on its first message,
not through this router."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import get_current_user
from api.schemas import ChatMessageOut, ConversationOut, ConversationRenameRequest
from store import get_store

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(user: dict = Depends(get_current_user)):
    user_store = get_store(user["user_id"])
    return [ConversationOut(**c) for c in user_store.list_conversations()]


@router.get("/{conversation_id}/messages", response_model=list[ChatMessageOut])
def get_messages(conversation_id: str, user: dict = Depends(get_current_user)):
    user_store = get_store(user["user_id"])
    messages = user_store.conversation_messages(conversation_id)
    if messages is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no conversation with that id")
    return [ChatMessageOut(**m) for m in messages]


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(conversation_id: str, body: ConversationRenameRequest,
                         user: dict = Depends(get_current_user)):
    user_store = get_store(user["user_id"])
    renamed = user_store.rename_conversation(conversation_id, body.title)
    if renamed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no conversation with that id")
    return ConversationOut(**renamed)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    user_store = get_store(user["user_id"])
    if not user_store.delete_conversation(conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no conversation with that id")
