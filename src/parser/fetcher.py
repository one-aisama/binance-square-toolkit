"""Trend fetcher — pulls data from bapi via BapiClient."""

import logging
from typing import Any

from src.bapi.client import BapiClient
from src.parser.models import ParsedPost

logger = logging.getLogger("bsq.parser")


def _extract_post(raw: dict[str, Any]) -> ParsedPost | None:
    """Extract a ParsedPost from raw bapi post data."""
    try:
        # bapi wraps post data in different structures
        # Try common paths
        content = raw.get("contentDetail", raw)

        post_id = str(content.get("id", content.get("contentId", "")))
        if not post_id:
            return None

        hashtags = []
        for h in content.get("hashtagList", []):
            if isinstance(h, dict):
                hashtags.append(h.get("name", h.get("hashtagName", "")))
            elif isinstance(h, str):
                hashtags.append(h)

        trading_pairs = []
        for t in content.get("tradingPairs", content.get("cashtagList", [])):
            if isinstance(t, dict):
                trading_pairs.append(t.get("symbol", t.get("name", "")))
            elif isinstance(t, str):
                trading_pairs.append(t)

        return ParsedPost(
            post_id=post_id,
            author_name=content.get("authorName", content.get("nickname", "")),
            author_id=str(content.get("authorId", content.get("userId", ""))),
            card_type=content.get("cardType", content.get("type", "")),
            view_count=int(content.get("viewCount", 0)),
            like_count=int(content.get("likeCount", 0)),
            comment_count=int(content.get("commentCount", 0)),
            share_count=int(content.get("shareCount", 0)),
            hashtags=hashtags,
            trading_pairs=trading_pairs,
            is_ai_created=bool(content.get("isCreatedByAI", False)),
            created_at=int(content.get("createTime", 0)),
            text_preview=str(content.get("title", content.get("text", "")))[:200],
        )
    except Exception as e:
        logger.debug(f"Failed to parse post: {e}")
        return None


class TrendFetcher:
    """Fetches posts and trends from bapi via BapiClient."""

    def __init__(self, client: BapiClient):
        self._client = client

    async def fetch_all(self, article_pages: int = 5, feed_pages: int = 5) -> list[ParsedPost]:
        """Pull articles + feed posts. Returns deduplicated list."""
        articles = await self._fetch_articles(pages=article_pages)
        feed = await self._fetch_feed(pages=feed_pages)

        # Deduplicate by post_id
        seen = set()
        result = []
        for post in articles + feed:
            if post.post_id not in seen:
                seen.add(post.post_id)
                result.append(post)

        logger.info(f"Fetched {len(result)} unique posts ({len(articles)} articles + {len(feed)} feed)")
        return result

    async def fetch_fear_greed(self) -> dict:
        """Get fear & greed index + popular coins."""
        return await self._client.get_fear_greed()

    async def fetch_hot_hashtags(self) -> list[dict]:
        """Get trending hashtags."""
        return await self._client.get_hot_hashtags()

    async def _fetch_articles(self, pages: int = 5) -> list[ParsedPost]:
        """Fetch top articles across multiple pages."""
        posts = []
        for page in range(1, pages + 1):
            try:
                raw_list = await self._client.get_top_articles(page=page)
                for raw in raw_list:
                    post = _extract_post(raw)
                    if post:
                        posts.append(post)
            except Exception as e:
                logger.warning(f"Failed to fetch articles page {page}: {e}")
        return posts

    async def _fetch_feed(self, pages: int = 5) -> list[ParsedPost]:
        """Fetch recommended feed across multiple pages."""
        posts = []
        for page in range(1, pages + 1):
            try:
                raw_list = await self._client.get_feed_recommend(page=page)
                for raw in raw_list:
                    post = _extract_post(raw)
                    if post:
                        posts.append(post)
            except Exception as e:
                logger.warning(f"Failed to fetch feed page {page}: {e}")
        return posts
