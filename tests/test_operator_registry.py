"""Tests for operator registry: config scanning and DB sync."""

import pytest
from pathlib import Path

from src.operator.models import AgentState
from src.operator.registry import scan_agent_configs, sync_registry
from src.operator.state_store import init_operator_tables, get_agent_state, load_all_agents, update_agent_state, upsert_agent
from src.operator.models import AgentSlot


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_operator_tables(path)
    return path


def test_scan_finds_configs():
    configs = scan_agent_configs()
    agent_ids = [s.agent_id for s in configs]
    assert "example_macro" in agent_ids


def test_scan_skips_example_files():
    configs = scan_agent_configs()
    config_paths = [s.config_path for s in configs]
    assert not any("example" in p for p in config_paths)


@pytest.mark.asyncio
async def test_sync_inserts_new_agents(db_path):
    slots = await sync_registry(db_path)
    assert len(slots) >= 1
    agent = await get_agent_state(db_path, "example_macro")
    assert agent is not None
    assert agent["state"] == "idle"


@pytest.mark.asyncio
async def test_sync_preserves_existing_state(db_path):
    # First sync
    await sync_registry(db_path)
    # Change state
    await update_agent_state(db_path, "example_macro", AgentState.WORKING)
    # Re-sync should NOT reset state
    await sync_registry(db_path)
    agent = await get_agent_state(db_path, "example_macro")
    assert agent["state"] == "working"


@pytest.mark.asyncio
async def test_sync_disables_removed_agents(db_path):
    # Insert a fake agent that has no config file
    fake = AgentSlot(
        agent_id="ghost_agent",
        config_path="config/active_agent.ghost.yaml",
        profile_serial="99",
        adspower_user_id="ghost",
    )
    await upsert_agent(db_path, fake)
    # Sync — ghost_agent should be disabled
    await sync_registry(db_path)
    agent = await get_agent_state(db_path, "ghost_agent")
    assert agent["state"] == "disabled"
