# Binance Square Toolkit

## Overview
SDK for managing activity on Binance Square through AdsPower browser profiles.
Software = hands (executes actions). Agent = brain (makes decisions, generates content).

## Tech Stack
- Python 3.12
- httpx (async HTTP — parsing, likes)
- Playwright (CDP — posts, comments, follows, reposts)
- SQLite + aiosqlite (runtime data)
- AdsPower Local API (browser profile management)
- Pydantic v2 (config validation)

## Architecture: Hybrid (httpx + Playwright CDP)
- **httpx** — parsing, likes, market data (fast, no browser needed)
- **Playwright CDP** — posts, comments, reposts, follows (require client-side signature or DOM)
- **Credentials** — captured via CDP once, then reused by httpx for parsing/likes

## Module Map
| Module | Path | Purpose | Status |
|--------|------|---------|--------|
| **sdk** | **src/sdk.py** | **Unified facade for agent — connect, get_feed, comment, post, like, follow** | **working** |
| session | src/session/ | AdsPower, CDP harvesting, browser actions, credentials | working |
| bapi | src/bapi/ | httpx client for Binance bapi, retry, rate limit | working |
| parser | src/parser/ | Feed parsing, articles, trend ranking | working |
| content | src/content/ | AI text generation (agent tool), queue, market data | working |
| activity | src/activity/ | Likes, comments, reposts — orchestration and targeting | working |
| **runtime** | **src/runtime/** | **ActionGuard (limits, circuit breaker), HumanBehavior (warm-up, delays)** | **working** |
| **metrics** | **src/metrics/** | **MetricsStore, Collector, Scorer — metrics collection and aggregation** | **working** |
| **memory** | **src/memory/** | **Compactor — generates performance.md, relationships.md from data** | **working** |
| **strategy** | **src/strategy/** | **Planner, Analyst, Reviewer, FeedFilter — agent strategy layer** | **working** |
| **pipeline** | **src/pipeline.py** | **Single script: collector -> scorer -> compactor -> analyst** | **working** |
| accounts | src/accounts/ | YAML account configs, limits, anti-detect | working |
| db | src/db/ | SQLite schema and initialization (8 tables incl. post_tracker) | working |
| scheduler | src/scheduler/ | Optional orchestration (agent can replace) | optional |
| main | src/main.py | Entry point, lifecycle | working |

## Specifications
- docs/specs/spec_session.md — Session (AdsPower, harvester, browser_actions)
- docs/specs/spec_bapi.md — Bapi client (httpx gateway, credentials, retry)
- docs/specs/spec_parser.md — Parser (feed, articles, trends, ranking)
- docs/specs/spec_content.md — Content (AI generation, queue, market data)
- docs/specs/spec_activity.md — Activity (likes, comments, reposts, targeting)
- docs/specs/spec_accounts.md — Accounts (config, limits, anti-detect)
- docs/design-spec.md — Overall architecture
- docs/agent_api.md — API documentation for the agent (SDK methods, examples)
- docs/PROJECT_IDEA.md — Project idea
- docs/PROJECT_BRIEF.md — Project brief

## Inter-Module Dependencies
- session -> db (CredentialStore uses SQLite)
- bapi -> session (BapiClient loads credentials from CredentialStore)
- parser -> bapi (TrendFetcher calls BapiClient methods)
- content -> bapi, db (ContentPublisher uses SQLite queue)
- activity -> bapi, accounts (ActivityExecutor uses BapiClient + ActionLimiter)
- scheduler -> all modules (orchestrates the pipeline)

## Code Standards (Imperatives)
- File: 200-300 lines, max 500. Larger — split it
- Function: 20-40 lines, max 100
- Type hints on all public functions
- Naming: verb + object (send_email, get_user). No utils/helpers/misc
- One file = one responsibility. If the description contains "and" — split it
- All imports at the top of the file. No dynamic imports
- Configuration only via .env + single read point
- Secrets NEVER in code

## Error Handling
- Format: WHERE + WHAT + CONTEXT
- Example: "BapiClient.like_post: 403 forbidden, post_id=12345"
- Forbidden: bare except, "something went wrong"
- Structured logging via logging, not print

## Workflow
- One task per session. Target: 3-5 files
- Commit after each logical change
- BEFORE changes — tests pass. AFTER changes — tests pass
- If file > 400 lines — warn and suggest splitting

## Technology Choices
- REQUIRED: 2-3 options with comparison table
- REQUIRED: recommendation with justification
- FORBIDDEN: single option without alternatives

## Sub-Agents
- .claude/agents/database-architect.md — DB schema, migrations
- .claude/agents/backend-engineer.md — API, server logic
- .claude/agents/frontend-developer.md — UI, components
- .claude/agents/qa-reviewer.md — Review by checklist (read-only)
- .claude/agents/spec-reviewer.md — Spec completeness check
- .claude/agents/skeptic.md — Architecture decision verification

## Quality Gate
- After each sub-agent: scripts/quality_gate.py
- GO = continue. CONDITIONAL = continue with remarks. NO-GO = STOP
- Final: scripts/quality_gate.py --tier=all

## Handoffs
- Each sub-agent creates an artifact in docs/handoffs/[module]/
- The next sub-agent MUST read the previous handoff
- Format: docs/handoffs/[module]/[number]_[what]_done.md

## Troubleshooting Routes
- "Browser won't start" -> src/session/adspower.py, config/accounts/*.yaml
- "Credentials expired" -> src/session/harvester.py, src/session/validator.py
- "Selectors broken" -> src/session/page_map.py, src/session/browser_actions.py
- "Post not publishing" -> src/session/browser_actions.py `create_post()`
- "Like not working" -> src/bapi/client.py `like_post()`
- "Parser returns empty" -> src/parser/fetcher.py, src/bapi/endpoints.py
- "Limits not counting" -> src/accounts/limiter.py
- "AI generation fails" -> src/content/generator.py, .env
- "Agent scrolls without acting" -> agents/aisama/prompt.md, src/strategy/planner.py
- "Guard blocks actions" -> src/runtime/guard.py, config/accounts/*.yaml (limits)
- "Metrics not collecting" -> src/pipeline.py, src/metrics/collector.py
- "performance.md is empty" -> src/memory/compactor.py, src/metrics/scorer.py

## Entry Points
- Run: `python src/main.py`
- Pipeline (metrics): `python src/pipeline.py <agent_id> <agent_dir> [db_path]`
- Tests: `python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py`
- Quality gate: `python scripts/quality_gate.py --tier=all`

## When in Doubt
- Ask the operator, don't guess
- Better less but correct than a lot but broken
- If you don't know — say "I don't know"

## Current Status
- **SDK facade: working** (src/sdk.py — single entry point for the agent)
- **All SDK methods tested and working:**
  - connect/disconnect — connect to AdsPower profile
  - get_feed_posts — collect posts from the recommended feed
  - get_market_data — prices, volumes, 24h change
  - like_post — like via browser
  - comment_on_post — comment with Follow popup handling
  - create_post — text + $CASHTAGS + chart + sentiment + image
  - create_article — title + body + cover image
  - quote_repost — quote post with comment
  - follow_user — follow with already-followed check
  - take_screenshot — screenshot any page/element
  - screenshot_chart — Binance chart screenshot (16:9, by selector)
  - download_image — download image from the internet
- ActionLimiter: **fixed** (hardcoded defaults, col overwrite, UTC/localtime)
- **Data methods:** get_trending_coins, get_crypto_news, get_article_content, get_ta_summary
- **Content validator:** src/content/validator.py — validates posts, comments, articles, quotes (banned phrases from YAML, duplicates, structure). Integrated into SDK create_post/create_article/quote_repost/comment_on_post
- **Supervisor agent:** agents/supervisor/ — monitoring, memory compaction, post tracker
- **Post tracker:** post_tracker table in SQLite — tracks all posts across all agents

## Agent Architecture v2
4-layer system following a reliability hierarchy:
1. **Runtime (code):** guard.py (limits, circuit breaker by action type), behavior.py (human-like behavior)
2. **Metrics (code):** collector -> scorer -> insights. pipeline.py runs on cron
3. **Memory (code):** compactor generates performance.md, relationships.md from insights
4. **Strategy (LLM):** analyst (triggered) -> planner (each session) -> reviewer (after session)
- Guard controls: daily limits, cooldown, circuit breaker per action type, fallback chains
- Feed filter removes spam and 0-like posts BEFORE the agent sees them
- Planner generates JSON plan with fallback for each action
- Scorer aggregates metrics without weights (first 30 sessions), auto-generates lessons
