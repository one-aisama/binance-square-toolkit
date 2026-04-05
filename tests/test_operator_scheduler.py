"""Tests for operator scheduler: priority queue and slot management."""

import pytest
from datetime import datetime, timedelta, timezone

from src.operator.models import AgentSlot, AgentState, Priority
from src.operator.scheduler import OperatorScheduler, _agent_stagger_offset
from src.operator.state_store import init_operator_tables, upsert_agent, update_agent_state


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_operator_tables(path)
    return path


def _slot(agent_id: str, next_run_at: datetime | None = None, priority: int = 2) -> AgentSlot:
    slot = AgentSlot(
        agent_id=agent_id,
        config_path=f"config/active_agent.{agent_id}.yaml",
        profile_serial="1",
        adspower_user_id="abc",
    )
    slot.next_run_at = next_run_at
    slot.priority = Priority(priority)
    return slot


class TestSlotManagement:
    def test_available_slots(self):
        scheduler = OperatorScheduler(max_slots=4)
        assert scheduler.available_slots == 4
        scheduler.register_active("aisama")
        assert scheduler.available_slots == 3
        scheduler.release_slot("aisama")
        assert scheduler.available_slots == 4

    def test_no_slots_available(self):
        scheduler = OperatorScheduler(max_slots=2)
        scheduler.register_active("a")
        scheduler.register_active("b")
        assert scheduler.available_slots == 0


class TestPickNextAgents:
    @pytest.mark.asyncio
    async def test_picks_due_agents(self, db_path):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await upsert_agent(db_path, _slot("aisama", next_run_at=past))
        await upsert_agent(db_path, _slot("sweetdi", next_run_at=past))

        scheduler = OperatorScheduler(max_slots=4)
        picked = await scheduler.pick_next_agents(db_path)
        assert len(picked) == 2

    @pytest.mark.asyncio
    async def test_skips_future_agents(self, db_path):
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        await upsert_agent(db_path, _slot("aisama", next_run_at=future))

        scheduler = OperatorScheduler(max_slots=4)
        picked = await scheduler.pick_next_agents(db_path)
        assert len(picked) == 0

    @pytest.mark.asyncio
    async def test_respects_slot_limit(self, db_path):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        for i in range(10):
            await upsert_agent(db_path, _slot(f"agent{i}", next_run_at=past))

        scheduler = OperatorScheduler(max_slots=3)
        picked = await scheduler.pick_next_agents(db_path)
        assert len(picked) == 3

    @pytest.mark.asyncio
    async def test_skips_active_agents(self, db_path):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await upsert_agent(db_path, _slot("aisama", next_run_at=past))
        await upsert_agent(db_path, _slot("sweetdi", next_run_at=past))

        scheduler = OperatorScheduler(max_slots=4)
        scheduler.register_active("aisama")
        picked = await scheduler.pick_next_agents(db_path)
        assert len(picked) == 1
        assert picked[0]["agent_id"] == "sweetdi"

    @pytest.mark.asyncio
    async def test_priority_ordering(self, db_path):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await upsert_agent(db_path, _slot("low_prio", next_run_at=past, priority=3))
        await upsert_agent(db_path, _slot("high_prio", next_run_at=past, priority=1))

        scheduler = OperatorScheduler(max_slots=4)
        picked = await scheduler.pick_next_agents(db_path)
        assert picked[0]["agent_id"] == "high_prio"

    @pytest.mark.asyncio
    async def test_skips_non_idle_agents(self, db_path):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await upsert_agent(db_path, _slot("aisama", next_run_at=past))
        await update_agent_state(db_path, "aisama", AgentState.WORKING)

        scheduler = OperatorScheduler(max_slots=4)
        picked = await scheduler.pick_next_agents(db_path)
        assert len(picked) == 0


class TestStagger:
    def test_deterministic(self):
        assert _agent_stagger_offset("aisama") == _agent_stagger_offset("aisama")

    def test_different_agents(self):
        assert _agent_stagger_offset("aisama") != _agent_stagger_offset("sweetdi")

    def test_range(self):
        offset = _agent_stagger_offset("test")
        assert 0 <= offset < 300
