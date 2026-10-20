"""선택적으로 OpenAI를 사용해 추천 설명을 다듬습니다."""

from openai import AsyncOpenAI

from app.config import settings


async def explain_recommendation(summary: str, reason: str) -> str:
    """키가 없거나 호출에 실패하면 규칙 기반 설명을 그대로 반환합니다."""
    if not settings.openai_api_key:
        return reason
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": "주어진 음식 영양 정보와 상황만 근거로 한국어 추천 이유를 한두 문장으로 작성하세요. 의료 조언은 하지 마세요.",
                },
                {"role": "user", "content": f"상황: {summary}\n규칙 설명: {reason}"},
            ],
            max_tokens=180,
        )
        content = response.choices[0].message.content
        return content.strip() if content else reason
    except Exception:
        return reason