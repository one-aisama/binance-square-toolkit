from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from src.runtime.daily_plan import is_daily_plan_complete, remaining_daily_targets
from src.runtime.platform_limits import is_reply_limited


@dataclass(frozen=True)
class CycleDirective:
    """Agent-specific operating directive for a single autonomous cycle."""

    stage: str
    target_comments: int
    target_likes: int
    target_posts: int
    target_follows: int
    interval_minutes: tuple[int, int]
    preferred_symbols: list[str] = field(default_factory=list)
    avoid_primary_symbols: list[str] = field(default_factory=list)
    article_policy: str = "disabled"
    style_notes: list[str] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)
    audit_notes: list[str] = field(default_factory=list)


def choose_sleep_seconds(
    interval_minutes: tuple[int, int],
    *,
    minimum_met: bool,
    randint_fn: Any = random.randint,
) -> int:
    """Choose next sleep duration in seconds."""
    low, high = interval_minutes
    if minimum_met:
        low = max(low, high)
        high = max(high, low + 10)
    return int(randint_fn(low * 60, high * 60))


def build_cycle_directive(agent: Any, context: Any, daily_plan_state: dict[str, Any] | None = None) -> CycleDirective:
    """Build stage-aware directives from agent identity and current profile state."""
    followers = _extract_metric(context.my_stats, "followers")
    following = _extract_metric(context.my_stats, "following")
    preferred_symbols = list(getattr(agent, "market_symbols", []))
    interval = tuple(getattr(agent, "cycle_interval_minutes", [20, 35]))
    policy = getattr(agent, "_policy", None)

    if policy and policy.stage_selection_rules:
        stage_name = _select_stage(policy, agent.agent_id, followers, following)
        stage_cfg = policy.stages.get(stage_name)
        if stage_cfg:
            exclude = set(stage_cfg.avoid_primary_symbols)
            filtered_symbols = [s for s in preferred_symbols if s not in exclude] or preferred_symbols
            directive = CycleDirective(
                stage=stage_name,
                target_comments=stage_cfg.target_comments,
                target_likes=stage_cfg.target_likes,
                target_posts=stage_cfg.target_posts,
                target_follows=stage_cfg.target_follows,
                interval_minutes=interval,
                preferred_symbols=filtered_symbols,
                avoid_primary_symbols=stage_cfg.avoid_primary_symbols,
                article_policy=stage_cfg.article_policy,
                style_notes=stage_cfg.style_notes,
                source_notes=stage_cfg.source_notes,
                audit_notes=stage_cfg.audit_notes,
            )
            directive = _apply_individual_overrides(directive, agent)
            return _apply_daily_plan_window(agent, directive, daily_plan_state, policy)

    # Fallback: default stage
    directive = CycleDirective(
        stage="default",
        target_comments=5,
        target_likes=7,
        target_posts=1,
        target_follows=1,
        interval_minutes=interval,
        preferred_symbols=preferred_symbols,
        avoid_primary_symbols=[],
        article_policy="rare",
        style_notes=[],
        source_notes=[],
        audit_notes=[],
    )
    directive = _apply_individual_overrides(directive, agent)
    return _apply_daily_plan_window(agent, directive, daily_plan_state, policy)


def _apply_individual_overrides(directive: CycleDirective, agent: Any) -> CycleDirective:
    """Apply individual-mode target overrides from agent.mode_override."""
    if getattr(agent, "mode", "standard") != "individual":
        return directive
    ovr = getattr(agent, "mode_override", None)
    if not ovr:
        return directive
    return CycleDirective(
        stage=directive.stage,
        target_comments=ovr.target_comments_override if ovr.target_comments_override is not None else directive.target_comments,
        target_likes=ovr.target_likes_override if ovr.target_likes_override is not None else directive.target_likes,
        target_posts=ovr.target_posts_override if ovr.target_posts_override is not None else directive.target_posts,
        target_follows=directive.target_follows,
        interval_minutes=directive.interval_minutes,
        preferred_symbols=directive.preferred_symbols,
        avoid_primary_symbols=directive.avoid_primary_symbols,
        article_policy=directive.article_policy,
        style_notes=directive.style_notes + list(ovr.style_notes or []),
        source_notes=directive.source_notes,
        audit_notes=directive.audit_notes + [f"individual mode: {ovr.label}"] if ovr.label else directive.audit_notes,
    )


