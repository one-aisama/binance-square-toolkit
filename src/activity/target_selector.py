"""Select posts to interact with."""

import random
import logging

logger = logging.getLogger("bsq.activity")


class TargetSelector:
    """Pick posts for likes/comments/reposts based on criteria."""

    def __init__(self, own_account_ids: set[str], min_views: int = 1000):
        self._own_ids = own_account_ids
        self._min_views = min_views

    def _filter_eligible(self, posts: list[dict]) -> list[dict]:
        """Filter posts: exclude own accounts, enforce min views."""
        eligible = []
        for post in posts:
            author_id = str(post.get("author_id", post.get("authorId", "")))
            if author_id in self._own_ids:
                continue
            views = int(post.get("view_count", post.get("viewCount", 0)))
            if views < self._min_views:
                continue
            eligible.append(post)
        return eligible

    def select_like_targets(self, posts: list[dict], count: int) -> list[dict]:
        """Select posts to like. Less strict — any eligible post works."""
        eligible = self._filter_eligible(posts)
        random.shuffle(eligible)
        return eligible[:count]

    def select_comment_targets(self, posts: list[dict], count: int) -> list[dict]:
        """Select posts to comment on. Prefer higher engagement."""
        eligible = self._filter_eligible(posts)
        # Sort by engagement (higher first), then sample
        eligible.sort(
            key=lambda p: int(p.get("view_count", p.get("viewCount", 0))),
            reverse=True,
        )
        # Take from top half to comment on higher-quality posts
        top_half = eligible[:max(len(eligible) // 2, count)]
        random.shuffle(top_half)
        return top_half[:count]

    def select_repost_targets(self, posts: list[dict], count: int) -> list[dict]:
        """Select posts to repost. Very selective — only top posts."""
        eligible = self._filter_eligible(posts)
        eligible.sort(
            key=lambda p: int(p.get("view_count", p.get("viewCount", 0))),
            reverse=True,
        )
        return eligible[:count]
