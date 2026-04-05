"""Persona policy: config-driven agent personality for the runtime layer.

Replaces all `if agent_id == ...` branches with a single policy object
loaded from YAML at startup. Adding a new agent = new YAML file, zero Python.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("bsq.persona_policy")


@dataclass(frozen=True)
class CoinBias:
    preferred: list[str]
    preferred_bonus: float
    other_bonus: float
    excluded_penalty: float  # negative number, e.g. -400.0
    exclude_from_posts: list[str]  # symbols to exclude from original posts


@dataclass(frozen=True)
class MarketAngleRules:
    high_change_threshold: float  # e.g. 2.0
    high_change_angle: str  # e.g. "rotation"
    low_change_angle: str  # e.g. "ta"
    major_coins_angle: str  # e.g. "macro"
    major_coins: list[str]  # e.g. ["BTC", "ETH", "BNB"]


@dataclass(frozen=True)
class StageConfig:
    target_comments: int
    target_likes: int
    target_posts: int
    target_follows: int
    avoid_primary_symbols: list[str] = field(default_factory=list)
    article_policy: str = "disabled"
    style_notes: list[str] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)
    audit_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StageSelectionRule:
    """One rule in the ordered list of stage selection conditions."""
    condition: str  # "reply_limited", "bootstrap", "default"
    stage_name: str
    min_followers: int = 0
    min_following: int = 0


@dataclass(frozen=True)
class OverflowConfig:
    target_comments: int
    target_likes: int
    target_posts: int
    target_follows: int
    reply_limited_comments: int  # override for reply-limited stage


@dataclass(frozen=True)
class AuditStyle:
    min_post_length: int
    min_paragraphs_market: int  # min paragraphs for market_chart posts (0 = no check)
    reject_coins_for_market: list[str]  # coins to reject in market_chart posts
    stage_rules: dict[str, list[str]]  # stage_name → list of rule descriptions


@dataclass(frozen=True)
class CommentStanceConfig:
    mode: str  # "coin_type" or "angle_based"
    alt_priority: list[str]  # stance order when alt coin present
    major_priority: list[str]  # stance order when major/no coin
    angle_stances: dict[str, list[str]]  # angle → stance order (for angle_based mode)


@dataclass(frozen=True)
class FeedScoring:
    keyword_bonuses: dict[str, float]  # keyword → bonus
    keyword_penalties: dict[str, float]  # keyword → penalty (negative)
    symbol_bonus: float  # bonus for preferred symbols
    symbol_penalty: float  # penalty for non-preferred symbols


@dataclass(frozen=True)
class CommentTierRule:
    """One rule for comment target tier assignment."""
    tier: int
    condition: str  # "reason_contains", "symbol_not_major_and_market", "reason_any", "domain_in", "symbol_and_market"
    values: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SimilarityThresholds:
    """Thresholds for content diversity checks in PlanAuditor."""
    comment_diversity: float = 0.82
    self_novelty_text: float = 0.58
    self_novelty_relaxed: float = 0.52
    feed_novelty_format: float = 0.45
    feed_novelty_coin: float = 0.50


@dataclass(frozen=True)
class DelayConfig:
    """Human-like delay distribution for behavior.py and plan_executor.py."""
    # Weighted delay buckets: (cumulative_probability, min_sec, max_sec)
    buckets: list[tuple[float, float, float]] = field(
        default_factory=lambda: [(0.60, 20, 35), (0.85, 35, 60), (0.95, 60, 90), (1.0, 5, 10)]
    )
    idle_visit_probability: float = 0.25
    post_action_delay_min: float = 8.0
    post_action_delay_max: float = 15.0
    light_action_delay_min: float = 3.0
    light_action_delay_max: float = 7.0


@dataclass(frozen=True)
class FeedCollectionConfig:
    """Feed collection and filtering parameters."""
    primary_limit: int = 60
    secondary_limit: int = 30
    min_text_length: int = 40
    max_text_length: int = 400
    spam_words: list[str] = field(
        default_factory=lambda: [
            "gift", "giveaway", "airdrop", "copy trading",
            "free crypto", "claim", "join my vip", "signal group",
        ]
    )


@dataclass(frozen=True)
class ContentLengthConfig:
    """Min/max text lengths for posts and comments."""
    min_post_length: int = 80
    min_comment_length: int = 15


@dataclass(frozen=True)
class ScoringConfig:
    """Scoring penalties and bonuses for editorial_brain."""
    family_repetition_penalty: float = 60.0
    symbol_self_overlap_penalty: float = 220.0
    news_url_overlap_penalty: float = 500.0
    news_title_overlap_penalty: float = 450.0
    feed_source_overlap_penalty: float = 300.0
    news_cooldown_penalty: float = 300.0


@dataclass(frozen=True)
class RuntimeTuning:
    """All tunable runtime parameters with sensible defaults.

    Added to PersonaPolicy as optional — existing YAMLs work without changes.
    """
    similarity: SimilarityThresholds = field(default_factory=SimilarityThresholds)
    delays: DelayConfig = field(default_factory=DelayConfig)
    feed: FeedCollectionConfig = field(default_factory=FeedCollectionConfig)
    content_length: ContentLengthConfig = field(default_factory=ContentLengthConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)


@dataclass(frozen=True)
class PersonaPolicy:
    """Complete persona configuration — replaces all if agent_id branches."""

    # --- Family scoring ---
    family_score_adjustments: dict[str, float]

    # --- Coin preferences ---
    coin_bias: CoinBias

    # --- Market angle ---
    market_angle_rules: MarketAngleRules

    # --- News keyword affinity ---
    news_keyword_affinity: dict[str, float]

    # --- Default angles ---
    default_news_angle: str
    default_editorial_angle: str

    # --- Timeframe ---
    default_chart_timeframe: str
    timeframe_overrides: dict[str, str]

    # --- Structures and openings per post_family ---
    structures: dict[str, list[str]]
    openings: dict[str, list[str]]

    # --- Text templates: hooks, insights, closes ---
    hooks: dict[str, dict[str, str]]  # family → {opening_mode → template}
    insights: dict[str, dict[str, str]]  # family → {condition → template}
    closes: dict[str, dict[str, str]]  # family → {condition → template}

    # --- Context line templates ---
    context_line_templates: dict[str, list[str]]

    # --- Comment stance ---
    comment_stance: CommentStanceConfig

    # --- Feed scoring ---
    feed_scoring: FeedScoring

    # --- Comment tier rules ---
    comment_tier_rules: list[CommentTierRule]

    # --- Cycle stages ---
    stages: dict[str, StageConfig]
    stage_selection_rules: list[StageSelectionRule]
    overflow: OverflowConfig

    # --- Audit style ---
    audit_style: AuditStyle

    # --- Runtime tuning (optional, defaults for all) ---
    runtime_tuning: RuntimeTuning = field(default_factory=RuntimeTuning)


def _load_runtime_tuning(raw: dict[str, Any]) -> RuntimeTuning:
    """Parse runtime_tuning from YAML, falling back to defaults."""
    rt = raw.get("runtime_tuning")
    if not rt:
        return RuntimeTuning()
    return RuntimeTuning(
        similarity=SimilarityThresholds(**rt["similarity"]) if "similarity" in rt else SimilarityThresholds(),
        delays=DelayConfig(
            **{k: (v if k != "buckets" else [tuple(b) for b in v]) for k, v in rt["delays"].items()}
        ) if "delays" in rt else DelayConfig(),
        feed=FeedCollectionConfig(**rt["feed"]) if "feed" in rt else FeedCollectionConfig(),
        content_length=ContentLengthConfig(**rt["content_length"]) if "content_length" in rt else ContentLengthConfig(),
        scoring=ScoringConfig(**rt["scoring"]) if "scoring" in rt else ScoringConfig(),
    )


def load_persona_policy(path: str | Path) -> PersonaPolicy:
    """Load persona policy from a YAML file."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    coin = raw["coin_bias"]
    market_angle = raw["market_angle_rules"]
    stance = raw["comment_stance"]
    feed = raw["feed_scoring"]
    overflow = raw["overflow"]
    audit = raw["audit_style"]

    return PersonaPolicy(
        family_score_adjustments=raw["family_score_adjustments"],
        coin_bias=CoinBias(
            preferred=coin["preferred"],
            preferred_bonus=coin["preferred_bonus"],
            other_bonus=coin["other_bonus"],
            excluded_penalty=coin.get("excluded_penalty", 0.0),
            exclude_from_posts=coin.get("exclude_from_posts", []),
        ),
        market_angle_rules=MarketAngleRules(
            high_change_threshold=market_angle["high_change_threshold"],
            high_change_angle=market_angle["high_change_angle"],
            low_change_angle=market_angle["low_change_angle"],
            major_coins_angle=market_angle["major_coins_angle"],
            major_coins=market_angle.get("major_coins", []),
        ),
        news_keyword_affinity=raw.get("news_keyword_affinity", {}),
        default_news_angle=raw["default_news_angle"],
        default_editorial_angle=raw["default_editorial_angle"],
        default_chart_timeframe=raw["default_chart_timeframe"],
        timeframe_overrides=raw.get("timeframe_overrides", {}),
        structures=raw["structures"],
        openings=raw["openings"],
        hooks=raw["hooks"],
        insights=raw["insights"],
        closes=raw["closes"],
        context_line_templates=raw.get("context_line_templates", {}),
        comment_stance=CommentStanceConfig(
            mode=stance["mode"],
            alt_priority=stance.get("alt_priority", []),
            major_priority=stance.get("major_priority", []),
            angle_stances=stance.get("angle_stances", {}),
        ),
        feed_scoring=FeedScoring(
            keyword_bonuses=feed.get("keyword_bonuses", {}),
            keyword_penalties=feed.get("keyword_penalties", {}),
            symbol_bonus=feed.get("symbol_bonus", 0.0),
            symbol_penalty=feed.get("symbol_penalty", 0.0),
        ),
        comment_tier_rules=[
            CommentTierRule(
                tier=r["tier"],
                condition=r["condition"],
                values=r.get("values", []),
            )
            for r in raw.get("comment_tier_rules", [])
        ],
        stages={
            name: StageConfig(**cfg)
            for name, cfg in raw.get("stages", {}).items()
        },
        stage_selection_rules=[
            StageSelectionRule(**r) for r in raw.get("stage_selection_rules", [])
        ],
        overflow=OverflowConfig(
            target_comments=overflow.get("target_comments", 2),
            target_likes=overflow.get("target_likes", 4),
            target_posts=overflow.get("target_posts", 0),
            target_follows=overflow.get("target_follows", 1),
            reply_limited_comments=overflow.get("reply_limited_comments", 0),
        ),
        audit_style=AuditStyle(
            min_post_length=audit.get("min_post_length", 70),
            min_paragraphs_market=audit.get("min_paragraphs_market", 0),
            reject_coins_for_market=audit.get("reject_coins_for_market", []),
            stage_rules=audit.get("stage_rules", {}),
        ),
        runtime_tuning=_load_runtime_tuning(raw),
    )


def apply_coin_bias_overrides(
    policy: PersonaPolicy,
    *,
    preferred: list[str] | None = None,
    exclude_from_posts: list[str] | None = None,
) -> PersonaPolicy:
    """Return a new PersonaPolicy with coin_bias overrides applied."""
    if preferred is None and exclude_from_posts is None:
        return policy
    from dataclasses import replace
    new_bias = replace(
        policy.coin_bias,
        preferred=preferred if preferred is not None else policy.coin_bias.preferred,
        exclude_from_posts=exclude_from_posts if exclude_from_posts is not None else policy.coin_bias.exclude_from_posts,
    )
    return replace(policy, coin_bias=new_bias)
