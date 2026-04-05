"""Tests for agent operating modes: standard, individual, test."""

import pytest
from datetime import datetime, timezone, timedelta

from src.runtime.agent_config import ActiveAgentConfig, ModeOverride, SessionMinimumConfig
from src.runtime.cycle_policy import CycleDirective, _apply_individual_overrides
from src.runtime.persona_policy import (
    CoinBias,
    PersonaPolicy,
    RuntimeTuning,
    apply_coin_bias_overrides,
)
from src.runtime.plan_executor import PlanExecutor
from src.runtime.agent_plan import AgentPlan, AgentAction


def _make_agent(**kwargs) -> ActiveAgentConfig:
    defaults = dict(
        agent_id="test_agent",
        binance_username="TestUser",
        profile_serial="1",
        adspower_user_id="test123",
        persona_id="test",
        agent_dir="agents/test",
        account_config_path="config/accounts/test.yaml",
    )
    defaults.update(kwargs)
    return ActiveAgentConfig(**defaults)


def _make_directive(**kwargs) -> CycleDirective:
    defaults = dict(
        stage="default",
        target_comments=5,
        target_likes=7,
        target_posts=1,
        target_follows=1,
        interval_minutes=(20, 35),
    )
    defaults.update(kwargs)
    return CycleDirective(**defaults)


class TestStandardMode:
    def test_default_mode_is_standard(self):
        agent = _make_agent()
        assert agent.mode == "standard"

    def test_effective_config_returns_self_for_standard(self):
        agent = _make_agent()
        assert agent.effective_config() is agent


class TestIndividualMode:
    def test_effective_config_overrides_market_symbols(self):
        agent = _make_agent(
            mode="individual",
            mode_override=ModeOverride(
                label="SOL push",
                market_symbols=["SOL", "JUP"],
            ),
        )
        effective = agent.effective_config()
        assert effective.market_symbols == ["SOL", "JUP"]
        assert effective.agent_id == "test_agent"  # unchanged

    def test_effective_config_merges_session_minimum(self):
        agent = _make_agent(
            mode="individual",
            mode_override=ModeOverride(session_minimum={"post": 5}),
        )
        effective = agent.effective_config()
        assert effective.session_minimum.post == 5
        assert effective.session_minimum.like == 20  # default preserved

    def test_expired_override_falls_back_to_standard(self):
        agent = _make_agent(
            mode="individual",
            mode_override=ModeOverride(
                label="expired",
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                market_symbols=["EXPIRED"],
            ),
        )
        effective = agent.effective_config()
        assert "EXPIRED" not in effective.market_symbols

    def test_directive_overrides_targets(self):
        agent = _make_agent(
            mode="individual",
            mode_override=ModeOverride(
                label="focus",
                target_posts_override=3,
                style_notes=["focus on memes"],
            ),
        )
        directive = _make_directive(target_posts=1)
        result = _apply_individual_overrides(directive, agent)
        assert result.target_posts == 3
        assert result.target_comments == 5  # unchanged
        assert "focus on memes" in result.style_notes

    def test_directive_unchanged_for_standard(self):
        agent = _make_agent()
        directive = _make_directive()
        result = _apply_individual_overrides(directive, agent)
        assert result is directive


class TestTestMode:
    def test_dry_run_returns_all_actions(self):
        executor = PlanExecutor(sdk=None, guard=None)
        plan = AgentPlan(actions=[
            AgentAction(action="comment", priority=1, reason="test", target="123", text="hello"),
            AgentAction(action="like", priority=2, reason="test", target="456"),
        ])
        results = executor._dry_run(plan)
        assert len(results) == 2
        assert all(r["success"] for r in results)
        assert all(r["response"]["dry_run"] for r in results)
        assert executor.last_completed is True

    @pytest.mark.asyncio
    async def test_executor_skips_action_without_text(self):
        executor = PlanExecutor(sdk=None, guard=None)
        plan = AgentPlan(actions=[
            AgentAction(action="comment", priority=1, reason="test", target="123", target_text="some post"),
            AgentAction(action="like", priority=2, reason="test", target="456"),
        ])
        results = await executor.execute(plan)
        comment_result = next(r for r in results if r["action"] == "comment")
        assert comment_result["success"] is False
        assert "text not provided" in comment_result["response"]["error"]


