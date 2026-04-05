"""Operator control plane data models.

Defines the state machine, priority system, and core data structures
for managing agent lifecycle across the operator.

State machine:
  IDLE → WORKING → COOLDOWN → WORKING → ...
  Error states: BLOCKED_REPLY_LIMIT, PAUSED_FOR_RESUME, PAUSED_ADSPOWER_DOWN, FAILED, DISABLED
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any


class AgentState(StrEnum):
    """State machine for a logical agent managed by the operator.

    Normal flow: IDLE → WORKING → COOLDOWN → WORKING → ...
    IDLE is only for initial state and recovery after errors.
    During WORKING, operator runs N micro-cycles (prepare→text→execute).
    """

    # Normal flow
    IDLE = "idle"
    WORKING = "working"
    COOLDOWN = "cooldown"

    # Error / special states
    BLOCKED_REPLY_LIMIT = "blocked_reply_limit"
    PAUSED_FOR_RESUME = "paused_for_resume"
    PAUSED_ADSPOWER_DOWN = "paused_adspower_down"
    FAILED = "failed"
    DISABLED = "disabled"


VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.WORKING, AgentState.FAILED, AgentState.DISABLED},
    AgentState.WORKING: {
        AgentState.COOLDOWN,
        AgentState.BLOCKED_REPLY_LIMIT,
        AgentState.PAUSED_FOR_RESUME,
        AgentState.PAUSED_ADSPOWER_DOWN,
        AgentState.FAILED,
    },
    AgentState.COOLDOWN: {AgentState.WORKING, AgentState.IDLE, AgentState.PAUSED_ADSPOWER_DOWN, AgentState.FAILED},
    AgentState.BLOCKED_REPLY_LIMIT: {AgentState.IDLE, AgentState.WORKING, AgentState.DISABLED},
    AgentState.PAUSED_FOR_RESUME: {AgentState.WORKING, AgentState.IDLE, AgentState.FAILED},
    AgentState.PAUSED_ADSPOWER_DOWN: {AgentState.IDLE, AgentState.FAILED},
    AgentState.FAILED: {AgentState.IDLE, AgentState.DISABLED},
    AgentState.DISABLED: {AgentState.IDLE},
}


def validate_transition(current: AgentState, target: AgentState) -> bool:
    """Check if a state transition is valid."""
    allowed = VALID_TRANSITIONS.get(current, set())
    return target in allowed


import re

_SAFE_AGENT_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_agent_id(agent_id: str) -> str:
    """Validate agent_id for safe use in file paths and SQL.

    Rejects: path traversal (..), slashes, special chars.
    Returns agent_id if valid, raises ValueError otherwise.
    """
    if not _SAFE_AGENT_ID.match(agent_id):
        raise ValueError(f"Invalid agent_id: {agent_id!r} (must be alphanumeric/underscore/dash, max 64 chars)")
    return agent_id


class Priority(IntEnum):
    """Agent scheduling priority (lower = higher priority)."""

    RESUME_CHECKPOINT = 1
    DAILY_INCOMPLETE = 2
    OVERFLOW = 3
    BLOCKED = 4
    DISABLED = 99


@dataclass
class AgentSlot:
    """Scheduling state for one logical agent."""

    agent_id: str
    config_path: str
    profile_serial: str
    adspower_user_id: str
    state: AgentState = AgentState.IDLE
    priority: Priority = Priority.DAILY_INCOMPLETE
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    cycle_count: int = 0
    consecutive_errors: int = 0
    cycle_interval_minutes: tuple[int, int] = (20, 35)


@dataclass
class OperatorRun:
    """Record of a single agent cycle (prepare -> author -> execute)."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status: str = "running"
    phase: str = ""
    error_code: str | None = None
    prepare_duration_sec: float = 0.0
    author_duration_sec: float = 0.0
    execute_duration_sec: float = 0.0
    action_count: int = 0
    success_count: int = 0


@dataclass
class Lease:
    """Exclusive lock on an agent profile."""

    agent_id: str
    holder_id: str
    acquired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    heartbeat_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OperatorConfig:
    """Tuning knobs for the operator."""

    max_slots: int = 4
    tick_interval_sec: int = 5
    health_check_interval_sec: int = 30
    prepare_timeout_sec: int = 300
    author_timeout_sec: int = 600
    execute_timeout_sec: int = 900
    lease_ttl_sec: int = 3600  # 1h — covers full working cycle (25-40 min + buffer)
    heartbeat_interval_sec: int = 30
    error_backoff_minutes: int = 10
    max_consecutive_errors: int = 3
    holder_id: str = field(default_factory=lambda: f"op-{uuid.uuid4().hex[:8]}")
    strategize_timeout_sec: int = 120
    reflect_timeout_sec: int = 120
    persona_bridge_mode: str = "cli"
    adspower_base_url: str = "http://local.adspower.net:50325"
    cycle_duration_min: tuple[int, int] = (25, 40)
    cooldown_min: tuple[int, int] = (10, 15)
