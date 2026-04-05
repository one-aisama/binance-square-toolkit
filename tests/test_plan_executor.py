from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from src.runtime.agent_plan import AgentPlan
from src.runtime.guard import Verdict, GuardDecision
from src.runtime.plan_executor import PlanExecutor
from src.runtime.visual_pipeline import ResolvedVisual


@pytest.mark.asyncio
async def test_execute_post_prefers_chart_card_over_implicit_screenshot():
    sdk = MagicMock()
    sdk.create_post = AsyncMock(return_value={"success": True, "post_id": "1"})
    sdk.screenshot_chart = AsyncMock(return_value="data/screenshots/btc.png")

    executor = PlanExecutor(sdk)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish a clean market take",
                "text": "$BTC still looks reactive here and the bounce still needs proof\n\nbest trades lately are the ones with smaller ego #BTC #Bitcoin",
                "coin": "BTC",
                "chart_symbol": "BTC_USDT",
            }
        ]
    )

    results = await executor.execute(plan)

    sdk.screenshot_chart.assert_not_awaited()
    sdk.create_post.assert_awaited_once_with(
        text=plan.actions[0].text,
        coin="BTC",
        sentiment=None,
        image_path=None,
        recent_posts=ANY,
    )
    assert results[0]["success"] is True


@pytest.mark.asyncio
async def test_execute_post_uses_explicit_chart_image_when_requested():
    sdk = MagicMock()
    sdk.create_post = AsyncMock(return_value={"success": True, "post_id": "1"})
    sdk.screenshot_chart = AsyncMock(return_value="data/screenshots/btc.png")

    executor = PlanExecutor(sdk)
    executor._human_delay = AsyncMock()
    executor._visuals.resolve = AsyncMock(
        return_value=ResolvedVisual(
            path="C:/tmp/chart.png",
            kind="chart_capture",
            signature="chartsig",
        )
    )
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish a chart-focused setup",
                "text": "$BTC still looks reactive here and the bounce still needs proof\n\nbest trades lately are the ones with smaller ego #BTC #Bitcoin",
                "chart_symbol": "BTC_USDT",
                "chart_timeframe": "1D",
                "chart_image": True,
            }
        ]
    )

    results = await executor.execute(plan)

    sdk.create_post.assert_awaited_once_with(
        text=plan.actions[0].text,
        coin=None,
        sentiment=None,
        image_path="C:/tmp/chart.png",
        recent_posts=ANY,
    )
    assert results[0]["success"] is True


@pytest.mark.asyncio
async def test_execute_post_uses_generated_visual_kind():
    sdk = MagicMock()
    sdk.create_post = AsyncMock(return_value={"success": True, "post_id": "1"})

    executor = PlanExecutor(sdk)
    executor._human_delay = AsyncMock()
    executor._visuals.resolve = AsyncMock(
        return_value=ResolvedVisual(
            path="C:/tmp/news_card.png",
            kind="news_card",
            signature="sig123",
        )
    )
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish a news reaction",
                "text": "the headline is loud but the second move matters more\n\nthat is where the tape stops borrowing conviction",
                "visual_kind": "news_card",
                "post_family": "news_reaction",
                "visual_title": "ETF flows wobble again",
            }
        ]
    )

    results = await executor.execute(plan)

    sdk.create_post.assert_awaited_once_with(
        text=plan.actions[0].text,
        coin=None,
        sentiment=None,
        image_path="C:/tmp/news_card.png",
        recent_posts=ANY,
    )
    assert results[0]["response"]["resolved_visual"]["kind"] == "news_card"


@pytest.mark.asyncio
async def test_execute_can_pause_before_next_action_for_resume():
    sdk = MagicMock()
    sdk.like_post = AsyncMock(return_value={"success": True})

    executor = PlanExecutor(sdk)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(
        actions=[
            {"action": "like", "priority": 1, "reason": "first", "target": "1"},
            {"action": "like", "priority": 2, "reason": "second", "target": "2"},
        ]
    )

    stop_checks = iter([False, True])
    results = await executor.execute(plan, should_stop=lambda: next(stop_checks, True))

    assert len(results) == 1
    assert executor.last_completed is False
    assert executor.last_next_action_index == 1
    sdk.like_post.assert_awaited_once_with("1")


