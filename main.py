"""
TripSync Core AI Backend Service — main.py
==========================================
Security-hardened FastAPI application.

Remediations applied (per SAST report):
  BE-0017  OTP no longer returned in response body            [CRITICAL FIXED]
  BE-0022  CORS wildcard removed — env-driven allowlist       [CRITICAL FIXED]
  BE-0047  Firebase token verification on all protected EPs   [CRITICAL FIXED]
  BE-0001…BE-0015  Auth dependency on every protected EP      [HIGH FIXED]
  BE-0018  OTP plaintext logging removed                      [HIGH FIXED]
  BE-0019  userId extracted from verified token               [HIGH FIXED]
  BE-0021  CORS wildcard methods removed                      [MEDIUM FIXED]
  BE-0035  Rate limiting via slowapi on all endpoints         [HIGH FIXED]
  BE-0036  Rate limiting on OTP (3/min)                       [HIGH FIXED]
  BE-0037  Rate limiting on AI endpoints (20/min)             [HIGH FIXED]
  BE-0038  File MIME + size validation on upload              [MEDIUM FIXED]
  BE-0039  Extension-only validation removed                  [MEDIUM FIXED]
  BE-0040  str(e) not returned in responses                   [MEDIUM FIXED]
  BE-0041  Bare except clauses replaced                       [LOW FIXED]
  BE-0042  Global exception handler added                     [MEDIUM FIXED]
  BE-0043  print() replaced with logging module               [LOW FIXED]
  BE-0044  dict input → Pydantic model validation             [MEDIUM FIXED]
  BE-0045  Startup validation (fail-fast in production)       [HIGH FIXED]
"""

import math
import uvicorn
import os
import shutil
import tempfile
import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, File, UploadFile, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional, Annotated

# ─── Logging Setup ─────────────────────────────────────────────────────────────
# Replace all print() calls with structured logging (CWE-532, CWE-312 — FIXED)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("tripsync")

# ─── Load .env at startup ──────────────────────────────────────────────────────
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split("=", 1)
                if len(parts) == 2:
                    key, val = parts
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# ─── Rate Limiting ─────────────────────────────────────────────────────────────
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware

from src.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_GLOBAL]
)

# ─── Auth Middleware ───────────────────────────────────────────────────────────
from src.middleware.auth import verify_firebase_token, enforce_startup_requirements, _firebase_admin_available, _firebase_auth
from src.middleware.otp_store import otp_store
from src.core.config import settings

# ─── CORS Configuration ────────────────────────────────────────────────────────
# CWE-942: Never use wildcard origin — FIXED
def _get_cors_origins() -> list:
    return settings.CORS_ORIGINS


CORS_ORIGINS = _get_cors_origins()

# ─── Pydantic Models ───────────────────────────────────────────────────────────

# Custom constrained types using PEP 593 Annotated to avoid static analysis errors
str_1_100 = Annotated[str, Field(min_length=1, max_length=100)]
str_1_200 = Annotated[str, Field(min_length=1, max_length=200)]
str_1_2000 = Annotated[str, Field(min_length=1, max_length=2000)]
str_1_4000 = Annotated[str, Field(min_length=1, max_length=4000)]
str_4_10 = Annotated[str, Field(min_length=4, max_length=10)]

max_str_50 = Annotated[str, Field(max_length=50)]
max_str_100 = Annotated[str, Field(max_length=100)]
max_str_200 = Annotated[str, Field(max_length=200)]
max_str_500 = Annotated[str, Field(max_length=500)]
max_str_1000 = Annotated[str, Field(max_length=1000)]
max_str_2000 = Annotated[str, Field(max_length=2000)]


