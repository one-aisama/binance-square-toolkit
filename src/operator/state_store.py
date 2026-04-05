"""Operator state store: SQLite persistence for agent states, runs, leases, events."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.operator.models import AgentSlot, AgentState, OperatorRun, Priority, validate_transition

logger = logging.getLogger("bsq.operator.state")

OPERATOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS operator_agents (
    agent_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'idle',
    priority INTEGER NOT NULL DEFAULT 2,
    next_run_at TIMESTAMP,
    last_run_at TIMESTAMP,
    cycle_count INTEGER DEFAULT 0,
    consecutive_errors INTEGER DEFAULT 0,
    config_path TEXT,
    updated_at TIMESTAMP,
    state_schema_version INTEGER DEFAULT 2
);

CREATE TABLE IF NOT EXISTS operator_runs (
    run_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running',
    phase TEXT,
    error_code TEXT,
    prepare_duration_sec REAL,
    author_duration_sec REAL,
    execute_duration_sec REAL,
    action_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_operator_runs_agent ON operator_runs(agent_id, started_at);

CREATE TABLE IF NOT EXISTS operator_leases (
    agent_id TEXT PRIMARY KEY,
    holder_id TEXT NOT NULL,
    acquired_at TIMESTAMP NOT NULL,
    heartbeat_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    agent_id TEXT,
    message TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_operator_events_agent ON operator_events(agent_id, created_at);
"""


async def init_operator_tables(db_path: str) -> None:
    """Create operator tables if they don't exist. Migrate schema if needed."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(OPERATOR_SCHEMA)
        # Migrate: add state_schema_version if missing (existing DBs)
        try:
            await db.execute("ALTER TABLE operator_agents ADD COLUMN state_schema_version INTEGER DEFAULT 2")
        except Exception:
            pass  # Column already exists
        await db.commit()


async def upsert_agent(db_path: str, slot: AgentSlot) -> None:
    """Insert or update an agent in operator_agents."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """INSERT INTO operator_agents
               (agent_id, state, priority, next_run_at, last_run_at, cycle_count,
                consecutive_errors, config_path, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(agent_id) DO UPDATE SET
                 config_path = excluded.config_path,
                 updated_at = excluded.updated_at""",
            (
                slot.agent_id, slot.state.value, slot.priority.value,
                slot.next_run_at.isoformat() if slot.next_run_at else None,
                slot.last_run_at.isoformat() if slot.last_run_at else None,
                slot.cycle_count, slot.consecutive_errors,
                slot.config_path, now,
            ),
        )
        await db.commit()


async def update_agent_state(
    db_path: str,
    agent_id: str,
    new_state: AgentState,
    *,
    priority: Priority | None = None,
    next_run_at: datetime | None = None,
    increment_cycle: bool = False,
    increment_error: bool = False,
    reset_errors: bool = False,
) -> None:
    """Transition agent to new state with validation.

    Uses BEGIN IMMEDIATE to prevent TOCTOU race between SELECT and UPDATE.
    """
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT state FROM operator_agents WHERE agent_id = ?",
                (agent_id,),
            )
            row = await cursor.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                raise ValueError(f"Agent {agent_id} not found in operator_agents")

            current = AgentState(row[0])
            if not validate_transition(current, new_state):
                msg = f"Invalid transition for {agent_id}: {current.value} -> {new_state.value}"
                logger.error(msg)
                await _record_event(db, "invalid_transition", agent_id, msg)
                await db.commit()
                raise ValueError(msg)

            # All update fragments are hardcoded column names — never user input
            updates = ["state = ?", "updated_at = ?"]
            params: list[Any] = [new_state.value, now]

            if priority is not None:
                updates.append("priority = ?")
                params.append(priority.value)
            if next_run_at is not None:
                updates.append("next_run_at = ?")
                params.append(next_run_at.isoformat())
            if new_state == AgentState.COOLDOWN:
                updates.append("last_run_at = ?")
                params.append(now)
            if increment_cycle:
                updates.append("cycle_count = cycle_count + 1")
            if increment_error:
                updates.append("consecutive_errors = consecutive_errors + 1")
            if reset_errors:
                updates.append("consecutive_errors = 0")

            params.append(agent_id)
            await db.execute(
                f"UPDATE operator_agents SET {', '.join(updates)} WHERE agent_id = ?",
                params,
            )
            await _record_event(db, "state_change", agent_id, f"{current.value} -> {new_state.value}")
            await db.commit()
        except ValueError:
            raise
        except Exception:
            await db.execute("ROLLBACK")
            raise


async def load_all_agents(db_path: str) -> list[dict[str, Any]]:
    """Load all agents from operator_agents."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM operator_agents ORDER BY priority, next_run_at")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_agent_state(db_path: str, agent_id: str) -> dict[str, Any] | None:
    """Get single agent state."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM operator_agents WHERE agent_id = ?", (agent_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def record_run_start(db_path: str, run: OperatorRun) -> None:
    """Record the start of a new cycle run."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """INSERT INTO operator_runs
               (run_id, agent_id, started_at, status, phase)
               VALUES (?, ?, ?, ?, ?)""",
            (run.run_id, run.agent_id, run.started_at.isoformat(), run.status, run.phase),
        )
        await db.commit()


async def record_run_end(
    db_path: str,
    run_id: str,
    *,
    status: str,
    phase: str = "",
    error_code: str | None = None,
    prepare_duration: float = 0.0,
    author_duration: float = 0.0,
    execute_duration: float = 0.0,
    action_count: int = 0,
    success_count: int = 0,
) -> None:
    """Record the end of a cycle run."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """UPDATE operator_runs SET
               finished_at = ?, status = ?, phase = ?, error_code = ?,
               prepare_duration_sec = ?, author_duration_sec = ?,
               execute_duration_sec = ?, action_count = ?, success_count = ?
               WHERE run_id = ?""",
            (now, status, phase, error_code,
             prepare_duration, author_duration, execute_duration,
             action_count, success_count, run_id),
        )
        await db.commit()


async def record_event(db_path: str, event_type: str, agent_id: str | None, message: str, metadata: dict | None = None) -> None:
    """Record an operator event for audit trail."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await _record_event(db, event_type, agent_id, message, metadata)
        await db.commit()


