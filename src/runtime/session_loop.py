from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.db.database import get_db_path, init_db
from src.metrics.store import MetricsStore, init_metrics_tables
from src.runtime.agent_config import load_active_agent
from src.runtime.persona_policy import apply_coin_bias_overrides
from src.runtime.agent_plan import AgentPlan
from src.runtime.cycle_policy import build_cycle_directive, choose_sleep_seconds
from src.runtime.daily_plan import (
    get_daily_plan_path,
    is_daily_plan_complete,
    load_daily_plan_state,
    remaining_daily_targets,
    update_daily_plan_state,
)
from src.runtime.deterministic_planner import DeterministicPlanGenerator
from src.runtime.execution_checkpoint import (
    clear_execution_checkpoint,
    get_checkpoint_path,
    load_execution_checkpoint,
    save_execution_checkpoint,
)
from src.runtime.plan_auditor import PlanAuditor
from src.runtime.plan_executor import PlanExecutor
from src.runtime.errors import PlanGenerationError
from src.runtime.platform_limits import get_platform_limits, update_limits_from_results
from src.runtime.runtime_settings import load_runtime_settings
from src.runtime.persona_policy import load_persona_policy
from src.runtime.post_registry import get_recent_agent_posts, get_recent_other_agent_posts, record_completed_posts
from src.runtime.topic_reservation import (
    cleanup_expired,
    confirm_reservation,
    get_active_reservations,
    release_all_agent_reservations,
)
from src.runtime.comment_coordination import (
    cleanup_expired_comment_locks,
    release_agent_comment_locks,
)
from src.runtime.news_cooldown import cleanup_expired_news_cooldowns, record_news_cooldown
from src.runtime.plan_io import save_pending_plan, plan_has_text, load_plan_for_execution, delete_pending_plan
from src.runtime.session_context import SessionContextBuilder, save_session_context
from src.sdk import BinanceSquareSDK
from src.strategy.reviewer import SessionReviewer

logger = logging.getLogger("bsq.session.loop")


def _agent_stagger_offset(agent_id: str) -> int:
    """Deterministic stagger offset (0-300s) from agent_id hash."""
    import hashlib
    digest = hashlib.md5(agent_id.encode()).hexdigest()
    return int(digest, 16) % 300
STATUS_DIR = Path("data/runs")
REVIEW_DIR = Path("data/session_reviews")


