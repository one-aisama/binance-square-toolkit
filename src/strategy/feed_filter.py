"""Feed filter — removes spam and low-quality posts before agent sees them.

Applied to results from sdk.get_feed_posts() which returns:
[{post_id: str, author: str, text: str, like_count: int, author_followers: int|None}, ...]
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("bsq.strategy.feed_filter")

SPAM_KEYWORDS: list[str] = [
    "giveaway", "airdrop", "copy trading", "click here", "free tokens",
    "gift", "send your", "comment your uid", "join telegram", "join discord",
]

_EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002702-\U000027B0\U0000FE00-\U0000FE0F"
    r"\U0000200D\U00002600-\U000026FF\U00002700-\U000027BF]+",
)
_PROMO_PATTERN = re.compile(r"(?:\$[A-Z]{2,10}|#[A-Za-z]{2,10}).*?(?:100x|moon|\U0001F680)", re.I)


@dataclass
class FilterResult:
    posts: list[dict] = field(default_factory=list)
    need_more: bool = False
    removed_count: int = 0
    removal_reasons: dict = field(default_factory=dict)


def is_spam(text: str) -> bool:
    """Check if text is spam by keywords or token promo patterns."""
    lower = text.lower()
    for kw in SPAM_KEYWORDS:
        if kw in lower:
            return True
    if _PROMO_PATTERN.search(text):
        return True
    return False


def filter_feed(posts: list[dict]) -> FilterResult:
    """Filter feed posts, removing spam and low-quality content."""
    passed: list[dict] = []
    reasons: dict[str, int] = {}

    for post in posts:
        text = post.get("text", "")
        like_count = post.get("like_count", 0)
        followers = post.get("author_followers")

        # 1 — spam filter
        if is_spam(text):
            reasons["spam"] = reasons.get("spam", 0) + 1
            continue

        stripped_of_emoji = _EMOJI_PATTERN.sub("", text).strip()
        if len(stripped_of_emoji) < 30:
            reasons["spam"] = reasons.get("spam", 0) + 1
            continue

        # 2 — low engagement
        if like_count < 5:
            reasons["low_engagement"] = reasons.get("low_engagement", 0) + 1
            continue

        # 3 — too short
        if len(text.strip()) < 50:
            reasons["too_short"] = reasons.get("too_short", 0) + 1
            continue

        # 4 — author followers (optional)
        if followers is not None and followers < 500:
            reasons["low_followers"] = reasons.get("low_followers", 0) + 1
            continue

        passed.append(post)

    removed = len(posts) - len(passed)
    result = FilterResult(
        posts=passed,
        need_more=len(passed) < 3,
        removed_count=removed,
        removal_reasons=reasons,
    )
    logger.info(
        "feed_filter: %d/%d passed, removed=%s",
        len(passed), len(posts), reasons,
    )
    return result
