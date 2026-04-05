"""Binance Square agent session runner.

Three modes:
  --prepare    Collect context, generate plan skeleton (no text), save to file
  --execute    Load plan with text, re-audit, execute through SDK, commit results
  --continuous Legacy autonomous loop (delegates to ContinuousSessionRunner)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.db.database import get_db_path, init_db
from src.metrics.store import init_metrics_tables
from src.runtime.agent_config import load_active_agent
from src.runtime.comment_coordination import cleanup_expired_comment_locks
from src.runtime.cycle_policy import build_cycle_directive, CycleDirective
from src.runtime.daily_plan import load_daily_plan_state
from src.runtime.deterministic_planner import DeterministicPlanGenerator
from src.runtime.news_cooldown import cleanup_expired_news_cooldowns, record_news_cooldown
from src.runtime.persona_policy import load_persona_policy, apply_coin_bias_overrides
from src.runtime.plan_auditor import PlanAuditor
from src.runtime.plan_executor import PlanExecutor
from src.runtime.plan_io import save_pending_plan, load_plan_for_execution, delete_pending_plan
from src.runtime.platform_limits import update_limits_from_results
from src.runtime.post_registry import (
    get_recent_agent_posts,
    get_recent_other_agent_posts,
    record_completed_posts,
)
from src.runtime.runtime_settings import load_runtime_settings
from src.runtime.session_context import SessionContextBuilder, save_session_context
from src.runtime.session_loop import ContinuousSessionRunner
from src.operator.strategic_bridge import load_strategic_directive
from src.runtime.topic_reservation import (
    cleanup_expired,
    confirm_reservation,
    get_active_reservations,
    release_all_agent_reservations,
)
from src.sdk import BinanceSquareSDK

logger = logging.getLogger("bsq.session.run")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Binance Square agent session.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true", help="Collect context and generate plan skeleton (no text).")
    mode.add_argument("--execute", action="store_true", help="Execute plan with agent-authored text.")
    mode.add_argument("--continuous", action="store_true", help="Legacy autonomous continuous loop.")
    mode.add_argument("--post-only", action="store_true", help="Run post-only validation slots.")
    parser.add_argument("--config", default="config/active_agent.yaml", help="Runtime agent config YAML.")
    parser.add_argument("--settings", default="config/settings.yaml", help="Runtime settings YAML.")
    parser.add_argument("--max-cycles", type=int, default=None, help="Optional cycle limit for continuous mode.")
    parser.add_argument("--stop-file", default=None, help="Optional stop flag path for continuous mode.")
    parser.add_argument("--post-count", type=int, default=1, help="Number of post-only slots to execute.")
    parser.add_argument("--post-delay-min", type=int, default=45, help="Minimum delay between post-only slots.")
    parser.add_argument("--post-delay-max", type=int, default=90, help="Maximum delay between post-only slots.")
    return parser


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


async def init_runtime_state() -> None:
    db_path = get_db_path()
    await init_db(db_path)
    await init_metrics_tables(db_path)


def _load_agent(config_path: str) -> Any:
    """Load agent config with effective_config and persona policy."""
    agent = load_active_agent(config_path)
    agent = agent.effective_config()

    policy_path = Path(f"config/persona_policies/{agent.agent_id}.yaml")
    if policy_path.exists():
        policy = load_persona_policy(policy_path)
        if agent.mode == "individual" and agent.mode_override:
            ovr = agent.mode_override
            policy = apply_coin_bias_overrides(
                policy,
                preferred=ovr.coin_bias_preferred,
                exclude_from_posts=ovr.coin_bias_exclude_from_posts,
            )
        agent._policy = policy
    else:
        agent._policy = None

    return agent


def _build_sdk(agent: Any, settings: dict[str, Any]) -> BinanceSquareSDK:
    return BinanceSquareSDK(
        profile_serial=agent.profile_serial,
        account_id=agent.agent_id,
        max_session_actions=agent.max_session_actions,
        session_minimum=agent.session_minimum.as_dict(),
        profile_username=agent.binance_username or None,
        adspower_base_url=settings.get("adspower_base_url"),
    )


# ---------------------------------------------------------------------------
# --prepare: collect context, generate plan skeleton, save to file
# ---------------------------------------------------------------------------

async def run_prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Collect context, generate plan (no text), save for agent authoring."""
    load_dotenv()
    settings = load_runtime_settings(args.settings)
    agent = _load_agent(args.config)
    await init_runtime_state()
    db_path = get_db_path()

    # Cleanup expired coordination locks
    await cleanup_expired(db_path)
    await cleanup_expired_comment_locks(db_path)
    await cleanup_expired_news_cooldowns(db_path)

    sdk = _build_sdk(agent, settings)
    builder = SessionContextBuilder(agent_dir=agent.agent_dir)
    generator = DeterministicPlanGenerator(agent=agent, sdk=sdk, db_path=db_path)
    auditor = PlanAuditor()

    # Load daily plan for directive adjustment
    daily_targets = agent.session_minimum.as_dict()
    daily_plan = load_daily_plan_state(
        agent.agent_id,
        targets=daily_targets,
        timezone_name=agent.daily_plan_timezone,
    )

    if agent.mode == "test":
        logger.info("TEST MODE: skipping SDK connect for %s", agent.agent_id)
    else:
        await sdk.connect()

    try:
        context = await builder.build(sdk, agent)
        context_files = save_session_context(context)
        directive = build_cycle_directive(agent, context, daily_plan_state=daily_plan)
        recent_other_posts = get_recent_other_agent_posts(agent.agent_id)
        recent_self_posts = get_recent_agent_posts(agent.agent_id)
        active_reservations = await get_active_reservations(db_path, exclude_agent_id=agent.agent_id)

        # Load strategic directive from persona (if available)
        strategic_directive = load_strategic_directive(agent.agent_id)
        if strategic_directive:
            logger.info("Using strategic directive for %s: %s", agent.agent_id, strategic_directive.get("focus_summary", "")[:80])

        # Generate plan (no text — brief_context and target_text only)
        plan = await _generate_audited_plan(
            generator=generator,
            auditor=auditor,
            agent=agent,
            context=context,
            directive=directive,
            recent_other_posts=recent_other_posts,
            recent_self_posts=recent_self_posts,
            active_reservations=active_reservations,
            db_path=db_path,
            strategic_directive=strategic_directive,
        )

        # Save plan for agent to author text
        plan_path = save_pending_plan(
            agent_id=agent.agent_id,
            plan=plan,
            directive=directive,
            context_files=context_files,
        )

        result = {
            "mode": "prepare",
            "agent_id": agent.agent_id,
            "plan_path": plan_path,
            "context_files": context_files,
            "action_count": len(plan.actions),
            "directive_stage": directive.stage,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    finally:
        if agent.mode != "test":
            await sdk.disconnect()


async def _generate_audited_plan(
    *,
    generator: DeterministicPlanGenerator,
    auditor: PlanAuditor,
    agent: Any,
    context: Any,
    directive: CycleDirective,
    recent_other_posts: list[dict[str, Any]],
    recent_self_posts: list[dict[str, Any]],
    active_reservations: list[dict[str, str | None]] | None = None,
    db_path: str | None = None,
    strategic_directive: dict[str, Any] | None = None,
) -> Any:
    """Generate plan with up to 2 audit retries."""
    audit_feedback: list[str] = []
    last_error = "plan generation did not run"

    for attempt_index in range(2):
        try:
            plan = await generator.generate_plan(
                context=context,
                directive=directive,
                recent_other_posts=recent_other_posts,
                recent_self_posts=recent_self_posts,
                audit_feedback=audit_feedback,
                attempt_index=attempt_index,
                strategic_directive=strategic_directive,
            )
        except Exception as exc:
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
            active_reservations=active_reservations or [],
        )
        if audit.valid:
            return plan

        audit_feedback = audit.messages()
        last_error = "; ".join(audit_feedback)
        logger.warning("plan audit rejected draft for %s: %s", agent.agent_id, last_error)
        if db_path:
            await release_all_agent_reservations(db_path, agent_id=agent.agent_id)

    raise RuntimeError(f"unable to produce a valid plan for {agent.agent_id}: {last_error}")


