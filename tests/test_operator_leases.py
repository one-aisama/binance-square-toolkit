"""Tests for operator lease management."""

import pytest
from datetime import datetime, timedelta, timezone

import aiosqlite

from src.operator.leases import (
    acquire_lease,
    cleanup_expired_leases,
    get_lease_holder,
    heartbeat_lease,
    release_lease,
)
from src.operator.state_store import init_operator_tables


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_operator_tables(path)
    return path


@pytest.mark.asyncio
async def test_acquire_lease_success(db_path):
    result = await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    assert result is True


@pytest.mark.asyncio
async def test_acquire_lease_conflict(db_path):
    await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    result = await acquire_lease(db_path, agent_id="aisama", holder_id="op-2", ttl_sec=60)
    assert result is False


@pytest.mark.asyncio
async def test_same_holder_can_reacquire(db_path):
    await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    result = await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    assert result is True


@pytest.mark.asyncio
async def test_expired_lease_can_be_taken(db_path):
    # Insert expired lease manually
    now = datetime.now(timezone.utc)
    expired = now - timedelta(minutes=5)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO operator_leases (agent_id, holder_id, acquired_at, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            ("aisama", "op-dead", expired.isoformat(), expired.isoformat(), expired.isoformat()),
        )
        await db.commit()

    result = await acquire_lease(db_path, agent_id="aisama", holder_id="op-new", ttl_sec=60)
    assert result is True


@pytest.mark.asyncio
async def test_heartbeat_extends_ttl(db_path):
    await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    result = await heartbeat_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=120)
    assert result is True


@pytest.mark.asyncio
async def test_heartbeat_wrong_holder_fails(db_path):
    await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    result = await heartbeat_lease(db_path, agent_id="aisama", holder_id="op-wrong", ttl_sec=120)
    assert result is False


@pytest.mark.asyncio
async def test_release_lease(db_path):
    await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    await release_lease(db_path, agent_id="aisama", holder_id="op-1")
    holder = await get_lease_holder(db_path, "aisama")
    assert holder is None


@pytest.mark.asyncio
async def test_cleanup_expired(db_path):
    now = datetime.now(timezone.utc)
    expired = now - timedelta(minutes=5)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO operator_leases (agent_id, holder_id, acquired_at, heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            ("ghost", "op-dead", expired.isoformat(), expired.isoformat(), expired.isoformat()),
        )
        await db.commit()

    deleted = await cleanup_expired_leases(db_path)
    assert deleted == 1


@pytest.mark.asyncio
async def test_get_lease_holder(db_path):
    await acquire_lease(db_path, agent_id="aisama", holder_id="op-1", ttl_sec=60)
    holder = await get_lease_holder(db_path, "aisama")
    assert holder == "op-1"


@pytest.mark.asyncio
async def test_get_lease_holder_no_lease(db_path):
    holder = await get_lease_holder(db_path, "nonexistent")
    assert holder is None
