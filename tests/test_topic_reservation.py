"""Tests for live topic reservation system."""

import pytest

from src.runtime.topic_reservation import (
    build_reservation_key,
    cleanup_expired,
    confirm_reservation,
    get_active_reservations,
    release_all_agent_reservations,
    release_reservation,
    reserve_topic,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary SQLite database with the topic_reservations table."""
    path = str(tmp_path / "test.db")
    import sqlite3
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_reservations (
            id INTEGER PRIMARY KEY,
            agent_id TEXT NOT NULL,
            reservation_key TEXT NOT NULL UNIQUE,
            post_family TEXT NOT NULL,
            primary_coin TEXT,
            angle TEXT,
            source_fingerprint TEXT,
            reserved_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return path


def test_build_reservation_key_with_all_fields():
    key = build_reservation_key(coin="SOL", angle="rotation", source_url="https://example.com/news/123")
    assert key.startswith("SOL:rotation:")
    assert len(key.split(":")) == 3


def test_build_reservation_key_without_source():
    key = build_reservation_key(coin="BTC", angle="macro")
    assert key == "BTC:macro:nosrc"


def test_build_reservation_key_none_coin():
    key = build_reservation_key(coin=None, angle="general")
    assert key.startswith("NONE:general:")


def test_build_reservation_key_deterministic():
    key1 = build_reservation_key(coin="ETH", angle="ta", source_url="https://x.com/post/1")
    key2 = build_reservation_key(coin="ETH", angle="ta", source_url="https://x.com/post/1")
    assert key1 == key2


def test_build_reservation_key_different_sources():
    key1 = build_reservation_key(coin="SOL", angle="rotation", source_url="https://a.com/1")
    key2 = build_reservation_key(coin="SOL", angle="rotation", source_url="https://b.com/2")
    assert key1 != key2


@pytest.mark.asyncio
async def test_reserve_topic_success(db_path):
    result = await reserve_topic(
        db_path,
        agent_id="example_macro",
        reservation_key="SOL:rotation:abc12345",
        post_family="news_reaction",
        primary_coin="SOL",
        angle="rotation",
    )
    assert result is True


@pytest.mark.asyncio
async def test_reserve_topic_conflict(db_path):
    key = "BTC:macro:def67890"
    first = await reserve_topic(
        db_path, agent_id="example_macro", reservation_key=key, post_family="market_chart",
    )
    second = await reserve_topic(
        db_path, agent_id="example_altcoin", reservation_key=key, post_family="market_chart",
    )
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_same_agent_cannot_double_reserve(db_path):
    key = "ETH:ta:aaa11111"
    first = await reserve_topic(
        db_path, agent_id="example_macro", reservation_key=key, post_family="market_chart",
    )
    second = await reserve_topic(
        db_path, agent_id="example_macro", reservation_key=key, post_family="market_chart",
    )
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_release_then_reserve(db_path):
    key = "SOL:rotation:bbb22222"
    await reserve_topic(db_path, agent_id="example_macro", reservation_key=key, post_family="news_reaction")
    await release_reservation(db_path, agent_id="example_macro", reservation_key=key)
    result = await reserve_topic(db_path, agent_id="example_altcoin", reservation_key=key, post_family="news_reaction")
    assert result is True


@pytest.mark.asyncio
async def test_confirm_deletes_reservation(db_path):
    """After confirm (post published), the key is freed for future use."""
    key = "BTC:macro:ccc33333"
    await reserve_topic(db_path, agent_id="example_macro", reservation_key=key, post_family="market_chart")
    await confirm_reservation(db_path, agent_id="example_macro", reservation_key=key)

    # Key is now free — another agent (or same agent later) can reserve it
    result = await reserve_topic(db_path, agent_id="example_altcoin", reservation_key=key, post_family="market_chart")
    assert result is True


@pytest.mark.asyncio
async def test_repeated_confirm_then_reserve(db_path):
    """Repeated publish of same topic key works without UNIQUE conflicts."""
    key = "BTC:macro:nosrc"
    # First cycle
    await reserve_topic(db_path, agent_id="example_macro", reservation_key=key, post_family="market_chart")
    await confirm_reservation(db_path, agent_id="example_macro", reservation_key=key)
    # Second cycle — same key
    result = await reserve_topic(db_path, agent_id="example_macro", reservation_key=key, post_family="market_chart")
    assert result is True
    await confirm_reservation(db_path, agent_id="example_macro", reservation_key=key)
    # Third cycle — different agent, same key
    result = await reserve_topic(db_path, agent_id="example_altcoin", reservation_key=key, post_family="market_chart")
    assert result is True


@pytest.mark.asyncio
async def test_cleanup_expired(db_path):
    import aiosqlite
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    expired = now - timedelta(hours=3)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO topic_reservations
               (agent_id, reservation_key, post_family, reserved_at, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("example_macro", "OLD:macro:expired1", "market_chart", expired.isoformat(), expired.isoformat()),
        )
        await db.commit()

    deleted = await cleanup_expired(db_path)
    assert deleted == 1

    active = await get_active_reservations(db_path, exclude_agent_id="example_altcoin")
    assert len(active) == 0


@pytest.mark.asyncio
async def test_get_active_reservations_excludes_own(db_path):
    await reserve_topic(db_path, agent_id="example_macro", reservation_key="SOL:rotation:own1", post_family="news_reaction")
    await reserve_topic(db_path, agent_id="example_altcoin", reservation_key="BTC:macro:own2", post_family="market_chart")

    example_macro_sees = await get_active_reservations(db_path, exclude_agent_id="example_macro")
    example_altcoin_sees = await get_active_reservations(db_path, exclude_agent_id="example_altcoin")

    assert len(example_macro_sees) == 1
    assert example_macro_sees[0]["agent_id"] == "example_altcoin"
    assert len(example_altcoin_sees) == 1
    assert example_altcoin_sees[0]["agent_id"] == "example_macro"


@pytest.mark.asyncio
async def test_release_all_agent_reservations(db_path):
    await reserve_topic(db_path, agent_id="example_macro", reservation_key="A:macro:r1", post_family="market_chart")
    await reserve_topic(db_path, agent_id="example_macro", reservation_key="B:ta:r2", post_family="market_chart")
    await reserve_topic(db_path, agent_id="example_altcoin", reservation_key="C:rotation:r3", post_family="news_reaction")

    await release_all_agent_reservations(db_path, agent_id="example_macro")

    active = await get_active_reservations(db_path, exclude_agent_id="nobody")
    assert len(active) == 1
    assert active[0]["agent_id"] == "example_altcoin"


@pytest.mark.asyncio
async def test_confirmed_reservations_not_returned_as_active(db_path):
    key = "SOL:rotation:pub1"
    await reserve_topic(db_path, agent_id="example_macro", reservation_key=key, post_family="news_reaction")
    await confirm_reservation(db_path, agent_id="example_macro", reservation_key=key)

    active = await get_active_reservations(db_path, exclude_agent_id="example_altcoin")
    assert len(active) == 0
