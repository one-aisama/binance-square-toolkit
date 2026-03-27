"""Tests for content engine."""

import pytest
from unittest.mock import AsyncMock, patch

from src.db.database import init_db
from src.content.generator import ContentGenerator
from src.content.publisher import ContentPublisher


# ---- Generator tests ----

def test_build_system_prompt():
    gen = ContentGenerator("anthropic", "test-model", "fake-key")
    prompt = gen._build_system_prompt("analytical, data-heavy", ["defi", "yield"])
    assert "analytical" in prompt
    assert "defi" in prompt
    assert "Never use typical AI writing style" in prompt
    assert "let's dive into" in prompt  # Bad example present
    assert "GOOD examples" in prompt
    assert "$CASHTAGS" in prompt


def test_build_user_prompt_with_market_data():
    gen = ContentGenerator("anthropic", "test-model", "fake-key")
    topic = {"name": "bitcoin", "hashtags": ["bitcoin", "btc"], "coins": ["BTC"]}
    market = {"BTC": {"price": 65000.0, "change_24h": 2.5, "volume": 1000000}}
    prompt = gen._build_user_prompt(topic, market)
    assert "bitcoin" in prompt
    assert "$BTC" in prompt
    assert "65,000" in prompt
    assert "+2.5%" in prompt


def test_build_user_prompt_empty():
    gen = ContentGenerator("anthropic", "test-model", "fake-key")
    prompt = gen._build_user_prompt({}, {})
    assert "crypto" in prompt


# ---- Publisher tests ----

@pytest.fixture
async def publisher(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    mock_client = AsyncMock()
    return ContentPublisher(mock_client, db_path), db_path


async def test_queue_and_get_pending(publisher):
    pub, _ = publisher
    queue_id = await pub.queue_content("acc1", "Test post $BTC", ["bitcoin"], topic="bitcoin")
    assert queue_id > 0

    pending = await pub.get_pending("acc1")
    assert len(pending) == 1
    assert pending[0]["text"] == "Test post $BTC"


async def test_mark_published(publisher):
    pub, _ = publisher
    queue_id = await pub.queue_content("acc1", "Test")
    await pub.mark_published(queue_id, post_id="post_123")

    pending = await pub.get_pending("acc1")
    assert len(pending) == 0  # No longer pending


async def test_mark_failed(publisher):
    pub, _ = publisher
    queue_id = await pub.queue_content("acc1", "Test")
    await pub.mark_failed(queue_id, "API error")

    pending = await pub.get_pending("acc1")
    assert len(pending) == 0
