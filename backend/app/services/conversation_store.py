"""Firestore persistence helpers for chat conversations."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status


def _serialize(document) -> dict:
    return {"id": document.id, **(document.to_dict() or {})}


def list_conversations(db, user_id: str) -> list[dict]:
    documents = db.collection("conversations").where("user_id", "==", user_id).stream()
    conversations = [_serialize(document) for document in documents]
    conversations.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return [
        {key: value for key, value in conversation.items() if key != "messages"}
        for conversation in conversations
    ]


def get_conversation(db, user_id: str, conversation_id: str) -> dict:
    snapshot = db.collection("conversations").document(conversation_id).get()
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="대화를 찾을 수 없습니다.",
        )
    conversation = _serialize(snapshot)
    if conversation.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="대화를 찾을 수 없습니다.",
        )
    return conversation


def save_conversation(
    db,
    user_id: str,
    title: str,
    messages: list[dict],
    conversation_id: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    if conversation_id:
        existing = get_conversation(db, user_id, conversation_id)
        created_at = existing["created_at"]
        record_id = conversation_id
    else:
        created_at = now
        record_id = str(uuid4())

    data = {
        "user_id": user_id,
        "title": title[:160],
        "messages": messages,
        "created_at": created_at,
        "updated_at": now,
    }
    db.collection("conversations").document(record_id).set(data)
    return {"id": record_id, **data}
