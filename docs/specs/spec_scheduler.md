# Specification: scheduler
# Module: src/scheduler/
# Status: optional

## Purpose
Pipeline orchestration on a schedule via APScheduler.
**Optional** — the agent (Claude/Codex) can manage timing directly by calling software functions without the scheduler.

## Files
| File | What it does |
|------|------------|
| scheduler.py | `CycleScheduler` — APScheduler wrapper, runs pipelines per account |

## Class CycleScheduler

### Constructor
```python
CycleScheduler(settings: dict, accounts: list[AccountConfig], db_path: str)
```
Creates: `CredentialStore`, `ActionLimiter`, `AdsPowerClient`, `AsyncIOScheduler`.

### Methods
| Method | What it does |
|--------|------------|
| `start()` | Starts APScheduler, first cycle in 5s if `first_run_immediate: true` |
| `stop()` | Stops scheduler |
| `_run_cycle()` | Iterates through accounts, calls `_process_account()` |
| `_process_account(account)` | Pipeline: validate creds → parse → generate → publish → activity |
| `_refresh_credentials(account)` | AdsPower start → harvest → save → stop |
| `_generate_content(account, topics, bapi_client)` | Select topics, market data, queue content |
| `_run_activity(account, posts, bapi_client)` | ActivityExecutor + run_cycle |

## Single Account Pipeline
```
1. Check credentials (valid + not expired)
   → if expired: _refresh_credentials()
2. Create BapiClient with credentials
3. TrendFetcher.fetch_all() → topics
4. rank_topics() → sorted
5. _generate_content() → queue
6. ContentPublisher.publish_pending() → publish
7. _run_activity() → likes, comments, reposts
```

## Configuration
Settings from `config/settings.yaml`:
- `cycle_interval_hours` — cycle frequency
- `first_run_immediate` — run first cycle immediately
- `adspower_base_url` — AdsPower API URL

## Dependencies
Uses ALL modules: session, bapi, parser, content, activity, accounts, db.

## Role in the System
Scheduler = pipeline for autonomous operation. Does not make creative decisions.
The agent can completely replace the scheduler by calling software functions directly based on human instructions.

## Known Issues
- Activity loop calls bapi comment/repost (stubs) — logs warning
- Publishing loop calls create_post (stub) — content stays in queue
- Accounts are processed sequentially, no parallelism