class TestCoinBiasOverride:
    def test_apply_coin_bias_overrides(self):
        # Create a minimal policy with frozen dataclass
        from src.runtime.persona_policy import (
            MarketAngleRules, CommentStanceConfig, FeedScoring,
            OverflowConfig, AuditStyle,
        )
        policy = PersonaPolicy(
            family_score_adjustments={},
            coin_bias=CoinBias(
                preferred=["BTC", "ETH"],
                preferred_bonus=70.0,
                other_bonus=20.0,
                excluded_penalty=0.0,
                exclude_from_posts=[],
            ),
            market_angle_rules=MarketAngleRules(
                high_change_threshold=2.0,
                high_change_angle="rotation",
                low_change_angle="ta",
                major_coins_angle="macro",
                major_coins=[],
            ),
            news_keyword_affinity={},
            default_news_angle="psychology",
            default_editorial_angle="observation",
            default_chart_timeframe="4H",
            timeframe_overrides={},
            structures={},
            openings={},
            hooks={},
            insights={},
            closes={},
        context_line_templates={},
            comment_stance=CommentStanceConfig(mode="coin_type", alt_priority=[], major_priority=[], angle_stances={}),
            feed_scoring=FeedScoring(keyword_bonuses={}, keyword_penalties={}, symbol_bonus=0.0, symbol_penalty=0.0),
            comment_tier_rules=[],
            stages={},
            stage_selection_rules=[],
            overflow=OverflowConfig(target_comments=2, target_likes=4, target_posts=0, target_follows=1, reply_limited_comments=0),
            audit_style=AuditStyle(min_post_length=70, min_paragraphs_market=0, reject_coins_for_market=[], stage_rules={}),
        )
        updated = apply_coin_bias_overrides(policy, preferred=["SOL", "JUP"])
        assert updated.coin_bias.preferred == ["SOL", "JUP"]
        assert updated.coin_bias.preferred_bonus == 70.0  # unchanged

    def test_no_op_when_none(self):
        from src.runtime.persona_policy import (
            MarketAngleRules, CommentStanceConfig, FeedScoring,
            OverflowConfig, AuditStyle,
        )
        policy = PersonaPolicy(
            family_score_adjustments={},
            coin_bias=CoinBias(preferred=["BTC"], preferred_bonus=70.0, other_bonus=20.0, excluded_penalty=0.0, exclude_from_posts=[]),
            market_angle_rules=MarketAngleRules(high_change_threshold=2.0, high_change_angle="r", low_change_angle="t", major_coins_angle="m", major_coins=[]),
            news_keyword_affinity={}, default_news_angle="p", default_editorial_angle="o",
            default_chart_timeframe="4H", timeframe_overrides={},
            structures={}, openings={}, hooks={}, insights={}, closes={}, context_line_templates={},
            comment_stance=CommentStanceConfig(mode="coin_type", alt_priority=[], major_priority=[], angle_stances={}),
            feed_scoring=FeedScoring(keyword_bonuses={}, keyword_penalties={}, symbol_bonus=0.0, symbol_penalty=0.0),
            comment_tier_rules=[], stages={}, stage_selection_rules=[],
            overflow=OverflowConfig(target_comments=2, target_likes=4, target_posts=0, target_follows=1, reply_limited_comments=0),
            audit_style=AuditStyle(min_post_length=70, min_paragraphs_market=0, reject_coins_for_market=[], stage_rules={}),
        )
        result = apply_coin_bias_overrides(policy)
        assert result is policy
