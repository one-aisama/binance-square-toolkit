from types import SimpleNamespace

from src.runtime.cycle_policy import build_cycle_directive, choose_sleep_seconds
from tests.helpers import make_agent


class DummyContext:
    def __init__(self, my_stats):
        self.my_stats = my_stats


def test_build_cycle_directive_for_sweetdi_bootstrap(monkeypatch):
    monkeypatch.setattr("src.runtime.cycle_policy.is_reply_limited", lambda agent_id: False)

    agent = make_agent(
        'sweetdi',
        market_symbols=['SOL', 'LINK', 'AVAX', 'BTC'],
        cycle_interval_minutes=[15, 28],
    )
    context = DummyContext({'followers': 0, 'following': 0})

    directive = build_cycle_directive(agent, context)

    assert directive.stage == 'bootstrap_graph'
    assert directive.target_follows == 2
    assert directive.target_posts == 1
    assert 'BTC' in directive.avoid_primary_symbols


def test_build_cycle_directive_shrinks_to_daily_remaining(monkeypatch):
    monkeypatch.setattr("src.runtime.cycle_policy.is_reply_limited", lambda agent_id: False)

    agent = make_agent(
        'aisama',
        market_symbols=['BTC', 'ETH', 'SOL'],
        cycle_interval_minutes=[20, 35],
    )
    context = DummyContext({'followers': 12, 'following': 8})
    daily_plan_state = {
        'targets': {'like': 7, 'comment': 5, 'post': 1},
        'completed': {'like': 6, 'comment': 4, 'post': 0, 'follow': 0},
    }

    directive = build_cycle_directive(agent, context, daily_plan_state=daily_plan_state)

    assert directive.target_likes == 1
    assert directive.target_comments == 1
    assert directive.target_posts == 1


def test_build_cycle_directive_enters_overflow_after_daily_completion(monkeypatch):
    monkeypatch.setattr("src.runtime.cycle_policy.is_reply_limited", lambda agent_id: False)

    agent = make_agent(
        'aisama',
        market_symbols=['BTC', 'ETH', 'SOL'],
        cycle_interval_minutes=[20, 35],
    )
    context = DummyContext({'followers': 12, 'following': 8})
    daily_plan_state = {
        'targets': {'like': 7, 'comment': 5, 'post': 1},
        'completed': {'like': 7, 'comment': 5, 'post': 1, 'follow': 1},
    }

    directive = build_cycle_directive(agent, context, daily_plan_state=daily_plan_state)

    assert directive.stage == 'analytical_builder_overflow'
    assert directive.target_posts == 0
    assert directive.target_comments == 2


def test_choose_sleep_seconds_expands_after_minimum_met():
    result = choose_sleep_seconds((20, 35), minimum_met=True, randint_fn=lambda low, high: low)
    assert result == 35 * 60
