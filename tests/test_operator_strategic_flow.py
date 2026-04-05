"""Tests for operator loop strategic flow integration."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.operator.models import OperatorConfig, OperatorRun


@pytest.mark.asyncio
async def test_micro_cycle_calls_strategize_and_reflect():
    """Verify that _run_micro_cycle calls strategize before prepare and reflect after execute."""
    from src.operator.loop import OperatorLoop

    loop = OperatorLoop(config=OperatorConfig())
    run = OperatorRun(agent_id="test", phase="micro_cycle")

    call_order = []

    async def mock_strategize(agent_id, agent_dir, *, timeout_sec=120):
        call_order.append("strategize")
        return True

    async def mock_reflect(agent_id, agent_dir, *, timeout_sec=120):
        call_order.append("reflect")
        return True

    async def mock_author(agent_id, agent_dir, plan_path, *, timeout_sec=600, mode="cli"):
        call_order.append("author")
        return True

    async def mock_subprocess(cmd, timeout_sec):
        phase = "prepare" if "--prepare" in cmd else "execute"
        call_order.append(phase)
        return {"returncode": 0, "stdout": "", "stderr": ""}

    with patch("src.operator.loop.compile_briefing_packet") as mock_compile, \
         patch("src.operator.loop.generate_strategic_directive", mock_strategize), \
         patch("src.operator.loop.author_plan_text", mock_author), \
         patch("src.operator.loop.audit_authored_plan", return_value=(True, [])), \
         patch("src.operator.loop.reflect_on_cycle", mock_reflect), \
         patch.object(loop, "_run_subprocess", mock_subprocess):

        mock_compile.return_value = "compiled"

        result = await loop._run_micro_cycle("test", "config/test.yaml", "agents/test", run)

    assert result is True
    assert call_order == ["strategize", "prepare", "author", "execute", "reflect"]


@pytest.mark.asyncio
async def test_micro_cycle_continues_if_strategize_fails():
    """Strategize failure is non-fatal: cycle should continue."""
    from src.operator.loop import OperatorLoop

    loop = OperatorLoop(config=OperatorConfig())
    run = OperatorRun(agent_id="test", phase="micro_cycle")

    async def mock_strategize(agent_id, agent_dir, *, timeout_sec=120):
        return False  # strategize failed

    async def mock_author(agent_id, agent_dir, plan_path, *, timeout_sec=600, mode="cli"):
        return True

    async def mock_subprocess(cmd, timeout_sec):
        return {"returncode": 0, "stdout": "", "stderr": ""}

    async def mock_reflect(agent_id, agent_dir, *, timeout_sec=120):
        return True

    with patch("src.operator.loop.compile_briefing_packet"), \
         patch("src.operator.loop.generate_strategic_directive", mock_strategize), \
         patch("src.operator.loop.author_plan_text", mock_author), \
         patch("src.operator.loop.audit_authored_plan", return_value=(True, [])), \
         patch("src.operator.loop.reflect_on_cycle", mock_reflect), \
         patch.object(loop, "_run_subprocess", mock_subprocess):

        result = await loop._run_micro_cycle("test", "config/test.yaml", "agents/test", run)

    assert result is True


@pytest.mark.asyncio
async def test_micro_cycle_continues_if_reflect_fails():
    """Reflect failure is non-fatal: cycle should still return True."""
    from src.operator.loop import OperatorLoop

    loop = OperatorLoop(config=OperatorConfig())
    run = OperatorRun(agent_id="test", phase="micro_cycle")

    async def mock_strategize(agent_id, agent_dir, *, timeout_sec=120):
        return True

    async def mock_author(agent_id, agent_dir, plan_path, *, timeout_sec=600, mode="cli"):
        return True

    async def mock_subprocess(cmd, timeout_sec):
        return {"returncode": 0, "stdout": "", "stderr": ""}

    async def mock_reflect(agent_id, agent_dir, *, timeout_sec=120):
        return False  # reflect failed

    with patch("src.operator.loop.compile_briefing_packet"), \
         patch("src.operator.loop.generate_strategic_directive", mock_strategize), \
         patch("src.operator.loop.author_plan_text", mock_author), \
         patch("src.operator.loop.audit_authored_plan", return_value=(True, [])), \
         patch("src.operator.loop.reflect_on_cycle", mock_reflect), \
         patch.object(loop, "_run_subprocess", mock_subprocess):

        result = await loop._run_micro_cycle("test", "config/test.yaml", "agents/test", run)

    assert result is True
