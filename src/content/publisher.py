"""Content publishing to Binance Square via bapi."""

import logging
from datetime import datetime
from typing import Any

import aiosqlite

from src.bapi.client import BapiClient

logger = logging.getLogger("bsq.content")


class ContentPublisher:
    """Publish posts and manage content queue."""

    def __init__(self, client: BapiClient, db_path: str):
        self._client = client
        self._db_path = db_path

    async def publish(self, text: str, hashtags: list[str] | None = None) -> dict:
        """Publish post via bapi and return result."""
        result = await self._client.create_post(text, hashtags)
        return result

    async def queue_content(
        self,
        account_id: str,
        text: str,
        hashtags: list[str] | None = None,
        topic: str = "",
        meta: dict | None = None,
        scheduled_at: str | None = None,
    ) -> int:
        """Add generated content to queue for later publishing."""
        import json
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO content_queue (account_id, text, hashtags, topic, generation_meta, scheduled_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    account_id,
                    text,
                    json.dumps(hashtags) if hashtags else None,
                    topic,
                    json.dumps(meta) if meta else None,
                    scheduled_at,
                ),
            )
            await db.commit()
            row_id = cursor.lastrowid
        logger.info(f"Queued content #{row_id} for {account_id}")
        return row_id

    async def get_pending(self, account_id: str) -> list[dict]:
        """Get all pending content for an account that is due for publishing."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM content_queue "
                "WHERE account_id = ? AND status = 'pending' "
                "AND (scheduled_at IS NULL OR scheduled_at <= ?) "
                "ORDER BY created_at",
                (account_id, now),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_published(self, queue_id: int, post_id: str = "") -> None:
        """Mark content as published."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE content_queue SET status = 'published', published_at = ?, post_id = ? "
                "WHERE id = ?",
                (datetime.utcnow().isoformat(), post_id, queue_id),
            )
            await db.commit()

    async def mark_failed(self, queue_id: int, error: str) -> None:
        """Mark content as failed."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE content_queue SET status = 'failed', error_message = ? WHERE id = ?",
                (error, queue_id),
            )
            await db.commit()