class ContinuousSessionRunner:
    """Keep one agent alive across multiple autonomous planning/execution cycles."""

    def __init__(
        self,
        *,
        config_path: str,
        settings_path: str = "config/settings.yaml",
        max_cycles: int | None = None,
        stop_file: str | None = None,
    ):
        self._config_path = config_path
        self._settings_path = settings_path
        self._max_cycles = max_cycles
        self._explicit_stop_file = stop_file

    async def run(self) -> dict[str, Any]:
        load_dotenv()
        settings = self._load_settings(self._settings_path)
        agent = load_active_agent(self._config_path)
        agent = agent.effective_config()
        logger.info("Agent mode: %s", agent.mode)

        # Load persona policy and attach to agent for runtime access
        policy_path = Path(f"config/persona_policies/{agent.agent_id}.yaml")
        if policy_path.exists():
            policy = load_persona_policy(policy_path)
            # Apply individual-mode coin bias overrides
            if agent.mode == "individual" and agent.mode_override:
                ovr = agent.mode_override
                policy = apply_coin_bias_overrides(
                    policy,
                    preferred=ovr.coin_bias_preferred,
                    exclude_from_posts=ovr.coin_bias_exclude_from_posts,
                )
            agent._policy = policy
            logger.info("Loaded persona policy for %s from %s", agent.agent_id, policy_path)
        else:
            agent._policy = None
            logger.warning("No persona policy found at %s, running without policy", policy_path)

        stop_path = Path(self._explicit_stop_file) if self._explicit_stop_file else STATUS_DIR / f"stop_{agent.agent_id}.flag"
        agent_runtime_dir = Path("data/runtime") / agent.agent_id
        agent_runtime_dir.mkdir(parents=True, exist_ok=True)
        status_path = agent_runtime_dir / "status.json"
        # Migrate legacy status file
        legacy_status = STATUS_DIR / f"{agent.agent_id}_continuous_status.json"
        if not status_path.exists() and legacy_status.exists():
            legacy_status.rename(status_path)
        checkpoint_path = get_checkpoint_path(agent.agent_id)
        daily_plan_path = get_daily_plan_path(agent.agent_id)
        daily_targets = agent.session_minimum.as_dict()
        timezone_name = getattr(agent, "daily_plan_timezone", "UTC")

        db_path = get_db_path()
        await init_db(db_path)
        await init_metrics_tables(db_path)

        sdk = BinanceSquareSDK(
            profile_serial=agent.profile_serial,
            account_id=agent.agent_id,
            max_session_actions=agent.max_session_actions,
            session_minimum=agent.session_minimum.as_dict(),
            profile_username=agent.binance_username or None,
            adspower_base_url=settings.get("adspower_base_url"),
        )
        builder = SessionContextBuilder(agent_dir=agent.agent_dir)
        generator: Any = DeterministicPlanGenerator(agent=agent, sdk=sdk, db_path=db_path)
        planner_mode = "local_role_orchestrator"
        auditor = PlanAuditor()
        reviewer = SessionReviewer(MetricsStore(db_path), agent.agent_dir)

        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)

        existing_status = self._load_status(status_path)
        cycles_completed = int(existing_status.get("cycles_completed", 0)) if existing_status else 0
        started_at = self._utc_now()
        initial_daily_plan = load_daily_plan_state(
            agent.agent_id,
            targets=daily_targets,
            timezone_name=timezone_name,
        )
        last_status: dict[str, Any] = {
            "agent_id": agent.agent_id,
            "mode": "continuous",
            "planner_mode": planner_mode,
            "config_path": self._config_path,
            "settings_path": self._settings_path,
            "started_at": started_at,
            "platform_limits": get_platform_limits(agent.agent_id),
            "stop_file": str(stop_path),
            "checkpoint_file": str(checkpoint_path),
            "daily_plan_file": str(daily_plan_path),
            "daily_plan": initial_daily_plan,
            "state": "starting",
            "cycles_completed": cycles_completed,
        }
        self._write_status(status_path, last_status)

        if agent.mode == "test":
            logger.info("TEST MODE: skipping SDK connect for %s", agent.agent_id)
        else:
            await sdk.connect()
        logger.info(
            "Continuous session connected for %s (serial=%s, planner=%s, mode=%s)",
            agent.agent_id,
            agent.profile_serial,
            planner_mode,
            agent.mode,
        )

        try:
            while True:
                daily_plan = load_daily_plan_state(
                    agent.agent_id,
                    targets=daily_targets,
                    timezone_name=timezone_name,
                )
                checkpoint = load_execution_checkpoint(agent.agent_id)
                if checkpoint and checkpoint.get("plan_date") != daily_plan.get("plan_date"):
                    logger.info(
                        "Discarding stale checkpoint for %s: checkpoint day=%s current day=%s",
                        agent.agent_id,
                        checkpoint.get("plan_date"),
                        daily_plan.get("plan_date"),
                    )
                    clear_execution_checkpoint(agent.agent_id)
                    checkpoint = None

                checkpoint_phase = str(checkpoint.get("phase") or "executing") if checkpoint else "executing"

                if self._should_stop(stop_path) and checkpoint is None:
                    last_status.update({"state": "stopping", "stop_reason": f"stop file detected: {stop_path}"})
                    self._write_status(status_path, last_status)
                    break
                if self._max_cycles is not None and cycles_completed >= self._max_cycles and checkpoint is None:
                    last_status.update({"state": "completed", "stop_reason": f"max cycles reached: {self._max_cycles}"})
                    self._write_status(status_path, last_status)
                    break
                if (
                    sdk.get_session_stats().get("total_actions", 0) >= agent.max_session_actions
                    and checkpoint is None
                ):
                    last_status.update({"state": "completed", "stop_reason": "max session actions reached"})
                    self._write_status(status_path, last_status)
                    break

                if checkpoint:
                    plan = self._load_checkpoint_plan(checkpoint)
                    if plan is None:
                        logger.warning("Discarding invalid checkpoint for %s", agent.agent_id)
                        clear_execution_checkpoint(agent.agent_id)
                        continue

                    cycle_index = int(checkpoint.get("cycle_index") or (cycles_completed + 1))
                    cycle_started_at = str(checkpoint.get("cycle_started_at") or self._utc_now())
                    context_files = list(checkpoint.get("context_files") or [])
                    directive_stage = str(checkpoint.get("directive_stage") or "resumed")
                    next_action_index = int(checkpoint.get("next_action_index") or 0)
                    existing_results = list(checkpoint.get("results") or [])
                    commit_state = dict(checkpoint.get("commit_state") or {})

                    last_status.update(
                        {
                            "state": "resuming_commit" if checkpoint_phase == "committing" else "resuming_plan",
                            "current_cycle": cycle_index,
                            "last_cycle_started_at": cycle_started_at,
                            "last_cycle_stage": directive_stage,
                            "last_cycle_context_files": context_files,
                            "planned_actions": len(plan.actions),
                            "completed_actions": len(existing_results),
                            "next_action_index": next_action_index,
                            "platform_limits": get_platform_limits(agent.agent_id),
                            "daily_plan": daily_plan,
                            "daily_plan_remaining": remaining_daily_targets(daily_plan),
                        }
                    )
                    self._write_status(status_path, last_status)
                else:
                    cycle_index = cycles_completed + 1
                    cycle_started_at = self._utc_now()
                    last_status.update({"state": "collecting_context", "current_cycle": cycle_index, "daily_plan": daily_plan})
                    self._write_status(status_path, last_status)

                    await cleanup_expired(db_path)
                    await cleanup_expired_comment_locks(db_path)
                    await cleanup_expired_news_cooldowns(db_path)

                    context = await builder.build(sdk, agent)
                    context_files = save_session_context(context)
                    directive = build_cycle_directive(agent, context, daily_plan_state=daily_plan)
                    recent_other_posts = get_recent_other_agent_posts(agent.agent_id)
                    recent_self_posts = get_recent_agent_posts(agent.agent_id)

                    plan = await self._generate_audited_plan(
                        generator=generator,
                        auditor=auditor,
                        agent=agent,
                        context=context,
                        directive=directive,
                        recent_other_posts=recent_other_posts,
                        recent_self_posts=recent_self_posts,
                        db_path=db_path,
                    )
                    if plan is None:
                        sleep_seconds = choose_sleep_seconds(directive.interval_minutes, minimum_met=False)
                        last_status.update(
                            {
                                "state": "sleeping_after_rejected_plan",
                                "current_cycle": cycle_index,
                                "last_error": "plan generation/audit failed twice",
                                "sleep_seconds": sleep_seconds,
                                "platform_limits": get_platform_limits(agent.agent_id),
                                "daily_plan": daily_plan,
                                "daily_plan_remaining": remaining_daily_targets(daily_plan),
                            }
                        )
                        self._write_status(status_path, last_status)
                        await self._sleep_with_stop(stop_path, sleep_seconds)
                        continue

                    directive_stage = directive.stage
                    next_action_index = 0
                    existing_results = []
                    commit_state = {}
                    checkpoint = self._build_checkpoint_payload(
                        agent_id=agent.agent_id,
                        cycle_index=cycle_index,
                        cycle_started_at=cycle_started_at,
                        directive_stage=directive_stage,
                        context_files=context_files,
                        plan=plan,
                        results=existing_results,
                        next_action_index=next_action_index,
                        plan_date=str(daily_plan.get("plan_date") or ""),
                        timezone_name=timezone_name,
                    )
                    # Save plan for agent session to write text
                    plan_path = save_pending_plan(
                        agent_id=agent.agent_id,
                        plan=plan,
                        directive=directive,
                        context_files=context_files,
                    )
                    last_status.update({"state": "awaiting_text", "plan_path": plan_path})
                    self._write_status(status_path, last_status)
                    logger.info(
                        "Plan saved at %s (%d actions). Waiting for agent to write text...",
                        plan_path, len(plan.actions),
                    )

                    # Poll until agent session fills in text (check every 10s, timeout 10min)
                    poll_deadline = asyncio.get_running_loop().time() + 600
                    while not plan_has_text(agent.agent_id):
                        if self._should_stop(stop_path):
                            logger.info("Stop file detected while waiting for text")
                            return last_status
                        if asyncio.get_running_loop().time() > poll_deadline:
                            logger.warning("Timeout waiting for agent text, skipping cycle")
                            delete_pending_plan(agent.agent_id)
                            break
                        await asyncio.sleep(10)
                    else:
                        # Agent wrote text — load the authored plan
                        try:
                            plan = load_plan_for_execution(agent.agent_id)
                            delete_pending_plan(agent.agent_id)
                            logger.info("Loaded authored plan with text for %s", agent.agent_id)
                        except (FileNotFoundError, ValueError) as exc:
                            logger.warning("Failed to load authored plan: %s, skipping cycle", exc)
                            delete_pending_plan(agent.agent_id)
                            break

                    checkpoint = self._build_checkpoint_payload(
                        agent_id=agent.agent_id,
                        cycle_index=cycle_index,
                        cycle_started_at=cycle_started_at,
                        directive_stage=directive_stage,
                        context_files=context_files,
                        plan=plan,
                        results=existing_results,
                        next_action_index=next_action_index,
                        plan_date=str(daily_plan.get("plan_date") or ""),
                        timezone_name=timezone_name,
                    )
                    checkpoint["phase"] = "executing"
                    checkpoint["commit_state"] = commit_state
                    save_execution_checkpoint(agent.agent_id, checkpoint)
                    checkpoint_phase = "executing"
                    last_status.update(
                        {
                            "state": "executing_plan",
                            "current_cycle": cycle_index,
                            "last_cycle_started_at": cycle_started_at,
                            "last_cycle_stage": directive_stage,
                            "last_cycle_context_files": context_files,
                            "planned_actions": len(plan.actions),
                            "completed_actions": 0,
                            "next_action_index": 0,
                            "daily_plan": daily_plan,
                            "daily_plan_remaining": remaining_daily_targets(daily_plan),
                        }
                    )
                    self._write_status(status_path, last_status)

                if checkpoint_phase != "committing":
                    executor = PlanExecutor(sdk, config_path=self._config_path, guard=getattr(sdk, '_guard', None))
                    if hasattr(agent, '_policy') and agent._policy:
                        executor._delay_config = agent._policy.runtime_tuning.delays

                    def persist_progress(next_index: int, results: list[dict[str, Any]]) -> None:
                        payload = self._build_checkpoint_payload(
                            agent_id=agent.agent_id,
                            cycle_index=cycle_index,
                            cycle_started_at=cycle_started_at,
                            directive_stage=directive_stage,
                            context_files=context_files,
                            plan=plan,
                            results=results,
                            next_action_index=next_index,
                            plan_date=str(daily_plan.get("plan_date") or ""),
                            timezone_name=timezone_name,
                        )
                        payload["phase"] = "executing"
                        payload["commit_state"] = commit_state
                        save_execution_checkpoint(agent.agent_id, payload)
                        last_status.update(
                            {
                                "state": "executing_plan",
                                "current_cycle": cycle_index,
                                "completed_actions": len(results),
                                "next_action_index": next_index,
                                "platform_limits": get_platform_limits(agent.agent_id),
                                "daily_plan": daily_plan,
                                "daily_plan_remaining": remaining_daily_targets(daily_plan),
                            }
                        )
                        self._write_status(status_path, last_status)

                    execution_results = await executor.execute(
                        plan,
                        start_index=next_action_index,
                        existing_results=existing_results,
                        should_stop=lambda: self._should_stop(stop_path),
                        on_action_complete=persist_progress,
                        dry_run=(agent.mode == "test"),
                    )

                    if not executor.last_completed:
                        last_status.update(
                            {
                                "state": "paused_for_resume",
                                "stop_reason": f"stop file detected during plan: {stop_path}",
                                "current_cycle": cycle_index,
                                "completed_actions": len(execution_results),
                                "next_action_index": executor.last_next_action_index,
                                "platform_limits": get_platform_limits(agent.agent_id),
                                "daily_plan": daily_plan,
                                "daily_plan_remaining": remaining_daily_targets(daily_plan),
                            }
                        )
                        self._write_status(status_path, last_status)
                        break

                    checkpoint = self._build_checkpoint_payload(
                        agent_id=agent.agent_id,
                        cycle_index=cycle_index,
                        cycle_started_at=cycle_started_at,
                        directive_stage=directive_stage,
                        context_files=context_files,
                        plan=plan,
                        results=execution_results,
                        next_action_index=executor.last_next_action_index,
                        plan_date=str(daily_plan.get("plan_date") or ""),
                        timezone_name=timezone_name,
                    )
                    checkpoint["phase"] = "committing"
                    checkpoint["commit_state"] = commit_state
                    save_execution_checkpoint(agent.agent_id, checkpoint)
                else:
                    execution_results = existing_results

                daily_plan, review_path = await self._commit_cycle_results(
                    agent_id=agent.agent_id,
                    checkpoint_payload=checkpoint,
                    plan=plan,
                    execution_results=execution_results,
                    daily_targets=daily_targets,
                    timezone_name=timezone_name,
                    reviewer=reviewer,
                    cycle_started_at=cycle_started_at,
                    cycle_index=cycle_index,
                    directive_stage=directive_stage,
                    sdk=sdk,
                    db_path=db_path,
                )
                clear_execution_checkpoint(agent.agent_id)

                cycles_completed = max(cycles_completed, cycle_index)
                daily_plan_complete = is_daily_plan_complete(daily_plan)
                daily_remaining = remaining_daily_targets(daily_plan)
                sleep_seconds = choose_sleep_seconds(agent.cycle_interval_minutes, minimum_met=daily_plan_complete)
                sleep_seconds += _agent_stagger_offset(agent.agent_id)
                last_status = {
                    "agent_id": agent.agent_id,
                    "mode": "continuous",
                    "planner_mode": planner_mode,
                    "config_path": self._config_path,
                    "settings_path": self._settings_path,
                    "started_at": started_at,
                    "last_cycle_started_at": cycle_started_at,
                    "last_cycle_completed_at": self._utc_now(),
                    "last_cycle_stage": directive_stage,
                    "last_cycle_context_files": context_files,
                    "last_session_review": str(review_path),
                    "checkpoint_file": str(checkpoint_path),
                    "daily_plan_file": str(daily_plan_path),
                    "daily_plan": daily_plan,
                    "cycles_completed": cycles_completed,
                    "minimum_status": daily_plan.get("completed"),
                    "minimum_met": daily_plan_complete,
                    "minimum_reason": "daily plan completed" if daily_plan_complete else f"daily remaining: {daily_remaining}",
                    "platform_limits": get_platform_limits(agent.agent_id),
                    "session_stats": sdk.get_session_stats(),
                    "state": "sleeping",
                    "sleep_seconds": sleep_seconds,
                    "stop_file": str(stop_path),
                }
                self._write_status(status_path, last_status)
                await self._sleep_with_stop(stop_path, sleep_seconds)

            return last_status
        finally:
            await sdk.disconnect()
            logger.info("Continuous session disconnected for %s", agent.agent_id)

    async def _generate_audited_plan(
        self,
        *,
        generator: Any,
        auditor: PlanAuditor,
        agent: Any,
        context: Any,
        directive: Any,
        recent_other_posts: list[dict[str, Any]],
        recent_self_posts: list[dict[str, Any]],
        db_path: str | None = None,
    ) -> Any | None:
        audit_feedback: list[str] = []
        last_error = ""

        active_reservations: list[dict[str, str | None]] = []
        if db_path:
            active_reservations = await get_active_reservations(db_path, exclude_agent_id=agent.agent_id)

        for _ in range(2):
            try:
                plan = await generator.generate_plan(
                    context=context,
                    directive=directive,
                    recent_other_posts=recent_other_posts,
                    recent_self_posts=recent_self_posts,
                    audit_feedback=audit_feedback,
                )
            except PlanGenerationError as exc:
                last_error = str(exc)
                audit_feedback = [last_error]
                logger.warning("plan generation failed for %s: %s", agent.agent_id, exc)
                continue

            audit = auditor.audit(
                plan,
                agent=agent,
                context=context,
                directive=directive,
                recent_other_posts=recent_other_posts,
                recent_self_posts=recent_self_posts,
                active_reservations=active_reservations,
            )
            if audit.valid:
                return plan

            audit_feedback = audit.messages()
            last_error = "; ".join(audit_feedback)
            logger.warning("plan audit rejected draft for %s: %s", agent.agent_id, last_error)
            if db_path:
                await release_all_agent_reservations(db_path, agent_id=agent.agent_id)
                await release_agent_comment_locks(db_path, agent_id=agent.agent_id)

        logger.error("Unable to produce a valid plan for %s: %s", agent.agent_id, last_error)
        if db_path:
            await release_all_agent_reservations(db_path, agent_id=agent.agent_id)
        return None

    async def _commit_cycle_results(
        self,
        *,
        agent_id: str,
        checkpoint_payload: dict[str, Any],
        plan: AgentPlan,
        execution_results: list[dict[str, Any]],
        daily_targets: dict[str, int],
        timezone_name: str,
        reviewer: SessionReviewer,
        cycle_started_at: str,
        cycle_index: int,
        directive_stage: str,
        sdk: BinanceSquareSDK,
        db_path: str | None = None,
    ) -> tuple[dict[str, Any], Path]:
        commit_state = dict(checkpoint_payload.get("commit_state") or {})
        session_id = str(
            checkpoint_payload.get("session_id")
            or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{agent_id}_cycle{cycle_index:03d}"
        )
        checkpoint_payload["phase"] = "committing"
        checkpoint_payload["session_id"] = session_id

        def persist() -> None:
            checkpoint_payload["commit_state"] = commit_state
            save_execution_checkpoint(agent_id, checkpoint_payload)

        if not commit_state.get("limits_updated"):
            update_limits_from_results(agent_id, execution_results)
            commit_state["limits_updated"] = True
            persist()

        if not commit_state.get("posts_recorded"):
            record_completed_posts(agent_id, plan, execution_results)
            if db_path:
                reservation_keys = [a.reservation_key for a in plan.sorted_actions() if a.reservation_key]
                for key in reservation_keys:
                    await confirm_reservation(db_path, agent_id=agent_id, reservation_key=key)
                # Record news cooldowns for successful news_reaction posts
                actions = plan.sorted_actions()
                for action, result in zip(actions, execution_results):
                    if action.action == "post" and action.post_family == "news_reaction" and result.get("success"):
                        await record_news_cooldown(
                            db_path,
                            agent_id=agent_id,
                            source_url=action.source_url or None,
                            headline=action.visual_title or None,
                        )
            commit_state["posts_recorded"] = True
            persist()

        if not commit_state.get("daily_plan_updated"):
            daily_plan = update_daily_plan_state(
                agent_id,
                execution_results,
                targets=daily_targets,
                timezone_name=timezone_name,
            )
            checkpoint_payload["daily_plan_snapshot"] = daily_plan
            commit_state["daily_plan_updated"] = True
            persist()
        else:
            daily_plan = dict(
                checkpoint_payload.get("daily_plan_snapshot")
                or load_daily_plan_state(
                    agent_id,
                    targets=daily_targets,
                    timezone_name=timezone_name,
                )
            )

        if not commit_state.get("review_written"):
            review_context = await reviewer.review(
                session_id=session_id,
                agent_id=agent_id,
                started_at=cycle_started_at,
                plan=[action.model_dump() for action in plan.sorted_actions()],
                results=execution_results,
                guard_stats=sdk.get_session_stats(),
            )
            review_path = REVIEW_DIR / f"{session_id}.md"
            review_path.write_text(review_context, encoding="utf-8")
            checkpoint_payload["session_review_path"] = str(review_path)
            checkpoint_payload["directive_stage"] = directive_stage
            commit_state["review_written"] = True
            persist()
        else:
            review_path = Path(
                str(checkpoint_payload.get("session_review_path") or REVIEW_DIR / f"{session_id}.md")
            )

        return daily_plan, review_path

    async def _sleep_with_stop(self, stop_path: Path, total_seconds: int) -> None:
        remaining = max(int(total_seconds), 1)
        while remaining > 0:
            if self._should_stop(stop_path):
                return
            await asyncio.sleep(min(remaining, 5))
            remaining -= 5

    def _build_checkpoint_payload(
        self,
        *,
        agent_id: str,
        cycle_index: int,
        cycle_started_at: str,
        directive_stage: str,
        context_files: list[str],
        plan: AgentPlan,
        results: list[dict[str, Any]],
        next_action_index: int,
        plan_date: str,
        timezone_name: str,
    ) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "cycle_index": cycle_index,
            "cycle_started_at": cycle_started_at,
            "directive_stage": directive_stage,
            "context_files": context_files,
            "plan": [action.model_dump() for action in plan.sorted_actions()],
            "results": results,
            "next_action_index": next_action_index,
            "plan_date": plan_date,
            "timezone": timezone_name,
            "updated_at": self._utc_now(),
        }

    def _load_checkpoint_plan(self, payload: dict[str, Any]) -> AgentPlan | None:
        try:
            return AgentPlan(actions=list(payload.get("plan") or []))
        except Exception as exc:
            logger.warning("Failed to load execution checkpoint plan: %s", exc)
            return None

    def _load_settings(self, path: str) -> dict[str, Any]:
        return load_runtime_settings(path)

    def _load_status(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _should_stop(self, stop_path: Path) -> bool:
        return stop_path.exists()

    def _write_status(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()





