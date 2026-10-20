"""개인화 다이어트 추천 MVP의 FastAPI 진입점."""

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.firebase import check_firestore_connection, get_firestore
from app.routers import (
    activity,
    analysis,
    auth,
    chat,
    conversations,
    data,
    diet,
    food_entries,
    food_nutrition,
    recommend,
    weather,
)
from app.security import enforce_app_user_scope, require_firebase_user

app = FastAPI(
    title="영양 기록 및 다이어트 추천 API",
    description="Firestore 식사 기록과 영양 분석, 개인화 추천 API",
    version="1.0.0",
    dependencies=[
        Depends(require_firebase_user),
        Depends(enforce_app_user_scope),
    ],
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(diet.router)
app.include_router(weather.router)
app.include_router(activity.router)
app.include_router(recommend.router)
app.include_router(food_entries.router)
app.include_router(food_nutrition.router)
app.include_router(analysis.router)
app.include_router(auth.router)
app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {"message": "영양 기록 및 다이어트 추천 API가 실행 중입니다."}


@app.get("/health")
def health_check():
    connected, error = check_firestore_connection()
    result = {
        "status": "ok" if connected else "degraded",
        "firestore_connected": connected,
    }
    if error:
        result["firestore_error"] = error
    return result