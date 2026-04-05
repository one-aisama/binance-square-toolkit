# Binance Square Toolkit — Design Specification
Date: 2026-04-03
Status: CURRENT (v3, policy-driven)

## Overview

SDK / toolkit for managing activity on Binance Square via AdsPower profiles.
**Software = hands. Agent = brain. Runtime = coordination.**

- Software (SDK) executes actions: posting, likes, comments, follows
- Agent (Claude session) makes decisions and generates content
- Runtime framework coordinates: planning, audit, execution, metrics

Monetization via Write to Earn (5% base trading commission from readers).

## Architecture by Layers

```
┌─────────────────────────────────────────────────────┐
│  Entry points: session_run.py / main.py             │
├─────────────────────────────────────────────────────┤
│  Runtime framework (src/runtime/, 29 modules)       │
│  session_loop → planner → auditor → executor        │
├─────────────────────────────────────────────────────┤
│  Data pipeline                                       │
│  metrics/ → memory/ → strategy/                     │
├─────────────────────────────────────────────────────┤
│  SDK facade (src/sdk.py)                            │
├──────────┬──────────┬───────────┬───────────────────┤
│ session/ │ bapi/    │ content/  │ activity/         │
├──────────┴──────────┴───────────┴───────────────────┤
│  accounts/ │ db/ (SQLite WAL) │ config/ (YAML)      │
└─────────────────────────────────────────────────────┘
```

### Transport
- **sdk.py** — unified facade for the agent: connect, create_post, comment, like, follow, feed, market data
- **session/** — AdsPower CDP, browser_actions (publishing), browser_engage (engagement), browser_data (parsing), harvester (credentials)
- **bapi/** — httpx client for Binance bapi with retry and rate limit (30 RPM)

### Coordination
- **topic_reservations** (SQLite) — cross-agent topic locking (coin+angle+source), TTL 2 hours
- **post_registry** — registry of published posts (72-hour window) for overlap avoidance

### Runtime Framework
Autonomous agent cycle:
1. **SessionContextBuilder** → context collection (market, news, TA, feed, replies)
2. **CyclePolicy** → stage selection (bootstrap / default / overflow / reply_limited)
3. **DeterministicPlanGenerator** → JSON plan (comment, like, follow, post) without LLM
4. **EditorialBrain** → brief for the post (family, coin, angle, hooks, insights)
5. **Agent** (Claude Code session) → writes text itself, using brief_context and its own files
6. **PlanAuditor** → deterministic validation (8 layers: style, duplicates, overlap, reservations)
7. **PlanExecutor** → execution via SDK + VisualPipeline (images)
8. **Commit** → daily_plan, post_registry, topic_reservation, journal

### Policy (per-agent)
- **persona_policies/{agent_id}.yaml** — all behavioral parameters: content mix, coin bias, angle rules, stages, audit style, comment stance, feed scoring
- **active_agent.{agent_id}.yaml** — runtime binding: AdsPower profile, symbols, session limits, visual config
- **accounts/{agent_id}.yaml** — daily limits, proxy, credentials

### Data Pipeline
- **metrics/** — store (SQLite), collector (deferred outcome collection 6h+), scorer (insight aggregation + auto-lessons)
- **memory/** — compactor: generates performance.md, relationships.md from insights
- **strategy/** — analyst (updates strategy.md), reviewer (session stats + journal), feed_filter (spam filter)
- **pipeline.py** — orchestration: collector → scorer → compactor → analyst

### State (per-agent files)
- `data/runtime/{agent_id}/` — checkpoint.json, daily_plan.json, status.json
- `data/generated_visuals/{agent_id}/` — AI-generated images
- `agents/{agent_id}/` — identity, style, strategy, lessons, journal, performance, relationships

## Hybrid Transport (httpx + Playwright CDP)

- **httpx** — parsing (feed, articles, trends, market data), likes. Fast, no browser.
- **Playwright CDP** — posting, commenting, reposts, follows. Requires client-side signature.
- **Credentials** — captured via CDP, stored in SQLite (encrypted), used by httpx.

## Module Map

| Module | Path | Purpose |
|--------|------|---------|
| sdk | src/sdk.py | Unified facade for the agent |
| session | src/session/ | AdsPower, CDP, browser actions/data, web authoring |
| bapi | src/bapi/ | httpx client for Binance bapi |
| parser | src/parser/ | Feed parsing, articles, trends |
| content | src/content/ | AI generation, validation, market data, news, TA |
| activity | src/activity/ | Likes, comments, reposts (orchestration) |
| runtime | src/runtime/ | 29 modules: planning, audit, execution, guard |
| metrics | src/metrics/ | MetricsStore, Collector, Scorer |
| memory | src/memory/ | Compactor (performance.md, relationships.md) |
| strategy | src/strategy/ | Planner, Analyst, Reviewer, FeedFilter |
| pipeline | src/pipeline.py | Data pipeline orchestration |
| accounts | src/accounts/ | YAML configs, limits, anti-detect |
| db | src/db/ | SQLite schema (10 tables), initialization |

## Database (SQLite + WAL mode)

10 tables: credentials, actions_log, daily_stats, parsed_trends, parsed_posts, discovered_endpoints, post_tracker, topic_reservations, comment_locks, news_cooldowns.

YAML is the source of truth for configs. SQLite stores runtime data.

## Adding a New Agent

1. `config/persona_policies/{id}.yaml` — behavioral policy
2. `config/active_agent.{id}.yaml` — runtime binding (AdsPower, symbols, visual)
3. `config/accounts/{id}.yaml` — account credentials and daily limits
4. `agents/{id}/` — identity.md, style.md, strategy.md, prompt.md, visual_profile.md
5. Zero changes to Python code

## Known Limitations

1. **create_post() confirmation** — publish confirmation via network response (`content/add`). If absent — `publish_unconfirmed`. Needs robust fallback (composer cleared, success toast, URL change).
2. **BapiClient stubs** — `comment_post()`, `repost()`, `create_post()` via httpx — stubs (NotImplementedError). Real path: browser_actions (CDP).
3. **Selectors** — CSS selectors in page_map.py are fragile. Binance Square UI updates can break them.

## Dependencies

```
httpx>=0.27
playwright>=1.40
anthropic>=0.40
openai>=1.50
apscheduler>=3.10,<4.0
aiosqlite>=0.20
pyyaml>=6.0
pydantic>=2.5
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.23
```