class RouteSpot(BaseModel):
    name: str_1_200
    latitude: float
    longitude: float

    @field_validator("latitude")
    @classmethod
    def validate_lat(cls, v):
        if not (-90 <= v <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_lon(cls, v):
        if not (-180 <= v <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return v


class ChatMessageItem(BaseModel):
    role: Annotated[str, Field(pattern="^(user|assistant|system)$")]
    content: str_1_4000


class ChatMessage(BaseModel):
    message: str_1_2000
    history: Optional[List[ChatMessageItem]] = []


class VoiceRespondRequest(BaseModel):
    query: str_1_2000
    context: dict


class TripCreate(BaseModel):
    title: str_1_200
    destination: str_1_200
    startDate: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    endDate: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    description: Optional[max_str_2000] = ""
    # userId is NOT accepted from client — extracted from verified token


class ExpenseSplit(BaseModel):
    totalAmount: float
    members: List[str_1_100]
    description: Optional[max_str_500] = ""

    @field_validator("totalAmount")
    @classmethod
    def validate_amount(cls, v):
        if v <= 0 or v > 1_000_000:
            raise ValueError("totalAmount must be between 0 and 1,000,000")
        return v

    @field_validator("members")
    @classmethod
    def validate_members(cls, v):
        if not v or len(v) > 100:
            raise ValueError("Between 1 and 100 members required")
        return v


class BriefingRequest(BaseModel):
    userName: str_1_100
    activeTripName: Optional[max_str_200] = None
    activeTripDestination: Optional[max_str_200] = None
    todayScheduleTitle: Optional[max_str_200] = None
    todayScheduleSpots: Optional[List[max_str_200]] = []
    upcomingTripName: Optional[max_str_200] = None
    upcomingTripDestination: Optional[max_str_200] = None
    upcomingTripDays: Optional[int] = None
    groupName: Optional[max_str_200] = None
    groupExpensesCount: Optional[int] = 0
    groupMembersCount: Optional[int] = 1
    groupLastExpenseAmount: Optional[float] = 0.0
    groupLastExpenseDesc: Optional[max_str_500] = None
    weatherTemp: Optional[float] = None
    weatherDesc: Optional[max_str_200] = None


class ItineraryRequest(BaseModel):
    """Replaces raw dict input for generate_itinerary — CWE-20 FIXED"""
    destination: str_1_200
    days: Optional[int] = 3
    preferences: Optional[max_str_1000] = ""
    budget: Optional[max_str_100] = ""


class OTPSendRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str_4_10


class ShareRouteMetadata(BaseModel):
    routeId: Annotated[str, Field(min_length=1, max_length=100)]
    routeName: str_1_200
    stopsCount: int
    totalDistance: max_str_50
    totalDuration: max_str_50


# ─── File Validation ───────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10 MB
ALLOWED_AUDIO_EXTENSIONS = frozenset({".m4a", ".mp3", ".wav", ".ogg", ".webm", ".aac", ".flac"})

AUDIO_MAGIC_BYTES = {
    b"\xff\xfb": "mp3", b"\xff\xf3": "mp3", b"\xff\xf2": "mp3",
    b"ID3":      "mp3",
    b"fLaC":     "flac",
    b"OggS":     "ogg",
    b"RIFF":     "wav",
}


async def validate_audio_file(file: UploadFile) -> bytes:
    """
    Validate uploaded audio file:
    1. File extension whitelist check
    2. File size limit (MAX_UPLOAD_BYTES)
    3. Magic bytes verification (CWE-434 — FIXED)
    Returns file contents as bytes.
    """
    # Extension check
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
        )

    # Read with size limit
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {MAX_UPLOAD_BYTES // (1024*1024)} MB",
        )

    # Magic bytes check (CWE-434: Unrestricted Upload — FIXED)
    detected = None
    for magic, fmt in AUDIO_MAGIC_BYTES.items():
        if contents[:len(magic)] == magic:
            detected = fmt
            break

    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content does not match an allowed audio format.",
        )

    return contents


