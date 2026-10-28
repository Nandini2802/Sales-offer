from fastapi import APIRouter
from app.api.v1 import health, chat , sessions, apim_test

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(sessions.router)
api_router.include_router(apim_test.router)