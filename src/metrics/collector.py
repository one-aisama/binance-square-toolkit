"""MetricsCollector — delayed collection of engagement metrics.

Runs as a separate process (not part of agent session). For each action
older than 6h without an outcome, collects views/likes/replies via SDK.
"""

import logging
import time
from typing import Any

from src.metrics.store import MetricsStore
from src.sdk import BinanceSquareSDK

logger = logging.getLogger("bsq.metrics.collector")


class MetricsCollector:
    """Collects delayed engagement metrics for agent actions.

    For each action without an outcome (older than 6h), calls the
    appropriate SDK method and records the result in MetricsStore.
    """

    def __init__(self, store: MetricsStore, sdk: BinanceSquareSDK):
        self._store = store
        self._sdk = sdk

    async def collect_all(self, agent_id: str) -> dict[str, int]:
        """Collect outcomes for all pending actions.

        Args:
            agent_id: Agent identifier to collect metrics for.

        Returns:
            Summary dict: {"collected": N, "unavailable": M, "errors": K}
        """
        start_time = time.monotonic()
        summary = {"collected": 0, "unavailable": 0, "errors": 0}

        actions = await self._store.get_actions_without_outcomes(
            agent_id, min_hours_old=6
        )
        logger.info(
            f"MetricsCollector.collect_all: found {len(actions)} pending actions, "
            f"agent_id={agent_id}"
        )

        dispatch = {
            "post": self._collect_post_outcome,
            "article": self._collect_post_outcome,
            "comment": self._collect_comment_outcome,
            "quote_repost": self._collect_post_outcome,
            "like": self._collect_post_outcome,
            "follow": self._collect_follow_outcome,
        }

        for action in actions:
            action_type = action.get("action_type", "")
            handler = dispatch.get(action_type)

            if handler is None:
                logger.warning(
                    f"MetricsCollector.collect_all: unknown action_type={action_type}, "
                    f"action_id={action['id']}"
                )
                summary["errors"] += 1
                continue

            try:
                await handler(action)
                summary["collected"] += 1
            except _UnavailableError:
                summary["unavailable"] += 1
            except Exception as exc:
                logger.error(
                    f"MetricsCollector.collect_all: unexpected error for "
                    f"action_id={action['id']}, action_type={action_type}: {exc}"
                )
                summary["errors"] += 1

        elapsed = round(time.monotonic() - start_time, 2)
        logger.info(
            f"MetricsCollector.collect_all: done in {elapsed}s, "
            f"collected={summary['collected']}, unavailable={summary['unavailable']}, "
            f"errors={summary['errors']}"
        )
        return summary

    async def _collect_post_outcome(self, action: dict[str, Any]) -> None:
        """Collect engagement stats for a post/article/quote/like action."""
        action_id = action["id"]
        target_id = action.get("target_id")

        if not target_id:
            logger.warning(
                f"MetricsCollector._collect_post_outcome: no target_id, "
                f"action_id={action_id}"
            )
            await self._record_unavailable(action_id, "no target_id on action")
            raise _UnavailableError()

        try:
            stats = await self._sdk.get_post_stats(target_id)
        except Exception as exc:
            logger.warning(
                f"MetricsCollector._collect_post_outcome: SDK error, "
                f"action_id={action_id}, target_id={target_id}: {exc}"
            )
            await self._record_unavailable(action_id, str(exc))
            raise _UnavailableError() from exc

        await self._store.record_outcome(
            action_id=action_id,
            hours_after=6,
            views=stats.get("views"),
            likes=stats.get("likes"),
            comments=stats.get("comments"),
            quotes=stats.get("quotes"),
            status="collected",
        )
        logger.info(
            f"MetricsCollector._collect_post_outcome: recorded, "
            f"action_id={action_id}, views={stats.get('views')}, "
            f"likes={stats.get('likes')}"
        )

    async def _collect_comment_outcome(self, action: dict[str, Any]) -> None:
        """Collect outcome for a comment action.

        Fetches comments on the target post, finds our comment,
        checks if the post author replied and counts other replies.
        """
        action_id = action["id"]
        target_id = action.get("target_id")
        target_author = action.get("target_author")

        if not target_id:
            logger.warning(
                f"MetricsCollector._collect_comment_outcome: no target_id, "
                f"action_id={action_id}"
            )
            await self._record_unavailable(action_id, "no target_id on action")
            raise _UnavailableError()

        try:
            comments = await self._sdk.get_post_comments(target_id, limit=50)
        except Exception as exc:
            logger.warning(
                f"MetricsCollector._collect_comment_outcome: SDK error, "
                f"action_id={action_id}, target_id={target_id}: {exc}"
            )
            await self._record_unavailable(action_id, str(exc))
            raise _UnavailableError() from exc

        # Determine if post author replied after our comment
        author_replied = False
        other_replies = 0

        if target_author and comments:
            # Check if target_author appears anywhere in the comments list.
            # Position-based detection is unreliable (SDK returns author name,
            # not account ID), so we use presence as a proxy.
            author_replied = any(
                (c.get("author") == target_author or c.get("author_handle") == target_author)
                for c in comments
            )
            # Exclude our own comment from the count
            other_replies = max(0, len(comments) - 1)

        await self._store.record_outcome(
            action_id=action_id,
            hours_after=6,
            likes=None,  # SDK may not return likes on individual comments
            comments=len(comments) if comments else 0,
            author_replied=author_replied,
            other_replies=other_replies,
            status="collected",
        )
        logger.info(
            f"MetricsCollector._collect_comment_outcome: recorded, "
            f"action_id={action_id}, author_replied={author_replied}, "
            f"other_replies={other_replies}"
        )

    async def _collect_follow_outcome(self, action: dict[str, Any]) -> None:
        """Record follow outcome. No meaningful engagement metrics available yet."""
        await self._store.record_outcome(
            action_id=action["id"],
            hours_after=6,
            status="collected",
        )
        logger.info(
            f"MetricsCollector._collect_follow_outcome: recorded (no metrics), "
            f"action_id={action['id']}"
        )

    async def collect_profile_snapshot(self, agent_id: str) -> None:
        """Collect and save a daily profile snapshot via SDK.

        Args:
            agent_id: Agent identifier.
        """
        try:
            stats = await self._sdk.get_my_stats()
        except Exception as exc:
            logger.warning(
                f"MetricsCollector.collect_profile_snapshot: SDK error, "
                f"agent_id={agent_id}: {exc}"
            )
            return

        dashboard = stats.get("dashboard", {})

        await self._store.save_profile_snapshot(
            agent_id=agent_id,
            followers=stats.get("followers", 0),
            following=stats.get("following", 0),
            total_views=dashboard.get("views", 0),
            total_likes=dashboard.get("likes", 0),
        )
        logger.info(
            f"MetricsCollector.collect_profile_snapshot: saved, agent_id={agent_id}, "
            f"followers={stats.get('followers')}"
        )

    async def _record_unavailable(self, action_id: int, reason: str) -> None:
        """Helper to record an unavailable outcome."""
        await self._store.record_outcome(
            action_id=action_id,
            hours_after=6,
            status="unavailable",
            reason=reason,
        )


class _UnavailableError(Exception):
    """Internal signal that collection failed with status=unavailable."""
    pass
