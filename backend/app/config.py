from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_FILE_PATH = PROJECT_ROOT / "backend" / "data" / "data.json"

DEFAULT_CORS_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
_VALID_SAMESITE = {"lax", "strict", "none"}


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_samesite(value: Optional[str], default: str = "lax") -> str:
    if not value:
        return default
    normalized = value.strip().lower()
    return normalized if normalized in _VALID_SAMESITE else default


def _parse_cors_origins(value: Optional[str]) -> Tuple[List[str], Optional[str]]:
    if not value:
        return [], DEFAULT_CORS_ORIGIN_REGEX

    raw = value.strip()
    if raw == "*":
        return [], ".*"

    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins, None


@dataclass(frozen=True)
class Settings:
    data_file_path: Path = DEFAULT_DATA_FILE_PATH
    token_enc_key: str = ""

    cors_allow_origins: List[str] = field(default_factory=list)
    cors_allow_origin_regex: Optional[str] = DEFAULT_CORS_ORIGIN_REGEX

    session_cookie_name: str = "session_id"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"

    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    @classmethod
    def from_env(cls) -> "Settings":
        data_file_path = Path(os.getenv("DATA_FILE_PATH", str(DEFAULT_DATA_FILE_PATH)))
        token_enc_key = os.getenv("TOKEN_ENC_KEY", "")

        cors_allow_origins, cors_allow_origin_regex = _parse_cors_origins(os.getenv("CORS_ORIGINS"))

        session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "session_id")
        session_cookie_secure = _parse_bool(os.getenv("SESSION_COOKIE_SECURE"), False)
        session_cookie_samesite = _parse_samesite(os.getenv("SESSION_COOKIE_SAMESITE"), "lax")

        default_admin_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
        default_admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

        return cls(
            data_file_path=data_file_path,
            token_enc_key=token_enc_key,
            cors_allow_origins=cors_allow_origins,
            cors_allow_origin_regex=cors_allow_origin_regex,
            session_cookie_name=session_cookie_name,
            session_cookie_secure=session_cookie_secure,
            session_cookie_samesite=session_cookie_samesite,
            default_admin_username=default_admin_username,
            default_admin_password=default_admin_password,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
