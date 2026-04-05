> **Status: OUTDATED (pre-v3)**
> This document describes the original vision for a multi-account farm (6+ accounts).
> Current architecture: policy-driven v3 (CLAUDE.md, docs/design-spec.md).
> Current operating mode: single-agent (docs/SINGLE_AGENT_OPERATIONS.md).

# Project Brief — Binance Square Toolkit
# Version: 1.0 | Date: 2026-03-25

---

## Current Operational Status

As of 2026-03-29, this brief partially describes the **historical target state** for multi-account mode.
The actual current deployment of the repository:

- 1 active AdsPower profile
- 1 active Binance Square agent: `example_macro`
- Primary runtime path: `BinanceSquareSDK` + `session_run.py`

Current operational documentation: see AGENTS.md and CLAUDE.md.

---

## Section A: Product Sketch (Idea)

### A.1. Product Name
Binance Square Toolkit

### A.2. One Sentence — What Is It
SDK/toolkit for automated content publishing and engagement on Binance Square, managed by an AI agent, monetized via Write to Earn.

### A.3. Problem We're Solving
I have 6 Binance Square accounts with different niches (DeFi, trading, news, infrastructure, education, institutional). Each needs 3-5 posts/day plus likes and comments to grow audience and W2E commissions. That's 18-30 posts, 180-360 likes, and 70-140 comments daily — impossible to do manually. Without automation, accounts sit idle and W2E revenue is lost.

### A.4. Who Is the User
Personal project. The AI agent (Claude/Codex) is the direct consumer of the toolkit API: it calls functions for parsing, generation, publishing, and engagement.

### A.5. What the Product MUST Do (mandatory)
1. Parse Binance Square feed, trending articles, fear & greed index, hot hashtags, and market data via bapi endpoints
2. Rank trending topics by engagement score (views, likes, comments)
3. Generate text content via AI (Claude/OpenAI) — `ContentGenerator` and `CommentGenerator` as agent tools — with persona style, real market data, trending cashtags/hashtags
4. Publish posts on Binance Square via Playwright CDP (requires client-side signatures)
5. Like posts via httpx (bapi endpoint)
6. Comment on posts via Playwright CDP (DOM-based input)
7. Follow authors via Playwright CDP
8. Manage 6+ account configurations via YAML (persona, proxy, limits)
9. Enforce daily limits per account (posts: 3-5, likes: 30-60, comments: 12-24)
10. Log all actions to SQLite for tracking and debugging
11. Capture and manage bapi credentials (cookies + headers) via CDP
12. Connect to AdsPower profiles for anti-detect browsing

### A.6. What the Product MAY Do (desirable)
1. Media content generation (price charts, HTML templates → PNG)
2. Full article creation (not just short posts)
3. Engagement analytics dashboard by account/topic
4. A/B testing of different content styles
5. Auto-adjust posting frequency based on engagement data
6. Revenue tracking (W2E commission by account)
7. Author profile viewing and post history scraping
8. Deleting posts/comments

### A.7. What the Product MUST NOT Do (boundaries)
1. Not make autonomous decisions — all decisions come from the AI agent, which gets assignments from a human
2. Not store API keys in code or configs (only .env)
3. Not interact between own accounts (no self-likes, self-comments, self-follows)
4. Not exceed implicit Binance limits (conservative approach)
5. Not publish content without persona style and real data
6. Not operate without valid credentials (fail fast on expired cookies)

---

## Section B: Technical Constraints

### B.1. Platform
- [x] Script / CLI
- Python toolkit consumed by an AI agent. No GUI. No web interface.

### B.2. Language and Framework
- Python 3.12
- httpx (async HTTP client for bapi parsing + likes)
- Playwright (CDP connection to AdsPower browsers for posting, commenting, following)
- anthropic / openai SDK (content generation — agent tools)
- APScheduler (task scheduling — optional, agent can manage cycles itself)
- pydantic (config validation)
- aiosqlite (async SQLite)
- pyyaml (config loading)

### B.3. Database
- [x] Needed (data persists between sessions)
- SQLite with WAL mode. 7 tables: credentials, actions_log, daily_stats, content_queue, parsed_trends, parsed_posts, discovered_endpoints.
- YAML is the source of truth for account/persona configs. SQLite stores only runtime data.

### B.4. External Services and APIs
- Binance bapi (internal endpoints) — feed parsing, likes. Requires captured cookies + 10 specific headers.
- Binance public market API — coin prices, volume, 24h change. No authentication.
- Claude API (Anthropic) — content generation (agent tool). Auth: ANTHROPIC_API_KEY.
- OpenAI API — content generation (fallback). Auth: OPENAI_API_KEY.
- AdsPower local API (localhost:50325) — start/stop browser profiles. No external authentication.
- iProxy — mobile proxies, one device per account.

### B.5. Where It Runs
- [x] On my computer (Windows 11)
- Local execution. AdsPower runs locally. Cloud deployment not planned.

### B.6. Expected Size
- [x] Medium (2000-10000 lines, 5-10 modules)
- Modules: parser, content, activity, accounts, session, bapi, db, scheduler. Plus configs and tests.

---

