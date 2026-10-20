"""Firestore 연결을 초기화합니다. 자격 증명이 없어도 앱은 실행됩니다."""

from pathlib import Path
import logging
import json

import firebase_admin
from firebase_admin import credentials, firestore

from app.config import settings

db = None
logger = logging.getLogger(__name__)
initialization_error = None

credential_path = settings.google_application_credentials
try:
    if not firebase_admin._apps:
        if settings.firebase_service_account_json:
            service_account = json.loads(settings.firebase_service_account_json)
            firebase_admin.initialize_app(credentials.Certificate(service_account))
        elif credential_path and Path(credential_path).is_file():
            if Path(credential_path).stat().st_size == 0:
                raise ValueError(
                    "Firebase 서비스 계정 파일이 비어 있습니다. Firebase 콘솔에서 "
                    "새 비공개 키를 발급하고 JSON 파일을 다시 저장하세요."
                )
            firebase_admin.initialize_app(credentials.Certificate(credential_path))
        else:
            raise FileNotFoundError(
                "Firebase 서비스 계정 JSON 파일이 없습니다. FIREBASE_KEY_PATH 또는 "
                "FIREBASE_SERVICE_ACCOUNT_JSON을 설정하세요."
            )
    db = firestore.client()
except (ValueError, OSError, json.JSONDecodeError) as error:
    initialization_error = str(error)
    logger.error("Firestore 초기화 실패: %s", initialization_error)
except Exception as error:
    initialization_error = f"Firebase 초기화 실패 ({type(error).__name__})."
    logger.exception("Firestore 초기화 중 예기치 않은 오류가 발생했습니다.")


def get_firestore():
    """Firestore 미설정 상태를 라우터에서 확인할 수 있게 반환합니다."""
    return db


def check_firestore_connection() -> tuple[bool, str | None]:
    """Firestore에 실제 읽기 요청을 보내 서버 인증과 접근을 확인합니다."""
    if db is None:
        return False, initialization_error or "Firestore 클라이언트가 초기화되지 않았습니다."
    try:
        db.collection("_health_checks").limit(1).get(timeout=5)
    except Exception as error:
        logger.exception("Firestore 연결 점검 실패")
        return False, f"Firestore 요청 실패 ({type(error).__name__})."
    return True, None


def get_user_collection(user_id: str, collection_name: str):
    """사용자별 하위 컬렉션(users/{id}/{collection})을 반환합니다."""
    if db is None:
        return None
    return db.collection("users").document(user_id).collection(collection_name)