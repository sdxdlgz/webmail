from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from ..config import Settings
from ..models import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    BatchDeleteRequest,
    BatchGroupRequest,
    BatchImportRequest,
    GroupCreate,
    GroupOut,
)
from ..storage.json_store import JSONStore
from .auth import get_current_user, get_store

router = APIRouter(prefix="/api", tags=["accounts"])


def get_fernet(request: Request) -> Optional[Fernet]:
    settings: Settings = request.app.state.settings
    if not settings.token_enc_key:
        return None
    try:
        return Fernet(settings.token_enc_key.encode())
    except Exception:
        return None


def encrypt_field(fernet: Optional[Fernet], value: str) -> str:
    if not fernet or not value:
        return value
    return fernet.encrypt(value.encode()).decode()


def decrypt_field(fernet: Optional[Fernet], value: str) -> str:
    if not fernet or not value:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return value


def parse_account_line(line: str) -> Optional[Dict[str, str]]:
    """Parse account line: email----password----refresh_token----client_id"""
    line = line.strip()
    if not line:
        return None

    parts = line.split("----")
    if len(parts) < 4:
        return None

    return {
        "email": parts[0].strip(),
        "password": parts[1].strip() if len(parts) > 1 else "",
        "refresh_token": parts[2].strip() if len(parts) > 2 else "",
        "client_id": parts[3].strip() if len(parts) > 3 else "",
    }


def account_to_out(account: Dict[str, Any]) -> AccountOut:
    return AccountOut(
        id=account["id"],
        email=account["email"],
        client_id=account["client_id"],
        group_id=account.get("group_id"),
        remark=account.get("remark"),
        status=account.get("status", "unknown"),
        last_verified=account.get("last_verified"),
        created_at=account["created_at"],
    )


# ============ Account Routes ============

