"""환경 변수와 기본 설정을 한곳에서 관리합니다."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _credential_path() -> str | None:
    path = os.getenv("FIREBASE_KEY_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BACKEND_DIR / candidate
    # 기존 작업공간의 파일명 오타(.jso)를 그대로 둬도 실행되게 합니다.
    if not candidate.is_file() and candidate.name == "serviceAccountKey.json":
        typo_path = candidate.with_suffix(".jso")
        if typo_path.is_file():
            candidate = typo_path
    return str(candidate)


class Settings:
    """외부 서비스 설정. API 키는 코드에 직접 넣지 않습니다."""

    firebase_key_path = _credential_path()
    firebase_service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    require_firebase_auth = os.getenv("REQUIRE_FIREBASE_AUTH", "false").strip().lower() == "true"
    firebase_allowed_uid = os.getenv("FIREBASE_ALLOWED_UID")
    app_user_id = os.getenv("APP_USER_ID", "demo-user")
    food_api_key = os.getenv("FOOD_API_KEY") or os.getenv("FOOD_SAFETY_API_KEY")
    food_safety_api_url = os.getenv(
        "FOOD_SAFETY_API_URL",
        "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03",
    )
    kma_api_key = os.getenv("KMA_API_KEY")
    kma_daily_api_url = os.getenv(
        "KMA_DAILY_API_URL",
        "https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList",
    )
    weather_csv_url = os.getenv("WEATHER_CSV_URL", "").strip()
    weather_csv_path = os.getenv("WEATHER_CSV_PATH", "").strip()
    weather_csv_refresh_minutes = int(os.getenv("WEATHER_CSV_REFRESH_MINUTES", "60"))
    weather_csv_user_id = os.getenv("WEATHER_CSV_USER_ID", os.getenv("APP_USER_ID", "demo-user"))
    kma_apihub_key = os.getenv("KMA_APIHUB_KEY")
    kma_midta_region_id = os.getenv("KMA_MIDTA_REGION_ID", "11H20301")
    kma_midta_api_url = os.getenv(
        "KMA_MIDTA_API_URL",
        "https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa",
    )
    ai_provider = (
        os.getenv("AI_PROVIDER")
        or ("gemini" if os.getenv("GEMINI_API_KEY") else "openai")
    ).strip().lower()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # 예전 설정 이름도 지원해 기존 환경 파일과 호환합니다.
    google_application_credentials = firebase_key_path
    food_safety_api_key = food_api_key


settings = Settings()