@pytest.mark.asyncio
async def test_execute_can_resume_from_saved_action_index():
    sdk = MagicMock()
    sdk.like_post = AsyncMock(return_value={"success": True})

    executor = PlanExecutor(sdk)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(
        actions=[
            {"action": "like", "priority": 1, "reason": "first", "target": "1"},
            {"action": "like", "priority": 2, "reason": "second", "target": "2"},
        ]
    )
    existing_results = [
        {
            "action": "like",
            "target": "1",
            "target_author": None,
            "priority": 1,
            "reason": "first",
            "success": True,
            "response": {"success": True},
        }
    ]

    results = await executor.execute(plan, start_index=1, existing_results=existing_results)

    assert len(results) == 2
    assert executor.last_completed is True
    assert executor.last_next_action_index == 2
    sdk.like_post.assert_awaited_once_with("2")




def test_executor_uses_agent_specific_config_path_for_visuals():
    sdk = MagicMock()
    with patch("src.runtime.plan_executor.VisualPipeline") as visual_cls:
        PlanExecutor(sdk, config_path="config/active_agent.example_altcoin.yaml")

    visual_cls.assert_called_once_with(sdk, config_path="config/active_agent.example_altcoin.yaml")


def _make_sdk_and_guard(verdict: Verdict, **kwargs):
    """Create a mock SDK + guard returning the given verdict."""
    sdk = MagicMock()
    sdk.like_post = AsyncMock(return_value={"success": True})
    sdk.comment_on_post = AsyncMock(return_value={"success": True})
    guard = MagicMock()
    guard.check = AsyncMock(return_value=GuardDecision(verdict=verdict, **kwargs))
    guard.record = MagicMock()
    return sdk, guard


@pytest.mark.asyncio
async def test_executor_skips_denied_action():
    sdk, guard = _make_sdk_and_guard(Verdict.DENIED, reason="Daily limit reached", fallback_action="comment")

    executor = PlanExecutor(sdk, guard=guard)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(actions=[
        {"action": "like", "priority": 1, "reason": "test", "target": "1"},
    ])

    results = await executor.execute(plan)

    assert len(results) == 1
    assert results[0]["success"] is False
    assert results[0]["response"]["guard"] == "denied"
    sdk.like_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_stops_on_session_over():
    sdk, guard = _make_sdk_and_guard(Verdict.SESSION_OVER, reason="3 types broken")

    executor = PlanExecutor(sdk, guard=guard)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(actions=[
        {"action": "like", "priority": 1, "reason": "first", "target": "1"},
        {"action": "like", "priority": 2, "reason": "second", "target": "2"},
    ])

    results = await executor.execute(plan)

    assert len(results) == 1
    assert results[0]["response"]["guard"] == "session_over"
    assert executor.last_completed is False
    sdk.like_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_waits_on_cooldown():
    sdk = MagicMock()
    sdk.like_post = AsyncMock(return_value={"success": True})
    guard = MagicMock()
    guard.check = AsyncMock(side_effect=[
        GuardDecision(verdict=Verdict.WAIT, wait_seconds=0.01),
        GuardDecision(verdict=Verdict.ALLOW),
    ])
    guard.record = MagicMock()

    executor = PlanExecutor(sdk, guard=guard)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(actions=[
        {"action": "like", "priority": 1, "reason": "test", "target": "1"},
    ])

    results = await executor.execute(plan)

    assert len(results) == 1
    assert results[0]["success"] is True
    assert guard.check.await_count == 2
    sdk.like_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_executor_does_not_double_record_to_guard():
    """Guard.record() is NOT called by PlanExecutor — SDK handles recording internally."""
    sdk, guard = _make_sdk_and_guard(Verdict.ALLOW)

    executor = PlanExecutor(sdk, guard=guard)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(actions=[
        {"action": "like", "priority": 1, "reason": "test", "target": "1"},
    ])

    await executor.execute(plan)

    guard.record.assert_not_called()


@pytest.mark.asyncio
async def test_executor_denied_after_wait():
    """WAIT re-check returns DENIED → action skipped with guard='denied_after_wait'."""
    sdk = MagicMock()
    sdk.like_post = AsyncMock(return_value={"success": True})
    guard = MagicMock()
    guard.check = AsyncMock(side_effect=[
        GuardDecision(verdict=Verdict.WAIT, wait_seconds=0.01),
        GuardDecision(verdict=Verdict.DENIED, reason="still blocked"),
    ])
    guard.record = MagicMock()

    executor = PlanExecutor(sdk, guard=guard)
    executor._human_delay = AsyncMock()
    plan = AgentPlan(actions=[
        {"action": "like", "priority": 1, "reason": "test", "target": "1"},
    ])

    results = await executor.execute(plan)

    assert len(results) == 1
    assert results[0]["success"] is False
    assert results[0]["response"]["guard"] == "denied_after_wait"
    sdk.like_post.assert_not_awaited()
