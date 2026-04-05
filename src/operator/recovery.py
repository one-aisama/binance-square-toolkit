"""Recovery manager: timeout enforcement, backoff, circuit breaker.

Handles failure scenarios across the operator lifecycle:
- Worker subprocess timeouts (phase-aware)
- Exponential backoff after failures
- Circuit breaker: disable agent after N consecutive errors
- AdsPower down/recovery: bulk state transitions
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.operator.models import AgentState, OperatorConfig, Priority
from src.operator.state_store import (
    get_agent_state,
    load_all_agents,
    record_event,
    update_agent_state,
)

logger = logging.getLogger("bsq.operator.recovery")


async def handle_phase_timeout(
    db_path: str,
    agent_id: str,
    phase: str,
    timeout_sec: int,
) -> None:
    """Handle a subprocess timeout in a specific phase."""
    message = f"Timeout in {phase} after {timeout_sec}s"
    logger.warning("Recovery: %s for %s", message, agent_id)
    await record_event(db_path, "phase_timeout", agent_id, message)


async def apply_failure_backoff(
    db_path: str,
    agent_id: str,
    config: OperatorConfig,
) -> str:
    """Apply exponential backoff after a failure. Returns resulting state.

    Returns:
        "disabled" if max errors reached
        "idle" with backoff next_run_at otherwise
    """
    agent_data = await get_agent_state(db_path, agent_id)
    if not agent_data:
        return "unknown"

    consecutive = agent_data.get("consecutive_errors", 0)

    if consecutive >= config.max_consecutive_errors:
        try:
            await update_agent_state(db_path, agent_id, AgentState.DISABLED)
            await record_event(
                db_path, "circuit_breaker",
                agent_id, f"Disabled after {consecutive} consecutive errors",
            )
            logger.error("Circuit breaker: %s disabled after %d errors", agent_id, consecutive)
            return "disabled"
        except ValueError as exc:
            logger.warning("Cannot disable %s: %s", agent_id, exc)
            return "failed"

    backoff_minutes = config.error_backoff_minutes * (2 ** max(consecutive - 1, 0))
    next_run = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
    try:
        await update_agent_state(
            db_path, agent_id, AgentState.IDLE,
            next_run_at=next_run,
        )
        await record_event(
            db_path, "backoff",
            agent_id, f"Backed off {backoff_minutes}min (error #{consecutive}), next at {next_run.isoformat()}",
        )
        logger.info("Backoff: %s for %dmin (error #%d)", agent_id, backoff_minutes, consecutive)
        return "idle"
    except ValueError as exc:
        logger.warning("Cannot apply backoff to %s: %s", agent_id, exc)
        return "failed"


async def handle_adspower_down(db_path: str) -> int:
    """Pause all active agents when AdsPower goes down. Returns count paused."""
    agents = await load_all_agents(db_path)
    active_states = {
        AgentState.WORKING.value,
        AgentState.COOLDOWN.value,
    }
    paused = 0
    for agent in agents:
        if agent["state"] in active_states:
            try:
                await update_agent_state(db_path, agent["agent_id"], AgentState.PAUSED_ADSPOWER_DOWN)
                paused += 1
            except ValueError:
                pass
    if paused:
        await record_event(db_path, "adspower_down", None, f"Paused {paused} agents")
        logger.error("AdsPower down: paused %d agents", paused)
    return paused


async def handle_adspower_recovery(db_path: str) -> int:
    """Unpause agents after AdsPower recovery. Returns count unpaused."""
    agents = await load_all_agents(db_path)
    unpaused = 0
    for agent in agents:
        if agent["state"] == AgentState.PAUSED_ADSPOWER_DOWN.value:
            try:
                await update_agent_state(db_path, agent["agent_id"], AgentState.IDLE)
                unpaused += 1
            except ValueError:
                pass
    if unpaused:
        await record_event(db_path, "adspower_recovered", None, f"Unpaused {unpaused} agents")
        logger.info("AdsPower recovered: unpaused %d agents", unpaused)
    return unpaused


async def check_stuck_agents(
    db_path: str,
    config: OperatorConfig,
) -> list[str]:
    """Find agents stuck in active states beyond expected timeouts.

    Returns list of agent_ids that were transitioned to FAILED.
    """
    agents = await load_all_agents(db_path)
    now = datetime.now(timezone.utc)
    stuck: list[str] = []

    # WORKING agents have full cycle timeout (prepare + author + execute)
    max_working_sec = config.prepare_timeout_sec + config.author_timeout_sec + config.execute_timeout_sec
    phase_timeouts = {
        AgentState.WORKING.value: max_working_sec,
    }

    for agent in agents:
        state = agent["state"]
        if state not in phase_timeouts:
            continue
        updated_at = agent.get("updated_at")
        if not updated_at:
            continue
        updated_dt = datetime.fromisoformat(updated_at)
        elapsed = (now - updated_dt).total_seconds()
        max_time = phase_timeouts[state] * 2  # 2x timeout as safety margin
        if elapsed > max_time:
            agent_id = agent["agent_id"]
            try:
                await update_agent_state(db_path, agent_id, AgentState.FAILED, increment_error=True)
                await record_event(
                    db_path, "stuck_agent",
                    agent_id, f"Stuck in {state} for {int(elapsed)}s (max {max_time}s)",
                )
                stuck.append(agent_id)
                logger.warning("Stuck agent %s in %s for %ds, moved to FAILED", agent_id, state, int(elapsed))
            except ValueError:
                pass

    return stuck
