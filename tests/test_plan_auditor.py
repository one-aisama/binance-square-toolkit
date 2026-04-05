from types import SimpleNamespace

from src.runtime.agent_plan import AgentPlan
from src.runtime.plan_auditor import PlanAuditor
from tests.helpers import make_agent


class DummyContext:
    def __init__(self, my_stats):
        self.my_stats = my_stats


def test_auditor_requires_follow_for_example_altcoin_bootstrap(monkeypatch):
    monkeypatch.setattr("src.runtime.plan_auditor.should_attach_image", lambda agent_id: False)

    auditor = PlanAuditor()
    plan = AgentPlan(
        actions=[
            {
                "action": "comment",
                "target": "123",
                "priority": 1,
                "reason": "join thread",
                "text": "sol looks cleaner than the narrative here",
                "like": True,
            },
            {
                "action": "comment",
                "target": "456",
                "priority": 1,
                "reason": "join thread",
                "text": "the breakout only matters if bids stay real",
                "like": True,
            },
            {
                "action": "comment",
                "target": "789",
                "priority": 2,
                "reason": "join thread",
                "text": "rotation looks early but not fake yet",
                "like": True,
            },
            {
                "action": "post",
                "priority": 3,
                "reason": "publish alt take",
                "text": "$SOL still looks cleaner than the crowd gives it credit for\n\nrelative strength matters more than noise #SOL",
                "chart_symbol": "SOL_USDT",
                "visual_kind": "chart_capture",
                "post_family": "market_chart",
                "editorial_angle": "rotation",
                "editorial_format": "spotlight",
            },
        ]
    )
    agent = make_agent("example_altcoin")
    directive = SimpleNamespace(stage="bootstrap_graph", target_posts=1)
    context = DummyContext({"followers": 0, "following": 0})

    result = auditor.audit(
        plan,
        agent=agent,
        context=context,
        directive=directive,
        recent_other_posts=[],
        recent_self_posts=[],
    )

    assert result.valid is False
    assert any("follow action" in message for message in result.messages())


def test_auditor_blocks_trailing_periods(monkeypatch):
    monkeypatch.setattr("src.runtime.plan_auditor.should_attach_image", lambda agent_id: False)

    auditor = PlanAuditor()
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish take",
                "text": "$BTC still looks heavy here.\n\nthat reclaim still needs proof.",
                "visual_kind": "chart_capture",
                "chart_symbol": "BTC_USDT",
                "post_family": "market_chart",
            }
        ]
    )
    agent = make_agent("example_macro")
    directive = SimpleNamespace(stage="analytical_builder", target_posts=1)
    context = DummyContext({"followers": 10, "following": 5})

    result = auditor.audit(
        plan,
        agent=agent,
        context=context,
        directive=directive,
        recent_other_posts=[],
        recent_self_posts=[],
    )

    assert result.valid is False
    assert any("trailing period" in message for message in result.messages())


def test_auditor_requires_image_when_media_policy_demands_it(monkeypatch):
    monkeypatch.setattr("src.runtime.plan_auditor.should_attach_image", lambda agent_id: True)

    auditor = PlanAuditor()
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish take",
                "text": "$BTC still looks heavy here\n\nthat reclaim still needs proof",
            }
        ]
    )
    agent = make_agent("example_macro")
    directive = SimpleNamespace(stage="analytical_builder", target_posts=1)
    context = DummyContext({"followers": 10, "following": 5})

    result = auditor.audit(
        plan,
        agent=agent,
        context=context,
        directive=directive,
        recent_other_posts=[],
        recent_self_posts=[],
    )

    assert result.valid is False
    assert any("every post" in message for message in result.messages())


