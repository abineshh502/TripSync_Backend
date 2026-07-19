"""
TripSync Backend — OTP Store
==============================
In-memory OTP store with:
  - Configurable expiry (default 5 minutes)
  - Retry limiting (default 3 attempts per OTP)
  - Single-use invalidation (OTP deleted after first successful verification)
  - Automatic cleanup of expired entries

CWE-287: Improper Authentication — FIXED (single-use + expiry)
CWE-307: Improper Restriction of Excessive Authentication — FIXED (retry limit)
OWASP A07: Identification and Authentication Failures — FIXED
"""

import os
import time
import secrets
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS: int = int(os.environ.get("OTP_TTL_SECONDS", "300"))   # 5 min
OTP_MAX_ATTEMPTS: int = int(os.environ.get("OTP_MAX_ATTEMPTS", "3"))
OTP_LENGTH: int = int(os.environ.get("OTP_LENGTH", "6"))
OTP_CLEANUP_INTERVAL: int = 120  # seconds


@dataclass
class OTPEntry:
    code: str
    created_at: float
    attempts: int = 0
    used: bool = False

    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > OTP_TTL_SECONDS

    def is_exhausted(self) -> bool:
        return self.attempts >= OTP_MAX_ATTEMPTS


class OTPStore:
    """
    Thread-safe, in-memory OTP store.
    For production with multiple workers, replace with Redis-backed store.
    """

    def __init__(self):
        self._store: Dict[str, OTPEntry] = {}
        self._lock = threading.Lock()
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        def cleanup():
            while True:
                time.sleep(OTP_CLEANUP_INTERVAL)
                self._purge_expired()

        t = threading.Thread(target=cleanup, daemon=True, name="otp-cleanup")
        t.start()

    def _purge_expired(self):
        with self._lock:
            expired_keys = [
                k for k, v in self._store.items() if v.is_expired()
            ]
            for k in expired_keys:
                del self._store[k]
            if expired_keys:
                logger.debug("[OTP] Purged %d expired OTP entries", len(expired_keys))

    def generate(self, email: str) -> str:
        """
        Generate a new OTP for the given email.
        Any previous OTP for this email is invalidated immediately.
        Returns the OTP code (to be sent by email — NEVER returned to client).
        """
        code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
        entry = OTPEntry(code=code, created_at=time.monotonic())
        with self._lock:
            # Invalidate any prior pending OTP for this email
            if email in self._store:
                logger.info("[OTP] Previous OTP for %s invalidated", _mask_email(email))
            self._store[email] = entry
        logger.info("[OTP] Generated OTP for %s (expires in %ds)", _mask_email(email), OTP_TTL_SECONDS)
        return code

    def verify(self, email: str, code: str) -> bool:
        """
        Verify an OTP for the given email.
        Returns True only if: code matches, not expired, not used, attempts < max.
        Always increments attempt counter. Invalidates on success.
        """
        with self._lock:
            entry = self._store.get(email)

            if entry is None:
                logger.warning("[OTP] Verification attempt for unknown email: %s", _mask_email(email))
                return False

            if entry.used:
                logger.warning("[OTP] Reuse attempt for already-used OTP: %s", _mask_email(email))
                del self._store[email]
                return False

            if entry.is_expired():
                logger.warning("[OTP] Expired OTP verification attempt: %s", _mask_email(email))
                del self._store[email]
                return False

            if entry.is_exhausted():
                logger.warning(
                    "[OTP] OTP locked out after %d failed attempts: %s",
                    OTP_MAX_ATTEMPTS, _mask_email(email)
                )
                del self._store[email]
                return False

            entry.attempts += 1

            if not secrets.compare_digest(entry.code, code):
                remaining = OTP_MAX_ATTEMPTS - entry.attempts
                logger.warning(
                    "[OTP] Invalid OTP for %s. Attempts: %d/%d (%d remaining)",
                    _mask_email(email), entry.attempts, OTP_MAX_ATTEMPTS, remaining
                )
                if entry.is_exhausted():
                    del self._store[email]
                return False

            # Success — mark as used and remove
            entry.used = True
            del self._store[email]
            logger.info("[OTP] OTP verified and invalidated for %s", _mask_email(email))
            return True

    def invalidate(self, email: str) -> None:
        """Explicitly invalidate any pending OTP for this email."""
        with self._lock:
            if email in self._store:
                del self._store[email]
                logger.info("[OTP] OTP explicitly invalidated for %s", _mask_email(email))

    def pending_count(self) -> int:
        with self._lock:
            return len(self._store)


def _mask_email(email: str) -> str:
    """Mask email for safe logging: user@domain.com → u***@domain.com"""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked_local = local[0] + "***" if len(local) > 1 else "***"
    return f"{masked_local}@{domain}"


# Singleton instance
otp_store = OTPStore()
