"""Answer questions grounded in stored numeric-data summaries using the configured AI provider."""

import logging
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from openai import APIError, AsyncOpenAI

from app.config import settings
from app.firebase import get_firestore
from app.models import ChatRequest
from app.routers.data import calculate_data_summary
from app.routers.food_entries import build_food_chat_summary
from app.services.conversation_store import get_conversation, save_conversation

logger = logging.getLogger(__name__)
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
router = APIRouter(prefix="/api/chat", tags=["데이터 기반 AI 채팅"])


def _append_food_record_evidence(
    answer: str,
    question: str,
    food_summary: dict,
    today: date,
) -> str:
    food_question_terms = (
        "먹",
        "식사",
        "음식",
        "메뉴",
        "칼로리",
        "열량",
        "섭취",
        "밥",
        "food",
        "meal",
        "eat",
        "calorie",
    )
    if not any(term in question.casefold() for term in food_question_terms):
        return answer

    requested_date = None
    normalized_question = question.casefold()
    if "오늘" in question or "today" in normalized_question:
        requested_date = today.isoformat()
    elif "어제" in question or "yesterday" in normalized_question:
        requested_date = (today - timedelta(days=1)).isoformat()
    else:
        explicit_date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", question)
        if explicit_date:
            requested_date = explicit_date.group()

    details = food_summary.get("food_details", [])
    if requested_date:
        details = [item for item in details if item.get("date") == requested_date]
        daily_summary = next(
            (
                item
                for item in food_summary.get("daily_summaries", [])
                if item.get("date") == requested_date
            ),
            None,
        )
        meal_count = daily_summary["meal_count"] if daily_summary else 0
        food_count = daily_summary["food_count"] if daily_summary else 0
        calories = (
            daily_summary["nutrients"].get("calories_kcal", 0)
            if daily_summary
            else 0
        )
        period_label = requested_date
    else:
        meal_count = food_summary.get("meal_count", 0)
        food_count = food_summary.get("food_count", 0)
        calories = food_summary.get("nutrient_totals", {}).get("calories_kcal", 0)
        period_label = "최근 30일"

    lines = [
        f"\n\n저장된 식사 기록 ({period_label}: {meal_count}끼, "
        f"{food_count}개 음식, 기록 열량 합계 {calories:g} kcal):"
    ]
    if not details:
        lines.append("- 이 기간에 상세 음식 기록이 없습니다.")
    else:
        shown = details[:30]
        for item in shown:
            item_calories = item.get("nutrients", {}).get("calories_kcal")
            calorie_text = (
                f"{item_calories:g} kcal"
                if isinstance(item_calories, (int, float))
                else "열량 미기록"
            )
            meal_type = {
                "breakfast": "아침",
                "lunch": "점심",
                "dinner": "저녁",
                "snack": "간식",
            }.get(item.get("meal_type"), item.get("meal_type") or "식사")
            lines.append(
                f"- {item.get('date')} {meal_type}: "
                f"{item.get('food_name') or '이름 미상'} "
                f"{item.get('amount')} {item.get('unit') or ''} · {calorie_text}"
            )
        if len(details) > len(shown) or food_summary.get("food_details_truncated"):
            lines.append("- 음식별 상세 목록은 일부만 표시했습니다. 열량 합계는 기간 전체 기록 기준입니다.")
    return answer + "\n".join(lines)