@router.get("/accounts", response_model=List[AccountOut])
def list_accounts(
    search: Optional[str] = Query(None, description="Search by email"),
    group_id: Optional[str] = Query(None, description="Filter by group"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> List[AccountOut]:
    data = store.read()
    accounts = data.get("accounts", [])

    # Multi-tenant: filter by owner_id
    accounts = [a for a in accounts if a.get("owner_id") == current_user["id"]]

    if search:
        search_lower = search.lower()
        accounts = [a for a in accounts if search_lower in a.get("email", "").lower()]

    if group_id:
        accounts = [a for a in accounts if a.get("group_id") == group_id]

    if status_filter:
        accounts = [a for a in accounts if a.get("status") == status_filter]

    return [account_to_out(a) for a in accounts]


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> AccountOut:
    fernet = get_fernet(request)
    user_id = current_user["id"]

    def _mutator(data: Dict[str, Any]) -> Dict[str, Any]:
        accounts = data.setdefault("accounts", [])

        # Check duplicate email for this user
        if any(a.get("email") == payload.email and a.get("owner_id") == user_id for a in accounts):
            raise HTTPException(status_code=400, detail="Account with this email already exists")

        # Validate group if provided (must belong to user)
        if payload.group_id:
            groups = data.get("groups", [])
            if not any(g.get("id") == payload.group_id and g.get("owner_id") == user_id for g in groups):
                raise HTTPException(status_code=400, detail="Group not found")

        now = datetime.now(timezone.utc).isoformat()
        account = {
            "id": str(uuid.uuid4()),
            "owner_id": user_id,
            "email": payload.email,
            "password": encrypt_field(fernet, payload.password),
            "refresh_token": encrypt_field(fernet, payload.refresh_token),
            "client_id": payload.client_id,
            "group_id": payload.group_id,
            "remark": payload.remark,
            "status": "unknown",
            "last_verified": None,
            "created_at": now,
        }
        accounts.append(account)
        return account

    account = store.update(_mutator)
    return account_to_out(account)


@router.post("/accounts/batch", response_model=Dict[str, Any])
def batch_import_accounts(
    payload: BatchImportRequest,
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, Any]:
    fernet = get_fernet(request)
    user_id = current_user["id"]
    lines = payload.data.strip().split("\n")

    imported = []
    skipped = []
    errors = []

    def _mutator(data: Dict[str, Any]) -> None:
        accounts = data.setdefault("accounts", [])
        # Only check duplicates within user's own accounts
        existing_emails = {a.get("email") for a in accounts if a.get("owner_id") == user_id}

        # Validate group if provided (must belong to user)
        if payload.group_id:
            groups = data.get("groups", [])
            if not any(g.get("id") == payload.group_id and g.get("owner_id") == user_id for g in groups):
                raise HTTPException(status_code=400, detail="Group not found")

        for i, line in enumerate(lines, 1):
            parsed = parse_account_line(line)
            if not parsed:
                if line.strip():
                    errors.append({"line": i, "error": "Invalid format"})
                continue

            if not parsed["email"] or not parsed["refresh_token"] or not parsed["client_id"]:
                errors.append({"line": i, "error": "Missing required fields"})
                continue

            if parsed["email"] in existing_emails:
                skipped.append({"line": i, "email": parsed["email"], "reason": "duplicate"})
                continue

            now = datetime.now(timezone.utc).isoformat()
            account = {
                "id": str(uuid.uuid4()),
                "owner_id": user_id,
                "email": parsed["email"],
                "password": encrypt_field(fernet, parsed["password"]),
                "refresh_token": encrypt_field(fernet, parsed["refresh_token"]),
                "client_id": parsed["client_id"],
                "group_id": payload.group_id,
                "status": "unknown",
                "last_verified": None,
                "created_at": now,
            }
            accounts.append(account)
            existing_emails.add(parsed["email"])
            imported.append({"line": i, "email": parsed["email"]})

    store.update(_mutator)

    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "errors": len(errors),
        "details": {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
        }
    }


@router.put("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: str,
    payload: AccountUpdate,
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> AccountOut:
    fernet = get_fernet(request)
    user_id = current_user["id"]

    def _mutator(data: Dict[str, Any]) -> Dict[str, Any]:
        accounts = data.get("accounts", [])
        account = next((a for a in accounts if a.get("id") == account_id and a.get("owner_id") == user_id), None)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        # Validate group if provided (must belong to user)
        if payload.group_id is not None:
            if payload.group_id:
                groups = data.get("groups", [])
                if not any(g.get("id") == payload.group_id and g.get("owner_id") == user_id for g in groups):
                    raise HTTPException(status_code=400, detail="Group not found")
            account["group_id"] = payload.group_id

        if payload.email is not None:
            # Check duplicate within user's accounts
            if any(a.get("email") == payload.email and a.get("id") != account_id and a.get("owner_id") == user_id for a in accounts):
                raise HTTPException(status_code=400, detail="Account with this email already exists")
            account["email"] = payload.email

        if payload.password is not None:
            account["password"] = encrypt_field(fernet, payload.password)

        if payload.refresh_token is not None:
            account["refresh_token"] = encrypt_field(fernet, payload.refresh_token)
            account["status"] = "unknown"  # Reset status when token updated

        if payload.client_id is not None:
            account["client_id"] = payload.client_id

        if payload.remark is not None:
            account["remark"] = payload.remark

        return account

    account = store.update(_mutator)
    return account_to_out(account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_account(
    account_id: str,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> None:
    user_id = current_user["id"]

    def _mutator(data: Dict[str, Any]) -> None:
        accounts = data.get("accounts", [])
        idx = next((i for i, a in enumerate(accounts) if a.get("id") == account_id and a.get("owner_id") == user_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Account not found")
        accounts.pop(idx)

    store.update(_mutator)


@router.post("/accounts/batch-delete", response_model=Dict[str, int])
def batch_delete_accounts(
    payload: BatchDeleteRequest,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, int]:
    user_id = current_user["id"]
    ids_to_delete = set(payload.ids)
    deleted_count = 0

    def _mutator(data: Dict[str, Any]) -> None:
        nonlocal deleted_count
        accounts = data.get("accounts", [])
        original_len = len(accounts)
        # Only delete accounts owned by current user
        data["accounts"] = [a for a in accounts if not (a.get("id") in ids_to_delete and a.get("owner_id") == user_id)]
        deleted_count = original_len - len(data["accounts"])

    store.update(_mutator)
    return {"deleted": deleted_count}


@router.post("/accounts/batch-group", response_model=Dict[str, int])
def batch_group_accounts(
    payload: BatchGroupRequest,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, int]:
    user_id = current_user["id"]
    ids_to_update = set(payload.ids)
    updated_count = 0

    def _mutator(data: Dict[str, Any]) -> None:
        nonlocal updated_count

        # Validate group if provided (must belong to user)
        if payload.group_id:
            groups = data.get("groups", [])
            if not any(g.get("id") == payload.group_id and g.get("owner_id") == user_id for g in groups):
                raise HTTPException(status_code=400, detail="Group not found")

        for account in data.get("accounts", []):
            if account.get("id") in ids_to_update and account.get("owner_id") == user_id:
                account["group_id"] = payload.group_id
                updated_count += 1

    store.update(_mutator)
    return {"updated": updated_count}


@router.get("/accounts/export", response_class=PlainTextResponse)
def export_accounts(
    request: Request,
    group_id: Optional[str] = Query(None),
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> str:
    fernet = get_fernet(request)
    user_id = current_user["id"]
    data = store.read()
    accounts = data.get("accounts", [])

    # Multi-tenant: filter by owner_id
    accounts = [a for a in accounts if a.get("owner_id") == user_id]

    if group_id:
        accounts = [a for a in accounts if a.get("group_id") == group_id]

    lines = []
    for a in accounts:
        password = decrypt_field(fernet, a.get("password", ""))
        refresh_token = decrypt_field(fernet, a.get("refresh_token", ""))
        line = f"{a['email']}----{password}----{refresh_token}----{a['client_id']}"
        lines.append(line)

    return "\n".join(lines)


# ============ Group Routes ============

@router.get("/groups", response_model=List[GroupOut])
def list_groups(
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> List[GroupOut]:
    user_id = current_user["id"]
    data = store.read()
    groups = data.get("groups", [])
    # Multi-tenant: filter by owner_id
    groups = [g for g in groups if g.get("owner_id") == user_id]
    return [GroupOut(id=g["id"], name=g["name"]) for g in groups]


@router.post("/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> GroupOut:
    user_id = current_user["id"]

    def _mutator(data: Dict[str, Any]) -> Dict[str, Any]:
        groups = data.setdefault("groups", [])

        # Check duplicate name within user's groups
        if any(g.get("name") == payload.name and g.get("owner_id") == user_id for g in groups):
            raise HTTPException(status_code=400, detail="Group with this name already exists")

        group = {
            "id": str(uuid.uuid4()),
            "owner_id": user_id,
            "name": payload.name,
        }
        groups.append(group)
        return group

    group = store.update(_mutator)
    return GroupOut(id=group["id"], name=group["name"])


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_group(
    group_id: str,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> None:
    user_id = current_user["id"]

    def _mutator(data: Dict[str, Any]) -> None:
        groups = data.get("groups", [])
        idx = next((i for i, g in enumerate(groups) if g.get("id") == group_id and g.get("owner_id") == user_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Group not found")
        groups.pop(idx)

        # Remove group_id from user's accounts only
        for account in data.get("accounts", []):
            if account.get("group_id") == group_id and account.get("owner_id") == user_id:
                account["group_id"] = None

    store.update(_mutator)
