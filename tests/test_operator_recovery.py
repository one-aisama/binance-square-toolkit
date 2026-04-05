"""Tests for operator recovery: backoff, circuit breaker, AdsPower handling."""

import pytest
from datetime import datetime, timedelta, timezone

from src.operator.models import AgentSlot, AgentState, OperatorConfig
from src.operator.recovery import (
    apply_failure_backoff,
    check_stuck_agents,
    handle_adspower_down,
    handle_adspower_recovery,
)
from src.operator.state_store import (
    get_agent_state,
    init_operator_tables,
    update_agent_state,
    upsert_agent,
)


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_operator_tables(path)
    return path


def _slot(agent_id: str = "aisama", state: AgentState = AgentState.IDLE) -> AgentSlot:
    slot = AgentSlot(
        agent_id=agent_id,
        config_path=f"config/active_agent.{agent_id}.yaml",
        profile_serial="1",
        adspower_user_id="abc",
        state=state,
    )
    return slot


@pytest.mark.asyncio
async def test_backoff_increases_next_run(db_path):
    await upsert_agent(db_path, _slot())
    await update_agent_state(db_path, "aisama", AgentState.WORKING)
    await update_agent_state(db_path, "aisama", AgentState.FAILED, increment_error=True)

    config = OperatorConfig(error_backoff_minutes=10)
    result = await apply_failure_backoff(db_path, "aisama", config)
    assert result == "idle"

    agent = await get_agent_state(db_path, "aisama")
    assert agent["state"] == "idle"
    assert agent["next_run_at"] is not None


@pytest.mark.asyncio
async def test_circuit_breaker_disables_after_max_errors(db_path):
    await upsert_agent(db_path, _slot())
    # Simulate 3 consecutive errors
    for _ in range(3):
        await update_agent_state(db_path, "aisama", AgentState.WORKING)
        await update_agent_state(db_path, "aisama", AgentState.FAILED, increment_error=True)
        try:
            await update_agent_state(db_path, "aisama", AgentState.IDLE)
        except ValueError:
            pass

    config = OperatorConfig(max_consecutive_errors=3)
    result = await apply_failure_backoff(db_path, "aisama", config)
    assert result == "disabled"

    agent = await get_agent_state(db_path, "aisama")
    assert agent["state"] == "disabled"


@pytest.mark.asyncio
async def test_adspower_down_pauses_active_agents(db_path):
    await upsert_agent(db_path, _slot("aisama"))
    await upsert_agent(db_path, _slot("sweetdi"))
    await update_agent_state(db_path, "aisama", AgentState.WORKING)
    # sweetdi stays IDLE — should NOT be paused

    paused = await handle_adspower_down(db_path)
    assert paused == 1

    aisama = await get_agent_state(db_path, "aisama")
    assert aisama["state"] == "paused_adspower_down"
    sweetdi = await get_agent_state(db_path, "sweetdi")
    assert sweetdi["state"] == "idle"


@pytest.mark.asyncio
async def test_adspower_recovery_unpauses(db_path):
    await upsert_agent(db_path, _slot("aisama"))
    await update_agent_state(db_path, "aisama", AgentState.WORKING)
    await update_agent_state(db_path, "aisama", AgentState.PAUSED_ADSPOWER_DOWN)

    unpaused = await handle_adspower_recovery(db_path)
    assert unpaused == 1

    aisama = await get_agent_state(db_path, "aisama")
    assert aisama["state"] == "idle"


@pytest.mark.asyncio
async def test_stuck_agent_detection(db_path):
    await upsert_agent(db_path, _slot("aisama"))
    await update_agent_state(db_path, "aisama", AgentState.WORKING)

    # Manually set updated_at to 30 minutes ago (simulating stuck)
    import aiosqlite
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE operator_agents SET updated_at = ? WHERE agent_id = ?", (old_time, "aisama"))
        await db.commit()

    # Total working timeout = prepare(60) + author(60) + execute(60) = 180s
    # 2x safety = 360s. 30 min (1800s) >> 360s → stuck
    config = OperatorConfig(prepare_timeout_sec=60, author_timeout_sec=60, execute_timeout_sec=60)
    stuck = await check_stuck_agents(db_path, config)
    assert "aisama" in stuck

    aisama = await get_agent_state(db_path, "aisama")
    assert aisama["state"] == "failed"
