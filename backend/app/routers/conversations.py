"""Create, list, load, and delete saved conversations."""

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.firebase import get_firestore
from app.models import ConversationCreate
from app.services.conversation_store import (
    get_conversation,
    list_conversations,
    save_conversation,
)

router = APIRouter(prefix="/api/conversations", tags=["대화 기록"])


def _database():
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다.",
        )
    return db


@router.post("", status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate):
    data = _database()
    messages = [message.model_dump(mode="json") for message in payload.messages]
    title = payload.title
    if title == "새 대화":
        first_message = next(
            (message["content"] for message in messages if message["role"] == "user"),
            None,
        )
        if first_message:
            title = first_message[:80]
    return save_conversation(data, payload.user_id, title, messages)


@router.get("")
def get_conversation_list(
    user_id: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
):
    return list_conversations(_database(), user_id)[:limit]


@router.get("/{conversation_id}")
def load_conversation(
    conversation_id: str,
    user_id: str = Query(min_length=1, max_length=128),
):
    return get_conversation(_database(), user_id, conversation_id)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_conversation(
    conversation_id: str,
    user_id: str = Query(min_length=1, max_length=128),
):
    db = _database()
    get_conversation(db, user_id, conversation_id)
    db.collection("conversations").document(conversation_id).delete()
