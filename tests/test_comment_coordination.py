"""Tests for comment coordination: SQLite-based comment locks."""

import sqlite3
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from src.runtime.comment_coordination import (
    cleanup_expired_comment_locks,
    get_locked_post_ids,
    lock_comment_target,
    release_agent_comment_locks,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comment_locks (
            id INTEGER PRIMARY KEY,
            agent_id TEXT NOT NULL,
            post_id TEXT NOT NULL UNIQUE,
            locked_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    return path


@pytest.mark.asyncio
async def test_lock_comment_target_success(db_path):
    result = await lock_comment_target(db_path, agent_id="agent_a", post_id="post_1")
    assert result is True


@pytest.mark.asyncio
async def test_lock_comment_target_already_taken(db_path):
    await lock_comment_target(db_path, agent_id="agent_a", post_id="post_1")
    result = await lock_comment_target(db_path, agent_id="agent_b", post_id="post_1")
    assert result is False


@pytest.mark.asyncio
async def test_get_locked_post_ids_excludes_self(db_path):
    await lock_comment_target(db_path, agent_id="agent_a", post_id="post_1")
    await lock_comment_target(db_path, agent_id="agent_b", post_id="post_2")

    locked = await get_locked_post_ids(db_path, exclude_agent_id="agent_a")
    assert "post_2" in locked
    assert "post_1" not in locked


@pytest.mark.asyncio
async def test_cleanup_expired_comment_locks(db_path):
    now = datetime.now(timezone.utc)
    expired = now - timedelta(minutes=5)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO comment_locks (agent_id, post_id, locked_at, expires_at) VALUES (?, ?, ?, ?)",
            ("agent_a", "old_post", expired.isoformat(), expired.isoformat()),
        )
        await db.commit()

    deleted = await cleanup_expired_comment_locks(db_path)
    assert deleted == 1

    locked = await get_locked_post_ids(db_path, exclude_agent_id="other")
    assert "old_post" not in locked


@pytest.mark.asyncio
async def test_release_agent_comment_locks(db_path):
    await lock_comment_target(db_path, agent_id="agent_a", post_id="post_1")
    await lock_comment_target(db_path, agent_id="agent_a", post_id="post_2")
    await release_agent_comment_locks(db_path, agent_id="agent_a")

    locked = await get_locked_post_ids(db_path, exclude_agent_id="other")
    assert len(locked) == 0
