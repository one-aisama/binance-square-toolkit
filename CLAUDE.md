# Binance Square Toolkit
# Project: personal | Status: in development | Updated: 2026-04-04
# Standard: standards/ | Workflow: standards/03_workflow.md

## What Is This
SDK for managing activity on Binance Square via AdsPower profiles.
Software = hands (executes actions). Agent = brain (makes decisions, generates content).

## CRITICAL: Text Generation
The agent is a Claude Code session. It generates post and comment text itself.
No external API needed (Anthropic, OpenAI, DeepSeek) and no ChatGPT/Gemini in browser.
The agent reads a brief (topic, angle, context) + its own files (style.md, strategy.md) and writes text itself.
The finished text is passed to the SDK: `create_post(text=...)`, `comment_on_post(text=...)`.

## Stack
- Python 3.12
- httpx (async HTTP — parsing, likes)
- Playwright (CDP — posts, comments, follows, reposts)
- SQLite + aiosqlite (runtime data)
- AdsPower Local API (browser profile management)
- Pydantic v2 (config validation)

## Architecture: Hybrid (httpx + Playwright CDP)
- **httpx** — parsing, likes, market data (fast, no browser)
- **Playwright CDP** — posts, comments, reposts, follows (require client-side signature or DOM)
- **Credentials** — captured via CDP once, used by httpx for parsing/likes

