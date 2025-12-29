from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .token_cache import token_cache

GRAPH_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0


class GraphAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0, error_code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


async def get_access_token(
    refresh_token: str,
    client_id: str,
    account_id: Optional[str] = None,
) -> Tuple[str, int]:
    """
    Exchange refresh token for access token.
    Returns (access_token, expires_in).
    """
    # Check cache first
    if account_id:
        cached = token_cache.get(account_id)
        if cached:
            return cached, 3600  # Return cached token with default expiry

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(
            GRAPH_TOKEN_URL,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "https://graph.microsoft.com/.default",
            },
        )

        if response.status_code != 200:
            try:
                error_data = response.json()
                error_msg = error_data.get("error_description", error_data.get("error", "Unknown error"))
                error_code = error_data.get("error", "")
            except Exception:
                error_msg = f"HTTP {response.status_code}"
                error_code = ""
            raise GraphAPIError(error_msg, response.status_code, error_code)

        data = response.json()
        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)

        # Cache the token
        if account_id:
            token_cache.set(account_id, access_token, expires_in)

        return access_token, expires_in


async def verify_account(refresh_token: str, client_id: str) -> Tuple[bool, Optional[str]]:
    """
    Verify if account credentials are valid.
    Returns (is_valid, error_message).
    """
    try:
        await get_access_token(refresh_token, client_id)
        return True, None
    except GraphAPIError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)


async def _make_graph_request(
    method: str,
    endpoint: str,
    access_token: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    """Make a request to Graph API with retry logic."""
    url = f"{GRAPH_API_BASE}{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for attempt in range(MAX_RETRIES):
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", RETRY_DELAY * (attempt + 1)))
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(retry_after)
                    continue
                raise GraphAPIError("Rate limited", 429, "TooManyRequests")

            return response

    raise GraphAPIError("Max retries exceeded", 0, "MaxRetriesExceeded")


async def get_mail_folders(access_token: str) -> List[Dict[str, Any]]:
    """Get list of mail folders."""
    response = await _make_graph_request(
        "GET",
        "/me/mailFolders",
        access_token,
        params={"$select": "id,displayName,unreadItemCount,totalItemCount"},
    )

    if response.status_code != 200:
        raise GraphAPIError(f"Failed to get folders: {response.text}", response.status_code)

    data = response.json()
    folders = []
    for f in data.get("value", []):
        folders.append({
            "id": f["id"],
            "name": f["displayName"],
            "unread_count": f.get("unreadItemCount", 0),
            "total_count": f.get("totalItemCount", 0),
        })
    return folders


async def get_messages(
    access_token: str,
    folder: str = "inbox",
    limit: int = 50,
    skip: int = 0,
    search: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Get messages from a folder.
    Returns (messages, total_count).
    """
    params: Dict[str, Any] = {
        "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
        "$orderby": "receivedDateTime desc",
        "$top": limit,
        "$skip": skip,
        "$count": "true",
    }

    if search:
        # Search in subject and from
        params["$search"] = f'"{search}"'

    endpoint = f"/me/mailFolders/{folder}/messages"
    response = await _make_graph_request("GET", endpoint, access_token, params=params)

    if response.status_code != 200:
        raise GraphAPIError(f"Failed to get messages: {response.text}", response.status_code)

    data = response.json()
    total_count = data.get("@odata.count", 0)

    messages = []
    for m in data.get("value", []):
        from_data = m.get("from", {}).get("emailAddress", {})
        messages.append({
            "id": m["id"],
            "subject": m.get("subject"),
            "from_address": from_data.get("address"),
            "from_name": from_data.get("name"),
            "received_at": m.get("receivedDateTime"),
            "is_read": m.get("isRead", False),
            "body_preview": m.get("bodyPreview"),
        })

    return messages, total_count


async def get_message_detail(access_token: str, message_id: str) -> Dict[str, Any]:
    """Get full message details."""
    params = {
        "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,body",
    }

    response = await _make_graph_request(
        "GET",
        f"/me/messages/{message_id}",
        access_token,
        params=params,
    )

    if response.status_code == 404:
        raise GraphAPIError("Message not found", 404, "ItemNotFound")

    if response.status_code != 200:
        raise GraphAPIError(f"Failed to get message: {response.text}", response.status_code)

    m = response.json()
    from_data = m.get("from", {}).get("emailAddress", {})
    body = m.get("body", {})

    to_list = [r.get("emailAddress", {}).get("address", "") for r in m.get("toRecipients", [])]
    cc_list = [r.get("emailAddress", {}).get("address", "") for r in m.get("ccRecipients", [])]

    return {
        "id": m["id"],
        "subject": m.get("subject"),
        "from_address": from_data.get("address"),
        "from_name": from_data.get("name"),
        "to": to_list,
        "cc": cc_list,
        "received_at": m.get("receivedDateTime"),
        "is_read": m.get("isRead", False),
        "body_content": body.get("content"),
        "body_type": body.get("contentType", "text"),
    }


async def delete_message(access_token: str, message_id: str) -> None:
    """Delete a message (moves to Deleted Items)."""
    response = await _make_graph_request(
        "DELETE",
        f"/me/messages/{message_id}",
        access_token,
    )

    if response.status_code == 404:
        raise GraphAPIError("Message not found", 404, "ItemNotFound")

    if response.status_code not in (200, 204):
        raise GraphAPIError(f"Failed to delete message: {response.text}", response.status_code)


async def get_unread_count(access_token: str, folder: str = "inbox") -> int:
    """Get unread message count for a folder."""
    response = await _make_graph_request(
        "GET",
        f"/me/mailFolders/{folder}",
        access_token,
        params={"$select": "unreadItemCount"},
    )

    if response.status_code != 200:
        raise GraphAPIError(f"Failed to get unread count: {response.text}", response.status_code)

    data = response.json()
    return data.get("unreadItemCount", 0)
