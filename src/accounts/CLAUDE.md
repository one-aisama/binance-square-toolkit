# Module: accounts
# Purpose: loading account/persona configs from YAML, daily limits, anti-detect
# Specification: docs/specs/spec_accounts.md

## Files
| File | Lines | What it does |
|------|-------|------------|
| manager.py | 94 | load_accounts() + load_personas() — reading YAML, merging persona into AccountConfig via Pydantic |
| limiter.py | 87 | ActionLimiter — checking daily counters vs randomized limit, writing to actions_log + daily_stats |
| anti_detect.py | 16 | are_own_accounts() + should_skip_post_by_author() — preventing cross-account interactions |

## Dependencies
- Uses: `db` (ActionLimiter reads/writes actions_log and daily_stats)
- Used by: `scheduler` (load_accounts at startup, ActionLimiter checked on every action)
- Used by: `activity` (ActivityExecutor receives ActionLimiter, TargetSelector uses account IDs)

## Key Functions
- `load_accounts(accounts_dir, personas_path)` — returns `list[AccountConfig]`
- `ActionLimiter(db_path)` — constructor
- `ActionLimiter.check_allowed(account_id, action_type, daily_limit)` — deterministic limit via seed hash
- `ActionLimiter.record_action(account_id, action_type, target_id, status, error)` — writes to DB
- `should_skip_post_by_author(post_author_id, own_account_ids)` — returns bool

## Common Tasks
- Add an account: create YAML in `config/accounts/`, specify persona_id from personas.yaml
- Change limits: `limits` block in account YAML or `LimitsConfig` defaults
- Debug limits: seed = hash(f"{account_id}:{date}:{action_type}") — deterministic

## Known Issues
- No validation that `adspower_profile_id` actually exists in AdsPower
- 2 bugs in limit counting in ActionLimiter
