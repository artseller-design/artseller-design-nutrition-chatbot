"""Authenticated session information for the frontend."""

from fastapi import APIRouter, Depends

from app.config import settings
from app.security import require_firebase_user

router = APIRouter(prefix="/api/auth", tags=["인증"])


@router.get("/session")
def get_session(user: dict | None = Depends(require_firebase_user)):
    return {
        "uid": user.get("uid") if user else None,
        "user_id": settings.app_user_id,
    }
