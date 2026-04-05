"""Tests for news cooldown coordination."""

import sqlite3
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from src.runtime.news_cooldown import (
    _news_fingerprint,
    check_news_cooldown,
    cleanup_expired_news_cooldowns,
    record_news_cooldown,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_cooldowns (
            id INTEGER PRIMARY KEY,
            agent_id TEXT NOT NULL,
            news_fingerprint TEXT NOT NULL UNIQUE,
            source_url TEXT,
            headline_hash TEXT,
            created_at TIMESTAMP NOT NULL,
            cooldown_until TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return path


def test_news_fingerprint_deterministic():
    fp1 = _news_fingerprint("https://example.com/article", None)
    fp2 = _news_fingerprint("https://example.com/article", None)
    assert fp1 == fp2


def test_news_fingerprint_different_urls():
    fp1 = _news_fingerprint("https://a.com", None)
    fp2 = _news_fingerprint("https://b.com", None)
    assert fp1 != fp2


@pytest.mark.asyncio
async def test_record_and_check_blocked(db_path):
    await record_news_cooldown(db_path, agent_id="agent_a", source_url="https://news.com/btc")
    result = await check_news_cooldown(db_path, exclude_agent_id="agent_b", source_url="https://news.com/btc")
    assert result == "blocked"


@pytest.mark.asyncio
async def test_check_after_hard_block_returns_stagger(db_path):
    now = datetime.now(timezone.utc)
    created = now - timedelta(minutes=35)
    cooldown_until = created + timedelta(minutes=90)
    fingerprint = _news_fingerprint("https://news.com/eth", None)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO news_cooldowns
               (agent_id, news_fingerprint, source_url, headline_hash, created_at, cooldown_until)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("agent_a", fingerprint, "https://news.com/eth", None,
             created.isoformat(), cooldown_until.isoformat()),
        )
        await db.commit()

    result = await check_news_cooldown(db_path, exclude_agent_id="agent_b", source_url="https://news.com/eth")
    assert result == "stagger"


@pytest.mark.asyncio
async def test_check_after_full_expiry_returns_clear(db_path):
    now = datetime.now(timezone.utc)
    created = now - timedelta(minutes=100)
    cooldown_until = created + timedelta(minutes=90)
    fingerprint = _news_fingerprint("https://old.com/sol", None)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO news_cooldowns
               (agent_id, news_fingerprint, source_url, headline_hash, created_at, cooldown_until)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("agent_a", fingerprint, "https://old.com/sol", None,
             created.isoformat(), cooldown_until.isoformat()),
        )
        await db.commit()

    result = await check_news_cooldown(db_path, exclude_agent_id="agent_b", source_url="https://old.com/sol")
    assert result == "clear"


@pytest.mark.asyncio
async def test_cleanup_expired_news_cooldowns(db_path):
    now = datetime.now(timezone.utc)
    expired = now - timedelta(minutes=5)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO news_cooldowns
               (agent_id, news_fingerprint, source_url, headline_hash, created_at, cooldown_until)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("agent_a", "fp_old", None, None, expired.isoformat(), expired.isoformat()),
        )
        await db.commit()

    deleted = await cleanup_expired_news_cooldowns(db_path)
    assert deleted == 1


@pytest.mark.asyncio
async def test_same_agent_not_blocked(db_path):
    await record_news_cooldown(db_path, agent_id="agent_a", source_url="https://news.com/btc")
    result = await check_news_cooldown(db_path, exclude_agent_id="agent_a", source_url="https://news.com/btc")
    assert result == "clear"
