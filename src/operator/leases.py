"""Lease management: exclusive locks on agent profiles.

Prevents two operators (or two sessions) from running the same agent
simultaneously. Uses SQLite with TTL-based expiry for crash recovery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

logger = logging.getLogger("bsq.operator.leases")


async def acquire_lease(
    db_path: str,
    *,
    agent_id: str,
    holder_id: str,
    ttl_sec: int = 900,
) -> bool:
    """Attempt to acquire exclusive lease on an agent profile.

    Returns True if acquired, False if held by another holder.
    Re-acquires if the current lease is expired or held by same holder.
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_sec)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            # BEGIN IMMEDIATE to prevent TOCTOU race between SELECT and INSERT
            await db.execute("BEGIN IMMEDIATE")
            try:
                cursor = await db.execute(
                    "SELECT holder_id, expires_at FROM operator_leases WHERE agent_id = ?",
                    (agent_id,),
                )
                row = await cursor.fetchone()

                if row:
                    existing_holder, existing_expires = row[0], row[1]
                    existing_expires_dt = datetime.fromisoformat(existing_expires)
                    if existing_holder != holder_id and existing_expires_dt > now:
                        await db.execute("ROLLBACK")
                        logger.info("Lease for %s held by %s (expires %s)", agent_id, existing_holder, existing_expires)
                        return False

                await db.execute(
                    """INSERT INTO operator_leases (agent_id, holder_id, acquired_at, heartbeat_at, expires_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(agent_id) DO UPDATE SET
                         holder_id = excluded.holder_id,
                         acquired_at = excluded.acquired_at,
                         heartbeat_at = excluded.heartbeat_at,
                         expires_at = excluded.expires_at""",
                    (agent_id, holder_id, now.isoformat(), now.isoformat(), expires.isoformat()),
                )
                await db.commit()
            except Exception:
                await db.execute("ROLLBACK")
                raise
            logger.debug("Lease acquired for %s by %s (expires %s)", agent_id, holder_id, expires.isoformat())
            return True
    except Exception:
        logger.exception("acquire_lease failed for %s", agent_id)
        return False


async def heartbeat_lease(
    db_path: str,
    *,
    agent_id: str,
    holder_id: str,
    ttl_sec: int = 900,
) -> bool:
    """Extend lease TTL. Returns False if lease is not held by this holder."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_sec)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                """UPDATE operator_leases
                   SET heartbeat_at = ?, expires_at = ?
                   WHERE agent_id = ? AND holder_id = ?""",
                (now.isoformat(), expires.isoformat(), agent_id, holder_id),
            )
            await db.commit()
            return cursor.rowcount > 0
    except Exception:
        logger.exception("heartbeat_lease failed for %s", agent_id)
        return False


async def release_lease(db_path: str, *, agent_id: str, holder_id: str) -> None:
    """Release lease after cycle completion."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                "DELETE FROM operator_leases WHERE agent_id = ? AND holder_id = ?",
                (agent_id, holder_id),
            )
            await db.commit()
            logger.debug("Lease released for %s by %s", agent_id, holder_id)
    except Exception:
        logger.exception("release_lease failed for %s", agent_id)


async def cleanup_expired_leases(db_path: str) -> int:
    """Remove expired leases (operator crash recovery). Returns count deleted."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "DELETE FROM operator_leases WHERE expires_at < ?",
                (now,),
            )
            await db.commit()
            deleted = cursor.rowcount
            if deleted:
                logger.info("Cleaned up %d expired leases", deleted)
            return deleted
    except Exception:
        logger.exception("cleanup_expired_leases failed")
        return 0


async def get_lease_holder(db_path: str, agent_id: str) -> str | None:
    """Get current lease holder for an agent, or None if not leased."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "SELECT holder_id FROM operator_leases WHERE agent_id = ? AND expires_at > ?",
                (agent_id, now),
            )
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception:
        logger.exception("get_lease_holder failed for %s", agent_id)
        return None
