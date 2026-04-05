"""Tests for reflection bridge: prompt construction and basic validation."""

from src.operator.reflection_bridge import _REFLECT_PROMPT_TEMPLATE


def test_reflect_prompt_contains_agent_id():
    prompt = _REFLECT_PROMPT_TEMPLATE.format(agent_id="example_macro", agent_dir="agents/example_macro")
    assert "example_macro" in prompt
    assert "briefing_packet.md" in prompt
    assert "strategic_state.md" in prompt
    assert "open_loops.md" in prompt
    assert "intent.md" in prompt


def test_reflect_prompt_has_all_update_targets():
    prompt = _REFLECT_PROMPT_TEMPLATE.format(agent_id="example_altcoin", agent_dir="agents/example_altcoin")
    assert "agents/example_altcoin/strategic_state.md" in prompt
    assert "agents/example_altcoin/open_loops.md" in prompt
    assert "agents/example_altcoin/intent.md" in prompt
    assert "journal.md" in prompt
