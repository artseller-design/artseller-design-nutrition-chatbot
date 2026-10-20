"""Firebase Authentication checks for protected API routes."""

from fastapi import HTTPException, Request, status
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError

from app.config import settings


async def require_firebase_user(request: Request) -> dict | None:
    if request.url.path in {"/", "/health", "/docs", "/openapi.json", "/redoc"}:
        return None
    if not settings.require_firebase_auth:
        return None
    if not settings.firebase_allowed_uid:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="서버에 Firebase 허용 UID가 설정되지 않았습니다.",
        )

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = auth.verify_id_token(token, check_revoked=True)
    except (FirebaseError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인 세션이 만료되었거나 유효하지 않습니다. 다시 로그인해 주세요.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    if claims.get("uid") != settings.firebase_allowed_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 계정은 이 앱에 접근할 수 없습니다.",
        )
    return claims


async def enforce_app_user_scope(
    request: Request,
) -> None:
    if not settings.require_firebase_auth:
        return

    requested_user_ids = []
    path_user_id = request.path_params.get("user_id")
    if path_user_id:
        requested_user_ids.append(path_user_id)
    query_user_id = request.query_params.get("user_id")
    if query_user_id:
        requested_user_ids.append(query_user_id)

    if request.method in {"POST", "PUT", "PATCH"}:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
            except ValueError:
                body = None
            if isinstance(body, dict) and isinstance(body.get("user_id"), str):
                requested_user_ids.append(body["user_id"])

    if any(user_id != settings.app_user_id for user_id in requested_user_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="요청한 사용자 데이터에 접근할 수 없습니다.",
        )
