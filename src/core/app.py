"""
TripSync Backend — Application Factory (src/core/app.py)
=========================================================
Secure application factory: CORS restricted to explicit origins,
startup validation enforced.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.api.router import api_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TripSync Enterprise Core API",
        description="Scalable, asynchronous AI travel engine supporting real-time group sync & route optimization.",
        version="1.0.0",
        # Disable docs in production (security hardening)
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
    )

    # ── CORS — explicit origins only, never wildcard ─────────────────────────
    # CWE-942: Permissive Cross-domain Policy — FIXED
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,   # explicit list from env
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    # ── Startup validation ────────────────────────────────────────────────────
    @app.on_event("startup")
    async def on_startup():
        settings.validate_for_startup()
        logger.info(
            "[STARTUP] TripSync Enterprise API started | env=%s | cors_origins=%s",
            settings.APP_ENV,
            settings.CORS_ORIGINS,
        )

    app.include_router(api_router, prefix="/api")

    @app.get("/")
    def read_root():
        return {
            "status": "Online",
            "service": "TripSync Core Backend",
            "engine": "FastAPI (Python)",
            "message": "Welcome to TripSync AI Core Backend API Services! 🚀"
        }

    return app

