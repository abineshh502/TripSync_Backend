from fastapi import APIRouter
from src.api.v1.assistant import router as assistant_router
from src.api.v1.recommendations import router as recommendations_router
from src.api.v1.maps import router as maps_router

api_router = APIRouter()
api_router.include_router(assistant_router, tags=["Chat Assistant"])
api_router.include_router(recommendations_router, tags=["Recommendations & Safety"])
api_router.include_router(maps_router, tags=["Maps & Routes"])
