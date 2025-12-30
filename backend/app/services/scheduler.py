from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

from . import graph
from ..storage.json_store import JSONStore

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

VERIFY_INTERVAL_HOURS = 6


def decrypt_field(fernet: Optional[Fernet], value: str) -> str:
    if not fernet or not value:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return value


class AccountVerifyScheduler:
    """Background scheduler for periodic account verification."""

    def __init__(
        self,
        store: JSONStore,
        settings: "Settings",
        interval_hours: int = VERIFY_INTERVAL_HOURS,
    ):
        self.store = store
        self.settings = settings
        self.interval_hours = interval_hours
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._fernet: Optional[Fernet] = None

        if settings.token_enc_key:
            try:
                self._fernet = Fernet(settings.token_enc_key.encode())
            except Exception:
                pass

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Account verify scheduler started (interval: {self.interval_hours}h)")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Account verify scheduler stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_hours * 3600)
                if self._running:
                    await self._verify_all_accounts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)

    async def _verify_all_accounts(self) -> None:
        """Verify all accounts."""
        logger.info("Starting scheduled account verification...")
        data = self.store.read()
        accounts = data.get("accounts", [])

        if not accounts:
            logger.info("No accounts to verify")
            return

        results = []
        semaphore = asyncio.Semaphore(10)

        async def verify_one(account: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                refresh_token = decrypt_field(self._fernet, account.get("refresh_token", ""))
                client_id = account.get("client_id", "")
                is_valid, error = await graph.verify_account(refresh_token, client_id)
                return {
                    "account_id": account["id"],
                    "email": account["email"],
                    "valid": is_valid,
                    "error": error,
                }

        results = await asyncio.gather(*[verify_one(a) for a in accounts], return_exceptions=True)

        valid_count = 0
        invalid_count = 0
        error_count = 0

        def _mutator(data: Dict[str, Any]) -> None:
            nonlocal valid_count, invalid_count, error_count
            accounts_map = {a["id"]: a for a in data.get("accounts", [])}
            now = datetime.now(timezone.utc).isoformat()

            for result in results:
                if isinstance(result, Exception):
                    error_count += 1
                    continue

                acc = accounts_map.get(result["account_id"])
                if acc:
                    if result["valid"]:
                        acc["status"] = "active"
                        valid_count += 1
                    else:
                        acc["status"] = "invalid"
                        invalid_count += 1
                    acc["last_verified"] = now

        self.store.update(_mutator)
        logger.info(
            f"Scheduled verification complete: {valid_count} valid, "
            f"{invalid_count} invalid, {error_count} errors"
        )