async def _record_event(db: aiosqlite.Connection, event_type: str, agent_id: str | None, message: str, metadata: dict | None = None) -> None:
    """Internal: record event within an existing connection."""
    meta_json = json.dumps(metadata) if metadata else None
    await db.execute(
        "INSERT INTO operator_events (event_type, agent_id, message, metadata) VALUES (?, ?, ?, ?)",
        (event_type, agent_id, message, meta_json),
    )


async def get_recent_events(db_path: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent operator events for dashboard."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM operator_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_operator_metrics(db_path: str) -> dict[str, Any]:
    """Get aggregate metrics for dashboard."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        cursor = await db.execute(
            "SELECT COUNT(*) FROM operator_agents WHERE state != 'disabled'"
        )
        active_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM operator_agents WHERE state = 'working'"
        )
        busy_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            """SELECT AVG(prepare_duration_sec + author_duration_sec + execute_duration_sec),
                      AVG(CASE WHEN status = 'completed' THEN 1.0 ELSE 0.0 END),
                      COUNT(*)
               FROM operator_runs WHERE finished_at IS NOT NULL"""
        )
        row = await cursor.fetchone()
        avg_cycle = row[0] or 0.0
        success_rate = (row[1] or 0.0) * 100
        total_runs = row[2] or 0

        return {
            "active_agents": active_count,
            "busy_slots": busy_count,
            "avg_cycle_sec": round(avg_cycle, 1),
            "success_rate_pct": round(success_rate, 1),
            "total_runs": total_runs,
        }
