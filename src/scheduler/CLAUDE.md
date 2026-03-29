# Module: scheduler
# Purpose: optional pipeline orchestration on a schedule (agent can manage timing directly)
# Specification: no separate spec (see docs/design-spec.md, scheduler section)

## Files
| File | Lines | What it does |
|------|-------|------------|
| scheduler.py | 304 | CycleScheduler — APScheduler wrapper, runs pipelines per account |

## Dependencies
- Uses: all other modules (session, bapi, parser, content, activity, accounts, db)
- Entry point: `src/main.py` constructs and starts CycleScheduler

## Key Functions
- `CycleScheduler(settings, accounts, db_path)` — creates CredentialStore + ActionLimiter
- `CycleScheduler.start()` — starts APScheduler, first cycle in 5s if `first_run_immediate: true`
- `CycleScheduler.stop()` — stops scheduler
- `_run_cycle()` — iterates through accounts, calls `_process_account()`
- `_process_account(account)` — pipeline: validate creds, parse, generate, publish, activity
- `_refresh_credentials(account)` — AdsPower start, harvest, save, stop
- `_generate_content(account, topics, bapi_client)` — select topics, market data, queue content
- `_run_activity(account, posts, bapi_client)` — ActivityExecutor + run_cycle

## Role in the System
The scheduler is optional. It executes defined pipelines on a timer but does not make creative decisions.
The agent (Claude/Codex) can completely replace the scheduler by calling software functions directly.

## Common Tasks
- Change cycle frequency: `cycle_interval_hours` in settings YAML
- Add a pipeline step: method `_do_step()`, call in `_process_account()`
- Debug a cycle: search for "CYCLE STARTED" / "CYCLE COMPLETED" in logs

## Known Issues
- Activity loop calls bapi comment/repost (stubs) — logs warning, continues
- Publishing loop calls create_post (stub) — content stays in queue
- Accounts are processed sequentially, no parallelism