@router.post("")
async def chat(request: ChatRequest):
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다.",
        )
    if settings.ai_provider == "gemini":
        api_key = settings.gemini_api_key or settings.openai_api_key
        model = settings.gemini_model
        base_url = GEMINI_OPENAI_BASE_URL
        key_setting = "GEMINI_API_KEY"
    elif settings.ai_provider == "openai":
        api_key = settings.openai_api_key
        model = settings.openai_model
        base_url = None
        key_setting = "OPENAI_API_KEY"
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI_PROVIDER는 'openai' 또는 'gemini'로 설정해야 합니다.",
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{key_setting}가 설정되지 않았습니다.",
        )

    if request.conversation_id:
        conversation = get_conversation(db, request.user_id, request.conversation_id)
        previous_messages = conversation.get("messages", [])
        title = conversation.get("title", "새 대화")
    else:
        conversation = None
        previous_messages = []
        title = request.message[:80]

    today = datetime.now(timezone.utc).date()
    period_start = today - timedelta(days=29)
    summary = calculate_data_summary(
        request.user_id, period_start, today
    ).model_dump(mode="json")
    food_summary = build_food_chat_summary(
        request.user_id, period_start, today
    )
    system_message = (
        "당신은 저장된 식사 기록과 일일 칼로리 데이터를 분석하는 한국어 도우미입니다. "
        "음식 섭취 관련 질문에는 음식별 식사 기록의 영양 정보를 우선 사용하세요. "
        "무엇을 먹었는지 또는 음식별 열량을 물으면 요청한 날짜에 해당하는 "
        "food_details의 모든 항목을 음식명·섭취량·열량과 함께 빠짐없이 각각 나열하세요. "
        "같은 음식이 여러 기록에 있어도 임의로 하나만 골라 대표하지 마세요. "
        "날짜별 합계는 daily_summaries, 기간 합계는 nutrient_totals를 사용하고 "
        "food_details가 잘린 경우 일부 상세 목록임을 알리세요. "
        "일일 칼로리 시계열은 별도의 데이터로 설명하세요. 두 자료는 같은 섭취를 "
        "기록했을 수 있으므로 서로 합산해 총섭취량이라고 말하지 마세요. "
        "아래 요약에 근거해 간결하게 답하고, 확인할 수 없는 원인은 추측하지 마세요. "
        "자료가 없거나 부족하면 그 자료의 기록 건수를 구분해 알려 주세요. "
        "수치는 단위와 기간을 명시하고 의료 진단은 하지 마세요. "
        "음식별 상세 목록이 잘렸다면 전체 목록인 것처럼 답하지 마세요.\n\n"
        f"분석 대상 기간(최근 30일 UTC): {period_start}~{today}\n"
        f"일일 칼로리 데이터 요약: {summary}\n"
        f"식사 기록 영양 요약 및 음식별 기록: {food_summary}"
    )
    messages = [
        {"role": "system", "content": system_message},
        *[
            {"role": item["role"], "content": item["content"]}
            for item in previous_messages[-20:]
            if item.get("role") in ("user", "assistant")
        ],
        {"role": "user", "content": request.message},
    ]

    try:
        client = (
            AsyncOpenAI(api_key=api_key, base_url=base_url)
            if base_url
            else AsyncOpenAI(api_key=api_key)
        )
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=600,
        )
    except APIError as error:
        logger.error(
            "%s chat request failed with HTTP status %s",
            settings.ai_provider,
            error.status_code,
        )
        if error.status_code == 401:
            detail = (
                f"{settings.ai_provider.capitalize()} API 키가 거부되었습니다. "
                f"{key_setting}와 제공자 설정을 확인하세요."
            )
        elif error.status_code == 404:
            detail = (
                f"{settings.ai_provider.capitalize()} 모델을 사용할 수 없습니다. "
                "모델 설정을 확인하세요."
            )
        elif error.status_code == 503:
            detail = (
                f"{settings.ai_provider.capitalize()} 서비스가 일시적으로 혼잡합니다. "
                "잠시 후 다시 시도해 주세요."
            )
        else:
            detail = (
                f"{settings.ai_provider.capitalize()} 요청이 실패했습니다. "
                "모델 및 서비스 설정을 확인한 뒤 다시 시도하세요."
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from error

    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{settings.ai_provider.capitalize()}가 답변을 반환하지 않았습니다.",
        )
    answer = _append_food_record_evidence(
        answer.strip(),
        request.message,
        food_summary,
        today,
    )
    now = datetime.now(timezone.utc).isoformat()
    transcript = [
        *previous_messages,
        {"role": "user", "content": request.message, "created_at": now},
        {"role": "assistant", "content": answer, "created_at": now},
    ]
    saved = save_conversation(
        db,
        request.user_id,
        title,
        transcript,
        conversation["id"] if conversation else None,
    )
    return {
        "conversation_id": saved["id"],
        "message": answer,
        "summary": summary,
        "food_summary": food_summary,
    }
