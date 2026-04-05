"""Operator scheduler: pick due agents, manage slot capacity, priority queue."""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from src.runtime.daily_plan import is_daily_plan_complete, load_daily_plan_state
from src.runtime.execution_checkpoint import load_execution_checkpoint
from src.runtime.platform_limits import is_reply_limited
from src.operator.models import AgentSlot, AgentState, Priority
from src.operator.state_store import load_all_agents

logger = logging.getLogger("bsq.operator.scheduler")


def _agent_stagger_offset(agent_id: str) -> int:
    """Deterministic stagger offset (0-300s) from agent_id hash."""
    digest = hashlib.md5(agent_id.encode()).hexdigest()
    return int(digest, 16) % 300


class OperatorScheduler:
    """Manages the slot pool and decides which agents to dispatch."""

    def __init__(self, max_slots: int = 4):
        self._max_slots = max_slots
        self._active: set[str] = set()

    @property
    def available_slots(self) -> int:
        return max(0, self._max_slots - len(self._active))

    @property
    def active_count(self) -> int:
        return len(self._active)

    def register_active(self, agent_id: str) -> None:
        self._active.add(agent_id)

    def release_slot(self, agent_id: str) -> None:
        self._active.discard(agent_id)

    def is_active(self, agent_id: str) -> bool:
        return agent_id in self._active

    def clear_all_slots(self) -> None:
        """Release all active slots (used on AdsPower down)."""
        self._active.clear()

    async def pick_next_agents(self, db_path: str, now: datetime | None = None) -> list[dict[str, Any]]:
        """Return up to available_slots agents that are ready to work.

        Eligible: IDLE agents with next_run_at <= now (or no next_run_at).
        Ordered by priority (lower = higher) then next_run_at.
        """
        if self.available_slots <= 0:
            return []

        now = now or datetime.now(timezone.utc)
        all_agents = await load_all_agents(db_path)
        candidates: list[dict[str, Any]] = []

        for agent in all_agents:
            if agent["agent_id"] in self._active:
                continue

            state = agent.get("state", "")
            if state != AgentState.IDLE.value:
                continue

            next_run = agent.get("next_run_at")
            if next_run:
                next_run_dt = datetime.fromisoformat(next_run)
                if next_run_dt > now:
                    continue

            candidates.append(agent)

        candidates.sort(key=lambda a: (a.get("priority", 99), a.get("next_run_at") or ""))
        return candidates[: self.available_slots]

    async def has_waiting_agents(self, db_path: str) -> bool:
        """Check if any agents are waiting for a slot (IDLE and due)."""
        now = datetime.now(timezone.utc)
        all_agents = await load_all_agents(db_path)
        for agent in all_agents:
            if agent["agent_id"] in self._active:
                continue
            if agent.get("state") != AgentState.IDLE.value:
                continue
            next_run = agent.get("next_run_at")
            if next_run and datetime.fromisoformat(next_run) > now:
                continue
            return True
        return False

    def compute_priority(self, agent_id: str, targets: dict[str, int] | None = None) -> Priority:
        """Compute scheduling priority based on current agent state.

        Args:
            targets: daily plan targets from agent config. Falls back to defaults if not provided.
        """
        # Check for checkpoint (crash recovery)
        checkpoint = load_execution_checkpoint(agent_id)
        if checkpoint:
            return Priority.RESUME_CHECKPOINT

        # Check reply limit
        if is_reply_limited(agent_id):
            return Priority.BLOCKED

        # Check daily plan
        daily_targets = targets or {"like": 20, "comment": 20, "post": 3}
        try:
            daily = load_daily_plan_state(agent_id, targets=daily_targets)
            if is_daily_plan_complete(daily):
                return Priority.OVERFLOW
        except Exception:
            pass

        return Priority.DAILY_INCOMPLETE

    def compute_next_run_at(
        self,
        agent_id: str,
        cycle_interval_minutes: tuple[int, int] = (20, 35),
        daily_complete: bool = False,
    ) -> datetime:
        """Compute when this agent should next run."""
        low, high = cycle_interval_minutes
        if daily_complete:
            low = max(low, high)
            high = max(high, low + 10)
        sleep_seconds = random.randint(low * 60, high * 60)
        sleep_seconds += _agent_stagger_offset(agent_id)
        return datetime.now(timezone.utc) + timedelta(seconds=sleep_seconds)
