"""Tests for reflection bridge: prompt construction and basic validation."""

from src.operator.reflection_bridge import _REFLECT_PROMPT_TEMPLATE


def test_reflect_prompt_contains_agent_id():
    prompt = _REFLECT_PROMPT_TEMPLATE.format(agent_id="aisama", agent_dir="agents/aisama")
    assert "aisama" in prompt
    assert "briefing_packet.md" in prompt
    assert "strategic_state.md" in prompt
    assert "open_loops.md" in prompt
    assert "intent.md" in prompt


def test_reflect_prompt_has_all_update_targets():
    prompt = _REFLECT_PROMPT_TEMPLATE.format(agent_id="sweetdi", agent_dir="agents/sweetdi")
    assert "agents/sweetdi/strategic_state.md" in prompt
    assert "agents/sweetdi/open_loops.md" in prompt
    assert "agents/sweetdi/intent.md" in prompt
    assert "journal.md" in prompt
