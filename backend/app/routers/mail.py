from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..config import Settings
from ..models import MailDetail, MailFolder, MailMessage, MessageResponse, VerifyResult
from ..services import graph
from ..services.graph import GraphAPIError
from ..storage.json_store import JSONStore
from .auth import get_current_user, get_store

router = APIRouter(prefix="/api", tags=["mail"])


def get_fernet(request: Request) -> Optional[Fernet]:
    settings: Settings = request.app.state.settings
    if not settings.token_enc_key:
        return None
    try:
        return Fernet(settings.token_enc_key.encode())
    except Exception:
        return None


def decrypt_field(fernet: Optional[Fernet], value: str) -> str:
    if not fernet or not value:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return value


def get_account_by_id(store: JSONStore, account_id: str) -> Dict[str, Any]:
    data = store.read()
    account = next((a for a in data.get("accounts", []) if a.get("id") == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


async def get_access_token_for_account(
    account: Dict[str, Any],
    fernet: Optional[Fernet],
) -> str:
    refresh_token = decrypt_field(fernet, account.get("refresh_token", ""))
    client_id = account.get("client_id", "")

    if not refresh_token or not client_id:
        raise HTTPException(status_code=400, detail="Account missing credentials")

    try:
        access_token, _ = await graph.get_access_token(
            refresh_token=refresh_token,
            client_id=client_id,
            account_id=account["id"],
        )
        return access_token
    except GraphAPIError as e:
        raise HTTPException(status_code=401, detail=f"Token error: {e}")


# ============ Verify Routes ============

@router.post("/accounts/{account_id}/verify", response_model=VerifyResult)
async def verify_single_account(
    account_id: str,
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> VerifyResult:
    fernet = get_fernet(request)
    account = get_account_by_id(store, account_id)

    refresh_token = decrypt_field(fernet, account.get("refresh_token", ""))
    client_id = account.get("client_id", "")

    is_valid, error = await graph.verify_account(refresh_token, client_id)

    # Update account status
    def _mutator(data: Dict[str, Any]) -> None:
        accounts = data.get("accounts", [])
        acc = next((a for a in accounts if a.get("id") == account_id), None)
        if acc:
            acc["status"] = "active" if is_valid else "invalid"
            acc["last_verified"] = datetime.now(timezone.utc).isoformat()

    store.update(_mutator)

    return VerifyResult(
        account_id=account_id,
        email=account["email"],
        valid=is_valid,
        error=error,
    )


@router.post("/accounts/batch-verify", response_model=List[VerifyResult])
async def batch_verify_accounts(
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> List[VerifyResult]:
    fernet = get_fernet(request)
    data = store.read()
    accounts = data.get("accounts", [])

    if not accounts:
        return []

    async def verify_one(account: Dict[str, Any]) -> VerifyResult:
        refresh_token = decrypt_field(fernet, account.get("refresh_token", ""))
        client_id = account.get("client_id", "")
        is_valid, error = await graph.verify_account(refresh_token, client_id)
        return VerifyResult(
            account_id=account["id"],
            email=account["email"],
            valid=is_valid,
            error=error,
        )

    # Run verification concurrently (with limit)
    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests

    async def verify_with_limit(account: Dict[str, Any]) -> VerifyResult:
        async with semaphore:
            return await verify_one(account)

    results = await asyncio.gather(*[verify_with_limit(a) for a in accounts])

    # Update all account statuses
    def _mutator(data: Dict[str, Any]) -> None:
        accounts_map = {a["id"]: a for a in data.get("accounts", [])}
        now = datetime.now(timezone.utc).isoformat()
        for result in results:
            acc = accounts_map.get(result.account_id)
            if acc:
                acc["status"] = "active" if result.valid else "invalid"
                acc["last_verified"] = now

    store.update(_mutator)

    return list(results)


# ============ Mail Routes ============

@router.get("/accounts/{account_id}/folders", response_model=List[MailFolder])
async def get_folders(
    account_id: str,
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> List[MailFolder]:
    fernet = get_fernet(request)
    account = get_account_by_id(store, account_id)
    access_token = await get_access_token_for_account(account, fernet)

    try:
        folders = await graph.get_mail_folders(access_token)
        return [MailFolder(**f) for f in folders]
    except GraphAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))


@router.get("/accounts/{account_id}/messages", response_model=Dict[str, Any])
async def get_messages(
    account_id: str,
    request: Request,
    folder: str = Query("inbox", description="Folder name or ID"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search query"),
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, Any]:
    fernet = get_fernet(request)
    account = get_account_by_id(store, account_id)
    access_token = await get_access_token_for_account(account, fernet)

    try:
        messages, total = await graph.get_messages(
            access_token=access_token,
            folder=folder,
            limit=limit,
            skip=skip,
            search=search,
        )
        return {
            "items": [MailMessage(**m) for m in messages],
            "total": total,
            "limit": limit,
            "skip": skip,
        }
    except GraphAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))


@router.get("/accounts/{account_id}/messages/{message_id}", response_model=MailDetail)
async def get_message_detail(
    account_id: str,
    message_id: str,
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> MailDetail:
    fernet = get_fernet(request)
    account = get_account_by_id(store, account_id)
    access_token = await get_access_token_for_account(account, fernet)

    try:
        detail = await graph.get_message_detail(access_token, message_id)
        return MailDetail(**detail)
    except GraphAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))


@router.delete("/accounts/{account_id}/messages/{message_id}", response_model=MessageResponse)
async def delete_message(
    account_id: str,
    message_id: str,
    request: Request,
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> MessageResponse:
    fernet = get_fernet(request)
    account = get_account_by_id(store, account_id)
    access_token = await get_access_token_for_account(account, fernet)

    try:
        await graph.delete_message(access_token, message_id)
        return MessageResponse(message="Message deleted")
    except GraphAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))


@router.get("/accounts/{account_id}/unread-count", response_model=Dict[str, int])
async def get_unread_count(
    account_id: str,
    request: Request,
    folder: str = Query("inbox"),
    store: JSONStore = Depends(get_store),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, int]:
    fernet = get_fernet(request)
    account = get_account_by_id(store, account_id)
    access_token = await get_access_token_for_account(account, fernet)

    try:
        count = await graph.get_unread_count(access_token, folder)
        return {"unread_count": count}
    except GraphAPIError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e))
