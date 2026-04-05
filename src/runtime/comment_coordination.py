"""Comment coordination: prevent multiple agents from commenting on the same post.

Same proven pattern as topic_reservation.py — SQLite with short TTL.
Agents lock target posts before selecting them as comment targets.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

logger = logging.getLogger("bsq.comment_coord")

COMMENT_LOCK_TTL_MINUTES = 30


async def lock_comment_target(db_path: str, *, agent_id: str, post_id: str) -> bool:
    """Attempt to lock a post for commenting. Returns True if locked, False if taken."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=COMMENT_LOCK_TTL_MINUTES)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                """INSERT OR IGNORE INTO comment_locks
                   (agent_id, post_id, locked_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (agent_id, post_id, now.isoformat(), expires.isoformat()),
            )
            await db.commit()
            if cursor.rowcount == 0:
                return False
            return True
    except Exception:
        logger.exception("comment_coordination.lock: failed for post_id=%s", post_id)
        return False


async def get_locked_post_ids(db_path: str, *, exclude_agent_id: str) -> set[str]:
    """Get post IDs locked by other agents (still active)."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "SELECT post_id FROM comment_locks WHERE expires_at > ? AND agent_id != ?",
                (now, exclude_agent_id),
            )
            rows = await cursor.fetchall()
            return {row[0] for row in rows}
    except Exception:
        logger.exception("comment_coordination.get_locked: failed")
        return set()


async def cleanup_expired_comment_locks(db_path: str) -> int:
    """Remove expired comment locks. Returns count of deleted rows."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "DELETE FROM comment_locks WHERE expires_at < ?",
                (now,),
            )
            await db.commit()
            deleted = cursor.rowcount
            if deleted:
                logger.info("comment_coordination.cleanup: removed %d expired locks", deleted)
            return deleted
    except Exception:
        logger.exception("comment_coordination.cleanup: failed")
        return 0


async def release_agent_comment_locks(db_path: str, *, agent_id: str) -> None:
    """Release all comment locks for an agent (cleanup on cycle failure)."""
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                "DELETE FROM comment_locks WHERE agent_id = ?",
                (agent_id,),
            )
            await db.commit()
    except Exception:
        logger.exception("comment_coordination.release_all: failed for agent=%s", agent_id)
