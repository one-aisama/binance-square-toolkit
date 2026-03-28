"""Tests for ActionGuard — programmatic safety layer between agent and SDK."""

import time

import pytest
from unittest.mock import AsyncMock

from src.runtime.guard import ActionGuard, Verdict
from src.accounts.limiter import ActionLimiter
from src.accounts.manager import LimitsConfig


@pytest.fixture
def mock_limiter():
    limiter = AsyncMock(spec=ActionLimiter)
    limiter.check_allowed = AsyncMock(return_value=True)
    return limiter


@pytest.fixture
def guard(mock_limiter):
    limits = LimitsConfig()
    return ActionGuard(limiter=mock_limiter, limits=limits, account_id="test_account")


# --- Basic allow/deny ---


@pytest.mark.asyncio
async def test_allow_when_all_clear(guard):
    """Fresh guard with no prior actions returns ALLOW."""
    decision = await guard.check("like")
    assert decision.verdict == Verdict.ALLOW


@pytest.mark.asyncio
async def test_daily_limit_denied(guard, mock_limiter):
    """When limiter reports daily limit reached, verdict is DENIED."""
    mock_limiter.check_allowed = AsyncMock(return_value=False)
    decision = await guard.check("like")
    assert decision.verdict == Verdict.DENIED


# --- Cooldown ---


@pytest.mark.asyncio
async def test_cooldown_wait(guard):
    """Action recorded just now triggers WAIT with positive wait_seconds."""
    guard.record("like", success=True)
    decision = await guard.check("like")
    assert decision.verdict == Verdict.WAIT
    assert decision.wait_seconds > 0


@pytest.mark.asyncio
async def test_cooldown_expired(guard):
    """After cooldown period passes, action is ALLOW again."""
    guard.record("like", success=True)
    # Simulate cooldown expiry by backdating the timestamp
    guard._last_action_time["like"] = time.time() - 60.0
    decision = await guard.check("like")
    assert decision.verdict == Verdict.ALLOW


# --- Circuit breaker ---


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_2_failures(guard):
    """Two consecutive failures open the circuit, blocking that action type."""
    guard.record("like", success=False)
    guard.record("like", success=False)
    # Backdate cooldown so it doesn't interfere
    guard._last_action_time["like"] = time.time() - 60.0
    decision = await guard.check("like")
    assert decision.verdict == Verdict.DENIED


@pytest.mark.asyncio
async def test_circuit_breaker_per_type(guard):
    """Circuit open for 'post' does not affect 'comment'."""
    guard.record("post", success=False)
    guard.record("post", success=False)
    decision = await guard.check("comment")
    assert decision.verdict == Verdict.ALLOW


@pytest.mark.asyncio
async def test_circuit_breaker_resets_on_success(guard):
    """A success after one failure resets the counter; type stays allowed."""
    guard.record("like", success=False)
    guard.record("like", success=True)
    guard._last_action_time["like"] = time.time() - 60.0
    decision = await guard.check("like")
    assert decision.verdict == Verdict.ALLOW


# --- Global stop ---


@pytest.mark.asyncio
async def test_global_stop_at_3_broken_types(guard):
    """Breaking 3 different action types returns SESSION_OVER for any check."""
    for action_type in ("like", "comment", "post"):
        guard.record(action_type, success=False)
        guard.record(action_type, success=False)
    decision = await guard.check("follow")
    assert decision.verdict == Verdict.SESSION_OVER


# --- Fallback chain ---


@pytest.mark.asyncio
async def test_fallback_chain(guard):
    """Circuit open for 'post' suggests 'quote_repost' as fallback."""
    guard.record("post", success=False)
    guard.record("post", success=False)
    guard._last_action_time["post"] = time.time() - 120.0
    decision = await guard.check("post")
    assert decision.fallback_action == "quote_repost"


@pytest.mark.asyncio
async def test_fallback_skips_broken(guard):
    """When 'post' and 'quote_repost' are both broken, fallback is 'comment'."""
    for action_type in ("post", "quote_repost"):
        guard.record(action_type, success=False)
        guard.record(action_type, success=False)
    guard._last_action_time["post"] = time.time() - 120.0
    decision = await guard.check("post")
    assert decision.fallback_action == "comment"


# --- Session limits ---


@pytest.mark.asyncio
async def test_session_limit(mock_limiter):
    """After max_session_actions reached, verdict is SESSION_OVER."""
    limits = LimitsConfig()
    guard = ActionGuard(
        limiter=mock_limiter, limits=limits,
        account_id="test_account", max_session_actions=3,
    )
    for _ in range(3):
        guard.record("like", success=True)
    decision = await guard.check("like")
    assert decision.verdict == Verdict.SESSION_OVER


# --- Session stats ---


def test_session_stats(guard):
    """get_session_stats returns correct counts after mixed actions."""
    guard.record("like", success=True)
    guard.record("comment", success=True)
    guard.record("post", success=False)
    stats = guard.get_session_stats()
    assert stats["total_actions"] == 3
    assert stats["successful"] == 2
    assert stats["failed"] == 1


# --- is_session_over property ---


def test_is_session_over_false_initially(guard):
    """Fresh guard reports session is not over."""
    assert guard.is_session_over is False


def test_is_session_over_true_after_limit(mock_limiter):
    """Property returns True when session action limit is reached."""
    limits = LimitsConfig()
    guard = ActionGuard(
        limiter=mock_limiter, limits=limits,
        account_id="test_account", max_session_actions=1,
    )
    guard.record("like", success=True)
    assert guard.is_session_over is True
