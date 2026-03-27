"""Crypto news fetcher via RSS feeds and article scraping."""

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger("bsq.content")

RSS_FEEDS = [
    {"source": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"source": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
    {"source": "Decrypt", "url": "https://decrypt.co/feed"},
]


async def get_crypto_news(limit: int = 10) -> list[dict[str, Any]]:
    """Fetch latest crypto news headlines from RSS feeds.

    No API key required. Sources: CoinDesk, CoinTelegraph, Decrypt.

    Args:
        limit: Total number of articles to return. Default: 10

    Returns:
        List of dicts sorted by date (newest first):
        [{title, source, url, published_at}]
        published_at is ISO 8601 string in UTC.
    """
    all_items: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for feed in RSS_FEEDS:
            try:
                resp = await client.get(feed["url"])
                resp.raise_for_status()
                items = _parse_rss(resp.text, feed["source"])
                all_items.extend(items)
            except Exception as e:
                logger.warning(f"RSS fetch failed for {feed['source']}: {e}")

    # Sort newest first
    all_items.sort(key=lambda x: x["published_at"], reverse=True)
    result = all_items[:limit]
    logger.info(f"Fetched {len(result)} news items from {len(RSS_FEEDS)} feeds")
    return result


async def get_article_content(url: str) -> dict[str, Any]:
    """Fetch full text of a news article by URL.

    Agent calls this when a headline looks interesting enough
    to write a deep post or article about.

    Args:
        url: Article URL from get_crypto_news()

    Returns:
        {title, text, url, published_at}
        text is cleaned plain text (no HTML tags).
    """
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RSS reader)"},
        )
        resp.raise_for_status()

    title, text, published_at = _extract_article(resp.text, url)
    logger.info(f"Fetched article: {title[:60]}... ({len(text)} chars)")
    return {"title": title, "text": text, "url": url, "published_at": published_at}


# ---- Internal helpers ----

def _parse_rss(xml: str, source: str) -> list[dict[str, Any]]:
    """Parse RSS XML and extract items."""
    items = []
    # Split on <item> blocks
    for block in re.split(r"<item[>\s]", xml)[1:]:
        title = _extract_tag(block, "title")
        link = _extract_tag(block, "link") or _extract_tag(block, "guid")
        pub_date = _extract_tag(block, "pubDate")

        if not title or not link:
            continue

        published_at = _parse_date(pub_date)
        items.append({
            "title": _clean_text(title),
            "source": source,
            "url": link.strip(),
            "published_at": published_at,
        })
    return items


def _extract_tag(text: str, tag: str) -> str:
    """Extract content from XML tag (handles CDATA)."""
    match = re.search(rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _clean_text(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return text.strip()


def _parse_date(date_str: str) -> str:
    """Parse RSS date to ISO 8601 UTC string. Returns empty string on failure."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _extract_article(html: str, url: str) -> tuple[str, str, str]:
    """Extract title, body text, and published date from article HTML."""
    # Title from <title> or <h1>
    title = _extract_tag(html, "title") or _extract_tag(html, "h1")
    title = _clean_text(title).split("|")[0].split(" - ")[0].strip()

    # Published date from common meta tags
    pub_match = re.search(
        r'(?:datePublished|article:published_time|pubdate)["\s:]+(["\']?)(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2})',
        html,
    )
    published_at = pub_match.group(2) if pub_match else ""

    # Body: extract paragraphs, skip navigation/footer noise
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
    cleaned = [_clean_text(p) for p in paragraphs]
    # Filter out short snippets (nav links, captions)
    body_parts = [p for p in cleaned if len(p) > 60]
    text = "\n\n".join(body_parts)

    return title, text, published_at
