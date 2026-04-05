"""Agent registry: scan config files and sync with operator state."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from src.runtime.agent_config import load_active_agent
from src.operator.models import AgentSlot, AgentState, Priority, validate_agent_id
from src.operator.state_store import upsert_agent, load_all_agents, update_agent_state, record_event

logger = logging.getLogger("bsq.operator.registry")

CONFIG_DIR = Path("config")
CONFIG_PATTERN = "active_agent*.yaml"
SKIP_SUFFIXES = (".example.yaml", ".bak.yaml")


def scan_agent_configs() -> list[AgentSlot]:
    """Scan config directory for all active_agent YAML files.

    Returns AgentSlot for each valid config found. Deduplicates by agent_id
    (first config found wins, others logged as warning).
    """
    slots: list[AgentSlot] = []
    seen_ids: dict[str, str] = {}  # agent_id -> config_path
    for path in sorted(CONFIG_DIR.glob(CONFIG_PATTERN)):
        if any(str(path).endswith(s) for s in SKIP_SUFFIXES):
            continue
        try:
            agent = load_active_agent(str(path))
            validate_agent_id(agent.agent_id)
            if agent.agent_id in seen_ids:
                logger.warning(
                    "Duplicate agent_id %s: %s already registered from %s, skipping %s",
                    agent.agent_id, agent.agent_id, seen_ids[agent.agent_id], path,
                )
                continue
            seen_ids[agent.agent_id] = str(path)
            slot = AgentSlot(
                agent_id=agent.agent_id,
                config_path=str(path),
                profile_serial=agent.profile_serial,
                adspower_user_id=agent.adspower_user_id,
                cycle_interval_minutes=(agent.cycle_interval_minutes[0], agent.cycle_interval_minutes[1]),
            )
            slots.append(slot)
            logger.info("Registered agent: %s (profile=%s, config=%s)", agent.agent_id, agent.profile_serial, path)
        except Exception as exc:
            logger.warning("Failed to load agent config %s: %s", path, exc)
    return slots


async def normalize_legacy_states(db_path: str) -> int:
    """Normalize any legacy/unknown states to IDLE on startup.

    Old operator had states like sleep_until_next_run, scheduled, preparing, etc.
    New operator only knows: idle, working, cooldown + error states.
    Unknown states make agents invisible to scheduler.
    """
    valid_states = {s.value for s in AgentState}
    agents = await load_all_agents(db_path)
    normalized = 0

    # Batch: single connection for all normalizations
    to_normalize = [(agent["agent_id"], agent.get("state", "")) for agent in agents if agent.get("state", "") not in valid_states]
    if to_normalize:
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                for agent_id, state in to_normalize:
                    await db.execute(
                        "UPDATE operator_agents SET state = 'idle', updated_at = datetime('now') WHERE agent_id = ?",
                        (agent_id,),
                    )
                    logger.warning("Normalized legacy state for %s: '%s' -> 'idle'", agent_id, state)
                await db.commit()
            for agent_id, state in to_normalize:
                await record_event(db_path, "legacy_state_normalized", agent_id, f"'{state}' -> 'idle'")
            normalized = len(to_normalize)
        except Exception as exc:
            logger.error("Failed to normalize legacy states: %s", exc)

    if normalized:
        logger.info("Normalized %d agents from legacy states", normalized)
    return normalized


async def sync_registry(db_path: str) -> list[AgentSlot]:
    """Sync scanned configs with operator_agents table.

    Normalizes legacy states first, then syncs configs.
    New configs -> IDLE. Removed configs -> DISABLED. Existing -> keep state.
    Returns list of all registered slots.
    """
    await normalize_legacy_states(db_path)
    scanned = scan_agent_configs()
    scanned_ids = {s.agent_id for s in scanned}

    # Upsert scanned agents
    for slot in scanned:
        await upsert_agent(db_path, slot)

    # Disable agents that are no longer in config
    existing = await load_all_agents(db_path)
    for agent_row in existing:
        agent_id = agent_row["agent_id"]
        if agent_id not in scanned_ids and agent_row["state"] != AgentState.DISABLED.value:
            try:
                await update_agent_state(db_path, agent_id, AgentState.DISABLED)
                logger.info("Disabled agent %s (config removed)", agent_id)
            except ValueError as exc:
                logger.warning("Cannot disable agent %s (state=%s): %s", agent_id, agent_row["state"], exc)

    logger.info("Registry sync: %d agents registered, %d from config", len(existing), len(scanned))
    return scanned
