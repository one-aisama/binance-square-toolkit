"""Tests for memory compiler: briefing packet generation."""

from pathlib import Path

from src.operator.memory_compiler import compile_briefing_packet


def _setup_agent_dir(tmp_path: Path, agent_id: str = "test_agent") -> Path:
    agent_dir = tmp_path / agent_id
    agent_dir.mkdir()
    (agent_dir / "identity.md").write_text("I am a crypto analyst focused on macro", encoding="utf-8")
    (agent_dir / "style.md").write_text("Analytical, direct, no fluff", encoding="utf-8")
    (agent_dir / "strategic_state.md").write_text("## Building\n- Macro voice\n- ETH positioning reads", encoding="utf-8")
    (agent_dir / "open_loops.md").write_text("## Threads\n- Follow up on ETH merge impact", encoding="utf-8")
    (agent_dir / "intent.md").write_text("## Today\n- 2 market posts\n- Focus on liquidity", encoding="utf-8")
    (agent_dir / "lessons.md").write_text("- Second-order reads get more engagement\n- Disagreement > agreement", encoding="utf-8")
    (agent_dir / "journal.md").write_text("2026-04-04: Posted about BTC structure, 3 comments on macro threads", encoding="utf-8")
    (agent_dir / "relationships.md").write_text("- @macrocat: high engagement, 4 interactions", encoding="utf-8")
    (agent_dir / "performance.md").write_text("Avg likes per post: 12. Top topic: ETH", encoding="utf-8")
    return agent_dir


def test_compile_produces_all_sections(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    packet = compile_briefing_packet(str(agent_dir), "test_agent")

    assert "WHO I AM" in packet
    assert "WHAT I AM BUILDING" in packet
    assert "OPEN LOOPS" in packet
    assert "MY INTENT" in packet
    assert "RECENT LESSONS" in packet
    assert "RECENT ACTIVITY" in packet
    assert "RELATIONSHIP PRIORITIES" in packet
    assert "PERFORMANCE SIGNALS" in packet
    assert "HARD CONSTRAINTS" in packet


def test_compile_writes_file(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    compile_briefing_packet(str(agent_dir), "test_agent")

    packet_path = agent_dir / "briefing_packet.md"
    assert packet_path.exists()
    content = packet_path.read_text(encoding="utf-8")
    assert "WHO I AM" in content


def test_compile_includes_identity(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    packet = compile_briefing_packet(str(agent_dir), "test_agent")
    assert "crypto analyst" in packet


def test_compile_includes_strategic_state(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    packet = compile_briefing_packet(str(agent_dir), "test_agent")
    assert "Macro voice" in packet


def test_compile_falls_back_to_strategy_md(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    (agent_dir / "strategic_state.md").unlink()
    (agent_dir / "strategy.md").write_text("Static fallback strategy", encoding="utf-8")
    packet = compile_briefing_packet(str(agent_dir), "test_agent")
    assert "Static fallback strategy" in packet


def test_compile_skips_empty_open_loops(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    (agent_dir / "open_loops.md").write_text("# Open Loops\n(none yet)", encoding="utf-8")
    packet = compile_briefing_packet(str(agent_dir), "test_agent")
    assert "OPEN LOOPS" not in packet


def test_compile_skips_unfilled_intent(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    (agent_dir / "intent.md").write_text("(agent fills based on context)", encoding="utf-8")
    packet = compile_briefing_packet(str(agent_dir), "test_agent")
    assert "MY INTENT" not in packet


def test_compile_handles_missing_files(tmp_path):
    agent_dir = tmp_path / "minimal"
    agent_dir.mkdir()
    (agent_dir / "identity.md").write_text("Minimal agent", encoding="utf-8")
    packet = compile_briefing_packet(str(agent_dir), "minimal")
    assert "WHO I AM" in packet
    assert "Minimal agent" in packet


def test_compile_trims_long_files(tmp_path):
    agent_dir = _setup_agent_dir(tmp_path)
    (agent_dir / "journal.md").write_text("x" * 50000, encoding="utf-8")
    packet = compile_briefing_packet(str(agent_dir), "test_agent")
    # Journal tail should be trimmed to ~2000 chars
    assert len(packet) < 20000
