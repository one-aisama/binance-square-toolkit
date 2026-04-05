from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

from src.session.credential_crypto import dump_secret, load_secret

logger = logging.getLogger("bsq.session")


class CredentialStore:
    """CRUD operations for the credentials table in SQLite."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    async def save(
        self,
        account_id: str,
        cookies: dict[str, Any],
        headers: dict[str, Any],
        max_age_hours: float = 12.0,
    ) -> None:
        """Save or update credentials for an account (upsert)."""
        now = datetime.utcnow().isoformat()
        expires = (datetime.utcnow() + timedelta(hours=max_age_hours)).isoformat()
        encrypted_cookies = dump_secret(cookies)
        encrypted_headers = dump_secret(headers)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO credentials (account_id, cookies, headers, harvested_at, expires_at, valid)
                   VALUES (?, ?, ?, ?, ?, TRUE)
                   ON CONFLICT(account_id) DO UPDATE SET
                       cookies = excluded.cookies,
                       headers = excluded.headers,
                       harvested_at = excluded.harvested_at,
                       expires_at = excluded.expires_at,
                       valid = TRUE""",
                (account_id, encrypted_cookies, encrypted_headers, now, expires),
            )
            await db.commit()
        logger.info("Credentials saved for %s", account_id)

    async def load(self, account_id: str) -> dict[str, Any] | None:
        """Load credentials for an account. Returns None if not found."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM credentials WHERE account_id = ?",
                (account_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "account_id": row["account_id"],
                "cookies": load_secret(row["cookies"]),
                "headers": load_secret(row["headers"]),
                "harvested_at": row["harvested_at"],
                "expires_at": row["expires_at"],
                "valid": bool(row["valid"]),
            }

    async def invalidate(self, account_id: str) -> None:
        """Mark credentials as invalid."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE credentials SET valid = FALSE WHERE account_id = ?",
                (account_id,),
            )
            await db.commit()
        logger.info("Credentials invalidated for %s", account_id)

    async def is_valid(self, account_id: str) -> bool:
        """Check if credentials exist and are marked valid."""
        cred = await self.load(account_id)
        if cred is None:
            return False
        return bool(cred["valid"])

    async def is_expired(self, account_id: str) -> bool:
        """Check if credentials have passed their expires_at time."""
        cred = await self.load(account_id)
        if cred is None:
            return True
        if cred["expires_at"] is None:
            return False
        return datetime.utcnow() > datetime.fromisoformat(cred["expires_at"])
