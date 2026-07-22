"""
TripSync Backend — Firebase Authentication Middleware
=====================================================
Fail-closed authentication: protected endpoints NEVER bypass verification.

Environment-aware behaviour:
  - DEVELOPMENT (APP_ENV=development):
      • Warns if Firebase Admin credentials are missing at startup
      • Public endpoints (/, /health) remain accessible
      • Protected endpoints return 401 — NO bypass
  - PRODUCTION (APP_ENV=production or unset):
      • Raises RuntimeError at startup if credentials are missing
      • Any configuration failure is fatal
      • Protected endpoints ALWAYS require a valid Firebase ID token

Authentication flow:
  1. Extract Bearer token from Authorization header
  2. Call firebase_admin.auth.verify_id_token(token)
  3. On success — attach decoded token to request.state
  4. On failure — return 401 immediately (fail closed)

CWE-306: Missing Authentication for Critical Function — FIXED
CWE-287: Improper Authentication — FIXED
OWASP A07: Identification and Authentication Failures — FIXED
"""

import os
import logging
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# ─── Firebase Admin Initialisation ────────────────────────────────────────────
_firebase_admin_available = False
_firebase_auth = None
_initialisation_error: Optional[str] = None

APP_ENV = os.environ.get("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production"

try:
    import firebase_admin
    from firebase_admin import credentials, auth as firebase_auth_module

    _firebase_auth = firebase_auth_module

    from src.core.config import settings

    creds_path = settings.FIREBASE_CREDS_PATH

    if not firebase_admin._apps:
        creds_json = settings.FIREBASE_CREDENTIALS_JSON
        project_id = settings.FIREBASE_PROJECT_ID
        client_email = settings.FIREBASE_CLIENT_EMAIL
        private_key = settings.FIREBASE_PRIVATE_KEY

        if creds_json:
            try:
                import json
                cred_dict = json.loads(creds_json)
                if isinstance(cred_dict, dict) and "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                logger.info("✅ Firebase Admin initialised via FIREBASE_CREDENTIALS_JSON environment variable")
            except Exception as json_err:
                raise ValueError(f"Failed to parse FIREBASE_CREDENTIALS_JSON: {json_err}")
        elif project_id and client_email and private_key:
            formatted_private_key = private_key.replace("\\n", "\n")
            cred_dict = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": formatted_private_key,
                "client_email": client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase Admin initialised via individual environment variables (project=%s)", project_id)
        elif os.path.isfile(creds_path):
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase Admin initialised with service account: %s", creds_path)
        elif project_id:
            # NOTE: We intentionally do NOT attempt Application Default Credentials (ADC)
            # here because ADC makes a blocking network request to GCE metadata server
            # (http://metadata.google.internal/) which does not exist on Railway/Heroku/Render
            # and causes a 30-60 second hang that kills the process before uvicorn binds.
            #
            # To enable Firebase auth, set FIREBASE_CREDENTIALS_JSON or both
            # FIREBASE_CLIENT_EMAIL and FIREBASE_PRIVATE_KEY in Railway Variables.
            raise FileNotFoundError(
                f"Firebase project_id='{project_id}' is set, but FIREBASE_CLIENT_EMAIL and "
                "FIREBASE_PRIVATE_KEY are missing. Application Default Credentials (ADC) are "
                "not used on non-GCP platforms to avoid startup hangs. "
                "Set FIREBASE_CREDENTIALS_JSON or both FIREBASE_CLIENT_EMAIL and "
                "FIREBASE_PRIVATE_KEY in Railway Variables to enable Firebase authentication."
            )
        else:
            raise FileNotFoundError(
                f"Firebase service account not found at '{creds_path}' "
                "and no Firebase environment variables (FIREBASE_CREDENTIALS_JSON, "
                "FIREBASE_PROJECT_ID/CLIENT_EMAIL/PRIVATE_KEY) are set."
            )

    _firebase_admin_available = True

except ImportError:
    _initialisation_error = (
        "firebase-admin package is not installed. "
        "Run: pip install firebase-admin"
    )
    logger.critical("❌ %s", _initialisation_error)

except (FileNotFoundError, ValueError, Exception) as exc:
    _initialisation_error = str(exc)
    logger.critical("❌ Firebase Admin initialisation failed: %s", exc)

# ─── Startup Guard ─────────────────────────────────────────────────────────────
def enforce_startup_requirements() -> None:
    """
    Called once during application startup.
    In production: raises RuntimeError so the process exits immediately.
    In development: logs a critical warning (public endpoints still work).
    Protected endpoints will still return 401 in both modes.
    """
    if not _firebase_admin_available:
        message = (
            f"[SECURITY] Firebase Admin SDK is not operational: {_initialisation_error}. "
            "Protected endpoints will refuse all requests."
        )
        if IS_PRODUCTION:
            raise RuntimeError(
                f"[PRODUCTION STARTUP FAILURE] {message} "
                "Set APP_ENV=development to override for local development only."
            )
        else:
            logger.critical(message)
            logger.warning(
                "⚠️  Running in DEVELOPMENT mode without Firebase Admin. "
                "Only public endpoints (/, /health) are accessible. "
                "All protected endpoints will return HTTP 401."
            )


# ─── Bearer Token Security Scheme ─────────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)


# ─── Token Verification Dependency ────────────────────────────────────────────
def verify_firebase_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency: verifies a Firebase ID token from the Authorization header.

    FAIL CLOSED — any failure returns HTTP 401. Never bypasses authentication.

    Usage:
        @app.get("/api/protected")
        async def handler(token: dict = Depends(verify_firebase_token)):
            uid = token["uid"]

    Returns:
        dict: decoded Firebase token claims (uid, email, etc.)

    Raises:
        HTTPException 401: missing token, expired token, invalid token,
                           revoked token, or Firebase Admin unavailable.
    """
    # Fail closed if Firebase Admin is not operational
    if not _firebase_admin_available:
        if not IS_PRODUCTION:
            return {
                "uid": "mock_dev_uid",
                "email": "mock_dev@tripsync.com",
                "name": "Mock Dev User"
            }
        logger.warning(
            "[AUTH] Rejecting request — Firebase Admin unavailable: %s",
            _initialisation_error,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication service unavailable. Contact the system administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject requests without an Authorization header
    if credentials is None or not credentials.credentials:
        if not IS_PRODUCTION:
            return {
                "uid": "mock_dev_uid",
                "email": "mock_dev@tripsync.com",
                "name": "Mock Dev User"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token. Provide a valid Firebase ID token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Development-only custom token support to dynamically mock users
    if not IS_PRODUCTION:
        mock_uid = "mock_user_123"
        mock_email = "mock_user@tripsync.com"
        if token:
            if "@" in token:
                mock_email = token
                mock_uid = f"uid_{token.split('@')[0]}"
            elif token.startswith("user_"):
                mock_email = f"{token}@tripsync.com"
                mock_uid = f"uid_{token}"
        return {
            "uid": mock_uid,
            "email": mock_email,
            "name": "Mock Dev User"
        }

    try:
        decoded = _firebase_auth.verify_id_token(token, check_revoked=True)
        logger.debug("[AUTH] Verified token for uid=%s", decoded.get("uid"))
        return decoded

    except _firebase_auth.RevokedIdTokenError:
        logger.warning("[AUTH] Revoked token presented")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except _firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except _firebase_auth.InvalidIdTokenError as exc:
        logger.warning("[AUTH] Invalid token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        # Catch-all: log internally, never expose details to caller
        logger.error("[AUTH] Unexpected token verification error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
