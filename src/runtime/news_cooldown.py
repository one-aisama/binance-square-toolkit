"""News cooldown: prevent all agents from rushing the same breaking news.

When agent A publishes a news_reaction, it records the news fingerprint.
Agent B sees it and either skips (< 30 min) or deprioritizes (30-90 min).

Fingerprint = MD5 of source_url (or headline if no URL).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import aiosqlite

logger = logging.getLogger("bsq.news_cooldown")

COOLDOWN_TOTAL_MINUTES = 90
HARD_BLOCK_MINUTES = 30


def _news_fingerprint(source_url: str | None, headline: str | None) -> str:
    """Build a deterministic fingerprint from URL or headline."""
    raw = str(source_url or headline or "").strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


async def record_news_cooldown(
    db_path: str,
    *,
    agent_id: str,
    source_url: str | None = None,
    headline: str | None = None,
) -> None:
    """Record that this agent just published about this news item."""
    fingerprint = _news_fingerprint(source_url, headline)
    now = datetime.now(timezone.utc)
    cooldown_until = now + timedelta(minutes=COOLDOWN_TOTAL_MINUTES)
    headline_hash = hashlib.md5((headline or "").encode()).hexdigest()[:12] if headline else None
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """INSERT OR IGNORE INTO news_cooldowns
                   (agent_id, news_fingerprint, source_url, headline_hash, created_at, cooldown_until)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (agent_id, fingerprint, source_url, headline_hash,
                 now.isoformat(), cooldown_until.isoformat()),
            )
            await db.commit()
    except Exception:
        logger.exception("news_cooldown.record: failed for fingerprint=%s", fingerprint)


async def check_news_cooldown(
    db_path: str,
    *,
    exclude_agent_id: str,
    source_url: str | None = None,
    headline: str | None = None,
) -> Literal["clear", "blocked", "stagger"]:
    """Check if this news item is in cooldown from another agent.

    Returns:
        "clear" — no cooldown, free to post
        "blocked" — within hard-block window (< 30 min), skip this news
        "stagger" — in cooldown but past hard-block (30-90 min), deprioritize
    """
    fingerprint = _news_fingerprint(source_url, headline)
    now = datetime.now(timezone.utc)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                """SELECT created_at, cooldown_until FROM news_cooldowns
                   WHERE news_fingerprint = ? AND agent_id != ? AND cooldown_until > ?""",
                (fingerprint, exclude_agent_id, now.isoformat()),
            )
            row = await cursor.fetchone()
            if not row:
                return "clear"
            created_at = datetime.fromisoformat(row[0])
            elapsed = (now - created_at).total_seconds() / 60.0
            if elapsed < HARD_BLOCK_MINUTES:
                return "blocked"
            return "stagger"
    except Exception:
        logger.exception("news_cooldown.check: failed for fingerprint=%s", fingerprint)
        return "clear"


async def get_active_news_fingerprints(db_path: str, *, exclude_agent_id: str) -> set[str]:
    """Get all active news fingerprints from other agents (for bulk scoring)."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "SELECT news_fingerprint FROM news_cooldowns WHERE cooldown_until > ? AND agent_id != ?",
                (now, exclude_agent_id),
            )
            rows = await cursor.fetchall()
            return {row[0] for row in rows}
    except Exception:
        logger.exception("news_cooldown.get_active: failed")
        return set()


async def cleanup_expired_news_cooldowns(db_path: str) -> int:
    """Remove expired news cooldowns. Returns count of deleted rows."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "DELETE FROM news_cooldowns WHERE cooldown_until < ?",
                (now,),
            )
            await db.commit()
            deleted = cursor.rowcount
            if deleted:
                logger.info("news_cooldown.cleanup: removed %d expired cooldowns", deleted)
            return deleted
    except Exception:
        logger.exception("news_cooldown.cleanup: failed")
        return 0
