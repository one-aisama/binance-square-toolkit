"""Daily action limit enforcement."""

import random
import logging
from datetime import date

import aiosqlite

logger = logging.getLogger("bsq.accounts")


class ActionLimiter:
    """Tracks and enforces daily action limits per account."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    async def check_allowed(
        self, account_id: str, action_type: str, daily_limit: list[int]
    ) -> bool:
        """Check if action is allowed based on today's count vs random limit in range.

        Args:
            account_id: The account performing the action
            action_type: One of: post, like, comment, repost
            daily_limit: [min, max] range — a random limit within is chosen per day
        """
        today = date.today().isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM actions_log "
                "WHERE account_id = ? AND action_type = ? AND status = 'success' "
                "AND DATE(created_at, 'localtime') = ?",
                (account_id, action_type, today),
            )
            count = (await cursor.fetchone())[0]

        # Deterministic daily limit using hash of account+date+type
        seed = hash(f"{account_id}:{today}:{action_type}")
        rng = random.Random(seed)
        limit = rng.randint(daily_limit[0], daily_limit[1])

        allowed = count < limit
        if not allowed:
            logger.info(f"Limit reached for {account_id}/{action_type}: {count}/{limit}")
        return allowed

    async def record_action(
        self,
        account_id: str,
        action_type: str,
        target_id: str | None = None,
        status: str = "success",
        error: str | None = None,
    ) -> None:
        """Record an action in actions_log and update daily_stats."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO actions_log (account_id, action_type, target_id, status, error_message) "
                "VALUES (?, ?, ?, ?, ?)",
                (account_id, action_type, target_id, status, error),
            )

            # Upsert daily stats
            today = date.today().isoformat()
            col = f"{action_type}s_count" if action_type != "repost" else "reposts_count"

            await db.execute(
                f"INSERT INTO daily_stats (account_id, date, {col}) VALUES (?, ?, 1) "
                f"ON CONFLICT(account_id, date) DO UPDATE SET {col} = {col} + 1",
                (account_id, today),
            )

            if status == "failed":
                await db.execute(
                    "INSERT INTO daily_stats (account_id, date, errors_count) VALUES (?, ?, 1) "
                    "ON CONFLICT(account_id, date) DO UPDATE SET errors_count = errors_count + 1",
                    (account_id, today),
                )

            await db.commit()

    async def get_today_count(self, account_id: str, action_type: str) -> int:
        """Get today's count for a specific action type."""
        today = date.today().isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM actions_log "
                "WHERE account_id = ? AND action_type = ? AND status = 'success' "
                "AND DATE(created_at, 'localtime') = ?",
                (account_id, action_type, today),
            )
            return (await cursor.fetchone())[0]
