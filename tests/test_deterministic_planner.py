import pytest
from types import SimpleNamespace

from src.runtime.deterministic_planner import DeterministicPlanGenerator
from src.runtime.plan_auditor import PlanAuditor
from tests.helpers import make_agent


class DummyPost:
    def __init__(self, post_id: str, author: str, text: str, selection_reason: str = ""):
        self.post_id = post_id
        self.author = author
        self.text = text
        self.selection_reason = selection_reason


class DummyContext:
    def __init__(self, feed_posts, market_data, news=None):
        self.feed_posts = feed_posts
        self.market_data = market_data
        self.news = news or []


def test_example_altcoin_plan_avoids_recent_self_coin_and_uses_chart_capture(monkeypatch):
    monkeypatch.setattr("src.runtime.deterministic_planner.is_reply_limited", lambda agent_id: False)

    generator = DeterministicPlanGenerator(agent=make_agent("example_altcoin"))
    context = DummyContext(
        feed_posts=[
            DummyPost("1", "altqueen", "$LINK still has the cleanest relative strength in this rotation", "preferred_alt:LINK,alt_rotation"),
            DummyPost("2", "solcat", "$SOL is the one i keep watching after the first squeeze cooled off", "preferred_alt:SOL,alt_rotation"),
            DummyPost("3", "avaxmaxi", "$AVAX looks cleaner now that the first chase already happened", "preferred_alt:AVAX,alt_rotation"),
        ],
        market_data={
            "LINK": {"price": 19.4, "change_24h": 4.8},
            "SOL": {"price": 84.3, "change_24h": 3.7},
            "AVAX": {"price": 41.2, "change_24h": 3.2},
        },
    )
    directive = SimpleNamespace(
        stage="altcoin_operator",
        target_comments=3,
        target_likes=4,
        target_posts=1,
        target_follows=2,
        preferred_symbols=["LINK", "SOL", "AVAX"],
        avoid_primary_symbols=["BTC", "ETH"],
    )
    recent_self_posts = [
        {
            "primary_coin": "LINK",
            "angle": "rotation",
            "editorial_format": "spotlight",
            "opening_signature": "focus",
            "chart_symbol": "LINK_USDT",
            "post_family": "market_chart",
            "text": "$LINK was my rotation focus earlier today",
        }
    ]

    plan = __import__("asyncio").run(
        generator.generate_plan(
            context=context,
            directive=directive,
            recent_other_posts=[],
            recent_self_posts=recent_self_posts,
        )
    )
    post = next(action for action in plan.actions if action.action == "post")

    assert post.visual_kind == "chart_capture"
    assert post.chart_symbol in {"SOL_USDT", "AVAX_USDT"}
    assert post.post_family == "market_chart"
    assert post.brief_context is not None
    assert "angle:" in post.brief_context
    assert sum(1 for action in plan.actions if action.action == "comment" and action.follow) >= 1


def test_example_macro_post_has_editorial_metadata():
    generator = DeterministicPlanGenerator(agent=make_agent("example_macro"))
    context = DummyContext(
        feed_posts=[
            DummyPost("1", "macrocat", "$BTC still looks fragile because liquidity has not improved", "macro_majors,macro_structure"),
            DummyPost("2", "ethtape", "$ETH bounce is getting called clean too early", "macro_majors,macro_structure"),
        ],
        market_data={
            "BTC": {"price": 67840.0, "change_24h": 1.7},
            "ETH": {"price": 2064.0, "change_24h": 2.1},
        },
    )
    directive = SimpleNamespace(
        stage="analytical_builder",
        target_comments=1,
        target_likes=1,
        target_posts=1,
        target_follows=0,
        preferred_symbols=["BTC", "ETH"],
        avoid_primary_symbols=[],
    )

    plan = __import__("asyncio").run(
        generator.generate_plan(
            context=context,
            directive=directive,
            recent_other_posts=[],
            recent_self_posts=[],
        )
    )
    post = next(action for action in plan.actions if action.action == "post")

    assert post.text is None  # agent writes text later
    assert post.brief_context is not None
    assert post.visual_kind == "chart_capture"
    assert post.chart_timeframe == "1D"
    assert post.post_family == "market_chart"
    assert post.editorial_format in {"observation", "contrast", "filter", "process"}
    assert post.editorial_angle in {"macro", "psychology", "ta"}


