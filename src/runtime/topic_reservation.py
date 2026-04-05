"""Live topic reservation to prevent simultaneous duplicate posts across agents.

Agents reserve a topic (coin + angle + source) BEFORE generating text.
If another agent already holds the reservation, the planner retries
with a different variation. Reservations expire after 2 hours as a
safety net against abandoned plans.

The table holds only active locks — no history. After successful
publication, the lock is DELETEd (post_registry.json keeps history).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

logger = logging.getLogger("bsq.reservation")

RESERVATION_TTL_HOURS = 2


def build_reservation_key(
    *,
    coin: str | None,
    angle: str | None,
    source_url: str | None = None,
    source_post_id: str | None = None,
) -> str:
    """Build a deterministic key from the topic's distinguishing fields."""
    coin_part = (coin or "NONE").upper()
    angle_part = (angle or "general").lower()
    raw_source = source_url or source_post_id or ""
    if raw_source:
        source_part = hashlib.md5(raw_source.encode()).hexdigest()[:8]
    else:
        source_part = "nosrc"
    return f"{coin_part}:{angle_part}:{source_part}"


async def reserve_topic(
    db_path: str,
    *,
    agent_id: str,
    reservation_key: str,
    post_family: str,
    primary_coin: str | None = None,
    angle: str | None = None,
    source_fingerprint: str | None = None,
) -> bool:
    """Attempt to reserve a topic. Returns True if reserved, False if already taken."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=RESERVATION_TTL_HOURS)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                """INSERT OR IGNORE INTO topic_reservations
                   (agent_id, reservation_key, post_family, primary_coin, angle,
                    source_fingerprint, reserved_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, reservation_key, post_family, primary_coin, angle,
                 source_fingerprint, now.isoformat(), expires.isoformat()),
            )
            await db.commit()
            if cursor.rowcount == 0:
                logger.info(
                    "topic_reservation.reserve_topic: key=%s already held, agent=%s",
                    reservation_key, agent_id,
                )
                return False
            logger.info(
                "topic_reservation.reserve_topic: reserved key=%s for agent=%s, expires=%s",
                reservation_key, agent_id, expires.isoformat(),
            )
            return True
    except Exception:
        logger.exception("topic_reservation.reserve_topic: failed for key=%s", reservation_key)
        return False


async def release_reservation(db_path: str, *, agent_id: str, reservation_key: str) -> None:
    """Release a reservation (plan rejected or retry needed)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                "DELETE FROM topic_reservations WHERE agent_id = ? AND reservation_key = ?",
                (agent_id, reservation_key),
            )
            await db.commit()
            logger.debug("topic_reservation.release: key=%s agent=%s", reservation_key, agent_id)
    except Exception:
        logger.exception("topic_reservation.release: failed for key=%s", reservation_key)


async def confirm_reservation(db_path: str, *, agent_id: str, reservation_key: str) -> None:
    """Remove reservation after successful publication (lock no longer needed)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                "DELETE FROM topic_reservations WHERE agent_id = ? AND reservation_key = ?",
                (agent_id, reservation_key),
            )
            await db.commit()
            logger.debug("topic_reservation.confirm: key=%s agent=%s (deleted)", reservation_key, agent_id)
    except Exception:
        logger.exception("topic_reservation.confirm: failed for key=%s", reservation_key)


async def cleanup_expired(db_path: str) -> int:
    """Remove expired reservations. Returns count of deleted rows."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "DELETE FROM topic_reservations WHERE expires_at < ?",
                (now,),
            )
            await db.commit()
            deleted = cursor.rowcount
            if deleted:
                logger.info("topic_reservation.cleanup: removed %d expired reservations", deleted)
            return deleted
    except Exception:
        logger.exception("topic_reservation.cleanup: failed")
        return 0


async def get_active_reservations(
    db_path: str,
    *,
    exclude_agent_id: str,
) -> list[dict[str, str | None]]:
    """Get all active reservations from other agents (for auditor overlap check)."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT agent_id, reservation_key, post_family, primary_coin, angle,
                          source_fingerprint, reserved_at, expires_at
                   FROM topic_reservations
                   WHERE expires_at > ? AND agent_id != ?""",
                (now, exclude_agent_id),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        logger.exception("topic_reservation.get_active: failed")
        return []


async def release_all_agent_reservations(db_path: str, *, agent_id: str) -> None:
    """Release all reservations for an agent (cleanup on cycle failure)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                "DELETE FROM topic_reservations WHERE agent_id = ?",
                (agent_id,),
            )
            await db.commit()
            logger.debug("topic_reservation.release_all: agent=%s", agent_id)
    except Exception:
        logger.exception("topic_reservation.release_all: failed for agent=%s", agent_id)
