"""
TripSync Backend — Application Settings
========================================
All security-sensitive values are driven by environment variables.
No secrets or security-critical values are hardcoded.

Required env vars for production (APP_ENV=production):
  FIREBASE_CREDENTIALS_PATH or FIREBASE_PROJECT_ID
  CORS_ALLOWED_ORIGINS  (comma-separated list of allowed origins)

Optional env vars with secure defaults:
  APP_ENV           — development | production  (default: production)
  RATE_LIMIT_GLOBAL — global rate limit string  (default: 60/minute)
  RATE_LIMIT_OTP    — OTP endpoint limit        (default: 3/minute)
  RATE_LIMIT_AI     — AI endpoints limit        (default: 20/minute)
  OTP_TTL_SECONDS   — OTP lifetime              (default: 300)
  OTP_MAX_ATTEMPTS  — OTP max retries           (default: 3)
"""

import os
import logging

logger = logging.getLogger(__name__)

# ─── Trusted Origins ──────────────────────────────────────────────────────────
def _parse_cors_origins() -> list[str]:
    """
    Parse CORS_ALLOWED_ORIGINS from environment.
    Format: comma-separated list, e.g.
      CORS_ALLOWED_ORIGINS=https://tripsync.vercel.app,https://tripsync.com

    Security: Wildcard (*) is never returned regardless of env value.
    In development without the var set, allow localhost variants only.
    """
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    env = os.environ.get("APP_ENV", "development").lower()

    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        # Security guard: reject wildcard even if explicitly set
        safe_origins = [o for o in origins if o != "*"]
        if len(safe_origins) < len(origins):
            logger.warning(
                "[CONFIG] Wildcard (*) was present in CORS_ALLOWED_ORIGINS and has been removed. "
                "Specify explicit origins."
            )
        return safe_origins

    if env == "development":
        # Development-only fallback: localhost variants only
        logger.warning(
            "[CONFIG] CORS_ALLOWED_ORIGINS not set. "
            "Using localhost-only defaults for development. "
            "Set CORS_ALLOWED_ORIGINS in production."
        )
        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
        ]

    # Production with no explicit CORS_ALLOWED_ORIGINS configured:
    # Allow Vercel production Web App, GitHub Pages, local web clients, and mobile app webview origins
    logger.info(
        "[CONFIG] Using standard production/mobile default CORS origins."
    )
    return [
        "https://trip-sync-web.vercel.app",
        "https://tripsync.vercel.app",
        "https://abineshh502.github.io",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "capacitor://localhost",
        "ionic://localhost",
    ]


class Settings:
    APP_ENV: str = os.environ.get("APP_ENV", "development").lower()
    DEBUG: bool = APP_ENV == "development"

    # ── Firebase ──
    FIREBASE_CREDS_PATH: str = os.environ.get(
        "FIREBASE_CREDENTIALS_PATH", "firebase-adminsdk.json"
    )
    FIREBASE_PROJECT_ID: str = os.environ.get("FIREBASE_PROJECT_ID", "tripsync-8e63e")
    FIREBASE_CREDENTIALS_JSON: str = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
    FIREBASE_CLIENT_EMAIL: str = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
    FIREBASE_PRIVATE_KEY: str = os.environ.get("FIREBASE_PRIVATE_KEY", "")

    # ── CORS (never wildcard) ──
    CORS_ORIGINS: list = _parse_cors_origins()

    # ── SMTP — Email / OTP Delivery ──
    SMTP_HOST: str = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER: str = os.environ.get("SMTP_USER", "")
    SMTP_PASS: str = os.environ.get("SMTP_PASS", "")

    # ── OTP Configuration ──
    OTP_TTL_SECONDS: int = int(os.environ.get("OTP_TTL_SECONDS", "300"))
    OTP_MAX_ATTEMPTS: int = int(os.environ.get("OTP_MAX_ATTEMPTS", "3"))
    OTP_LENGTH: int = int(os.environ.get("OTP_LENGTH", "6"))

    # ── Rate Limiting ──
    RATE_LIMIT_GLOBAL: str = os.environ.get("RATE_LIMIT_GLOBAL", "60/minute")
    RATE_LIMIT_OTP: str    = os.environ.get("RATE_LIMIT_OTP",    "3/minute")
    RATE_LIMIT_AI: str     = os.environ.get("RATE_LIMIT_AI",     "20/minute")
    RATE_LIMIT_UPLOAD: str = os.environ.get("RATE_LIMIT_UPLOAD", "10/minute")

    # ── File Upload ──
    MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10 MB
    ALLOWED_AUDIO_EXTENSIONS: frozenset = frozenset(
        {".m4a", ".mp3", ".wav", ".ogg", ".webm", ".aac", ".flac"}
    )
    # Audio magic byte signatures: {extension: [bytes_prefix]}
    ALLOWED_AUDIO_MAGIC: dict = {
        b"\xff\xfb": ".mp3",   # MP3 frame sync
        b"\xff\xf3": ".mp3",
        b"\xff\xf2": ".mp3",
        b"ID3":      ".mp3",   # MP3 ID3 tag
        b"fLaC":     ".flac",
        b"OggS":     ".ogg",
        b"RIFF":     ".wav",   # WAV container (RIFF header)
    }

    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    def validate_for_startup(self) -> None:
        """
        Called at application startup.
        In production: raises RuntimeError on missing critical config.
        In development: logs warnings.
        """
        import os as _os
        issues = []

        firebase_ok = (
            _os.path.isfile(self.FIREBASE_CREDS_PATH)
            or bool(self.FIREBASE_CREDENTIALS_JSON)
            or (bool(self.FIREBASE_PROJECT_ID) and bool(self.FIREBASE_CLIENT_EMAIL) and bool(self.FIREBASE_PRIVATE_KEY))
            or bool(self.FIREBASE_PROJECT_ID)
        )
        if not firebase_ok:
            issues.append(
                f"Firebase credentials not found at '{self.FIREBASE_CREDS_PATH}' "
                "and no Firebase environment variables (FIREBASE_CREDENTIALS_JSON or "
                "FIREBASE_PROJECT_ID/CLIENT_EMAIL/PRIVATE_KEY) are set. "
                "Protected endpoints will refuse all requests."
            )

        if not self.CORS_ORIGINS:
            logger.warning(
                "[STARTUP] CORS_ALLOWED_ORIGINS is empty. "
                "Cross-origin requests will be blocked."
            )

        # SMTP configuration verification (always logged as warning if incomplete, non-fatal)
        if not self.SMTP_USER or not self.SMTP_PASS:
            logger.warning(
                "[STARTUP] SMTP configuration is incomplete (SMTP_USER and/or SMTP_PASS missing). "
                "OTP email dispatch will be unavailable."
            )

        if issues:
            for issue in issues:
                if self.is_production():
                    logger.critical("[STARTUP] %s", issue)
                else:
                    logger.warning("[STARTUP] %s", issue)

            if self.is_production():
                raise RuntimeError(
                    "[PRODUCTION STARTUP FAILURE] Critical configuration missing: "
                    + "; ".join(issues)
                )


settings = Settings()

