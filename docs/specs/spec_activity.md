# Specification: Activity Module

**Path:** `src/activity/`
**Files:** `executor.py`, `target_selector.py`, `randomizer.py`, `comment_gen.py`

---

## Description

> **Module status in v3:** Legacy. `ActivityExecutor` is only used in `src/scheduler/scheduler.py` (not active). In the current deployment (runtime v3), likes, comments, follows, and reposts are executed via `PlanExecutor` -> `SDK` -> `browser_actions/browser_engage`. Target selection is handled by `DeterministicPlanGenerator` + `PersonaPolicy`. Delays are managed by `src/runtime/behavior.py`. Post and comment text is written by the agent (Claude Code session).

The Activity module provides legacy tools for interacting with posts: target selection (`TargetSelector`), randomization (`HumanRandomizer`), AI comment generation (`CommentGenerator`). These components may be useful outside of runtime, but are not involved in the current control flow.

---

## User Stories

- As an agent, I want to run a like/comment/repost cycle on a list of parsed posts, to build engagement for an account.
- As an agent, I want posts to be filtered to exclude my own accounts and low-engagement content, so I never interact with my own posts and focus on high-visibility content.
- As an agent, I want human-like random delays between actions and probabilistic skips, so activity patterns look natural.
- As an agent, I want AI-generated comments that sound like a real person responding to a specific post, so comments are relevant rather than templated.
- As an agent, I want daily limits enforced per action type, so accounts don't exceed safe activity thresholds.

---

## Data Model

No dedicated tables. The module reads/writes through `ActionLimiter` (from `src/accounts/limiter.py`), which uses the `actions_log` and `daily_stats` tables.

---

## API

### ActivityExecutor (`src/activity/executor.py`)

```python
class ActivityExecutor:
    def __init__(
        self,
        client: BapiClient,
        limiter: ActionLimiter,
        randomizer: HumanRandomizer,
        target_selector: TargetSelector,
        comment_generator=None,
    )
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `run_cycle` | `(account_id: str, posts: list[dict], limits: dict[str, list[int]]) -> dict[str, int]` | `{"likes": N, "comments": N, "reposts": N, "skipped": N, "errors": N}` |

**Cycle behavior:**
1. **Likes:** Selects `random.randint(*limits["like"])` targets. For each: check daily limit, possibly skip (randomizer), call `BapiClient.like_post()`.
2. **Comments:** Selects `random.randint(*limits["comment"])` targets from high-engagement posts. For each: check limit, possibly skip, generate comment text via `CommentGenerator`, call `BapiClient.comment_post()` (currently a stub -- raises `NotImplementedError`).
3. **Reposts:** Selects `random.randint(*limits["repost"])` top posts. Same flow as comments but calls `BapiClient.repost()` (stub).

When a stub raises `NotImplementedError`, the cycle breaks with a warning log. This is expected behavior until comments/reposts are connected to `browser_actions`.

---

### TargetSelector (`src/activity/target_selector.py`)

```python
class TargetSelector:
    def __init__(self, own_account_ids: set[str], min_views: int = 1000)
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `select_like_targets` | `(posts: list[dict], count: int) -> list[dict]` | Random sample from eligible posts |
| `select_comment_targets` | `(posts: list[dict], count: int) -> list[dict]` | From the top half by views, shuffled |
| `select_repost_targets` | `(posts: list[dict], count: int) -> list[dict]` | Top posts by views |

**Filtering (`_filter_eligible`):**
- Excludes posts where `author_id` is in `own_account_ids`
- Excludes posts with `view_count < min_views`

---

### HumanRandomizer (`src/activity/randomizer.py`)

```python
class HumanRandomizer:
    def __init__(self, delay_range: tuple[int, int] = (30, 120), skip_rate: float = 0.35)
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `should_skip` | `() -> bool` | `True` with probability `skip_rate` |
| `human_delay` | `() -> None` | `await asyncio.sleep(random.uniform(*delay_range))` |

---

### CommentGenerator (`src/activity/comment_gen.py`)

```python
class CommentGenerator:
    def __init__(self, provider: str = "deepseek", model: str = "deepseek-chat", api_key: str = "")
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `generate` | `(post_text: str, author_name: str = "") -> str` | Comment text (1-2 sentences) |
| `generate_comment` | `(post_text: str, persona_style: str = "", comment_type: str \| None = None) -> str` | Backward-compatible alias for `generate()` |

**Providers:** `"deepseek"` (via OpenAI-compatible API at `api.deepseek.com`), `"openai"`, `"anthropic"`.

**System prompt** ensures:
- Maximum 1-2 sentences
- Relevance to the specific post content
- Conversational, informal tone (addressing the author)
- No templated comments ("Great post!", "Thanks for sharing!")
- Types: agreement, question, addition, mild disagreement

Strips surrounding quotes from AI output. Returns an empty string on generation error.

---

## Business Logic

### Anti-detection
- `TargetSelector` prevents interaction with own accounts
- `HumanRandomizer` adds a 30-120 second delay between actions
- 35% of actions are randomly skipped
- Comments only on posts with >1000 views (configurable)

### Limit Control
`ActivityExecutor` checks `ActionLimiter.check_allowed()` before each action. The limiter uses a deterministic daily limit: `hash(account_id:date:action_type)` seeds the RNG, which picks a number in the configured range `[min, max]`. The same account+date+type always gets the same limit.

### Comment Generation vs browser_actions

> **Current state (v3):** `BapiClient.comment_post()`, `BapiClient.repost()`, and `BapiClient.create_post()` are stubs (NotImplementedError). Bapi endpoints for these actions have not been discovered. Actual comment, repost, and post execution goes through `browser_actions` (Playwright CDP). `browse_and_interact()` has been removed -- the agent decides what to do on its own.

Working path: `sdk.comment_on_post()` -> `browser_actions.comment_on_post()` (DOM).
Working path: `sdk.create_post()` -> `browser_actions.create_post()` (DOM).
Working path: `sdk.quote_repost()` -> `browser_actions.repost()` (DOM).

ActivityExecutor from this module is a legacy orchestrator. In v3 runtime, `PlanExecutor` from `src/runtime/plan_executor.py` is used instead.

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| All posts filtered out (own accounts or low views) | `select_*_targets` returns an empty list, no actions performed |
| `CommentGenerator` returns an empty string | Executor should use fallback text or skip the comment |
| `BapiClient.comment_post()` raises NotImplementedError | Warning logged, comment cycle breaks, likes may still work |
| Daily limit already reached | `check_allowed` returns False, cycle breaks for that action type |
| `posts` list is empty | No targets selected, cycle returns all zeros |
| AI API is unavailable | `CommentGenerator.generate()` returns an empty string, error is logged |

---

## Priority and Dependencies

- **Priority:** Medium (likes work via httpx; comments/reposts require browser_actions integration)
- **Depends on:** `src/bapi/client.py` (like_post), `src/accounts/limiter.py` (ActionLimiter), `src/session/browser_actions.py` (for comments/reposts via CDP)
- **Blocks:** Full activity cycles in the scheduler
