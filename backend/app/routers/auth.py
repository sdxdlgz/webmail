from __future__ import annotations

import threading
import uuid
from typing import Dict, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..config import Settings
from ..models import LoginRequest, MessageResponse, UserOut
from ..storage.json_store import JSONStore

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SessionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, str] = {}

    def create(self, user_id: str) -> str:
        session_id = str(uuid.uuid4())
        with self._lock:
            self._sessions[session_id] = user_id
        return session_id

    def get_user_id(self, session_id: str) -> Optional[str]:
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def get_store(request: Request) -> JSONStore:
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise RuntimeError("Store not initialized")
    return store


def get_sessions(request: Request) -> SessionManager:
    sessions = getattr(request.app.state, "sessions", None)
    if sessions is None:
        raise RuntimeError("Sessions not initialized")
    return sessions


def get_settings_from_request(request: Request) -> Settings:
    return request.app.state.settings


def get_current_user(
    request: Request,
    store: JSONStore = Depends(get_store),
    sessions: SessionManager = Depends(get_sessions),
) -> Dict[str, str]:
    settings: Settings = request.app.state.settings
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = sessions.get_user_id(session_id)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    data = store.read()
    user = next((u for u in data.get("users", []) if u.get("id") == user_id), None)
    if not user:
        sessions.delete(session_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return {"id": user["id"], "username": user["username"]}


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    store: JSONStore = Depends(get_store),
    sessions: SessionManager = Depends(get_sessions),
) -> Dict[str, str]:
    data = store.read()
    user = next((u for u in data.get("users", []) if u.get("username") == payload.username), None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if not verify_password(payload.password, str(user.get("password_hash", ""))):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    session_id = sessions.create(user["id"])
    settings: Settings = request.app.state.settings
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return {"id": user["id"], "username": user["username"]}


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    request: Request,
    sessions: SessionManager = Depends(get_sessions),
) -> Dict[str, str]:
    settings: Settings = request.app.state.settings
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        sessions.delete(session_id)

    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"message": "ok"}


@router.get("/me", response_model=UserOut)
def me(current_user: Dict[str, str] = Depends(get_current_user)) -> Dict[str, str]:
    return current_user