# ---------------------------------------------------------------------------
# --execute: load authored plan, re-audit with text, execute, commit
# ---------------------------------------------------------------------------

async def run_execute(args: argparse.Namespace) -> dict[str, Any]:
    """Load plan with agent-authored text, re-audit, execute, commit."""
    load_dotenv()
    settings = load_runtime_settings(args.settings)
    agent = _load_agent(args.config)
    await init_runtime_state()
    db_path = get_db_path()

    # Load plan and validate text is present
    plan = load_plan_for_execution(agent.agent_id)

    # Re-audit with text (now checks length, paragraphs, similarity, trailing period)
    auditor = PlanAuditor()
    recent_other_posts = get_recent_other_agent_posts(agent.agent_id)
    recent_self_posts = get_recent_agent_posts(agent.agent_id)

    # Build minimal context for audit (directive from plan file)
    from src.runtime.plan_io import load_pending_plan
    plan_data = load_pending_plan(agent.agent_id)
    directive_data = plan_data.get("directive", {})
    directive = CycleDirective(
        stage=directive_data.get("stage", "default"),
        target_comments=directive_data.get("target_comments", 0),
        target_likes=directive_data.get("target_likes", 0),
        target_posts=directive_data.get("target_posts", 0),
        target_follows=directive_data.get("target_follows", 0),
        interval_minutes=(20, 35),
    )

    audit = auditor.audit(
        plan,
        agent=agent,
        context=None,
        directive=directive,
        recent_other_posts=recent_other_posts,
        recent_self_posts=recent_self_posts,
    )
    if not audit.valid:
        error_msg = "; ".join(audit.messages())
        logger.error("Plan re-audit failed for %s: %s", agent.agent_id, error_msg)
        result = {
            "mode": "execute",
            "agent_id": agent.agent_id,
            "success": False,
            "error": f"re-audit failed: {error_msg}",
            "audit_issues": audit.messages(),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    sdk = _build_sdk(agent, settings)
    executor = PlanExecutor(sdk, config_path=args.config, guard=getattr(sdk, '_guard', None))
    if hasattr(agent, '_policy') and agent._policy:
        executor._delay_config = agent._policy.runtime_tuning.delays

    if agent.mode == "test":
        logger.info("TEST MODE: skipping SDK connect for %s", agent.agent_id)
    else:
        await sdk.connect()

    try:
        results = await executor.execute(
            plan,
            dry_run=(agent.mode == "test"),
        )

        # Commit results
        update_limits_from_results(agent.agent_id, results)
        record_completed_posts(agent.agent_id, plan, results)

        # Confirm reservations
        reservation_keys = [a.reservation_key for a in plan.sorted_actions() if a.reservation_key]
        for key in reservation_keys:
            await confirm_reservation(db_path, agent_id=agent.agent_id, reservation_key=key)

        # Record news cooldowns for successful news_reaction posts
        actions = plan.sorted_actions()
        for action, action_result in zip(actions, results):
            if action.action == "post" and action.post_family == "news_reaction" and action_result.get("success"):
                await record_news_cooldown(
                    db_path,
                    agent_id=agent.agent_id,
                    source_url=action.source_url or None,
                    headline=action.visual_title or None,
                )

        # Update daily plan
        from src.runtime.daily_plan import update_daily_plan_state
        update_daily_plan_state(
            agent.agent_id,
            results=results,
            targets=agent.session_minimum.as_dict(),
            timezone_name=agent.daily_plan_timezone,
        )

        # Clean up pending plan
        delete_pending_plan(agent.agent_id)

        # Compute actual success based on mandatory action results
        mandatory_types = {"post", "comment", "quote_repost"}
        mandatory_results = [r for r in results if r.get("action") in mandatory_types]
        mandatory_successes = [r for r in mandatory_results if r.get("success")]
        all_mandatory_failed = bool(mandatory_results) and len(mandatory_successes) == 0

        result = {
            "mode": "execute",
            "agent_id": agent.agent_id,
            "success": not all_mandatory_failed,
            "all_mandatory_failed": all_mandatory_failed,
            "mandatory_attempted": len(mandatory_results),
            "mandatory_succeeded": len(mandatory_successes),
            "results": results,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    finally:
        if agent.mode != "test":
            await sdk.disconnect()


# ---------------------------------------------------------------------------
# --continuous (legacy) and --post-only
# ---------------------------------------------------------------------------

async def run_continuous(args: argparse.Namespace) -> dict[str, Any]:
    runner = ContinuousSessionRunner(
        config_path=args.config,
        settings_path=args.settings,
        max_cycles=args.max_cycles,
        stop_file=args.stop_file,
    )
    return await runner.run()


async def run_post_only(args: argparse.Namespace) -> dict[str, Any]:
    """Legacy post-only mode — uses prepare+execute internally."""
    load_dotenv()
    settings = load_runtime_settings(args.settings)
    agent = _load_agent(args.config)
    await init_runtime_state()

    sdk = _build_sdk(agent, settings)
    executor = PlanExecutor(sdk, config_path=args.config, guard=getattr(sdk, '_guard', None))
    await sdk.connect()

    try:
        # Post-only still uses the old flow since it's legacy
        from src.runtime.deterministic_planner import DeterministicPlanGenerator
        db_path = get_db_path()
        builder = SessionContextBuilder(agent_dir=agent.agent_dir)
        generator = DeterministicPlanGenerator(agent=agent, sdk=sdk, db_path=db_path)
        auditor = PlanAuditor()

        directive = CycleDirective(
            stage="post_only_validation",
            target_comments=0, target_likes=0, target_posts=1, target_follows=0,
            interval_minutes=(1, 2),
            preferred_symbols=list(getattr(agent, "market_symbols", [])),
        )

        slots = []
        for slot_index in range(args.post_count):
            context = await builder.build(sdk, agent)
            context_files = save_session_context(context)
            recent_other = get_recent_other_agent_posts(agent.agent_id)
            recent_self = get_recent_agent_posts(agent.agent_id)
            reservations = await get_active_reservations(db_path, exclude_agent_id=agent.agent_id)
            plan = await _generate_audited_plan(
                generator=generator, auditor=auditor, agent=agent,
                context=context, directive=directive,
                recent_other_posts=recent_other, recent_self_posts=recent_self,
                active_reservations=reservations, db_path=db_path,
            )
            results = await executor.execute(plan)
            update_limits_from_results(agent.agent_id, results)
            record_completed_posts(agent.agent_id, plan, results)
            slots.append({"slot": slot_index + 1, "results": results})
            if slot_index + 1 < args.post_count:
                await asyncio.sleep(random.randint(args.post_delay_min, args.post_delay_max))
        return {"mode": "post_only", "slots": slots}
    finally:
        await sdk.disconnect()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main_async() -> int:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging()

    if args.prepare:
        await run_prepare(args)
    elif args.execute:
        await run_execute(args)
        # Always return 0 — operator reads JSON stdout for actual success
    elif args.post_only:
        await run_post_only(args)
    else:
        await run_continuous(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
