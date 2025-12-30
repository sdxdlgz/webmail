from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings, PROJECT_ROOT
from .routers import auth as auth_router
from .routers import accounts as accounts_router
from .routers import mail as mail_router
from .routers.auth import SessionManager, hash_password
from .services.scheduler import AccountVerifyScheduler
from .storage.json_store import JSONStore

FRONTEND_DIR = PROJECT_ROOT / "frontend"


def _ensure_default_admin(store: JSONStore, settings: Settings) -> None:
    from datetime import datetime, timezone

    def _mutator(data):
        data.setdefault("groups", [])
        data.setdefault("accounts", [])
        data.setdefault("settings", {"allow_registration": True})

        users = data.setdefault("users", [])
        if users:
            return

        now = datetime.now(timezone.utc).isoformat()
        users.append(
            {
                "id": str(uuid.uuid4()),
                "username": settings.default_admin_username,
                "password_hash": hash_password(settings.default_admin_password),
                "role": "admin",
                "must_change_password": True,
                "created_at": now,
            }
        )

    store.update(_mutator)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    store = JSONStore(settings.data_file_path)
    scheduler = AccountVerifyScheduler(store, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup
        store.ensure_initialized()
        _ensure_default_admin(store, settings)
        await scheduler.start()
        yield
        # Shutdown
        await scheduler.stop()

    app = FastAPI(title="Outlook Mail Manager API", lifespan=lifespan)

    app.state.settings = settings
    app.state.store = store
    app.state.sessions = SessionManager()
    app.state.scheduler = scheduler

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router.router)
    app.include_router(accounts_router.router)
    app.include_router(mail_router.router)

    # Mount frontend static files
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app


app = create_app()
