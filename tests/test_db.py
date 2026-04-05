import pytest
import aiosqlite

from src.db.database import init_db


async def test_init_db_creates_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

    assert "credentials" in tables
    assert "actions_log" in tables
    assert "daily_stats" in tables
    assert "parsed_trends" in tables
    assert "parsed_posts" in tables
    assert "discovered_endpoints" in tables
    assert "post_tracker" in tables
    assert "topic_reservations" in tables


async def test_init_db_enables_wal(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        mode = (await cursor.fetchone())[0]

    assert mode == "wal"


async def test_init_db_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    await init_db(db_path)  # Should not raise

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        )
        count = (await cursor.fetchone())[0]

    assert count == 10


async def test_init_db_creates_indexes(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = [row[0] for row in await cursor.fetchall()]

    assert "idx_actions_account_type_time" in indexes
    assert "idx_parsed_posts_cycle" in indexes
    assert "idx_post_tracker_account" in indexes
    assert "idx_reservations_active" in indexes
