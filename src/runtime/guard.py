"""ActionGuard — programmatic safety layer between agent and SDK.

Enforces daily limits, cooldowns, per-type circuit breakers, and session tracking.
LLM cannot bypass this layer. All action decisions pass through guard first.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum

from src.accounts.limiter import ActionLimiter
from src.accounts.manager import LimitsConfig

logger = logging.getLogger("bsq.runtime.guard")


class Verdict(Enum):
    ALLOW = "allow"
    WAIT = "wait"
    DENIED = "denied"
    SESSION_OVER = "session_over"


@dataclass
class GuardDecision:
    verdict: Verdict
    reason: str = ""
    wait_seconds: float = 0.0
    fallback_action: str | None = None


# Fallback chains: if action type is circuit-broken, suggest alternative
FALLBACK_CHAINS: dict[str, list[str]] = {
    "post": ["quote_repost", "comment"],
    "quote_repost": ["comment"],
    "comment": [],
    "like": [],
    "follow": [],
}

# Map action types to LimitsConfig field names
ACTION_TO_LIMIT_FIELD: dict[str, str] = {
    "post": "posts_per_day",
    "like": "likes_per_day",
    "comment": "comments_per_day",
    "repost": "reposts_per_day",
    "quote_repost": "reposts_per_day",
    "follow": "follows_per_day",
}

# Minimum seconds between same action type
DEFAULT_COOLDOWNS: dict[str, float] = {
    "post": 60.0,
    "like": 15.0,
    "comment": 30.0,
    "repost": 60.0,
    "quote_repost": 60.0,
    "follow": 30.0,
}

# Circuit breaker threshold: consecutive failures before type is blocked
CIRCUIT_BREAKER_THRESHOLD = 2

# Global stop: if this many action types are circuit-broken, end session
GLOBAL_STOP_THRESHOLD = 3


class ActionGuard:
    """Guards every agent action with programmatic checks.

    Usage:
        guard = ActionGuard(limiter, limits_config, account_id)
        decision = await guard.check(action_type)
        if decision.verdict == Verdict.ALLOW:
            result = await sdk.do_action(...)
            guard.record(action_type, success=True)
        elif decision.verdict == Verdict.WAIT:
            await asyncio.sleep(decision.wait_seconds)
            # retry check
        elif decision.verdict == Verdict.DENIED:
            # try decision.fallback_action or skip
    """

    def __init__(
        self,
        limiter: ActionLimiter,
        limits: LimitsConfig,
        account_id: str,
        max_session_actions: int = 80,
        session_minimum: dict[str, int] | None = None,
    ):
        self._limiter = limiter
        self._limits = limits
        self._account_id = account_id
        self._max_session_actions = max_session_actions
        self._session_minimum = session_minimum or {"like": 20, "comment": 20, "post": 3}

        # Session state (in-memory, reset each session)
        self._session_action_count = 0
        self._session_success_count = 0
        self._session_fail_count = 0
        self._session_start_time = time.time()

        # Successful actions by type (for session minimum tracking)
        self._success_by_type: dict[str, int] = {}

        # Cooldown tracking: action_type -> last execution timestamp
        self._last_action_time: dict[str, float] = {}

        # Circuit breaker: action_type -> consecutive failure count
        self._failure_counters: dict[str, int] = {}
        self._circuit_open: set[str] = set()

    async def check(self, action_type: str) -> GuardDecision:
        """Check if action is allowed. Returns decision with verdict."""

        # 1. Global stop: too many circuit-broken types
        if len(self._circuit_open) >= GLOBAL_STOP_THRESHOLD:
            return GuardDecision(
                verdict=Verdict.SESSION_OVER,
                reason=f"Session terminated: {len(self._circuit_open)} action types broken "
                       f"({', '.join(self._circuit_open)}), likely browser state issue",
            )

        # 2. Session limit
        if self._session_action_count >= self._max_session_actions:
            return GuardDecision(
                verdict=Verdict.SESSION_OVER,
                reason=f"Session action limit reached: {self._session_action_count}/{self._max_session_actions}",
            )

        # 3. Circuit breaker for this type
        if action_type in self._circuit_open:
            fallback = self._find_fallback(action_type)
            return GuardDecision(
                verdict=Verdict.DENIED,
                reason=f"Circuit open for {action_type}: "
                       f"{self._failure_counters.get(action_type, 0)} consecutive failures",
                fallback_action=fallback,
            )

        # 4. Daily limit
        limit_field = ACTION_TO_LIMIT_FIELD.get(action_type)
        if limit_field:
            daily_limit = getattr(self._limits, limit_field)
            allowed = await self._limiter.check_allowed(
                self._account_id, action_type, daily_limit
            )
            if not allowed:
                fallback = self._find_fallback(action_type)
                return GuardDecision(
                    verdict=Verdict.DENIED,
                    reason=f"Daily limit reached for {action_type}",
                    fallback_action=fallback,
                )

        # 5. Cooldown
        cooldown = DEFAULT_COOLDOWNS.get(action_type, 15.0)
        last_time = self._last_action_time.get(action_type, 0.0)
        elapsed = time.time() - last_time
        if elapsed < cooldown:
            wait = cooldown - elapsed
            return GuardDecision(
                verdict=Verdict.WAIT,
                reason=f"Cooldown for {action_type}: wait {wait:.1f}s",
                wait_seconds=wait,
            )

        return GuardDecision(verdict=Verdict.ALLOW)

    def record(
        self,
        action_type: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Record action result. Updates counters, circuit breakers."""
        self._session_action_count += 1
        self._last_action_time[action_type] = time.time()

        if success:
            self._session_success_count += 1
            self._success_by_type[action_type] = self._success_by_type.get(action_type, 0) + 1
            self._failure_counters[action_type] = 0
            # Re-close circuit if it was open and action recovered
            if action_type in self._circuit_open:
                self._circuit_open.discard(action_type)
                logger.info(f"Circuit closed for {action_type} after successful retry")
        else:
            self._session_fail_count += 1
            count = self._failure_counters.get(action_type, 0) + 1
            self._failure_counters[action_type] = count

            if count >= CIRCUIT_BREAKER_THRESHOLD:
                self._circuit_open.add(action_type)
                logger.warning(
                    f"Circuit OPEN for {action_type}: {count} consecutive failures. "
                    f"Error: {error or 'unknown'}"
                )

    def _find_fallback(self, action_type: str) -> str | None:
        """Find first available fallback that isn't circuit-broken."""
        chain = FALLBACK_CHAINS.get(action_type, [])
        for fallback in chain:
            if fallback not in self._circuit_open:
                return fallback
        return None

    def can_finish(self) -> tuple[bool, str]:
        """Check if session minimum is met. Returns (can_finish, reason).

        Agent cannot end session until minimum is fulfilled.
        """
        missing = []
        for action_type, required in self._session_minimum.items():
            done = self._success_by_type.get(action_type, 0)
            if done < required:
                missing.append(f"{action_type}: {done}/{required}")

        if missing:
            return False, f"Minimum not met: {', '.join(missing)}"
        return True, "Minimum fulfilled — you are free to continue or stop"

    def get_minimum_status(self) -> dict[str, dict[str, int]]:
        """Return current progress toward session minimum."""
        status = {}
        for action_type, required in self._session_minimum.items():
            done = self._success_by_type.get(action_type, 0)
            status[action_type] = {"done": done, "required": required, "remaining": max(0, required - done)}
        return status

    def get_session_stats(self) -> dict:
        """Return current session statistics."""
        duration = time.time() - self._session_start_time
        duration_minutes = duration / 60.0
        return {
            "total_actions": self._session_action_count,
            "successful": self._session_success_count,
            "failed": self._session_fail_count,
            "circuits_opened": list(self._circuit_open),
            "duration_seconds": int(duration),
            "efficiency": (
                self._session_success_count / duration_minutes
                if duration_minutes > 0
                else 0.0
            ),
        }

    @property
    def is_session_over(self) -> bool:
        """Check if session should end (too many broken types or action limit)."""
        return (
            len(self._circuit_open) >= GLOBAL_STOP_THRESHOLD
            or self._session_action_count >= self._max_session_actions
        )
