from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.runtime.session_loop as session_loop
from src.runtime.agent_plan import AgentPlan


@pytest.mark.asyncio
async def test_commit_cycle_results_skips_already_applied_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(session_loop, "REVIEW_DIR", tmp_path)
    runner = session_loop.ContinuousSessionRunner(config_path="config/active_agent.yaml")
    reviewer = MagicMock()
    reviewer.review = AsyncMock(return_value="# review")
    sdk = MagicMock()
    sdk.get_session_stats.return_value = {"total_actions": 3}
    plan = AgentPlan(
        actions=[
            {
                "action": "post",
                "priority": 1,
                "reason": "publish",
                "text": "$BTC still needs confirmation after the impulse\n\nwatching how price reacts into liquidity.",
            }
        ]
    )
    checkpoint_payload = {
        "commit_state": {
            "limits_updated": True,
            "posts_recorded": True,
            "daily_plan_updated": True,
        },
        "daily_plan_snapshot": {
            "plan_date": "2026-03-31",
            "targets": {"like": 0, "comment": 0, "post": 1},
            "completed": {"like": 0, "comment": 0, "follow": 0, "post": 1},
            "status": "completed",
        },
        "session_id": "resume-test",
    }

    with patch.object(session_loop, "update_limits_from_results") as mock_limits, \
         patch.object(session_loop, "record_completed_posts") as mock_posts, \
         patch.object(session_loop, "update_daily_plan_state") as mock_daily, \
         patch.object(session_loop, "save_execution_checkpoint") as mock_save:
        daily_plan, review_path = await runner._commit_cycle_results(
            agent_id="aisama",
            checkpoint_payload=checkpoint_payload,
            plan=plan,
            execution_results=[{"action": "post", "success": True, "response": {"success": True}}],
            daily_targets={"like": 0, "comment": 0, "post": 1},
            timezone_name="UTC",
            reviewer=reviewer,
            cycle_started_at="2026-03-31T00:00:00Z",
            cycle_index=1,
            directive_stage="write",
            sdk=sdk,
        )

    mock_limits.assert_not_called()
    mock_posts.assert_not_called()
    mock_daily.assert_not_called()
    reviewer.review.assert_awaited_once()
    assert mock_save.called
    assert daily_plan["completed"]["post"] == 1
    assert review_path == Path(tmp_path / "resume-test.md")
    assert review_path.exists()