## Module Map
| Module | Path | Purpose | Status |
|--------|------|---------|--------|
| **sdk** | **src/sdk.py** | **Unified facade for the agent — connect, get_feed, comment, post, like, follow** | **working** |
| session | src/session/ | AdsPower, CDP harvesting, browser actions, credentials, web_visual (ChatGPT/Manus/Gemini image gen) | working |
| bapi | src/bapi/ | httpx client for Binance bapi, retry, rate limit | working |
| parser | src/parser/ | Feed parsing, articles, trend ranking | working |
| content | src/content/ | AI text generation (agent tool), queue, market data | working |
| activity | src/activity/ | Likes, comments, reposts — orchestration and targeting | working |
| **runtime** | **src/runtime/** | **29 modules: guard, behavior, agent_config/plan, session_loop/context, editorial_brain, visual_pipeline/providers/prompt_builder, plan_executor/planner/auditor, media_policy, comment_coordination, news_cooldown, post_registry, persona_policy, etc.** | **working** |
| **operator** | **src/operator/** | **Control plane: loop, scheduler, state machine, leases, recovery, persona/auditor/strategic/reflection bridges, memory_compiler** | **working** |
| **metrics** | **src/metrics/** | **MetricsStore, Collector, Scorer — metrics collection and aggregation** | **new** |
| **memory** | **src/memory/** | **Compactor — generates performance.md, relationships.md from data** | **new** |
| **strategy** | **src/strategy/** | **Planner, Analyst, Reviewer, FeedFilter — agent strategy** | **new** |
| **pipeline** | **src/pipeline.py** | **Single script: collector → scorer → compactor → analyst** | **new** |
| accounts | src/accounts/ | YAML account configs, limits, anti-detect | working |
| db | src/db/ | SQLite schema and initialization (10 runtime + 4 operator tables) | working |
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
- docs/PROJECT_IDEA.md — Project idea
- docs/PROJECT_BRIEF.md — Project brief

## Module Dependencies
- session -> db (CredentialStore uses SQLite)
- bapi -> session (BapiClient loads credentials from CredentialStore)
- parser -> bapi (TrendFetcher calls BapiClient methods)
- content -> bapi, db (ContentPublisher uses queue in SQLite)
- activity -> bapi, accounts (ActivityExecutor uses BapiClient + ActionLimiter)
- scheduler -> all modules (orchestrates the pipeline)

## Code Standards (imperatives)
- File: 200-300 lines, max 500. Larger — split it
- Function: 20-40 lines, max 100
- Type annotations on all public functions
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

## Work Process
- One task per session. Target: 3-5 files
- Commit after each logical change
- BEFORE changes — tests pass. AFTER — tests pass
- If file > 400 lines — warn and suggest splitting

## Technology Choices
- REQUIRED: 2-3 options with comparison table
- REQUIRED: recommendation with justification
- FORBIDDEN: single option without alternatives

## Subagents
- .claude/agents/database-architect.md — DB schema, migrations
- .claude/agents/backend-engineer.md — API, server logic
- .claude/agents/frontend-developer.md — UI, components
- .claude/agents/qa-reviewer.md — review by checklist (Read-only)
- .claude/agents/spec-reviewer.md — specification completeness check
- .claude/agents/skeptic.md — architectural decision verification

## Quality Gate
- After each subagent: scripts/quality_gate.py
- GO = proceed. CONDITIONAL = proceed with notes. NO-GO = STOP
- Final: scripts/quality_gate.py --tier=all

## Handoffs
- Each subagent creates an artifact in docs/handoffs/[module]/
- The next subagent MUST read the previous handoff
- Format: docs/handoffs/[module]/[number]_[what]_done.md

## Problem Routing
- "Browser won't start" -> src/session/adspower.py, config/accounts/*.yaml
- "Credentials expired" -> src/session/harvester.py, src/session/validator.py
- "Selectors broken" -> src/session/page_map.py, src/session/browser_actions.py
- "Post won't publish" -> src/session/browser_actions.py `create_post()`
- "Like not working" -> src/bapi/client.py `like_post()`
- "Parsing empty" -> src/parser/fetcher.py, src/bapi/endpoints.py
- "Limits not counting" -> src/accounts/limiter.py
- "AI generation failing" -> src/content/generator.py, .env
- "Agent scrolls without acting" -> agents/example_macro/prompt.md, src/strategy/planner.py
- "Guard blocking actions" -> src/runtime/guard.py, config/accounts/*.yaml (limits)
- "Metrics not collecting" -> src/pipeline.py, src/metrics/collector.py
- "performance.md empty" -> src/memory/compactor.py, src/metrics/scorer.py
- "Directive not generating" -> src/operator/strategic_bridge.py, agents/{id}/briefing_packet.md
- "Agent not reflecting" -> src/operator/reflection_bridge.py, agents/{id}/strategic_state.md
- "Briefing empty" -> src/operator/memory_compiler.py, agents/{id}/

## Entry Points
- **Operator (production):** `python scripts/run_operator.py --max-slots 4`
- **Status dashboard:** `python scripts/operator_status.py`
- Prepare: `python session_run.py --prepare --config config/active_agent.yaml`
- Execute: `python session_run.py --execute --config config/active_agent.yaml`
- Legacy continuous: `python session_run.py --continuous`
- Legacy scheduler: `python src/main.py`
- Pipeline (metrics): `python src/pipeline.py <agent_id> <agent_dir> [db_path]`
- Tests: `python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py`
- Quality gate: `python scripts/quality_gate.py --tier=all`

## When in Doubt
- Ask the operator, don't guess
- Better less but correct, than a lot but broken
- If you don't know — say "I don't know"

## Current Status
- **SDK facade: working** (src/sdk.py — single entry point for the agent)
- **All SDK methods tested live 2026-03-27:**
  - connect/disconnect — connect to AdsPower profile
  - get_feed_posts — collect posts from recommended feed
  - get_market_data — prices, volumes, 24h change
  - like_post — like via browser
  - comment_on_post — comment with Follow popup handling
  - create_post — text + $CASHTAGS + chart + sentiment + image
  - create_article — title + body + cover
  - quote_repost — quote a post with comment
  - follow_user — follow with already-following check
  - take_screenshot — screenshot of any page/element
  - screenshot_chart — Binance chart screenshot (16:9, by selector)
  - download_image — download image from the internet
- ActionLimiter: **fixed** (hardcoded defaults, col overwrite, UTC/localtime)
- **New Data methods:** get_trending_coins, get_crypto_news, get_article_content, get_ta_summary
- **browse_and_interact() removed** — agent decides on its own, SDK only executes
- **Content validator:** src/content/validator.py — validation of posts, comments, articles, quotes (banned phrases from YAML, duplicates, structure). Integrated into SDK create_post/create_article/quote_repost/comment_on_post
- **Supervisor agent:** agents/supervisor/ — monitoring, memory compaction, post tracker
- **Post tracker:** post_tracker table in SQLite — tracking all posts from all agents
- **Policy migration: complete** (0 hardcoded agent_id branches in src/runtime/)

## Specifications
- docs/specs/spec_session.md — Session (AdsPower, harvester, browser_actions)
- docs/specs/spec_bapi.md — Bapi client (httpx gateway, credentials, retry)
- docs/specs/spec_parser.md — Parser (feed, articles, trends, ranking)
- docs/specs/spec_content.md — Content (AI generation, queue, market data)
- docs/specs/spec_activity.md — Activity (likes, comments, reposts, targeting)
- docs/specs/spec_accounts.md — Accounts (config, limits, anti-detect)
- docs/design-spec.md — Overall architecture
- docs/agent_api.md — **API documentation for the agent (SDK methods, examples)**
- docs/PROJECT_IDEA.md — Project idea
- docs/PROJECT_BRIEF.md — Project brief

## Agent Architecture v2 (2026-03-28)
4-layer system by reliability hierarchy:
1. **Runtime (code):** guard.py (limits, circuit breaker by type), behavior.py (human-like behavior)
2. **Metrics (code):** collector → scorer → insights. Pipeline.py runs via cron
3. **Memory (code):** compactor generates performance.md, relationships.md from insights
4. **Strategy (LLM):** analyst (by trigger) → planner (each session) → reviewer (after session)
- Guard controls: daily limits, cooldown, circuit breaker by action type, fallback chains
- Feed filter removes spam and 0-like posts BEFORE the agent sees them
- Planner generates JSON plan with fallback for each action
- Scorer aggregates metrics without weights (first 30 sessions), auto-generates lessons
- Foundation document: square_idea.md

## Architecture v3: Policy-Driven Runtime (2026-04-01)
One runtime framework + N policy profiles. New agent = YAML + persona files, zero Python.

### Layers
| Layer | What | Shared/Per-agent |
|-------|------|-----------------|
| Transport | SDK, browser_actions, AdsPower, publish | Shared |
| Coordination | topic_reservations, comment_locks, news_cooldowns (SQLite), post_registry.json | Shared |
| Runtime framework | orchestration, plan execution, guard | Shared |
| Policy | selection, framing, authoring, audit thresholds, visual | Per-agent (YAML) |
| State | checkpoint, daily_plan, status, visuals | Per-agent (files) |

### Key Files
- `src/runtime/persona_policy.py` — PersonaPolicy dataclass + YAML loader
- `config/persona_policies/{agent_id}.yaml` — all behavioral parameters for an agent
- `src/runtime/topic_reservation.py` — live topic lock (SQLite, reserve/confirm/release)
- Runtime files: `data/runtime/{agent_id}/` (checkpoint, daily_plan, status)
- Visuals: `data/generated_visuals/{agent_id}/`

### Shared SQLite = Control Plane
`data/bsq.db` — this is a coordination layer, NOT per-agent state:
- `topic_reservations` — live locks on post topics (2h TTL)
- `comment_locks` — preventing duplicate comments (30min TTL)
- `news_cooldowns` — cooldown on news (30min hard block + 60min soft penalty)
- `credentials` — per account_id
- `actions_log`, `daily_stats`, `post_tracker` — partitioned by account_id
- Per-agent state lives in files: `data/runtime/{agent_id}/`

### Adding a New Agent
1. `config/persona_policies/{id}.yaml` — behavioral policy
2. `config/active_agent.{id}.yaml` — runtime binding (AdsPower, symbols, visual)
3. `config/accounts/{id}.yaml` — account credentials
4. `agents/{id}/` — identity, style, strategy, prompt, visual_profile
5. Zero changes to Python code

### Agent Operating Modes (2026-04-03)
- `mode: "standard"` — current behavior (default)
- `mode: "individual"` — overlay config (market_symbols, coin_bias, targets, expires_at)
- `mode: "test"` — dry-run without SDK, plan is generated and audited but not executed

### Agent Coordination (2026-04-03)
- Comment locks — SQLite, 30min TTL, prevent duplicate comments
- News cooldowns — SQLite, 90min TTL (30min hard block), prevent news races
- Territory drift — auditor rejects plan if ALL posts are outside the agent's niche
- Timing stagger — deterministic offset 0-300s per agent_id via MD5

## Architecture v4: Strategic Control (2026-04-04)
Agent is a strategist, not a copywriter. Three persona spawns per micro-cycle:

### Micro-cycle flow
```
1. COMPILE    → MemoryCompiler gathers briefing_packet.md from 10 memory layers
2. STRATEGIZE → persona reads briefing + context → strategic_directive.json
3. PREPARE    → context + plan skeleton (planner uses directive)
4. AUTHOR     → persona writes text based on plan + directive
5. AUDIT      → text validation
6. EXECUTE    → SDK executes
7. REFLECT    → persona updates strategic_state.md, open_loops.md, intent.md
```

### Key New Files
- `src/operator/strategic_bridge.py` — spawn persona for strategic decisions
- `src/operator/reflection_bridge.py` — spawn persona for reflection after execute
- `src/operator/memory_compiler.py` — compile briefing_packet from 10 memory layers

### Strategic directive (data/runtime/{id}/strategic_directive.json)
```json
{
  "focus_summary": "...", "preferred_coins": [...], "avoid_coins": [...],
  "post_direction": "...", "comment_direction": "...",
  "skip_families": [...], "tone": "..."
}
```

### Agent Files (living documents)
```
agents/{id}/
  identity.md          — stable (written by human)
  style.md             — stable (written by human)
  strategic_state.md   — living (written by agent via reflect)
  open_loops.md        — living (written by agent via reflect)
  intent.md            — living (written by agent via reflect)
  briefing_packet.md   — compiled (written by MemoryCompiler)
  journal.md           — raw (written by automation)
  relationships.md     — raw (written by pipeline)
  lessons.md           — raw (written by agent + supervisor)
  performance.md       — raw (written by pipeline)
```

### How Directive Affects Planner
- `preferred_coins` → +80 to symbol score in EditorialBrain
- `avoid_coins` → filtered from candidates
- `skip_families` → -500 to post family score
- Candidate order is reranked by preferred_coins

## Recent Changes
- 2026-04-04 (v4): **Strategic Control** — strategic_bridge.py (persona directs planner), reflection_bridge.py (persona updates living memory), memory_compiler.py (briefing packet from 10 layers). Micro-cycle: compile → strategize → prepare → author → audit → execute → reflect. EditorialBrain accepts strategic_directive (preferred_coins, avoid_coins, skip_families). 390 tests green
- 2026-04-04: session_run.py --prepare/--execute + continuous mode with polling. plan_io.py — save/load pending_plan.json. Continuous: plan → save → waits for text from agent (poll 10s) → execute. Agent session writes text to pending_plan.json. **Operator control plane:** src/operator/ — persistent loop, slot scheduler, state machine (14 states), leases, recovery, persona/auditor bridges. scripts/run_operator.py + operator_status.py. 359 tests green
- 2026-04-03: Removed post_author.py and web_author.py — agent generates text itself (brief_context/target_text). Auditor skips text-based checks when no text present. Modes (standard/individual/test), coordination (comment_locks, news_cooldowns, territory drift, stagger), media_policy, RuntimeTuning (hardcoded → YAML), browser_actions split. 307 tests green
- 2026-04-01 (v3): Policy-Driven Runtime — PersonaPolicy, topic_reservation, all if agent_id branches replaced with YAML config, per-agent state isolation (files), 249 tests green
- 2026-03-28 (v2): Agent System v2 — 4 new modules (runtime, metrics, memory, strategy), pipeline.py, rewritten prompt.md, 159 tests green
- 2026-03-28: Content validator (src/content/validator.py), SDK integration, supervisor agent (agents/supervisor/), post_tracker table in SQLite, 145 tests green
- 2026-03-27 (session 3): Removed browse_and_interact() (agent decides on its own), updated agent_api.md (all new methods), tech debt closed, 106 tests green
- 2026-03-27 (session 2): Fix $CASHTAGS (re.split on # and $), fix ActionLimiter (4 bugs), fix quote_repost (selector detail-quote-button), rewritten create_article (textarea title, article-editor-main Publish, \n normalization), added take_screenshot/screenshot_chart/download_image, 87 tests green, all SDK methods tested live
- 2026-03-27: Created src/sdk.py — unified facade for the agent. Added collect_feed_posts(), fixed text parsing (cookie banners). Tested live: 5 comments + 2 posts. docs/agent_api.md
- 2026-03-26: Restructured to standard, added CLAUDE.md sections
- 2026-03-25: CLAUDE.md converted to templates, translated to Russian
- 2026-03-24: Updated CSS selectors in page_map.py
