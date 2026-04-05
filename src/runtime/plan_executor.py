from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable

logger = logging.getLogger("bsq.plan_executor")

from src.runtime.agent_plan import AgentAction, AgentPlan
from src.runtime.guard import Verdict
from src.runtime.visual_pipeline import VisualPipeline

ProgressCallback = Callable[[int, list[dict[str, Any]]], None]
StopCallback = Callable[[], bool]


class PlanExecutor:
    """Execute an explicit agent-authored plan through the SDK."""

    def __init__(self, sdk: Any, *, config_path: str = "config/active_agent.yaml", guard: Any = None):
        self._sdk = sdk
        self._guard = guard
        self._visuals = VisualPipeline(sdk, config_path=config_path)
        self.last_completed: bool = True
        self.last_next_action_index: int = 0

    async def execute(
        self,
        plan: AgentPlan,
        *,
        start_index: int = 0,
        existing_results: list[dict[str, Any]] | None = None,
        should_stop: StopCallback | None = None,
        on_action_complete: ProgressCallback | None = None,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        if dry_run:
            return self._dry_run(plan)
        results: list[dict[str, Any]] = list(existing_results or [])
        recent_posts: list[str] = [
            str(result.get("response", {}).get("text") or "")
            for result in results
            if result.get("action") == "post" and result.get("success")
        ]
        actions = plan.sorted_actions()

        self.last_completed = True
        self.last_next_action_index = start_index

        for index in range(start_index, len(actions)):
            if should_stop and should_stop():
                self.last_completed = False
                self.last_next_action_index = index
                break

            action = actions[index]

            # Safety: agent must have written text before execution
            if action.action in {"comment", "post", "quote_repost"} and not (action.text or "").strip():
                logger.warning("Skipping %s: text not provided by agent (target=%s)", action.action, action.target)
                results.append(self._build_result(action, False, {"error": "text not provided by agent"}))
                self.last_next_action_index = index + 1
                if on_action_complete:
                    on_action_complete(self.last_next_action_index, list(results))
                continue

            guard = self._guard
            if guard:
                decision = await guard.check(action.action)
                if decision.verdict == Verdict.SESSION_OVER:
                    self.last_completed = False
                    self.last_next_action_index = index
                    results.append(self._build_result(action, False, {"error": decision.reason, "guard": "session_over"}))
                    break
                elif decision.verdict == Verdict.DENIED:
                    results.append(self._build_result(action, False, {"error": decision.reason, "guard": "denied", "fallback": decision.fallback_action}))
                    self.last_next_action_index = index + 1
                    if on_action_complete:
                        on_action_complete(self.last_next_action_index, list(results))
                    continue
                elif decision.verdict == Verdict.WAIT:
                    await asyncio.sleep(decision.wait_seconds)
                    decision = await guard.check(action.action)
                    if decision.verdict != Verdict.ALLOW:
                        results.append(self._build_result(action, False, {"error": decision.reason, "guard": "denied_after_wait"}))
                        self.last_next_action_index = index + 1
                        if on_action_complete:
                            on_action_complete(self.last_next_action_index, list(results))
                        continue

            try:
                response = await self._execute_action(action, recent_posts)
                success = self._is_success(action, response)
                if success and action.action == "post" and action.text:
                    recent_posts.append(action.text)
                results.append(self._build_result(action, success, response))
            except Exception as exc:
                results.append(self._build_result(action, False, {"error": str(exc)}))

            self.last_next_action_index = index + 1
            if on_action_complete:
                on_action_complete(self.last_next_action_index, list(results))

            await self._human_delay(action)
        else:
            self.last_next_action_index = len(actions)

        return results

    async def _execute_action(
        self,
        action: AgentAction,
        recent_posts: list[str],
    ) -> dict[str, Any]:
        if action.action == "comment":
            return await self._execute_comment(action)
        if action.action == "like":
            return await self._sdk.like_post(action.target)
        if action.action == "follow":
            return await self._sdk.follow_user(action.target)
        if action.action == "quote_repost":
            return await self._sdk.quote_repost(action.target, comment=action.text)

        resolved_visual = await self._resolve_visual(action)
        response = await self._sdk.create_post(
            text=action.text,
            coin=self._resolve_coin(action),
            sentiment=action.sentiment,
            image_path=resolved_visual.path if resolved_visual else None,
            recent_posts=recent_posts,
        )
        if resolved_visual:
            response = {**response, "resolved_visual": {"path": resolved_visual.path, "kind": resolved_visual.kind, "signature": resolved_visual.signature}}
        return response

    async def _execute_comment(self, action: AgentAction) -> dict[str, Any]:
        if action.like or action.follow:
            return await self._sdk.engage_post(
                action.target,
                like=action.like,
                comment=action.text,
                follow=action.follow,
            )
        return await self._sdk.comment_on_post(action.target, action.text)

    def _resolve_coin(self, action: AgentAction) -> str | None:
        if action.image_path or action.chart_image or action.visual_kind:
            return None
        return action.coin

    async def _resolve_visual(self, action: AgentAction):
        return await self._visuals.resolve(action)

    def _is_success(self, action: AgentAction, response: dict[str, Any]) -> bool:
        if action.action == "comment" and (action.like or action.follow):
            return bool(
                response.get("commented")
                or response.get("liked")
                or response.get("followed")
                or response.get("success")
            )
        return bool(response.get("success"))

    def _build_result(
        self,
        action: AgentAction,
        success: bool,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "action": action.action,
            "target": action.target,
            "target_author": action.target_author,
            "priority": action.priority,
            "reason": action.reason,
            "success": success,
            "response": response,
        }

    def _dry_run(self, plan: AgentPlan) -> list[dict[str, Any]]:
        """Execute plan in dry-run mode: no SDK calls, just simulate results."""
        results: list[dict[str, Any]] = []
        for action in plan.sorted_actions():
            logger.info("DRY RUN: %s target=%s text_preview=%s",
                        action.action, action.target, (action.text or "")[:60])
            results.append(self._build_result(action, True, {"dry_run": True}))
        self.last_completed = True
        self.last_next_action_index = len(plan.sorted_actions())
        return results

    async def _human_delay(self, action: AgentAction) -> None:
        delays = getattr(self, "_delay_config", None)
        if action.action in {"comment", "post", "quote_repost"}:
            lo = delays.post_action_delay_min if delays else 8.0
            hi = delays.post_action_delay_max if delays else 15.0
        else:
            lo = delays.light_action_delay_min if delays else 3.0
            hi = delays.light_action_delay_max if delays else 7.0
        await asyncio.sleep(random.uniform(lo, hi))
