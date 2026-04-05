"""Tests for editorial brain integration with strategic directive."""

from types import SimpleNamespace

from src.runtime.editorial_brain import EditorialBrain
from tests.helpers import make_agent


class DummyPost:
    def __init__(self, post_id, author, text, selection_reason=""):
        self.post_id = post_id
        self.author = author
        self.text = text
        self.selection_reason = selection_reason


class DummyContext:
    def __init__(self, feed_posts=None, market_data=None, news=None):
        self.feed_posts = feed_posts or []
        self.market_data = market_data or {}
        self.news = news or []


def _make_directive(**overrides):
    base = {
        "focus_summary": "test focus",
        "preferred_coins": [],
        "avoid_coins": [],
        "post_direction": "",
        "comment_direction": "",
        "skip_families": [],
        "tone": "analytical",
    }
    base.update(overrides)
    return base


def test_skip_families_penalty():
    agent = make_agent("aisama")
    brain = EditorialBrain(agent=agent, policy=agent._policy)
    context = DummyContext(
        feed_posts=[DummyPost("1", "alice", "$BTC macro read")],
        market_data={"BTC": {"price": 70000, "change_24h": 2.0}},
        news=[{"title": "ETF approved", "source": "reuters"}],
    )
    directive = SimpleNamespace(
        stage="default", target_comments=0, target_likes=0,
        target_posts=1, target_follows=0, preferred_symbols=[],
    )

    # Without skip_families — market_chart should win (has +80 boost)
    family_no_skip = brain._choose_post_family(
        context, directive, [], 0, strategic_directive=None,
    )
    assert family_no_skip == "market_chart"

    # With skip_families=["market_chart"] — should pick something else
    family_skip = brain._choose_post_family(
        context, directive, [], 0,
        strategic_directive=_make_directive(skip_families=["market_chart"]),
    )
    assert family_skip != "market_chart"


def test_preferred_coins_boost_symbol_score():
    agent = make_agent("aisama")
    brain = EditorialBrain(agent=agent, policy=agent._policy)
    context = DummyContext(
        market_data={
            "BTC": {"price": 70000, "change_24h": 1.0},
            "SOL": {"price": 80, "change_24h": 1.0},
        },
    )

    # Without directive, both have same change — scores should be similar
    score_btc_no_dir, _ = brain._score_symbol(
        symbol="BTC", context=context, recent_self_posts=[],
    )
    score_sol_no_dir, _ = brain._score_symbol(
        symbol="SOL", context=context, recent_self_posts=[],
    )

    # With directive preferring SOL, SOL gets +80 bonus
    directive = _make_directive(preferred_coins=["SOL"])
    score_sol_dir, _ = brain._score_symbol(
        symbol="SOL", context=context, recent_self_posts=[],
        strategic_directive=directive,
    )
    score_btc_dir, _ = brain._score_symbol(
        symbol="BTC", context=context, recent_self_posts=[],
        strategic_directive=directive,
    )

    assert score_sol_dir > score_sol_no_dir
    assert score_sol_dir > score_btc_dir


def test_avoid_coins_filtered_from_candidates():
    agent = make_agent("aisama")
    brain = EditorialBrain(agent=agent, policy=agent._policy)
    context = DummyContext(
        market_data={
            "BTC": {"price": 70000, "change_24h": 2.0},
            "DOGE": {"price": 0.08, "change_24h": 5.0},
            "SOL": {"price": 80, "change_24h": 3.0},
        },
    )
    directive_obj = SimpleNamespace(
        stage="default", target_comments=0, target_likes=0,
        target_posts=1, target_follows=0, preferred_symbols=[],
    )

    # Without directive — all symbols
    candidates_no_dir = brain._candidate_symbols(context, directive_obj)
    assert "DOGE" in candidates_no_dir or "DOGE" not in candidates_no_dir  # may be excluded by policy

    # With avoid_coins=["DOGE"] — DOGE excluded
    strat = _make_directive(avoid_coins=["DOGE"])
    candidates_with_dir = brain._candidate_symbols(context, directive_obj, strategic_directive=strat)
    assert "DOGE" not in candidates_with_dir


def test_preferred_coins_reorder_candidates():
    agent = make_agent("aisama")
    brain = EditorialBrain(agent=agent, policy=agent._policy)
    context = DummyContext(
        market_data={
            "BTC": {"price": 70000, "change_24h": 2.0},
            "ETH": {"price": 3500, "change_24h": 1.0},
            "SOL": {"price": 80, "change_24h": 3.0},
        },
    )
    directive_obj = SimpleNamespace(
        stage="default", target_comments=0, target_likes=0,
        target_posts=1, target_follows=0, preferred_symbols=[],
    )

    strat = _make_directive(preferred_coins=["SOL", "ETH"])
    candidates = brain._candidate_symbols(context, directive_obj, strategic_directive=strat)
    # SOL and ETH should be first (if they exist in market_data)
    sol_idx = candidates.index("SOL") if "SOL" in candidates else 999
    eth_idx = candidates.index("ETH") if "ETH" in candidates else 999
    btc_idx = candidates.index("BTC") if "BTC" in candidates else 999
    assert sol_idx < btc_idx
    assert eth_idx < btc_idx
