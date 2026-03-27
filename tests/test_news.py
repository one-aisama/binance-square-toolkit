"""Tests for crypto news fetcher."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.content.news import get_crypto_news, get_article_content, _parse_rss, _clean_text


SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>CoinDesk</title>
<item>
  <title><![CDATA[Bitcoin Hits $100K as Institutional Demand Surges]]></title>
  <link>https://coindesk.com/markets/2026/btc-100k</link>
  <pubDate>Fri, 28 Mar 2026 12:00:00 +0000</pubDate>
</item>
<item>
  <title><![CDATA[Ethereum ETF Sees Record Inflows]]></title>
  <link>https://coindesk.com/markets/2026/eth-etf</link>
  <pubDate>Fri, 28 Mar 2026 10:00:00 +0000</pubDate>
</item>
</channel>
</rss>"""

SAMPLE_ARTICLE_HTML = """<html>
<head><title>Bitcoin Analysis | CoinDesk</title></head>
<body>
<h1>Bitcoin Analysis</h1>
<p>Bitcoin has been showing strong momentum above the $90,000 support level in recent weeks.</p>
<p>Analysts point to increasing institutional adoption as the primary driver of current prices.</p>
<p>The RSI indicator suggests the asset is not yet in overbought territory, leaving room for further gains.</p>
<p>Short.</p>
</body>
</html>"""


def test_parse_rss_extracts_items():
    items = _parse_rss(SAMPLE_RSS, "CoinDesk")
    assert len(items) == 2
    assert items[0]["title"] == "Bitcoin Hits $100K as Institutional Demand Surges"
    assert items[0]["source"] == "CoinDesk"
    assert "coindesk.com" in items[0]["url"]


def test_parse_rss_empty_feed():
    items = _parse_rss("<rss><channel></channel></rss>", "Test")
    assert items == []


def test_clean_text_strips_html():
    result = _clean_text("<p>Hello &amp; <b>world</b></p>")
    assert result == "Hello & world"


async def test_get_crypto_news_returns_sorted():
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_RSS
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.news.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_crypto_news(limit=5)

    assert len(result) <= 5
    # Sorted newest first
    if len(result) >= 2:
        assert result[0]["published_at"] >= result[1]["published_at"]


async def test_get_crypto_news_limit():
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_RSS
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.news.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_crypto_news(limit=1)

    assert len(result) == 1


async def test_get_crypto_news_failed_feed_skipped():
    """If one feed fails, others still return results."""
    mock_ok = MagicMock()
    mock_ok.text = SAMPLE_RSS
    mock_ok.raise_for_status = MagicMock()

    call_count = 0

    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("timeout")
        return mock_ok

    import httpx
    with patch("src.content.news.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_crypto_news(limit=10)

    assert len(result) > 0  # Got results from working feeds


async def test_get_article_content_extracts_text():
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_ARTICLE_HTML
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.news.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_article_content("https://coindesk.com/btc-analysis")

    assert result["title"] == "Bitcoin Analysis"
    assert "momentum" in result["text"]
    assert "institutional" in result["text"]
    # Short paragraph filtered out
    assert "Short." not in result["text"]
    assert result["url"] == "https://coindesk.com/btc-analysis"
