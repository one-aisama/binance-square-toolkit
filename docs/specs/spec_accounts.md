# Specification: Accounts Module

**Path:** `src/accounts/`
**Files:** `manager.py`, `limiter.py`, `anti_detect.py`

---

## Description

The Accounts module provides tools for loading account/persona configurations from YAML, controlling daily action limits, and preventing cross-account interactions. The agent uses this module to know which accounts exist, what personas and limits they have, and to check whether an action is allowed before executing it.

---

## User Stories

- As an agent, I want to load all account configs with merged persona data, so I know the style, topics, and limits of each account.
- As an agent, I want to check whether a specific action is allowed for an account today, so I don't exceed safe daily thresholds.
- As an agent, I want every action (success or failure) to be recorded in the DB, so I can track activity and debug.
- As an agent, I want to verify that the target post is not written by one of my accounts, so I never create self-interactions.

---

## Data Model

### Pydantic Config Models (`src/accounts/manager.py`)

```python
class ProxyConfig(BaseModel):
    host: str
    port: int

class LimitsConfig(BaseModel):
    posts_per_day: list[int] = [3, 5]
    likes_per_day: list[int] = [30, 60]
    comments_per_day: list[int] = [12, 24]
    min_interval_sec: int = 90

class PersonaConfig(BaseModel):
    id: str
    name: str
    topics: list[str]
    style: str
    language: str = "en"

class AccountConfig(BaseModel):
    account_id: str
    persona_id: str
    binance_uid: str = ""
    adspower_profile_id: str
    proxy: ProxyConfig | None = None
    limits: LimitsConfig = LimitsConfig()
    persona: PersonaConfig | None = None  # Populated after merge
```

### DB Tables (read/written by ActionLimiter)

```sql
CREATE TABLE IF NOT EXISTS actions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    action_type TEXT NOT NULL,       -- post | like | comment | repost | follow
    target_id TEXT,
    status TEXT DEFAULT 'success',   -- success | failed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    posts_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    reposts_count INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    UNIQUE(account_id, date)
);
```

---

## API

### load_accounts / load_personas (`src/accounts/manager.py`)

```python
def load_personas(personas_path: str) -> dict[str, PersonaConfig]
def load_accounts(accounts_dir: str, personas_path: str) -> list[AccountConfig]
```

`load_accounts` reads all `*.yaml` files from `accounts_dir` (skipping files starting with `_` or `.`), parses each into `AccountConfig`, and merges with the corresponding persona from `personas_path`. Returns a list of fully configured accounts.

---

### ActionLimiter (`src/accounts/limiter.py`)

```python
class ActionLimiter:
    def __init__(self, db_path: str)
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `check_allowed` | `(account_id: str, action_type: str, daily_limit: list[int]) -> bool` | True if today's count < deterministic daily limit |
| `record_action` | `(account_id: str, action_type: str, target_id: str \| None, status: str, error: str \| None) -> None` | Writes to actions_log + upserts daily_stats |
| `get_today_count` | `(account_id: str, action_type: str) -> int` | Count of successful actions for today |

**Deterministic daily limit:** for each triple `(account_id, date, action_type)` a seed hash determines the exact limit within the range `[min, max]`. One account gets the same limit all day, but different limits on different days. Prevents predictable patterns.

---

### anti_detect (`src/accounts/anti_detect.py`)

```python
def are_own_accounts(account_id_1: str, account_id_2: str, all_account_ids: set[str]) -> bool
def should_skip_post_by_author(post_author_id: str, own_account_ids: set[str]) -> bool
```

Simple set membership checks. `should_skip_post_by_author` returns `True` if the post author is one of our accounts.

---

## Business Logic

### Config Loading Pipeline
```
config/personas.yaml  ->  load_personas()  ->  dict[str, PersonaConfig]
config/accounts/*.yaml  ->  load_accounts()  ->  list[AccountConfig]
                                                    (each with merged persona)
```

Files starting with `_` (e.g. `_example.yaml`) are skipped. If a persona_id from the account config doesn't exist in personas.yaml — a warning is logged, but the account is loaded (with `persona = None`).

### Daily Limit Control
```
Agent wants to like a post for account X
  -> calls limiter.check_allowed("X", "like", [30, 60])
  -> limiter counts today's successful likes for X
  -> limiter computes deterministic limit for today (e.g. 47)
  -> returns True if count < 47, False otherwise
  -> after successful like: limiter.record_action("X", "like", target_id="post123")
```

### Daily Stats Upsert
`record_action` writes to both tables: `actions_log` (separate row) and `daily_stats` (upsert increment). The updated column depends on `action_type` (maps to `{type}s_count`), and `status` failed increments `errors_count`.

---

## Edge Cases

| Situation | Expected Behavior |
|-----------|-------------------|
| No account YAML files in directory | `load_accounts` returns empty list, logs warning |
| Account references non-existent persona_id | Warning logged, account loads with `persona = None` |
| Invalid YAML format | Pydantic validation error |
| `daily_limit` with [min > max] | `random.randint` raises ValueError |
| `check_allowed` with empty actions_log | Count = 0, always allowed (unless limit is [0, 0]) |
| `record_action` without existing daily_stats row | INSERT creates new row via UPSERT |
| Multiple `check_allowed` calls between actions | Count doesn't change until `record_action` is called |

---

## Priority and Dependencies

- **Priority:** High (all modules depend on account configs and limits)
- **Depends on:** `src/db/` (actions_log and daily_stats tables must exist)
- **Blocks:** `src/activity/` (ActivityExecutor uses ActionLimiter), `src/scheduler/` (loads accounts at startup)
