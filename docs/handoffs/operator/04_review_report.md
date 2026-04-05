# QA Review: operator (Stage 3 — Strategic Control)
# Date: 2026-04-04
# Reviewer: qa-reviewer (opus)

## Verdict: CONDITIONAL

## Critical (blockers — fix before merge):
None.

## Major (fix before merge):

1. **src/runtime/editorial_brain.py — 604 lines, exceeds 500-line limit.**
   The project standard (CLAUDE.md) caps files at 500 lines. This file was already close before Stage 3 and the directive integration pushed it over. Needs to be split (e.g., extract symbol scoring or template resolution into a separate module).

2. **Three of seven directive fields are dead data: `comment_direction`, `post_direction`, `tone`.**
   `strategic_bridge.py:35-38` defines these fields in the prompt, and the LLM will spend tokens generating them, but no Python code reads or uses them. `editorial_brain.py` only consumes `preferred_coins`, `avoid_coins`, and `skip_families`. Either wire these fields into the planner/editorial brain or remove them from the schema to avoid misleading the persona subagent.

3. **`agent_dir` parameter accepted but unused in both bridges.**
   `strategic_bridge.py:76` and `reflection_bridge.py:48` accept `agent_dir` but never reference it. The prompt templates hardcode `agents/{agent_id}/` paths instead. This is a dead parameter that could confuse future callers — either use it (to support non-default agent directories) or remove it from the signature.

## Minor (tech debt — can fix later):

1. **`session_run.py` is 461 lines — approaching the 500-line limit.**
   Not yet over, but close. The `run_post_only` function (lines 390-437) could be extracted.

2. **Reflection bridge gives `Edit` permission to subagent (`--allowedTools Read,Edit,Write`).**
   This is broader than strategic bridge (`Read,Write`). Confirm that `Edit` is intentional — the reflection prompt says "Read each file first, then edit it" which justifies Edit. However, persona bridge also has `Bash` access (`--allowedTools Edit,Read,Write,Bash`). The permission surface varies across bridges without a documented rationale.

3. **No test for `generate_strategic_directive()` or `reflect_on_cycle()` async behavior.**
   The test files only cover directive loading/parsing and prompt template formatting. The actual subprocess spawning logic (timeout handling, returncode checks, FileNotFoundError) is not unit-tested. The `test_operator_strategic_flow.py` tests mock the entire function. A unit test that mocks `asyncio.create_subprocess_exec` would improve coverage of the timeout/kill paths.

4. **`_find_latest_context_summary` relies on lexicographic sort of filenames.**
   `strategic_bridge.py:49` uses `sorted(..., reverse=True)` on glob results. This works correctly only if filenames are zero-padded ISO timestamps (`20260404T120000Z_example_macro.md`). If any file breaks this pattern (e.g., extra prefix), the "latest" heuristic fails silently. Not a bug today, but fragile.

5. **Plan step ordering discrepancy with plan document.**
   The plan (`humble-purring-riddle.md`, Stage 3) describes the flow as: `prepare -> compile -> strategize -> plan -> author -> execute -> reflect`. The actual implementation in `loop.py:185` is: `compile -> strategize -> prepare -> author -> audit -> execute -> reflect`. The reordering is correct (compile must precede strategize so the briefing packet is ready), but the plan document is now stale and should be updated.

6. **Pre-existing test failures in `test_agent_config.py` (2 tests).**
   `test_load_active_agent` and `test_load_example_altcoin_agent_config` fail on `cycle_interval_minutes` assertion. These are not caused by Stage 3 changes but indicate config values were changed without updating test expectations.

## Checklist results

### Security: 5/5 relevant checks passed
- [x] No hardcoded secrets — all secrets from .env
- [x] .env in .gitignore
- [x] SQL: parameterized queries only (no raw SQL in new code)
- [x] Subprocess uses `create_subprocess_exec` (not shell) — no shell injection
- [x] Prompt template values (agent_id, paths) come from trusted config, not user input

### Spec compliance: 3/5 passed
- [x] Directive reaches planner via `session_run.py` -> `generate_plan()` -> `build_post_brief()`
- [x] Directive reaches editorial brain (preferred_coins, avoid_coins, skip_families all wired)
- [ ] Three directive fields (`comment_direction`, `post_direction`, `tone`) are defined but unused
- [x] Backward compatibility: all `strategic_directive: dict | None` paths handle None correctly
- [ ] Plan document flow order is stale

### Code quality: 5/7 passed
- [ ] All files < 500 lines — `editorial_brain.py` is 604 lines
- [x] All functions < 100 lines
- [x] No empty catch/except blocks
- [x] No hardcoded URLs, keys, timeouts (timeouts from OperatorConfig)
- [x] All public functions typed
- [x] Error messages include WHERE + WHAT + CONTEXT
- [ ] Dead parameter: `agent_dir` unused in both bridges

### Tests: 4/5 passed
- [x] All 16 Stage 3 tests pass
- [x] Test names describe what they verify
- [x] Tests contain real assertions
- [x] Edge cases covered (missing directive, invalid JSON, missing focus_summary, strategize/reflect failures)
- [ ] No unit tests for subprocess timeout/kill paths in bridges

### Total: 17/22 passed

## Positive observations
- **Non-fatal design is correct and well-tested.** Both `generate_strategic_directive` and `reflect_on_cycle` failures are properly handled as non-fatal — the micro-cycle continues. Three separate tests verify this: strategize failure, reflect failure, and the full happy path ordering.
- **Clean separation of concerns.** The strategic bridge writes a JSON file, the planner reads it independently via `load_strategic_directive()`. No tight coupling between the two.
- **Backward compatibility is solid.** Every `strategic_directive` parameter defaults to `None`, and all consumers (editorial brain, deterministic planner) have explicit `if strategic_directive:` guards. First-cycle-without-directive case works.
- **The -500 penalty for skip_families is effective.** Given that family base scores are in the 100-220 range, a -500 penalty guarantees the family won't be selected unless all alternatives are also penalized.
- **Subprocess execution uses `create_subprocess_exec` everywhere.** No shell=True, no injection vectors.
