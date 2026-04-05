"""Tests for operator state store: SQLite persistence."""

import pytest
from datetime import datetime, timezone

from src.operator.models import AgentSlot, AgentState, OperatorRun, Priority
from src.operator.state_store import (
    get_agent_state,
    get_operator_metrics,
    get_recent_events,
    init_operator_tables,
    load_all_agents,
    record_event,
    record_run_end,
    record_run_start,
    update_agent_state,
    upsert_agent,
)


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_operator_tables(path)
    return path


def _slot(agent_id: str = "aisama") -> AgentSlot:
    return AgentSlot(
        agent_id=agent_id,
        config_path=f"config/active_agent.{agent_id}.yaml",
        profile_serial="1",
        adspower_user_id="abc",
    )


@pytest.mark.asyncio
async def test_upsert_and_load(db_path):
    await upsert_agent(db_path, _slot("aisama"))
    await upsert_agent(db_path, _slot("sweetdi"))
    agents = await load_all_agents(db_path)
    assert len(agents) == 2
    assert agents[0]["agent_id"] in ("aisama", "sweetdi")


@pytest.mark.asyncio
async def test_update_state_valid_transition(db_path):
    await upsert_agent(db_path, _slot())
    await update_agent_state(db_path, "aisama", AgentState.WORKING)
    agent = await get_agent_state(db_path, "aisama")
    assert agent["state"] == "working"


@pytest.mark.asyncio
async def test_update_state_invalid_transition_raises(db_path):
    await upsert_agent(db_path, _slot())
    with pytest.raises(ValueError, match="Invalid transition"):
        await update_agent_state(db_path, "aisama", AgentState.COOLDOWN)


@pytest.mark.asyncio
async def test_update_state_increment_cycle(db_path):
    await upsert_agent(db_path, _slot())
    await update_agent_state(db_path, "aisama", AgentState.WORKING)
    await update_agent_state(db_path, "aisama", AgentState.COOLDOWN, increment_cycle=True, reset_errors=True)
    agent = await get_agent_state(db_path, "aisama")
    assert agent["cycle_count"] == 1
    assert agent["consecutive_errors"] == 0


@pytest.mark.asyncio
async def test_record_run(db_path):
    run = OperatorRun(agent_id="aisama")
    await record_run_start(db_path, run)
    await record_run_end(db_path, run.run_id, status="completed", action_count=5, success_count=4)


@pytest.mark.asyncio
async def test_record_event_and_retrieve(db_path):
    await record_event(db_path, "test_event", "aisama", "something happened")
    events = await get_recent_events(db_path, limit=5)
    assert len(events) == 1
    assert events[0]["event_type"] == "test_event"


@pytest.mark.asyncio
async def test_metrics_empty_db(db_path):
    metrics = await get_operator_metrics(db_path)
    assert metrics["active_agents"] == 0
    assert metrics["total_runs"] == 0
