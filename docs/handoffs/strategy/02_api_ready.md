# API: strategy (planner, analyst, reviewer)

## Refactoring Summary
Removed `_call_llm()` and LLM prompt building from all three modules. The agent IS a Claude session -- it does not need to call an external LLM API. Instead, modules now expose `prepare_context()` methods that return structured markdown text for the agent to read and act on.

## API Changes

### SessionPlanner (planner.py)
- `create_plan(filtered_feed, market_data, news, is_bootstrap)` -- now synchronous (was async), always returns bootstrap plan. Use for bootstrap only.
- `prepare_context(filtered_feed, market_data, news) -> str` -- NEW. Returns formatted context string with strategy.md, lessons.md, relationships.md, feed, market, news. Agent reads this and creates its own plan.
- `validate_plan(plan) -> list[dict]` -- unchanged.
- REMOVED: `_call_llm()`, `_build_prompt()`

### StrategyAnalyst (analyst.py)
- `analyze(agent_id, market_summary) -> str | None` -- was `-> None`. Now returns context string for agent (or None if bootstrap strategy was written).
- `prepare_context(agent_id, market_summary, total_sessions) -> str` -- NEW. Returns formatted context with performance.md, relationships.md, lessons.md, tactics.md, current strategy.md.
- `should_run(agent_id) -> bool` -- unchanged.
- REMOVED: `_call_llm()`

### SessionReviewer (reviewer.py)
- `review(session_id, agent_id, started_at, plan, results, guard_stats) -> str` -- was `-> None`. Now returns review context string.
- `prepare_review_context(plan, results, guard_stats) -> str` -- NEW. Returns formatted context with session stats, action breakdown, failures, skipped actions, current lessons.
- REMOVED: `_call_llm()`

## Breaking changes
- `planner.create_plan()` is now synchronous (no `await` needed)
- `analyst.analyze()` returns `str | None` instead of `None`
- `reviewer.review()` returns `str` instead of `None`

## Pipeline impact
- `src/pipeline.py` updated: removed `NotImplementedError` catch (no longer raised)

## Tests
- 174 tests pass (no regressions)
- No strategy-specific tests existed before; none added (these are context-formatting methods, not business logic with edge cases)

## Usage pattern for agent
```python
planner = SessionPlanner(agent_dir)
if is_bootstrap:
    plan = planner.create_plan(filtered_feed, market_data, news, is_bootstrap=True)
else:
    context = planner.prepare_context(filtered_feed, market_data, news)
    # Agent reads context, decides plan, then validates:
    plan = planner.validate_plan(agent_created_plan)

analyst = StrategyAnalyst(agent_dir, store)
if await analyst.should_run(agent_id):
    context = await analyst.analyze(agent_id, market_summary)
    if context:  # None means bootstrap was written automatically
        # Agent reads context, rewrites strategy.md

reviewer = SessionReviewer(store, agent_dir)
review_context = await reviewer.review(session_id, agent_id, started_at, plan, results, guard_stats)
# Agent reads review_context, decides what lessons to add
```
