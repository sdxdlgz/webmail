from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..config import Settings
from ..models import (
    AdminUserOut,
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    SystemSettings,
    UserOut,
    UserUpdateRequest,
)
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
) -> Dict[str, Any]:
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

    return {
        "id": user["id"],
        "username": user["username"],
        "role": user.get("role", "user"),
        "must_change_password": user.get("must_change_password", False),
    }


def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    store: JSONStore = Depends(get_store),
    sessions: SessionManager = Depends(get_sessions),
) -> Dict[str, Any]:
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
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user.get("role", "user"),
        "must_change_password": user.get("must_change_password", False),
    }


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    store: JSONStore = Depends(get_store),
) -> Dict[str, Any]:
    def _mutator(data: Dict[str, Any]) -> Dict[str, Any]:
        # Check if registration is allowed
        settings_data = data.get("settings", {})
        if not settings_data.get("allow_registration", True):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled")

        users = data.setdefault("users", [])

        # Check duplicate username
        if any(u.get("username") == payload.username for u in users):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

        now = datetime.now(timezone.utc).isoformat()
        user = {
            "id": str(uuid.uuid4()),
            "username": payload.username,
            "password_hash": hash_password(payload.password),
            "role": "user",
            "must_change_password": False,
            "created_at": now,
        }
        users.append(user)
        return user

    user = store.update(_mutator)
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "must_change_password": user["must_change_password"],
    }


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
def me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return current_user


@router.put("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    store: JSONStore = Depends(get_store),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    def _mutator(data: Dict[str, Any]) -> None:
        users = data.get("users", [])
        user = next((u for u in users if u.get("id") == current_user["id"]), None)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if not verify_password(payload.old_password, str(user.get("password_hash", ""))):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        user["password_hash"] = hash_password(payload.new_password)
        user["must_change_password"] = False

        if payload.new_username:
            # Check duplicate
            if any(u.get("username") == payload.new_username and u.get("id") != current_user["id"] for u in users):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
            user["username"] = payload.new_username

    store.update(_mutator)
    return {"message": "Password changed successfully"}


@router.get("/settings", response_model=SystemSettings)
def get_system_settings(
    store: JSONStore = Depends(get_store),
) -> Dict[str, Any]:
    data = store.read()
    settings_data = data.get("settings", {})
    return {"allow_registration": settings_data.get("allow_registration", True)}


# ============ Admin Routes ============

@router.get("/admin/users", response_model=List[AdminUserOut])
def list_users(
    store: JSONStore = Depends(get_store),
    admin: Dict[str, Any] = Depends(require_admin),
) -> List[Dict[str, Any]]:
    data = store.read()
    users = data.get("users", [])
    return [
        {
            "id": u["id"],
            "username": u["username"],
            "role": u.get("role", "user"),
            "must_change_password": u.get("must_change_password", False),
            "created_at": u.get("created_at", ""),
        }
        for u in users
    ]


@router.put("/admin/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    store: JSONStore = Depends(get_store),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    def _mutator(data: Dict[str, Any]) -> Dict[str, Any]:
        users = data.get("users", [])
        user = next((u for u in users if u.get("id") == user_id), None)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if payload.username:
            if any(u.get("username") == payload.username and u.get("id") != user_id for u in users):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
            user["username"] = payload.username

        if payload.password:
            user["password_hash"] = hash_password(payload.password)
            user["must_change_password"] = True

        if payload.role:
            user["role"] = payload.role

        return user

    user = store.update(_mutator)
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user.get("role", "user"),
        "must_change_password": user.get("must_change_password", False),
        "created_at": user.get("created_at", ""),
    }


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    store: JSONStore = Depends(get_store),
    admin: Dict[str, Any] = Depends(require_admin),
) -> None:
    if user_id == admin["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    def _mutator(data: Dict[str, Any]) -> None:
        users = data.get("users", [])
        idx = next((i for i, u in enumerate(users) if u.get("id") == user_id), None)
        if idx is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Also delete user's accounts and groups
        deleted_user_id = users[idx]["id"]
        users.pop(idx)

        # Remove user's accounts
        data["accounts"] = [a for a in data.get("accounts", []) if a.get("owner_id") != deleted_user_id]
        # Remove user's groups
        data["groups"] = [g for g in data.get("groups", []) if g.get("owner_id") != deleted_user_id]

    store.update(_mutator)


@router.put("/admin/settings", response_model=SystemSettings)
def update_system_settings(
    payload: SystemSettings,
    store: JSONStore = Depends(get_store),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    def _mutator(data: Dict[str, Any]) -> Dict[str, Any]:
        settings_data = data.setdefault("settings", {})
        settings_data["allow_registration"] = payload.allow_registration
        return settings_data

    settings_data = store.update(_mutator)
    return {"allow_registration": settings_data.get("allow_registration", True)}