def _select_stage(policy: Any, agent_id: str, followers: int, following: int) -> str:
    """Walk ordered stage_selection_rules to find the matching stage."""
    for rule in policy.stage_selection_rules:
        if rule.condition == "reply_limited":
            if is_reply_limited(agent_id):
                return rule.stage_name
        elif rule.condition == "bootstrap":
            if followers < rule.min_followers or following < rule.min_following:
                return rule.stage_name
        elif rule.condition == "default":
            return rule.stage_name
    return policy.stage_selection_rules[-1].stage_name if policy.stage_selection_rules else "default"


def _apply_daily_plan_window(
    agent: Any,
    directive: CycleDirective,
    daily_plan_state: dict[str, Any] | None,
    policy: Any = None,
) -> CycleDirective:
    if not daily_plan_state:
        return directive

    if is_daily_plan_complete(daily_plan_state):
        return _build_overflow_directive(agent, directive, daily_plan_state, policy)

    remaining = remaining_daily_targets(daily_plan_state)
    return CycleDirective(
        stage=directive.stage,
        target_comments=min(directive.target_comments, remaining.get("comment", directive.target_comments)),
        target_likes=min(directive.target_likes, remaining.get("like", directive.target_likes)),
        target_posts=min(directive.target_posts, remaining.get("post", directive.target_posts)),
        target_follows=directive.target_follows,
        interval_minutes=directive.interval_minutes,
        preferred_symbols=directive.preferred_symbols,
        avoid_primary_symbols=directive.avoid_primary_symbols,
        article_policy=directive.article_policy,
        style_notes=directive.style_notes,
        source_notes=directive.source_notes,
        audit_notes=directive.audit_notes + [f"daily remaining targets: {remaining}"],
    )


def _build_overflow_directive(
    agent: Any,
    directive: CycleDirective,
    daily_plan_state: dict[str, Any],
    policy: Any = None,
) -> CycleDirective:
    remaining = remaining_daily_targets(daily_plan_state)
    if policy and policy.overflow:
        overflow = policy.overflow
        is_reply_limited_stage = "reply_limited" in directive.stage
        target_comments = overflow.reply_limited_comments if is_reply_limited_stage else overflow.target_comments
        return CycleDirective(
            stage=f"{directive.stage}_overflow",
            target_comments=target_comments,
            target_likes=overflow.target_likes,
            target_posts=overflow.target_posts,
            target_follows=overflow.target_follows,
            interval_minutes=directive.interval_minutes,
            preferred_symbols=directive.preferred_symbols,
            avoid_primary_symbols=directive.avoid_primary_symbols,
            article_policy="disabled",
            style_notes=directive.style_notes + ["daily plan is already complete so focus on clean growth actions"],
            source_notes=directive.source_notes,
            audit_notes=directive.audit_notes + [f"daily plan already completed today; remaining targets now {remaining}"],
        )

    return CycleDirective(
        stage=f"{directive.stage}_overflow",
        target_comments=2,
        target_likes=4,
        target_posts=0,
        target_follows=1,
        interval_minutes=directive.interval_minutes,
        preferred_symbols=directive.preferred_symbols,
        avoid_primary_symbols=directive.avoid_primary_symbols,
        article_policy="disabled",
        style_notes=directive.style_notes + ["daily plan is already complete so focus on visibility and relationships"],
        source_notes=directive.source_notes,
        audit_notes=directive.audit_notes + [f"daily plan already completed today; remaining targets now {remaining}"],
    )


def _extract_metric(payload: Any, key: str) -> int:
    if isinstance(payload, dict):
        if key in payload:
            return _coerce_int(payload.get(key))
        for value in payload.values():
            extracted = _extract_metric(value, key)
            if extracted:
                return extracted
    if isinstance(payload, list):
        for item in payload:
            extracted = _extract_metric(item, key)
            if extracted:
                return extracted
    return 0


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