## Section C: Architectural Requirements

### C.1. Technical Requirements Reference
The project is developed in accordance with:
- 01_technical_requirements.md (all standards are mandatory)

### C.2. Additional Project Constraints
- All browser actions via AdsPower profiles (never launch raw Playwright)
- Credential capture is a separate explicit step (not automatic with every action)
- Each module testable without live Binance connection (mock-friendly interfaces)
- Config validation at startup — fail fast if YAML configs are invalid

### C.3. Security Requirements
- [x] Working with tokens (credentials from browser — cookies, csrftoken, fvideo-id, fvideo-token)
- [x] Working with crypto (Binance platform, W2E monetization)
- API keys only in .env, never in YAML or code
- Captured credentials in SQLite (local file, not transmitted)
- Each account's credentials are isolated (no cross-usage)

### C.4. Reliability Requirements
- [x] Important — log errors and continue working
- If one account's credentials expire, the rest continue working
- If AI API goes down, skip the generation cycle and retry next time
- If AdsPower profile fails to start, log the error, skip the account, continue with others
- All actions wrapped in try/except with structured logging
- Graceful shutdown: finish current action, don't start new ones

---

## Section D: Implementation Phases

### D.1. Phase Breakdown

**Phase 1: Foundation (Parser + DB + Accounts)**
After this phase: can parse Binance Square feed, trending articles, fear & greed, hot hashtags, and market data. Data in SQLite. Account configs loaded from YAML. Credential capture works.

**Phase 2: Content Engine (Generation + Publishing)**
After this phase: can generate text content via AI (agent calls `ContentGenerator` as a tool) with persona styles and publish posts on Binance Square via Playwright CDP. Content queue in SQLite.

**Phase 3: Activity Engine (Likes + Comments + Follows)**
After this phase: can like posts via httpx, comment and follow via Playwright CDP. Limits enforced. All actions logged.

**Phase 4: Orchestration (Scheduler + Multi-Account)**
After this phase: APScheduler (or agent directly) runs cycles of parsing→generation→publishing→engagement across all 6 accounts. Anti-detect rules enforced (no overlaps, no cross-interactions).

**Phase 5: Media + Analytics (Phase 2-3)**
After this phase: media content generation (charts, images), analytics dashboard, A/B testing, revenue tracking.

### D.2. Module Specifications
Before implementing each phase, create specification documents (docs/spec_[module].md) with:
1. User Stories
2. Data model
3. API (function signatures, inputs/outputs, error handling)
4. Business logic (limits, validation, state transitions)
5. Edge cases (expired credentials, API failures, concurrent access)

Note: no UI components — this is a headless toolkit.

### D.3. Priorities
1. Parser (foundation — everything depends on trend data)
2. Session manager + credential capture (needed for both httpx and CDP)
3. Content engine (core value — post generation and publishing)
4. Activity engine (engagement — likes, comments, follows)
5. Multi-account orchestration (scaling from 1 to 6 accounts)
6. Media generation (desirable, Phase 2)
7. Analytics (optimization, Phase 3)

### D.4. "Done" Criteria by Phase

**Phase 1:** Run the parser, see 100 feed posts + 100 articles + fear/greed + hashtags in SQLite. Account config loads without errors. Credential capture extracts cookies and headers from AdsPower profile.

**Phase 2:** Run content generation for 1 account, see an AI-generated post with real market data and persona style. Post appears on Binance Square. Verify in browser.

**Phase 3:** Run activity cycle for 1 account, see 5-10 likes in actions_log, 2-4 published comments (visible on Binance Square), 1-2 follows completed.

**Phase 4:** Run the scheduler (or agent runs cycles), leave for 24 hours. Verify: 6 accounts, each published 3-5 posts, liked 30-60 posts, commented 12-24 times. No bans, no errors in logs.

**Phase 5:** Posts include generated price charts. Dashboard shows engagement metrics by account.

---

## Section E: Acceptance and Quality Control

### E.1. How I Verify the Work
- Run the toolkit, check Binance Square in browser — posts appear in each account's profile
- Check SQLite — actions_log contains entries for each post/like/comment
- Check daily_stats — numbers within expected ranges (3-5 posts, 30-60 likes per account)
- Monitor accounts for 7 days — no bans, no warnings from Binance
- Check content quality — reads as human-written, with real numbers, matches persona style

### E.2. What Counts as a Bug
- Toolkit crashes without a clear error message
- Post published but not visible on Binance Square
- Credentials expired but toolkit keeps trying with dead credentials instead of fail fast
- Limits exceeded (more actions than configured maximum)
- Cross-interaction detected (account A liked account B's post)
- Content contains AI cliches ("in the ever-evolving world of", "it's worth noting that")
- Action logged as successful but actually failed on the Binance side

### E.3. What Counts as Success
- 6 accounts operating by agent commands for 7+ days without bans
- Each account publishes 3-5 posts/day with unique persona style and real market data
- Activity engine generates 30-60 likes and 12-24 comments per account per day
- All actions logged, daily stats aggregated, errors trackable
- W2E revenue measurable (even if initially small)
- Adding a 7th account requires only a new YAML config and AdsPower profile

---