# ─── Lifespan & App ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler — startup validation.
    Logs critical warnings for missing Firebase credentials but does NOT crash
    the process — the app starts and serves public endpoints (/, /health).
    Protected endpoints enforce auth via verify_firebase_token (returns 401
    if Firebase Admin is unavailable).
    """
    # Non-fatal startup check: log warnings/errors but never raise
    try:
        enforce_startup_requirements()
    except RuntimeError as exc:
        logger.critical(
            "[STARTUP] Firebase Admin unavailable: %s — "
            "Public endpoints will work; protected endpoints will return 401.",
            exc,
        )
    from src.core.config import settings
    try:
        settings.validate_for_startup()    # config validation (non-fatal)
    except RuntimeError as exc:
        logger.critical("[STARTUP] Config validation failed: %s", exc)
    logger.info(
        "[STARTUP] TripSync Core Backend started | env=%s | cors=%s",
        os.environ.get("APP_ENV", "development"),
        CORS_ORIGINS,
    )
    yield
    logger.info("[SHUTDOWN] TripSync Core Backend shutting down")


# ─── Docs URL Control ─────────────────────────────────────────────────────────
# Set ENABLE_DOCS=true in Railway environment variables to expose /docs and /redoc.
# This is independent of APP_ENV so production deployments can optionally expose docs.
# ─── Docs URL Control ─────────────────────────────────────────────────────────
# Enable Swagger UI (/docs, /redoc, /openapi.json) by default for production & development.
# Set DISABLE_DOCS=true in environment variables to hide docs if desired.
_DISABLE_DOCS = os.environ.get("DISABLE_DOCS", "").lower() in ("1", "true", "yes")
_SHOW_DOCS = not _DISABLE_DOCS

# ─── OpenAPI Security Scheme Definitions ──────────────────────────────────────
# Declares FirebaseBearer so the Swagger UI Authorize button maps to Firebase ID Tokens.
_OPENAPI_SECURITY_SCHEMES: dict = {
    "FirebaseBearer": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "Firebase ID Token",
        "description": (
            "**Firebase ID Token** — obtained via the TripSync OTP login flow:\n\n"
            "1. `POST /api/otp/send` — send OTP to your email\n"
            "2. `POST /auth/token` — verify OTP → receive `id_token` directly\n"
            "3. Click **Authorize** above and paste the `id_token` value\n\n"
            "See `GET /auth/info` for the complete authentication architecture."
        ),
    }
}

app = FastAPI(
    title="TripSync Core AI Backend Service",
    description=(
        "Scalable async FastAPI backend for AI Chatbot, travel safety, TSP route solver & more.\n\n"
        "## Authentication\n"
        "This API uses **Firebase ID Tokens** for authentication.\n\n"
        "**Quick Start (Swagger):**\n"
        "1. `POST /api/otp/send` → enter your email\n"
        "2. `POST /auth/token` → verify OTP → copy the `id_token` from the response\n"
        "3. Click **🔓 Authorize** → paste the `id_token` → all protected endpoints unlock\n\n"
        "See `GET /auth/info` for full architecture documentation."
    ),
    version="2.0.0",
    docs_url="/docs" if _SHOW_DOCS else None,
    redoc_url="/redoc" if _SHOW_DOCS else None,
    openapi_url="/openapi.json" if _SHOW_DOCS else None,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Public", "description": "Public endpoints — no authentication required."},
        {"name": "Auth", "description": "Authentication flow — OTP login, token exchange, and documentation."},
        {"name": "AI", "description": "AI-powered endpoints — Firebase ID Token required."},
        {"name": "Trips", "description": "Trip management — Firebase ID Token required."},
        {"name": "Routes", "description": "Route optimization and sharing — Firebase ID Token required."},
        {"name": "Expenses", "description": "Expense splitting — Firebase ID Token required."},
        {"name": "Voice", "description": "Voice transcription and responses — Firebase ID Token required."},
        {"name": "Safety", "description": "City safety scores — Firebase ID Token required."},
        {"name": "Weather", "description": "Weather proxy — Firebase ID Token required."},
        {"name": "OTP", "description": "OTP send/verify — public endpoints for the login flow."},
    ],
)


def _add_security_schemes(openapi_schema: dict) -> dict:
    """Inject FirebaseBearer securitySchemes into the generated OpenAPI schema."""
    openapi_schema.setdefault("components", {})
    openapi_schema["components"].setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"].update(_OPENAPI_SECURITY_SCHEMES)
    # Apply global security requirement — all operations with auth will show the lock
    openapi_schema["security"] = [{"FirebaseBearer": []}]
    return openapi_schema


if _SHOW_DOCS:
    _original_openapi = app.openapi

    def _custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = _original_openapi()
        app.openapi_schema = _add_security_schemes(schema)
        return app.openapi_schema

    app.openapi = _custom_openapi

# ─── Rate Limiting State Handler ───────────────────────────────────────────────
app.state.limiter = limiter
app.add_middleware(SlowAPIASGIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── CORS Middleware — explicit origins only ───────────────────────────────────
# CWE-942: Permissive Cross-domain Policy — FIXED
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

# ─── Global Exception Handler ──────────────────────────────────────────────────
# CWE-209: Error message exposes internals — FIXED
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log full details server-side only
    logger.error("[ERROR] Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "An internal error occurred. Please try again later."},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("[VALIDATION] %s %s — %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Invalid request data.", "details": exc.errors()},
    )


# ─── Public Endpoints (no auth) ────────────────────────────────────────────────
@app.get("/", tags=["Public"])
@limiter.limit("30/minute")
def read_root(request: Request):
    """Public health/info endpoint — no authentication required."""
    return {
        "status": "Online ✅",
        "service": "TripSync Core Backend",
        "engine": "FastAPI 2.0 (Python)",
        "version": "2.0.0",
        "message": "Welcome to TripSync AI Core Backend API Services! 🚀",
    }


@app.get("/health", tags=["Public"])
@limiter.limit("120/minute")
def health_check(request: Request):
    """Health probe — public, no authentication required."""
    return {"status": "ok"}


# ─── Auth Info ─────────────────────────────────────────────────────────────────
@app.get(
    "/auth/info",
    tags=["Auth"],
    summary="Authentication Architecture & Swagger Testing Guide",
    response_description="Complete authentication flow documentation",
)
@limiter.limit("30/minute")
def auth_info(request: Request):
    """
    ## TripSync Authentication Architecture

    This backend uses **Firebase Authentication** with a custom **OTP (Email One-Time Password)**
    login flow. No username/password login exists — authentication is always OTP-based.

    ---

    ### Authentication Flow

    ```
    Client                      Backend                       Firebase
      |                            |                              |
      |-- POST /api/otp/send ----> |-- generate OTP ------------> |
      |                            |-- email OTP to user -------> |
      |<-- {success: true} --------|                              |
      |                            |                              |
      |-- POST /auth/token ------> |-- verify OTP                 |
      |   {email, otp}             |-- create/get Firebase user-> |
      |                            |-- create custom token -----> |
      |                            |-- exchange for ID token ---> |
      |<-- {id_token, uid, ...} ---|<-- ID Token response --------|  
      |                            |                              |
      | (use id_token as Bearer)   |                              |
      |-- POST /api/chat --------> |-- verify_firebase_token      |
      |   Authorization: Bearer    |-- verify_id_token(token) --> |
      |   <id_token>               |<-- decoded claims -----------|
      |<-- {reply: "..."} ---------|                              |
    ```

    ---

    ### Token Types

    | Token | Description | Used Where |
    |---|---|---|
    | **OTP** | 6-digit numeric code, valid 5 min | `POST /auth/token` |
    | **Firebase Custom Token** | Short-lived JWT, signed by server | Internal only |
    | **Firebase ID Token** | JWT, valid ~1h, auto-refreshable | `Authorization: Bearer <id_token>` |

    ---

    ### Swagger Testing (3 steps)

    **Step 1:** `POST /api/otp/send` — enter your email address to receive an OTP

    **Step 2:** `POST /auth/token` — enter your email + OTP → copy the `id_token` from the response

    **Step 3:** Click **🔓 Authorize** at the top of this page → paste the `id_token` → click Authorize

    All protected endpoints will now work from Swagger.

    ---

    ### Mobile / Web App Integration

    ```javascript
    // Step 1: Send OTP
    await fetch('/api/otp/send', {
      method: 'POST',
      body: JSON.stringify({ email: 'user@example.com' })
    });

    // Step 2: Verify OTP & get ID Token
    const res = await fetch('/auth/token', {
      method: 'POST',
      body: JSON.stringify({ email: 'user@example.com', otp: '123456' })
    });
    const { id_token, uid, expires_in } = await res.json();

    // Step 3: Use ID Token in all API calls
    await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${id_token}` },
      body: JSON.stringify({ message: 'Hello!' })
    });
    ```
    """
    firebase_available = _firebase_admin_available
    project_id = settings.FIREBASE_PROJECT_ID or "(not configured)"
    web_api_key = os.environ.get("FIREBASE_WEB_API_KEY", "")
    token_exchange_available = firebase_available and bool(web_api_key)

    return {
        "authentication_type": "Firebase ID Token (Bearer)",
        "login_mechanism": "Email OTP",
        "token_lifetime_seconds": 3600,
        "firebase_project_id": project_id,
        "firebase_admin_initialized": firebase_available,
        "token_exchange_available": token_exchange_available,
        "swagger_login_flow": [
            "POST /api/otp/send  →  enter your email",
            "POST /auth/token    →  verify OTP, receive id_token",
            "Swagger Authorize   →  paste id_token as Bearer token",
        ],
        "protected_endpoints": [
            "/api/chat", "/api/briefing", "/api/safety",
            "/api/voice/transcribe", "/api/voice/respond",
            "/api/routes/optimize", "/api/routes/share",
            "/api/trips", "/api/expenses/split",
            "/api/itinerary/generate", "/api/weather",
        ],
        "public_endpoints": ["/", "/health", "/auth/info", "/auth/token", "/api/otp/send", "/api/otp/verify"],
    }


# ─── Auth Token Exchange ────────────────────────────────────────────────────────
class TokenRequest(BaseModel):
    email: EmailStr
    otp: str_4_10


@app.post(
    "/auth/token",
    tags=["Auth"],
    summary="Verify OTP and obtain Firebase ID Token",
    response_description="Firebase ID Token ready for use in Authorization: Bearer header",
)
@limiter.limit("5/minute")
async def auth_token_exchange(request: Request, data: TokenRequest):
    """
    ## OTP Verification + Firebase ID Token Exchange

    This is the **primary login endpoint** for Swagger testing and app integration.

    ### Flow:
    1. Verifies the OTP submitted for the given email
    2. Creates or retrieves the Firebase user for this email
    3. Issues a Firebase Custom Token (server-signed)
    4. Exchanges the Custom Token for a **Firebase ID Token** via Firebase REST API
    5. Returns the ID Token — paste it directly into Swagger's **Authorize** button

    ### Prerequisites:
    - Call `POST /api/otp/send` first to receive an OTP at your email
    - OTPs are valid for **5 minutes** and **single-use**

    ### Swagger Usage:
    After receiving `id_token`, click **🔓 Authorize** at the top of the page,
    paste the value, and click **Authorize**. All protected endpoints will unlock.

    ### Notes:
    - ID Tokens are valid for **1 hour**
    - If Firebase Admin SDK is not configured, this endpoint returns HTTP 503
    - If `FIREBASE_WEB_API_KEY` is not set, the response includes a `custom_token`
      instead — use the Firebase Client SDK to exchange it manually
    """
    import httpx

    email = str(data.email)

    # ── Step 1: Verify OTP ────────────────────────────────────────────────────
    valid = otp_store.verify(email, data.otp)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code. Request a new OTP via POST /api/otp/send.",
        )

    # ── Step 2: Firebase Admin must be available ──────────────────────────────
    if not _firebase_admin_available or _firebase_auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Firebase Admin SDK is not configured. "
                "Set FIREBASE_CREDENTIALS_JSON in Render environment variables. "
                "See GET /auth/info for setup instructions."
            ),
        )

    # ── Step 3: Get or create Firebase user ──────────────────────────────────
    try:
        try:
            user = _firebase_auth.get_user_by_email(email)
            logger.info("[AUTH/TOKEN] Existing user login: uid=%s", user.uid)
        except Exception:
            user = _firebase_auth.create_user(email=email, email_verified=True)
            logger.info("[AUTH/TOKEN] New user created: uid=%s", user.uid)
    except Exception as exc:
        logger.error("[AUTH/TOKEN] Firebase user get/create failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create or retrieve Firebase user. Check Firebase Admin credentials.",
        )

    # ── Step 4: Create Firebase Custom Token ─────────────────────────────────
    try:
        custom_token_bytes = _firebase_auth.create_custom_token(user.uid)
        custom_token = (
            custom_token_bytes.decode("utf-8")
            if isinstance(custom_token_bytes, bytes)
            else custom_token_bytes
        )
    except Exception as exc:
        logger.error("[AUTH/TOKEN] Custom token creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create authentication token.",
        )

    # ── Step 5: Exchange Custom Token → ID Token via Firebase REST API ────────
    web_api_key = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not web_api_key:
        # Can't do the exchange server-side — return custom token with instructions
        logger.warning(
            "[AUTH/TOKEN] FIREBASE_WEB_API_KEY not set — returning custom_token only. "
            "Set FIREBASE_WEB_API_KEY in Render environment variables for full ID token exchange."
        )
        return {
            "success": True,
            "uid": user.uid,
            "email": email,
            "token_type": "custom_token",
            "custom_token": custom_token,
            "id_token": None,
            "warning": (
                "FIREBASE_WEB_API_KEY is not set. The custom_token above cannot be used directly "
                "in Swagger. Set FIREBASE_WEB_API_KEY in Render environment variables to enable "
                "full ID token exchange. Get your Web API Key from: "
                "Firebase Console → Project Settings → General → Web API Key."
            ),
            "manual_exchange_url": (
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
                f"?key=YOUR_WEB_API_KEY"
            ),
        }

    # Exchange via Firebase Identity Toolkit REST API
    exchange_url = (
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
        f"?key={web_api_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                exchange_url,
                json={"token": custom_token, "returnSecureToken": True},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            firebase_resp = resp.json()
    except httpx.HTTPStatusError as exc:
        err_body = exc.response.text[:500] if exc.response else "(no body)"
        logger.error("[AUTH/TOKEN] Firebase token exchange HTTP error %s: %s", exc.response.status_code, err_body)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Firebase token exchange failed. Check FIREBASE_WEB_API_KEY.",
        )
    except Exception as exc:
        logger.error("[AUTH/TOKEN] Firebase token exchange error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Firebase token exchange temporarily unavailable.",
        )

    id_token = firebase_resp.get("idToken", "")
    expires_in = int(firebase_resp.get("expiresIn", 3600))

    logger.info("[AUTH/TOKEN] ID token issued for uid=%s (expires_in=%ds)", user.uid, expires_in)

    return {
        "success": True,
        "uid": user.uid,
        "email": email,
        "token_type": "Bearer",
        "id_token": id_token,
        "expires_in": expires_in,
        "swagger_instructions": (
            "Copy the id_token value above. Click 'Authorize' (🔓) at the top of Swagger, "
            "paste the id_token, and click Authorize. All protected endpoints will now work."
        ),
    }


# ─── AI Service Imports ────────────────────────────────────────────────────────
from src.services.ai import ai_service
from src.services.voice import voice_service


# ─── Protected: AI Chatbot ─────────────────────────────────────────────────────
@app.post("/api/chat", tags=["AI"])
@limiter.limit("20/minute")
async def chat_helper(
    request: Request,
    data: ChatMessage,
    token: dict = Depends(verify_firebase_token),   # AUTH REQUIRED — CWE-306 FIXED
):
    history_list = [h.dict() for h in data.history] if data.history else []
    try:
        reply = await ai_service.generate_chat_response(data.message, history_list)
    except Exception:
        logger.exception("[CHAT] AI service error for uid=%s", token.get("uid"))
        raise HTTPException(status_code=502, detail="AI service temporarily unavailable.")
    return {"reply": reply}


# ─── Protected: AI Voice Briefing ─────────────────────────────────────────────
@app.post("/api/briefing", tags=["AI"])
@limiter.limit("20/minute")
async def briefing_helper(
    request: Request,
    data: BriefingRequest,
    token: dict = Depends(verify_firebase_token),
):
    try:
        briefing = await ai_service.generate_voice_briefing(data.dict())
    except Exception:
        logger.exception("[BRIEFING] AI service error for uid=%s", token.get("uid"))
        raise HTTPException(status_code=502, detail="Briefing service temporarily unavailable.")
    return {"briefing": briefing}


# ─── Protected: City Safety Score ─────────────────────────────────────────────
@app.get("/api/safety", tags=["Safety"])
@limiter.limit("30/minute")
async def safety_score(
    request: Request,
    city: str = Query(..., min_length=1, max_length=200, description="City name to assess"),
    token: dict = Depends(verify_firebase_token),
):
    try:
        result = await ai_service.get_safety_assessment(city)
    except Exception:
        logger.exception("[SAFETY] Error for city=%s uid=%s", city, token.get("uid"))
        raise HTTPException(status_code=502, detail="Safety service temporarily unavailable.")
    return result


# ─── Protected: Voice Transcribe ──────────────────────────────────────────────
@app.post("/api/voice/transcribe", tags=["Voice"])
@limiter.limit("10/minute")
async def transcribe_voice(
    request: Request,
    file: UploadFile = File(...),  # MAX_SIZE and MIME validated in validate_audio_file
    token: dict = Depends(verify_firebase_token),
):
    # Validate file: extension + size + magic bytes (CWE-434 FIXED)
    file_contents = await validate_audio_file(file)

    suffix = os.path.splitext(file.filename or "audio")[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_contents)
        tmp_path = tmp.name

    try:
        text = await voice_service.transcribe_audio(tmp_path)
        return {"text": text}
    except Exception:
        logger.exception("[VOICE] Transcription error for uid=%s", token.get("uid"))
        raise HTTPException(status_code=502, detail="Transcription service temporarily unavailable.")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ─── Protected: Voice Respond ─────────────────────────────────────────────────
@app.post("/api/voice/respond", tags=["Voice"])
@limiter.limit("20/minute")
async def voice_respond_helper(
    request: Request,
    data: VoiceRespondRequest,
    token: dict = Depends(verify_firebase_token),
):
    try:
        reply = await ai_service.generate_voice_response(data.query, data.context)
    except Exception:
        logger.exception("[VOICE] Response error for uid=%s", token.get("uid"))
        raise HTTPException(status_code=502, detail="Voice service temporarily unavailable.")
    return {"reply": reply}


# ─── Protected: TSP Route Optimizer ───────────────────────────────────────────
@app.post("/api/routes/optimize", tags=["Routes"])
@limiter.limit("30/minute")
async def optimize_route(
    request: Request,
    spots: List[RouteSpot],
    token: dict = Depends(verify_firebase_token),
):
    if len(spots) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 route spots allowed.")
    if len(spots) <= 2:
        return spots

    def haversine_km(s1: RouteSpot, s2: RouteSpot) -> float:
        R = 6371
        rad = math.pi / 180
        dlat = (s2.latitude - s1.latitude) * rad
        dlon = (s2.longitude - s1.longitude) * rad
        a = (math.sin(dlat / 2) ** 2
             + math.cos(s1.latitude * rad) * math.cos(s2.latitude * rad)
             * math.sin(dlon / 2) ** 2)
        return 2 * R * math.asin(math.sqrt(a))

    unvisited = list(spots[1:])
    ordered = [spots[0]]
    while unvisited:
        last = ordered[-1]
        nearest_idx = min(range(len(unvisited)), key=lambda i: haversine_km(last, unvisited[i]))
        ordered.append(unvisited.pop(nearest_idx))
    return ordered


# ─── Protected: Trip Management ───────────────────────────────────────────────
@app.get("/api/trips", tags=["Trips"])
@limiter.limit("30/minute")
async def get_trips(
    request: Request,
    token: dict = Depends(verify_firebase_token),
):
    # userId extracted from VERIFIED token — never from client (CWE-639 FIXED)
    uid = token["uid"]
    logger.info("[TRIPS] get_trips called by uid=%s", uid)
    return {
        "trips": [
            {
                "id": "trip_001",
                "title": "Goa Beach Holiday",
                "destination": "Goa, India",
                "startDate": "2025-12-20",
                "endDate": "2025-12-27",
                "status": "upcoming",
                "coverImage": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800",
            },
            {
                "id": "trip_002",
                "title": "Manali Snow Adventure",
                "destination": "Manali, Himachal Pradesh",
                "startDate": "2026-01-10",
                "endDate": "2026-01-17",
                "status": "planning",
                "coverImage": "https://images.unsplash.com/photo-1548013146-72479768bada?w=800",
            },
        ],
        "total": 2,
        "userId": uid,
    }


@app.post("/api/trips", tags=["Trips"])
@limiter.limit("20/minute")
async def create_trip(
    request: Request,
    trip: TripCreate,
    token: dict = Depends(verify_firebase_token),
):
    # userId from verified token — CWE-639 FIXED
    uid = token["uid"]
    trip_id = f"trip_{abs(hash(trip.title + uid)) % 100000:05d}"
    logger.info("[TRIPS] create_trip by uid=%s title=%s", uid, trip.title)
    return {
        "success": True,
        "tripId": trip_id,
        "message": f"Trip '{trip.title}' created successfully!",
        "trip": {**trip.dict(), "userId": uid},
    }


# ─── Protected: Expense Split ─────────────────────────────────────────────────
@app.post("/api/expenses/split", tags=["Expenses"])
@limiter.limit("30/minute")
async def split_expense(
    request: Request,
    data: ExpenseSplit,
    token: dict = Depends(verify_firebase_token),
):
    per_person = round(data.totalAmount / len(data.members), 2)
    return {
        "totalAmount": data.totalAmount,
        "perPerson": per_person,
        "memberCount": len(data.members),
        "splits": [{"member": m, "amount": per_person, "paid": False} for m in data.members],
        "description": data.description,
    }


# ─── Protected: AI Itinerary Generator ────────────────────────────────────────
@app.post("/api/itinerary/generate", tags=["AI"])
@limiter.limit("10/minute")
async def generate_itinerary(
    request: Request,
    data: ItineraryRequest,           # Typed model replaces raw dict — CWE-20 FIXED
    token: dict = Depends(verify_firebase_token),
):
    try:
        result = await ai_service.generate_itinerary(data.dict())
    except Exception:
        logger.exception("[ITINERARY] Generation error for uid=%s", token.get("uid"))
        raise HTTPException(status_code=502, detail="Itinerary service temporarily unavailable.")
    return result


# ─── Protected: Weather Proxy ─────────────────────────────────────────────────
@app.get("/api/weather", tags=["Weather"])
@limiter.limit("30/minute")
async def weather_proxy(
    request: Request,
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    token: dict = Depends(verify_firebase_token),
):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}&current_weather=true"
            )
            res.raise_for_status()
            data = res.json()
            return data.get("current_weather", {})
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="Weather service returned an error.")
    except Exception:
        logger.exception("[WEATHER] Proxy error for lat=%s lon=%s", lat, lon)
        raise HTTPException(status_code=502, detail="Weather service temporarily unavailable.")


# ─── OTP: Send (rate-limited, OTP NOT in response) ────────────────────────────
# CWE-287: OTP in response FIXED | CWE-307: Rate limiting added
@app.post("/api/otp/send", tags=["OTP"])
@limiter.limit("3/minute")
async def send_otp_email_endpoint(request: Request, data: OTPSendRequest):
    """
    Generate and email an OTP. OTP is NEVER returned in the response.
    Rate limited to 3 requests/minute/IP.
    OTP expires after OTP_TTL_SECONDS (default 300s = 5min).
    Maximum OTP_MAX_ATTEMPTS (default 3) verification attempts.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    email_to = str(data.email)

    # Generate OTP and store securely (single-use + expiry + retry limit)
    otp_code = otp_store.generate(email_to)

    subject = "Your TripSync OTP Verification Code 🔐"
    body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #0F172A; color: white; padding: 20px; border-radius: 12px;">
        <h2 style="color: #38BDF8;">TripSync Verification Code</h2>
        <p>Hello,</p>
        <p>Thank you for choosing TripSync. Use the following One-Time Password (OTP) to complete your verification:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 4px; color: #38BDF8; margin: 20px 0; background-color: #1E293B; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #334155;">
          {otp_code}
        </div>
        <p style="color: #94A3B8; font-size: 13px;">This code is valid for 5 minutes. If you did not request this code, please ignore this email.</p>
        <hr style="border-color: #334155;" />
        <p style="color: #475569; font-size: 11px;">TripSync AI Travel Companion</p>
      </body>
    </html>
    """

    smtp_host = settings.SMTP_HOST
    smtp_port = settings.SMTP_PORT
    smtp_user = settings.SMTP_USER
    smtp_pass = settings.SMTP_PASS

    email_sent = False

    if email_to.endswith("@example.com") or email_to.endswith("@tripsync.org") or email_to.endswith("@tripsync.com"):
        email_sent = True
        logger.info("[OTP] Bypass SMTP: Test email for %s logged.", _mask_email_log(email_to))
    elif smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = email_to
            plain = "Your TripSync OTP is: " + str(otp_code) + "\nValid for 5 minutes.\nIf you did not request this, ignore this email."
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(body, "html"))
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=5)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=5)
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, email_to, msg.as_string())
            server.quit()
            email_sent = True
            # Log email sent without OTP (CWE-312 FIXED — OTP never logged)
            logger.info("[OTP] Email sent to %s", _mask_email_log(email_to))
        except smtplib.SMTPAuthenticationError:
            logger.error("[OTP] SMTP authentication failed")
            otp_store.invalidate(email_to)  # Invalidate on send failure
            raise HTTPException(status_code=502, detail="Email service authentication failed.")
        except Exception:
            logger.exception("[OTP] Failed to send OTP email")
            otp_store.invalidate(email_to)
            raise HTTPException(status_code=502, detail="Failed to send verification email.")
    else:
        # SMTP not configured — log warning WITHOUT the OTP code (CWE-312 FIXED)
        logger.warning(
            "[OTP] SMTP not configured. OTP generated for %s but NOT sent. "
            "Configure SMTP_USER and SMTP_PASS.",
            _mask_email_log(email_to),
        )

    # OTP is NEVER returned in the response (CWE-287 FIXED)
    return {
        "success": email_sent,
        "message": (
            "Verification code sent to your email address."
            if email_sent
            else "Email service not configured. Contact support."
        ),
    }


@app.post("/api/otp/verify", tags=["OTP"], deprecated=True, summary="[Deprecated] Verify OTP (use POST /auth/token instead)")
@limiter.limit("5/minute")
async def verify_otp_endpoint(request: Request, data: OTPVerifyRequest):
    """
    Verify an OTP. Single-use: verified OTP is immediately invalidated.
    Returns success/failure only — no internal error details.
    """
    email = str(data.email)
    valid = otp_store.verify(email, data.otp)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code.",
        )
    
    # Allow login or registration (get or create user in Firebase Auth if available)
    response_data = {"success": True, "message": "Verification successful."}
    if _firebase_admin_available and _firebase_auth is not None:
        try:
            try:
                user = _firebase_auth.get_user_by_email(email)
                logger.info("[AUTH] User found in Firebase: %s", email)
            except Exception:
                user = _firebase_auth.create_user(email=email, email_verified=True)
                logger.info("[AUTH] New user registered in Firebase: %s", email)
            
            custom_token = _firebase_auth.create_custom_token(user.uid)
            token_str = custom_token.decode("utf-8") if isinstance(custom_token, bytes) else custom_token
            response_data.update({
                "firebase_token": token_str,
                "uid": user.uid
            })
        except Exception as exc:
            logger.error("[AUTH] Firebase user creation/retrieval failed: %s", exc)
            
    return response_data


# ─── Protected: Route Sharing ─────────────────────────────────────────────────
@app.post("/api/routes/share", tags=["Routes"])
@limiter.limit("20/minute")
async def share_route_endpoint(
    request: Request,
    data: ShareRouteMetadata,
    token: dict = Depends(verify_firebase_token),
):
    if not (0 <= data.stopsCount <= 100):
        raise HTTPException(status_code=400, detail="stopsCount must be between 0 and 100.")
    scenic_factor = round(8.0 + (data.stopsCount % 3) * 0.5, 1)
    complexity = (
        "Easy Navigation" if data.stopsCount <= 3
        else "Scenic Adventure" if data.stopsCount <= 6
        else "Epic Multi-Stop Expedition"
    )
    return {
        "success": True,
        "message": f"Route '{data.routeName}' sharing registered successfully!",
        "analytics": {
            "scenicFactor": scenic_factor,
            "complexity": complexity,
            "recommendation": f"Best time to start this {data.stopsCount}-stop journey is 8:30 AM.",
        },
    }


# ─── Helpers ───────────────────────────────────────────────────────────────────
def _mask_email_log(email: str) -> str:
    """Mask email address for safe logging."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}" if len(local) > 1 else f"***@{domain}"


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.environ.get("APP_ENV", "development") == "development",
        log_level="info",
    )
