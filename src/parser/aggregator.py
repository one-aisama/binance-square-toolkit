"""Trend aggregation — rank topics by engagement score."""

import logging
from collections import Counter
from src.parser.models import ParsedPost, Topic

logger = logging.getLogger("bsq.parser")


def compute_engagement(post: ParsedPost) -> float:
    """Compute engagement score: views * 0.3 + likes * 0.5 + comments * 0.2"""
    return post.view_count * 0.3 + post.like_count * 0.5 + post.comment_count * 0.2


def rank_topics(posts: list[ParsedPost], top_n: int = 10) -> list[Topic]:
    """Aggregate posts by hashtag, rank by total engagement score.

    Groups posts by their hashtags, sums engagement per hashtag,
    and returns top N topics sorted by engagement score.
    """
    if not posts:
        return []

    # Count hashtag frequency and accumulate engagement
    hashtag_engagement: dict[str, float] = Counter()
    hashtag_posts: dict[str, int] = Counter()
    hashtag_coins: dict[str, set[str]] = {}

    for post in posts:
        engagement = compute_engagement(post)
        tags = post.hashtags if post.hashtags else ["_untagged"]

        for tag in tags:
            tag_lower = tag.lower().strip("#")
            if not tag_lower:
                continue
            hashtag_engagement[tag_lower] += engagement
            hashtag_posts[tag_lower] += 1
            if tag_lower not in hashtag_coins:
                hashtag_coins[tag_lower] = set()
            for coin in post.trading_pairs:
                hashtag_coins[tag_lower].add(coin)

    # Build topics and sort by engagement
    topics = []
    for tag, score in hashtag_engagement.most_common(top_n):
        if tag == "_untagged":
            continue
        topics.append(Topic(
            name=tag,
            hashtags=[tag],
            coins=sorted(hashtag_coins.get(tag, set())),
            engagement_score=round(score, 2),
            post_count=hashtag_posts[tag],
        ))

    logger.info(f"Ranked {len(topics)} topics from {len(posts)} posts")
    return topics[:top_n]
