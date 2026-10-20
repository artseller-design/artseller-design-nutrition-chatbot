"""공공데이터포털 식품의약품안전처 식품영양성분DB정보 Open API."""

import math
import logging
import time
from collections import OrderedDict
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_CACHE_MAX_ENTRIES = 256
_FALLBACK_PAGE_SIZE = 50
_PRIMARY_TIMEOUT_SECONDS = 7
_FALLBACK_TIMEOUT_SECONDS = 8
_search_cache: OrderedDict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = (
    OrderedDict()
)


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """공공데이터 응답의 중첩 구조에서 음식 목록을 꺼냅니다."""
    response = payload.get("response", payload)
    header = response.get("header", {}) if isinstance(response, dict) else {}
    result_code = str(header.get("resultCode", "00"))
    if result_code not in ("00", "0"):
        message = header.get("resultMsg") or "알 수 없는 API 오류"
        raise RuntimeError(f"공공데이터 식품 영양정보 API 오류 ({result_code}): {message}")
    body = response.get("body", {}) if isinstance(response, dict) else {}
    items = body.get("items", {}) if isinstance(body, dict) else {}
    rows = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _total_count(payload: dict[str, Any]) -> int:
    response = payload.get("response", payload)
    body = response.get("body", {}) if isinstance(response, dict) else {}
    try:
        return max(0, int(body.get("totalCount", 0)))
    except (TypeError, ValueError):
        return 0


def _normalized_name(value: Any) -> str:
    return "".join(
        character
        for character in str(value or "").casefold()
        if character.isalnum()
    )


async def search_foods(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """공공데이터포털의 음식 영양성분 표준데이터를 이름으로 검색합니다."""
    if not settings.food_api_key:
        raise RuntimeError(
            "FOOD_API_KEY가 설정되지 않았습니다. 공공데이터포털에서 "
            "식품의약품안전처_식품영양성분DB정보 API 활용 신청 후 발급한 키를 설정하세요."
        )

    normalized_query = "".join(character for character in query.strip() if not character.isspace())
    normalized_query = normalized_query.replace("시레기", "시래기")
    cache_key = (normalized_query.casefold(), limit)
    now = time.monotonic()
    cached = _search_cache.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        _search_cache.move_to_end(cache_key)
        return [dict(item) for item in cached[1]]
    if cached:
        del _search_cache[cache_key]

    params = {
        "serviceKey": settings.food_api_key,
        "type": "json",
        "FOOD_NM_KR": normalized_query,
        "numOfRows": limit,
    }
    timeout = httpx.Timeout(_PRIMARY_TIMEOUT_SECONDS, connect=3)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            settings.food_safety_api_url,
            params={**params, "pageNo": 1},
        )
        response.raise_for_status()
        payload = response.json()
        items = _extract_items(payload)[:limit]
        exact_name = _normalized_name(normalized_query)
        has_exact_match = any(
            _normalized_name(
                item.get("FOOD_NM_KR", item.get("food_name"))
            )
            == exact_name
            for item in items
        )
        total_count = _total_count(payload)
        fallback_page = (
            math.ceil(total_count / _FALLBACK_PAGE_SIZE) if total_count else 0
        )
        if not has_exact_match and fallback_page > 1:
            try:
                last_response = await client.get(
                    settings.food_safety_api_url,
                    params={
                        **params,
                        "pageNo": fallback_page,
                        "numOfRows": _FALLBACK_PAGE_SIZE,
                    },
                    timeout=httpx.Timeout(_FALLBACK_TIMEOUT_SECONDS, connect=3),
                )
                last_response.raise_for_status()
                last_items = _extract_items(last_response.json())
                seen = {
                    (
                        item.get("FOOD_CD") or item.get("food_code"),
                        item.get("FOOD_NM_KR") or item.get("food_name"),
                        item.get("SERVING_SIZE"),
                        item.get("AMT_NUM1"),
                    )
                    for item in items
                }
                for item in last_items:
                    signature = (
                        item.get("FOOD_CD") or item.get("food_code"),
                        item.get("FOOD_NM_KR") or item.get("food_name"),
                        item.get("SERVING_SIZE"),
                        item.get("AMT_NUM1"),
                    )
                    if signature not in seen:
                        items.append(item)
                        seen.add(signature)
            except (httpx.RequestError, httpx.HTTPStatusError) as error:
                logger.warning(
                    "Food-search fallback page %s failed; returning first-page results: %s",
                    fallback_page,
                    error,
                )
    _search_cache[cache_key] = (time.monotonic(), items)
    _search_cache.move_to_end(cache_key)
    while len(_search_cache) > _CACHE_MAX_ENTRIES:
        _search_cache.popitem(last=False)
    return [dict(item) for item in items]