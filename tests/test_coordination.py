"""Tests for multi-agent coordination: stagger and territory drift."""

from src.runtime.session_loop import _agent_stagger_offset
from src.runtime.plan_auditor import PlanAuditor, AuditIssue
from src.runtime.agent_plan import AgentPlan, AgentAction


def test_agent_stagger_offset_deterministic():
    offset1 = _agent_stagger_offset("aisama")
    offset2 = _agent_stagger_offset("aisama")
    assert offset1 == offset2
    assert 0 <= offset1 < 300


def test_different_agents_get_different_offsets():
    offset_a = _agent_stagger_offset("aisama")
    offset_b = _agent_stagger_offset("sweetdi")
    assert offset_a != offset_b


class _MockAgent:
    def __init__(self, preferred=None):
        self.agent_id = "test"
        coins = preferred or []

        coin_bias = type("CoinBias", (), {"preferred": coins})()
        similarity = type("S", (), {
            "comment_diversity": 0.82,
            "self_novelty_text": 0.58,
            "self_novelty_relaxed": 0.52,
            "feed_novelty_format": 0.45,
            "feed_novelty_coin": 0.50,
        })()
        runtime_tuning = type("RT", (), {"similarity": similarity})()
        self._policy = type("P", (), {"coin_bias": coin_bias, "runtime_tuning": runtime_tuning})() if preferred is not None else None


def test_territory_drift_all_off_niche_flagged():
    auditor = PlanAuditor()
    agent = _MockAgent(preferred=["BTC", "ETH"])
    actions = [
        AgentAction(action="post", priority=1, reason="t", text="SOL is pumping $SOL", coin="SOL"),
        AgentAction(action="post", priority=2, reason="t", text="AVAX breakout $AVAX", coin="AVAX"),
    ]
    issues = auditor._audit_territory_drift(actions, agent)
    assert len(issues) == 1
    assert "territory" in issues[0].message.lower()


def test_territory_drift_one_off_niche_allowed():
    auditor = PlanAuditor()
    agent = _MockAgent(preferred=["BTC", "ETH"])
    actions = [
        AgentAction(action="post", priority=1, reason="t", text="BTC analysis $BTC", coin="BTC"),
        AgentAction(action="post", priority=2, reason="t", text="SOL is pumping $SOL", coin="SOL"),
    ]
    issues = auditor._audit_territory_drift(actions, agent)
    assert len(issues) == 0


def test_territory_drift_single_post_not_checked():
    auditor = PlanAuditor()
    agent = _MockAgent(preferred=["BTC", "ETH"])
    actions = [
        AgentAction(action="post", priority=1, reason="t", text="SOL is pumping $SOL", coin="SOL"),
    ]
    issues = auditor._audit_territory_drift(actions, agent)
    assert len(issues) == 0


def test_territory_drift_no_policy_skips():
    auditor = PlanAuditor()
    agent = _MockAgent()
    agent._policy = None
    actions = [
        AgentAction(action="post", priority=1, reason="t", text="SOL", coin="SOL"),
        AgentAction(action="post", priority=2, reason="t", text="AVAX", coin="AVAX"),
    ]
    issues = auditor._audit_territory_drift(actions, agent)
    assert len(issues) == 0