def test_comment_action_has_target_text_not_generated_text():
    generator = DeterministicPlanGenerator(agent=make_agent("example_macro"))
    context = DummyContext(
        feed_posts=[
            DummyPost("1", "macrocat", "$BTC bounce has everyone calling the tape clean again", "macro_majors,macro_structure"),
        ],
        market_data={"BTC": {"price": 67840.0, "change_24h": 1.7}},
    )
    directive = SimpleNamespace(
        stage="analytical_builder",
        target_comments=1,
        target_likes=1,
        target_posts=0,
        target_follows=0,
        preferred_symbols=["BTC"],
        avoid_primary_symbols=[],
    )

    plan = __import__("asyncio").run(
        generator.generate_plan(
            context=context,
            directive=directive,
            recent_other_posts=[],
            recent_self_posts=[],
        )
    )
    comment = next(action for action in plan.actions if action.action == "comment")

    assert comment.text is None  # agent writes text later
    assert comment.target_text == "$BTC bounce has everyone calling the tape clean again"
    assert comment.target == "1"
    assert comment.target_author == "macrocat"


def test_comment_targets_skip_identity_threads():
    generator = DeterministicPlanGenerator(agent=make_agent("example_macro"))
    context = DummyContext(
        feed_posts=[
            DummyPost("1", "macrocat", "$BTC reclaim only matters if liquidity keeps improving", "macro_majors,macro_structure"),
            DummyPost("2", "idbuilder", "Digital identity will matter more than hype because users need portable reputation onchain", "general"),
            DummyPost("3", "ethflow", "$ETH still looks fragile if flows stall again", "macro_majors,macro_structure"),
            DummyPost("4", "solswing", "$SOL reclaim is interesting only if the follow through stays clean", "general"),
        ],
        market_data={
            "BTC": {"price": 67840.0, "change_24h": 1.7},
            "ETH": {"price": 2064.0, "change_24h": 2.1},
            "SOL": {"price": 154.0, "change_24h": 3.4},
        },
    )
    directive = SimpleNamespace(
        stage="analytical_builder",
        target_comments=3,
        target_likes=3,
        target_posts=0,
        target_follows=0,
        preferred_symbols=["BTC", "ETH", "SOL"],
        avoid_primary_symbols=[],
    )

    plan = __import__("asyncio").run(
        generator.generate_plan(
            context=context,
            directive=directive,
            recent_other_posts=[],
            recent_self_posts=[],
        )
    )
    comment_targets = [action.target for action in plan.actions if action.action == "comment"]
    assert comment_targets == ["1", "3", "4"]


def test_example_altcoin_comment_targets_stay_on_alt_lane(monkeypatch):
    monkeypatch.setattr("src.runtime.deterministic_planner.is_reply_limited", lambda agent_id: False)
    generator = DeterministicPlanGenerator(agent=make_agent("example_altcoin"))
    context = DummyContext(
        feed_posts=[
            DummyPost("1", "macrocat", "$BTC reclaim looks stronger if ETF flows improve", "deprioritized_macro"),
            DummyPost("2", "ethtape", "$ETH bounce is getting called clean too early", "deprioritized_macro"),
            DummyPost("3", "linklord", "$LINK still has the cleanest relative strength in this rotation", "preferred_alt:LINK,alt_rotation"),
            DummyPost("4", "solcat", "$SOL is interesting if the follow through still holds after the first squeeze", "general"),
            DummyPost("5", "avaxmaxi", "$AVAX still looks orderly while the sector gets noisy", "general"),
        ],
        market_data={
            "LINK": {"price": 19.4, "change_24h": 4.8},
            "SOL": {"price": 84.3, "change_24h": 3.7},
            "AVAX": {"price": 41.2, "change_24h": 3.2},
        },
    )
    directive = SimpleNamespace(
        stage="altcoin_operator",
        target_comments=3,
        target_likes=3,
        target_posts=0,
        target_follows=0,
        preferred_symbols=["LINK", "SOL", "AVAX"],
        avoid_primary_symbols=["BTC", "ETH"],
    )

    plan = __import__("asyncio").run(
        generator.generate_plan(
            context=context,
            directive=directive,
            recent_other_posts=[],
            recent_self_posts=[],
        )
    )
    comment_targets = [action.target for action in plan.actions if action.action == "comment"]
    assert comment_targets == ["3", "4", "5"]


