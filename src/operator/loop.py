"""Operator main loop: persistent control plane for all agents.

Time-based model:
- Working cycle = 25-40 min of continuous micro-cycles
- After cycle: cooldown 10-15 min (or yield slot if queue exists)
- Agents are WORKING or COOLDOWN, never idle during normal operation

Note: subprocess calls use create_subprocess_exec (not shell) for safety.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from src.db.database import get_db_path
from src.operator.auditor_bridge import audit_authored_plan
from src.operator.memory_compiler import compile_briefing_packet
from src.operator.leases import acquire_lease, cleanup_expired_leases, heartbeat_lease, release_lease
from src.operator.models import AgentState, OperatorConfig, OperatorRun, Priority
from src.operator.persona_bridge import author_plan_text
from src.operator.recovery import check_stuck_agents
from src.operator.reflection_bridge import reflect_on_cycle
from src.operator.registry import sync_registry
from src.operator.scheduler import OperatorScheduler
from src.operator.strategic_bridge import generate_strategic_directive
from src.operator.state_store import (
    get_agent_state,
    init_operator_tables,
    load_all_agents,
    record_event,
    record_run_end,
    record_run_start,
    update_agent_state,
)
from src.runtime.agent_config import load_active_agent
from src.runtime.daily_plan import is_daily_plan_complete, load_daily_plan_state
from src.runtime.plan_io import delete_pending_plan

logger = logging.getLogger("bsq.operator.loop")


class OperatorLoop:
    """Persistent operator that schedules and manages all agent cycles."""

    def __init__(self, config: OperatorConfig | None = None):
        self._config = config or OperatorConfig()
        self._scheduler = OperatorScheduler(max_slots=self._config.max_slots)
        self._db_path = get_db_path()
        self._running = True
        self._tasks: dict[str, asyncio.Task] = {}
        self._last_health_check = 0.0
        self._adspower_healthy = True

    async def run(self) -> None:
        """Main persistent loop. Runs until stopped."""
        await init_operator_tables(self._db_path)
        await sync_registry(self._db_path)
        await record_event(self._db_path, "operator_start", None, f"Started (max_slots={self._config.max_slots})")
        logger.info("Operator started: max_slots=%d, tick=%ds", self._config.max_slots, self._config.tick_interval_sec)

        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self._config.tick_interval_sec)
        except asyncio.CancelledError:
            logger.info("Operator cancelled")
        finally:
            await self._shutdown()

    async def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        now = time.monotonic()
        if now - self._last_health_check >= self._config.health_check_interval_sec:
            self._last_health_check = now
            await self._check_adspower_health()

        if not self._adspower_healthy:
            return

        self._cleanup_finished_tasks()
        await cleanup_expired_leases(self._db_path)
        await check_stuck_agents(self._db_path, self._config)
        await self._wake_cooldown_agents()

        # Dispatch agents that are IDLE or just woke from COOLDOWN
        candidates = await self._scheduler.pick_next_agents(self._db_path)
        for agent_data in candidates:
            agent_id = agent_data["agent_id"]
            if agent_id in self._tasks:
                continue
            config_path = agent_data.get("config_path", "")
            if not config_path:
                continue
            task = asyncio.create_task(self._run_working_cycle(agent_id, config_path), name=f"work-{agent_id}")
            self._tasks[agent_id] = task
            self._scheduler.register_active(agent_id)

    async def _run_working_cycle(self, agent_id: str, config_path: str) -> None:
        """Full working cycle: 25-40 min of micro-cycles, then cooldown or yield."""
        # Acquire lease
        leased = await acquire_lease(
            self._db_path, agent_id=agent_id,
            holder_id=self._config.holder_id, ttl_sec=self._config.lease_ttl_sec,
        )
        if not leased:
            logger.info("Cannot acquire lease for %s, skipping", agent_id)
            return

        try:
            agent = load_active_agent(config_path)
            agent_dir = agent.agent_dir
            targets = agent.session_minimum.as_dict()

            # Transition to WORKING
            await update_agent_state(self._db_path, agent_id, AgentState.WORKING)
            await record_event(self._db_path, "cycle_start", agent_id, "Working cycle started")

            # Compute cycle deadline (25-40 min)
            low, high = self._config.cycle_duration_min
            cycle_seconds = random.randint(low * 60, high * 60)
            deadline = time.monotonic() + cycle_seconds
            micro_cycle_count = 0

            # Run micro-cycles until deadline
            while time.monotonic() < deadline and self._running:
                micro_cycle_count += 1
                run = OperatorRun(agent_id=agent_id, phase="micro_cycle")
                await record_run_start(self._db_path, run)

                success = await self._run_micro_cycle(agent_id, config_path, agent_dir, run)

                if not success:
                    break

                await record_run_end(self._db_path, run.run_id, status="completed", phase="done")

                # Heartbeat lease
                await heartbeat_lease(self._db_path, agent_id=agent_id, holder_id=self._config.holder_id, ttl_sec=self._config.lease_ttl_sec)

                # Behavior delay between micro-cycles (human-like pause)
                if time.monotonic() < deadline:
                    await asyncio.sleep(random.uniform(20, 60))

            # Working cycle done
            logger.info("Working cycle done for %s: %d micro-cycles in %ds", agent_id, micro_cycle_count, int(time.monotonic() - (deadline - cycle_seconds)))

            # Decide: cooldown or yield slot
            has_waiting = await self._scheduler.has_waiting_agents(self._db_path)
            if has_waiting and micro_cycle_count > 0:
                # Yield slot to waiting agent, short cooldown
                cooldown_sec = random.randint(60, 180)  # 1-3 min
                logger.info("Yielding slot for %s (queue exists), short cooldown %ds", agent_id, cooldown_sec)
            else:
                # Normal cooldown
                low_cd, high_cd = self._config.cooldown_min
                cooldown_sec = random.randint(low_cd * 60, high_cd * 60)

            next_run = datetime.now(timezone.utc) + timedelta(seconds=cooldown_sec)
            priority = self._scheduler.compute_priority(agent_id, targets=targets)
            await update_agent_state(
                self._db_path, agent_id, AgentState.COOLDOWN,
                priority=priority, next_run_at=next_run, increment_cycle=True, reset_errors=True,
            )
            await record_event(self._db_path, "cycle_complete", agent_id, f"{micro_cycle_count} micro-cycles, cooldown {cooldown_sec}s")

        except Exception as exc:
            logger.error("Working cycle error for %s: %s", agent_id, exc)
            await self._handle_failure(agent_id, "working_cycle", str(exc))
        finally:
            await release_lease(self._db_path, agent_id=agent_id, holder_id=self._config.holder_id)
            self._scheduler.release_slot(agent_id)
            self._tasks.pop(agent_id, None)

    async def _run_micro_cycle(self, agent_id: str, config_path: str, agent_dir: str, run: OperatorRun) -> bool:
        """One micro-cycle: compile -> strategize -> prepare -> author -> audit -> execute -> reflect.

        Returns True on success.
        """
        t0 = time.monotonic()

        # 1. COMPILE BRIEFING PACKET (memory -> compact state bundle for persona)
        compile_briefing_packet(agent_dir, agent_id)

        # 2. STRATEGIZE (persona reads briefing + previous context -> strategic directive)
        #    Non-fatal: if strategize fails, planner uses existing directive or defaults.
        await generate_strategic_directive(
            agent_id, agent_dir,
            timeout_sec=self._config.strategize_timeout_sec,
        )

        # 3. PREPARE (collect context + generate plan skeleton using directive)
        prepare_result = await self._run_subprocess(
            ["python", "session_run.py", "--prepare", "--config", config_path],
            timeout_sec=self._config.prepare_timeout_sec,
        )
        prepare_duration = time.monotonic() - t0

        if prepare_result["returncode"] != 0:
            error = prepare_result.get("stderr", "")[:200]
            logger.warning("Prepare failed for %s: %s", agent_id, error)
            await record_run_end(self._db_path, run.run_id, status="failed", phase="prepare", error_code=error)
            await record_event(self._db_path, "prepare_failed", agent_id, error)
            return False

        # 4. AUTHOR TEXT (persona writes text for each action in plan)
        t1 = time.monotonic()
        plan_path = f"data/runtime/{agent_id}/pending_plan.json"
        authored = await author_plan_text(
            agent_id, agent_dir, plan_path,
            timeout_sec=self._config.author_timeout_sec,
            mode=self._config.persona_bridge_mode,
        )
        author_duration = time.monotonic() - t1

        if not authored:
            logger.warning("Authoring failed for %s", agent_id)
            await record_run_end(self._db_path, run.run_id, status="failed", phase="authoring")
            delete_pending_plan(agent_id)
            return False

        # 5. AUDIT
        valid, issues = audit_authored_plan(agent_id, config_path)
        if not valid:
            logger.warning("Audit rejected for %s: %s", agent_id, "; ".join(issues))
            await record_event(self._db_path, "audit_reject", agent_id, "; ".join(issues))
            await record_run_end(self._db_path, run.run_id, status="failed", phase="auditing", error_code="; ".join(issues)[:200])
            delete_pending_plan(agent_id)
            return False

        # 6. EXECUTE
        t2 = time.monotonic()
        execute_result = await self._run_subprocess(
            ["python", "session_run.py", "--execute", "--config", config_path],
            timeout_sec=self._config.execute_timeout_sec,
        )
        execute_duration = time.monotonic() - t2

        if execute_result["returncode"] != 0:
            error = execute_result.get("stderr", "")[:200]
            if "timeout" in error.lower():
                logger.warning("Execute timeout for %s, pausing for resume", agent_id)
                try:
                    await update_agent_state(self._db_path, agent_id, AgentState.PAUSED_FOR_RESUME)
                except ValueError:
                    pass
                await record_run_end(self._db_path, run.run_id, status="paused", phase="executing", error_code=error)
                return False
            logger.warning("Execute failed for %s: %s", agent_id, error)
            await record_run_end(self._db_path, run.run_id, status="failed", phase="executing", error_code=error)
            return False

        # Check actual execution results (not just returncode)
        exec_output = self._parse_subprocess_json(execute_result.get("stdout", ""))
        if exec_output and exec_output.get("all_mandatory_failed"):
            mandatory_tried = exec_output.get("mandatory_attempted", 0)
            mandatory_ok = exec_output.get("mandatory_succeeded", 0)
            logger.warning(
                "Execute partial failure for %s: %d/%d mandatory actions failed",
                agent_id, mandatory_tried - mandatory_ok, mandatory_tried,
            )
            await record_run_end(self._db_path, run.run_id, status="partial_failure", phase="executing",
                                error_code=f"mandatory: {mandatory_ok}/{mandatory_tried} succeeded")
            await record_event(self._db_path, "partial_failure", agent_id,
                              f"All mandatory actions failed ({mandatory_tried} attempted)")
            return False

        # 7. REFLECT (persona reviews results -> updates strategic_state, open_loops, intent)
        #    Non-fatal: reflection failure doesn't invalidate the executed cycle.
        #    Only runs after confirmed successful execution.
        await reflect_on_cycle(
            agent_id, agent_dir,
            timeout_sec=self._config.reflect_timeout_sec,
        )

        run.prepare_duration_sec = prepare_duration
        run.author_duration_sec = author_duration
        run.execute_duration_sec = execute_duration
        return True

    async def _handle_failure(self, agent_id: str, phase: str, error: str) -> None:
        """Handle cycle failure: increment errors, apply backoff or disable."""
        logger.warning("Failure for %s at %s: %s", agent_id, phase, error[:200])
        await record_event(self._db_path, "cycle_failed", agent_id, f"{phase}: {error[:200]}")

        agent_data = await get_agent_state(self._db_path, agent_id)
        consecutive = (agent_data or {}).get("consecutive_errors", 0) + 1

        if consecutive >= self._config.max_consecutive_errors:
            try:
                await update_agent_state(self._db_path, agent_id, AgentState.FAILED, increment_error=True)
                await update_agent_state(self._db_path, agent_id, AgentState.DISABLED)
                await record_event(self._db_path, "agent_disabled", agent_id, f"After {consecutive} errors")
            except ValueError as exc:
                logger.warning("Cannot disable %s: %s", agent_id, exc)
        else:
            backoff_minutes = self._config.error_backoff_minutes * (2 ** max(consecutive - 1, 0))
            next_run = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
            try:
                await update_agent_state(self._db_path, agent_id, AgentState.FAILED, increment_error=True)
                await update_agent_state(self._db_path, agent_id, AgentState.IDLE, next_run_at=next_run)
            except ValueError as exc:
                logger.warning("Cannot apply backoff to %s: %s", agent_id, exc)

        delete_pending_plan(agent_id)

    async def _run_subprocess(self, cmd: list[str], timeout_sec: int) -> dict[str, Any]:
        """Run subprocess with timeout. Uses exec (no shell) for safety."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path.cwd()),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                return {"returncode": -1, "stdout": "", "stderr": f"timeout after {timeout_sec}s"}
            return {
                "returncode": proc.returncode,
                "stdout": (stdout or b"").decode(errors="replace"),
                "stderr": (stderr or b"").decode(errors="replace"),
            }
        except Exception as exc:
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}

    def _parse_subprocess_json(self, stdout: str) -> dict[str, Any] | None:
        """Extract JSON result from subprocess stdout.

        Stdout may contain log lines before the JSON. Finds the last
        complete JSON object by walking backward from the last '}'.
        """
        text = stdout.strip()
        if not text:
            return None
        try:
            # Try parsing the whole output first (simple case)
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        # Find last JSON object
        end = text.rfind("}")
        if end == -1:
            return None
        depth = 0
        for i in range(end, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[i:end + 1])
                except (json.JSONDecodeError, ValueError):
                    return None
        return None

    async def _check_adspower_health(self) -> None:
        url = f"{self._config.adspower_base_url}/status"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    if not self._adspower_healthy:
                        self._adspower_healthy = True
                        await self._recover_from_adspower_down()
                    return
        except Exception:
            pass
        if self._adspower_healthy:
            self._adspower_healthy = False
            await self._pause_all_for_adspower()

    async def _pause_all_for_adspower(self) -> None:
        logger.error("AdsPower unreachable - pausing all agents")
        await record_event(self._db_path, "adspower_down", None, "Unreachable")
        agents = await load_all_agents(self._db_path)
        pausable = {AgentState.WORKING.value, AgentState.COOLDOWN.value}
        for agent in agents:
            if agent["state"] in pausable:
                try:
                    await update_agent_state(self._db_path, agent["agent_id"], AgentState.PAUSED_ADSPOWER_DOWN)
                except ValueError:
                    pass
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        self._scheduler.clear_all_slots()

    async def _recover_from_adspower_down(self) -> None:
        logger.info("AdsPower recovered - unpausing agents")
        await record_event(self._db_path, "adspower_recovered", None, "Recovered")
        agents = await load_all_agents(self._db_path)
        for agent in agents:
            if agent["state"] == AgentState.PAUSED_ADSPOWER_DOWN.value:
                try:
                    await update_agent_state(self._db_path, agent["agent_id"], AgentState.IDLE)
                except ValueError:
                    pass

    async def _wake_cooldown_agents(self) -> None:
        """Transition COOLDOWN agents to IDLE when their cooldown expires."""
        now = datetime.now(timezone.utc)
        agents = await load_all_agents(self._db_path)
        for agent in agents:
            if agent["state"] != AgentState.COOLDOWN.value:
                continue
            next_run = agent.get("next_run_at")
            if not next_run:
                continue
            if datetime.fromisoformat(next_run) <= now:
                try:
                    await update_agent_state(self._db_path, agent["agent_id"], AgentState.IDLE)
                except ValueError:
                    pass

    def _cleanup_finished_tasks(self) -> None:
        finished = [aid for aid, task in self._tasks.items() if task.done()]
        for agent_id in finished:
            self._tasks.pop(agent_id, None)
            self._scheduler.release_slot(agent_id)

    async def _shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        await record_event(self._db_path, "operator_stop", None, "Stopped")
        logger.info("Operator stopped")
