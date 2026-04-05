# Specification: scheduler
# Module: src/scheduler/
# Status: optional

## Purpose
Pipeline orchestration on a schedule via APScheduler.
**Optional** -- the agent (Claude/Codex) can manage timing directly by calling the software's functions without the scheduler.

## Files
| File | What It Does |
|------|--------------|
| scheduler.py | `CycleScheduler` -- APScheduler wrapper, runs pipelines per account |

## CycleScheduler Class

### Constructor
```python
CycleScheduler(settings: dict, accounts: list[AccountConfig], db_path: str)
```
Creates: `CredentialStore`, `ActionLimiter`, `AdsPowerClient`, `AsyncIOScheduler`.

### Methods
| Method | What It Does |
|--------|--------------|
| `start()` | Starts APScheduler, first cycle in 5s if `first_run_immediate: true` |
| `stop()` | Stops the scheduler |
| `_run_cycle()` | Iterates over accounts, calls `_process_account()` |
| `_process_account(account)` | Pipeline: validate creds -> parse -> generate -> publish -> activity |
| `_refresh_credentials(account)` | AdsPower start -> harvest -> save -> stop |
| `_generate_content(account, topics, bapi_client)` | Topic selection, market data, queue insertion |
| `_run_activity(account, posts, bapi_client)` | ActivityExecutor + run_cycle |

## Single Account Pipeline
```
1. Check credentials (valid + not expired)
   -> if expired: _refresh_credentials()
2. Create BapiClient with credentials
3. TrendFetcher.fetch_all() -> topics
4. rank_topics() -> sorted
5. _generate_content() -> queue
6. ContentPublisher.publish_pending() -> publish
7. _run_activity() -> likes, comments, reposts
```

## Configuration
Settings from `config/settings.yaml`:
- `cycle_interval_hours` -- cycle frequency
- `first_run_immediate` -- run the first cycle immediately
- `adspower_base_url` -- AdsPower API URL

## Dependencies
Uses ALL modules: session, bapi, parser, content, activity, accounts, db.

## Role in the System
Scheduler = pipeline for autonomous operation. Does not make creative decisions.
The agent can replace the scheduler entirely by calling the software's functions directly on human instruction.

## Known Issues
- Activity loop calls bapi comment/repost (stubs) -- logs a warning
- Publishing loop calls create_post (stub) -- content stays in the queue
- Accounts are processed sequentially, no parallelism