def test_post_only_mode_rotates_away_from_recent_market_family():
    generator = DeterministicPlanGenerator(agent=make_agent("example_macro"))
    context = DummyContext(
        feed_posts=[
            DummyPost("1", "macrocat", "$BTC bounce has everyone calling the tape clean again", "macro_majors,macro_structure"),
        ],
        market_data={"BTC": {"price": 67840.0, "change_24h": 1.7}},
        news=[
            {
                "title": "ETF flows turn negative again as traders price another volatile week",
                "source": "CoinDesk",
                "url": "https://example.com/etf",
            }
        ],
    )
    directive = SimpleNamespace(
        stage="post_only_validation",
        target_comments=0,
        target_likes=0,
        target_posts=1,
        target_follows=0,
        preferred_symbols=["BTC", "ETH"],
        avoid_primary_symbols=[],
    )
    recent_self_posts = [
        {
            "primary_coin": "BTC",
            "angle": "macro",
            "editorial_format": "observation",
            "opening_signature": "what matters",
            "chart_symbol": "BTC_USDT",
            "post_family": "market_chart",
            "visual_kind": "chart_capture",
            "text": "$BTC was my market take earlier today",
        }
    ]

    plan = __import__("asyncio").run(
        generator.generate_plan(
            context=context,
            directive=directive,
            recent_other_posts=[],
            recent_self_posts=recent_self_posts,
        )
    )
    post = next(action for action in plan.actions if action.action == "post")
    assert post.post_family == "news_reaction"
    assert post.visual_kind == "news_card"
    assert post.brief_context is not None


def test_post_avoids_news_source_used_by_other_agent():
    generator = DeterministicPlanGenerator(agent=make_agent("example_macro"))
    context = DummyContext(
        feed_posts=[
            DummyPost("1", "macrocat", "$BTC bounce has everyone calling the tape clean again", "macro_majors,macro_structure"),
        ],
        market_data={"BTC": {"price": 67840.0, "change_24h": 1.7}},
        news=[
            {
                "title": "ETF flows turn negative again as traders price another volatile week",
                "source": "CoinDesk",
                "url": "https://example.com/used-news",
            },
            {
                "title": "Fed path still looks unclear as bitcoin traders wait for liquidity confirmation",
                "source": "Decrypt",
                "url": "https://example.com/fresh-news",
            },
        ],
    )
    directive = SimpleNamespace(
        stage="post_only_validation",
        target_comments=0,
        target_likes=0,
        target_posts=1,
        target_follows=0,
        preferred_symbols=["BTC", "ETH"],
        avoid_primary_symbols=[],
    )
    recent_other_posts = [
        {
            "source_url": "https://example.com/used-news",
            "source_title": "ETF flows turn negative",
            "post_family": "news_reaction",
            "visual_type": "news_card",
            "normalized_text": "other agent already used this headline",
        }
    ]

    plan = __import__("asyncio").run(
        generator.generate_plan(
            context=context,
            directive=directive,
            recent_other_posts=recent_other_posts,
            recent_self_posts=[],
        )
    )
    post = next(action for action in plan.actions if action.action == "post")
    assert post.source_url != "https://example.com/used-news"


def test_agent_action_allows_none_text_for_post():
    from src.runtime.agent_plan import AgentAction
    action = AgentAction(action="post", priority=3, reason="test", brief_context="angle: macro")
    assert action.text is None
    assert action.brief_context == "angle: macro"


def test_agent_action_allows_none_text_for_comment():
    from src.runtime.agent_plan import AgentAction
    action = AgentAction(action="comment", priority=1, reason="test", target="123", target_text="some post")
    assert action.text is None
    assert action.target_text == "some post"


def test_agent_action_requires_text_for_quote_repost():
    from src.runtime.agent_plan import AgentAction
    with pytest.raises(ValueError, match="text is required"):
        AgentAction(action="quote_repost", priority=2, reason="test", target="123")


def test_planner_does_not_require_sdk():
    """Planner should work without SDK since agent writes text, not the planner."""
    generator = DeterministicPlanGenerator(agent=make_agent("example_macro"))
    assert generator._sdk is None
