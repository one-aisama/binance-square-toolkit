"""Tests for parser: aggregator + fetcher."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.parser.models import ParsedPost, Topic
from src.parser.aggregator import rank_topics, compute_engagement
from src.parser.fetcher import TrendFetcher, _extract_post


# ---- Aggregator tests ----

def _make_post(post_id: str, views: int, likes: int, comments: int,
               hashtags: list[str] = None, coins: list[str] = None) -> ParsedPost:
    return ParsedPost(
        post_id=post_id,
        view_count=views,
        like_count=likes,
        comment_count=comments,
        hashtags=hashtags or [],
        trading_pairs=coins or [],
    )


def test_compute_engagement():
    post = _make_post("1", views=1000, likes=100, comments=50)
    score = compute_engagement(post)
    # 1000*0.3 + 100*0.5 + 50*0.2 = 300 + 50 + 10 = 360
    assert score == 360.0


def test_rank_topics_basic():
    posts = [
        _make_post("1", 1000, 100, 50, hashtags=["bitcoin"], coins=["BTC"]),
        _make_post("2", 2000, 200, 100, hashtags=["bitcoin"], coins=["BTC"]),
        _make_post("3", 500, 50, 20, hashtags=["ethereum"], coins=["ETH"]),
    ]
    topics = rank_topics(posts, top_n=10)
    assert len(topics) == 2
    assert topics[0].name == "bitcoin"  # Higher engagement
    assert topics[0].post_count == 2
    assert "BTC" in topics[0].coins
    assert topics[1].name == "ethereum"


def test_rank_topics_empty():
    assert rank_topics([]) == []


def test_rank_topics_top_n():
    posts = [_make_post(str(i), 100, 10, 5, hashtags=[f"tag{i}"]) for i in range(20)]
    topics = rank_topics(posts, top_n=5)
    assert len(topics) == 5


def test_rank_topics_case_insensitive():
    posts = [
        _make_post("1", 100, 10, 5, hashtags=["Bitcoin"]),
        _make_post("2", 100, 10, 5, hashtags=["bitcoin"]),
    ]
    topics = rank_topics(posts, top_n=10)
    assert len(topics) == 1
    assert topics[0].post_count == 2


# ---- Fetcher extraction tests ----

def test_extract_post_basic():
    raw = {
        "contentDetail": {
            "id": "123",
            "authorName": "Alice",
            "authorId": "456",
            "cardType": "BUZZ_SHORT",
            "viewCount": 1000,
            "likeCount": 50,
            "commentCount": 10,
            "shareCount": 5,
            "hashtagList": [{"name": "bitcoin"}],
            "tradingPairs": [{"symbol": "BTC"}],
            "isCreatedByAI": False,
            "createTime": 1700000000,
            "title": "Test post",
        }
    }
    post = _extract_post(raw)
    assert post is not None
    assert post.post_id == "123"
    assert post.author_name == "Alice"
    assert post.hashtags == ["bitcoin"]
    assert post.trading_pairs == ["BTC"]


def test_extract_post_flat():
    """Test extraction when data is not wrapped in contentDetail."""
    raw = {
        "id": "789",
        "nickname": "Bob",
        "viewCount": 500,
        "likeCount": 20,
    }
    post = _extract_post(raw)
    assert post is not None
    assert post.post_id == "789"
    assert post.author_name == "Bob"


def test_extract_post_missing_id():
    post = _extract_post({})
    assert post is None


# ---- Fetcher async tests ----

async def test_fetch_all_deduplicates():
    mock_client = AsyncMock()
    mock_client.get_top_articles = AsyncMock(return_value=[
        {"contentDetail": {"id": "1", "viewCount": 100}},
        {"contentDetail": {"id": "2", "viewCount": 200}},
    ])
    mock_client.get_feed_recommend = AsyncMock(return_value=[
        {"contentDetail": {"id": "2", "viewCount": 200}},  # duplicate
        {"contentDetail": {"id": "3", "viewCount": 300}},
    ])

    fetcher = TrendFetcher(mock_client)
    posts = await fetcher.fetch_all(article_pages=1, feed_pages=1)
    assert len(posts) == 3
    ids = {p.post_id for p in posts}
    assert ids == {"1", "2", "3"}


async def test_fetch_handles_errors():
    mock_client = AsyncMock()
    mock_client.get_top_articles = AsyncMock(side_effect=Exception("network error"))
    mock_client.get_feed_recommend = AsyncMock(return_value=[
        {"contentDetail": {"id": "1", "viewCount": 100}},
    ])

    fetcher = TrendFetcher(mock_client)
    posts = await fetcher.fetch_all(article_pages=1, feed_pages=1)
    assert len(posts) == 1  # Only feed posts, articles failed gracefully
