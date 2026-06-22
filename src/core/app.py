from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.api.router import api_router

def create_app() -> FastAPI:
    app = FastAPI(
        title="TripSync Enterprise Core API",
        description="Scalable, asynchronous AI travel engine supporting real-time group sync & route optimization.",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