def test_auditor_blocks_self_repeat_by_family_and_coin(monkeypatch):
    monkeypatch.setattr("src.runtime.plan_auditor.should_attach_image", lambda agent_id: True)

    auditor = PlanAuditor()
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish take",
                "text": "$ETH can look cleaner on the screen than it actually feels underneath\n\nETH is trading near 2.1K and the feed is already calling it clean\n\nI need the structure in ETH to do more than trigger a fast certainty trade",
                "chart_symbol": "ETH_USDT",
                "visual_kind": "chart_capture",
                "post_family": "market_chart",
                "editorial_angle": "macro",
                "editorial_format": "observation",
            }
        ]
    )
    agent = make_agent("example_macro")
    directive = SimpleNamespace(stage="analytical_builder", target_posts=1)
    context = DummyContext({"followers": 10, "following": 5})
    recent_self_posts = [
        {
            "primary_coin": "ETH",
            "angle": "macro",
            "chart_symbol": "ETH_USDT",
            "text": "$ETH was my macro focus earlier today",
            "opening_signature": "eth can look cleaner on the screen than it actually feels underneath",
            "editorial_format": "observation",
            "post_family": "market_chart",
            "visual_kind": "chart_capture",
        }
    ]

    result = auditor.audit(
        plan,
        agent=agent,
        context=context,
        directive=directive,
        recent_other_posts=[],
        recent_self_posts=recent_self_posts,
    )

    assert result.valid is False
    assert any("recent" in message.lower() or "same coin and angle" in message.lower() for message in result.messages())


def test_auditor_blocks_social_actions_in_post_only_mode(monkeypatch):
    monkeypatch.setattr("src.runtime.plan_auditor.should_attach_image", lambda agent_id: True)

    auditor = PlanAuditor()
    plan = AgentPlan(
        actions=[
            {
                "action": "like",
                "priority": 1,
                "reason": "not allowed here",
                "target": "123",
            },
            {
                "action": "post",
                "priority": 2,
                "reason": "publish note",
                "text": "the timeline gets loud faster than the evidence deserves\n\nthat alone is enough for me to slow down",
                "visual_kind": "reaction_card",
                "post_family": "editorial_note",
                "editorial_format": "sharp_take",
            },
        ]
    )
    agent = make_agent("example_macro")
    directive = SimpleNamespace(stage="post_only_validation", target_posts=1)
    context = DummyContext({"followers": 10, "following": 5})

    result = auditor.audit(
        plan,
        agent=agent,
        context=context,
        directive=directive,
        recent_other_posts=[],
        recent_self_posts=[],
    )

    assert result.valid is False
    assert any("Post-only validation" in message for message in result.messages())

def test_auditor_allows_example_altcoin_reply_limited_plan_with_follow_only(monkeypatch):
    monkeypatch.setattr("src.runtime.plan_auditor.should_attach_image", lambda agent_id: False)

    auditor = PlanAuditor()
    plan = AgentPlan(
        actions=[
            {
                "action": "follow",
                "priority": 1,
                "reason": "keep graph moving",
                "target": "123",
            },
            {
                "action": "post",
                "priority": 2,
                "reason": "publish alt take",
                "text": "$LINK still matters more when the second reaction stays cleaner than the first chase\n\nthat is where selection starts mattering more than the headline",
                "visual_kind": "reaction_card",
                "post_family": "editorial_note",
                "editorial_angle": "rotation",
                "editorial_format": "watchlist_note",
            },
        ]
    )
    agent = make_agent("example_altcoin")
    directive = SimpleNamespace(stage="reply_limited_growth", target_posts=1)
    context = DummyContext({"followers": 1, "following": 6})

    result = auditor.audit(
        plan,
        agent=agent,
        context=context,
        directive=directive,
        recent_other_posts=[],
        recent_self_posts=[],
    )

    assert all("visible non-post activity" not in message for message in result.messages())


def test_auditor_blocks_reusing_same_news_source_from_other_agent(monkeypatch):
    monkeypatch.setattr("src.runtime.plan_auditor.should_attach_image", lambda agent_id: False)

    auditor = PlanAuditor()
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish news take",
                "text": "the headline is loud but i care more about what survives after the first reaction\n\nthat is where the tape stops borrowing conviction",
                "visual_kind": "news_card",
                "post_family": "news_reaction",
                "editorial_angle": "macro",
                "editorial_format": "headline_check",
                "source_kind": "news",
                "source_url": "https://example.com/same-headline",
            }
        ]
    )
    agent = make_agent("example_macro")
    directive = SimpleNamespace(stage="post_only_validation", target_posts=1)
    context = DummyContext({"followers": 10, "following": 5})
    recent_other_posts = [
        {
            "agent_id": "example_altcoin",
            "source_url": "https://example.com/same-headline",
            "post_family": "news_reaction",
            "visual_type": "news_card",
            "normalized_text": "different text",
        }
    ]

    result = auditor.audit(
        plan,
        agent=agent,
        context=context,
        directive=directive,
        recent_other_posts=recent_other_posts,
        recent_self_posts=[],
    )

    assert result.valid is False
    assert any("same news source" in message.lower() for message in result.messages())
