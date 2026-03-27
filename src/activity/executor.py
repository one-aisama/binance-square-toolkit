"""Activity engine — execute likes, comments, reposts."""

import random
import logging
from typing import Any

from src.bapi.client import BapiClient
from src.accounts.limiter import ActionLimiter
from src.activity.randomizer import HumanRandomizer
from src.activity.target_selector import TargetSelector
from src.activity.comment_gen import CommentGenerator

logger = logging.getLogger("bsq.activity")


class ActivityExecutor:
    """Execute activity cycles: likes, comments, reposts."""

    def __init__(
        self,
        client: BapiClient,
        limiter: ActionLimiter,
        randomizer: HumanRandomizer,
        target_selector: TargetSelector,
        comment_generator=None,  # ContentGenerator or similar
    ):
        self._client = client
        self._limiter = limiter
        self._randomizer = randomizer
        self._selector = target_selector
        self._comment_gen = comment_generator

    async def run_cycle(
        self,
        account_id: str,
        posts: list[dict],
        limits: dict[str, list[int]],
    ) -> dict[str, int]:
        """Execute one activity cycle.

        Args:
            account_id: Account performing actions
            posts: Posts to interact with (from parser)
            limits: Daily limits per action type {"like": [5,10], "comment": [2,4], "repost": [0,1]}

        Returns:
            Summary dict with counts: likes, comments, reposts, skipped, errors
        """
        results = {"likes": 0, "comments": 0, "reposts": 0, "skipped": 0, "errors": 0}

        # Likes
        like_count = random.randint(*limits["like"])
        like_targets = self._selector.select_like_targets(posts, like_count)
        for post in like_targets:
            if not await self._limiter.check_allowed(account_id, "like", limits["like"]):
                break
            if self._randomizer.should_skip():
                results["skipped"] += 1
                continue
            try:
                post_id = str(post.get("post_id", post.get("id", "")))
                await self._client.like_post(post_id)
                await self._limiter.record_action(account_id, "like", target_id=post_id)
                results["likes"] += 1
                await self._randomizer.human_delay()
            except NotImplementedError:
                logger.warning("like_post not yet implemented — skipping likes")
                break
            except Exception as e:
                logger.warning(f"Like failed: {e}")
                await self._limiter.record_action(account_id, "like", status="failed", error=str(e))
                results["errors"] += 1

        # Comments
        comment_count = random.randint(*limits["comment"])
        comment_targets = self._selector.select_comment_targets(posts, comment_count)
        for post in comment_targets:
            if not await self._limiter.check_allowed(account_id, "comment", limits["comment"]):
                break
            if self._randomizer.should_skip():
                results["skipped"] += 1
                continue
            try:
                post_id = str(post.get("post_id", post.get("id", "")))
                comment_text = "Interesting perspective."  # Default fallback
                if self._comment_gen:
                    post_text = post.get("text_preview", post.get("title", ""))
                    comment_text = await self._comment_gen.generate_comment(post_text)
                await self._client.comment_post(post_id, comment_text)
                await self._limiter.record_action(account_id, "comment", target_id=post_id)
                results["comments"] += 1
                await self._randomizer.human_delay()
            except NotImplementedError:
                logger.warning("comment_post not yet implemented — skipping comments")
                break
            except Exception as e:
                logger.warning(f"Comment failed: {e}")
                await self._limiter.record_action(account_id, "comment", status="failed", error=str(e))
                results["errors"] += 1

        # Reposts
        repost_count = random.randint(*limits["repost"])
        repost_targets = self._selector.select_repost_targets(posts, repost_count)
        for post in repost_targets:
            if not await self._limiter.check_allowed(account_id, "repost", limits["repost"]):
                break
            if self._randomizer.should_skip():
                results["skipped"] += 1
                continue
            try:
                post_id = str(post.get("post_id", post.get("id", "")))
                await self._client.repost(post_id)
                await self._limiter.record_action(account_id, "repost", target_id=post_id)
                results["reposts"] += 1
                await self._randomizer.human_delay()
            except NotImplementedError:
                logger.warning("repost not yet implemented — skipping reposts")
                break
            except Exception as e:
                logger.warning(f"Repost failed: {e}")
                await self._limiter.record_action(account_id, "repost", status="failed", error=str(e))
                results["errors"] += 1

        logger.info(
            f"Activity cycle for {account_id}: "
            f"{results['likes']}L {results['comments']}C {results['reposts']}R "
            f"({results['skipped']} skipped, {results['errors']} errors)"
        )
        return results


