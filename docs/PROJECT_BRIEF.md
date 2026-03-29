# Project Brief — Binance Square Toolkit
# Version: 1.0 | Date: 2026-03-25

---

## Current operational status

As of 2026-03-29, this brief partially describes the **historical target-state** for multi-account mode.
The actual current deployment of the repository:

- 1 active AdsPower profile
- 1 active Binance Square agent: `aisama`
- main runtime path: `BinanceSquareSDK` + `session_run.py`

Current operational documentation is in [docs/SINGLE_AGENT_OPERATIONS.md](docs/SINGLE_AGENT_OPERATIONS.md).

---

## Section A: Product Sketch (idea)

### A.1. Product Name
Binance Square Toolkit

### A.2. One sentence — what is it
SDK/toolkit for automated content publishing and engagement on Binance Square, controlled by an AI agent, monetized through Write to Earn.

### A.3. Problem being solved
I have 6 Binance Square accounts with different niches (DeFi, trading, news, infrastructure, education, institutional). Each needs 3-5 posts/day plus likes and comments to grow the audience and W2E commissions. That's 18-30 posts, 180-360 likes, and 70-140 comments daily — impossible manually. Without automation, accounts sit idle, W2E revenue is lost.

### A.4. Who is the user
Me (Rahim). Personal project. The AI agent (Claude/Codex) is the direct consumer of the toolkit API: it calls functions for parsing, generation, publishing, and engagement.

### A.5. What the product MUST do (required)
1. Parse the Binance Square feed, trending articles, fear/greed index, hot hashtags, and market data via bapi endpoints
2. Rank trending topics by engagement score (views, likes, comments)
3. Generate text content via AI (Claude/OpenAI) — `ContentGenerator` and `CommentGenerator` as agent tools — with persona style, real market data, trending cashtags/hashtags
4. Publish posts on Binance Square via Playwright CDP (requires client-side signatures)
5. Like posts via httpx (bapi endpoint)
6. Comment on posts via Playwright CDP (DOM-based input)
7. Follow authors via Playwright CDP
8. Manage configurations for 6+ accounts via YAML (persona, proxy, limits)
9. Enforce daily limits per account (posts: 3-5, likes: 30-60, comments: 12-24)
10. Log all actions to SQLite for tracking and debugging
11. Capture and manage bapi credentials (cookies + headers) via CDP
12. Connect to AdsPower profiles for anti-detect browsing

### A.6. What the product MAY do (nice to have)
1. Media content generation (price charts, HTML templates → PNG)
2. Full article creation (not just short posts)
3. Engagement analytics dashboard by account/topic
4. A/B testing of different content styles
5. Auto-adjust posting frequency based on engagement data
6. Revenue tracking (W2E commission by account)
7. Author profile viewing and post history scraping
8. Post/comment deletion

### A.7. What the product MUST NOT do (boundaries)
1. Not make autonomous decisions — all decisions from the AI agent, which receives tasks from a human
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
- Playwright (CDP connection to AdsPower browsers for posting, commenting, follows)
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

### B.5. Where it runs
- [x] On my computer (Windows 11)
- Local execution. AdsPower runs locally. Cloud deployment not planned.

### B.6. Expected size
- [x] Medium (2000-10000 lines, 5-10 modules)
- Modules: parser, content, activity, accounts, session, bapi, db, scheduler. Plus configs and tests.

---

## Section C: Architecture Requirements

### C.1. Technical Requirements Reference
Project is developed in accordance with:
- 01_technical_requirements.md (all standards are mandatory)

### C.2. Additional Project Constraints
- All browser actions through AdsPower profiles (never launch raw Playwright)
- Credential capture is a separate explicit step (not automatic on every action)
- Each module is testable without live connection to Binance (mock-friendly interfaces)
- Config validation at startup — fail fast if YAML configs are invalid

### C.3. Security Requirements
- [x] Token handling (browser credentials — cookies, csrftoken, fvideo-id, fvideo-token)
- [x] Crypto operations (Binance platform, W2E monetization)
- API keys only in .env, never in YAML or code
- Captured credentials in SQLite (local file, not transmitted)
- Each account's credentials are isolated (no cross-use)

### C.4. Reliability Requirements
- [x] Important — log errors and continue operating
- If one account's credentials expire, the rest continue working
- If the AI API is down, skip the generation cycle and retry in the next one
- If an AdsPower profile fails to start, log the error, skip the account, continue with the rest
- All actions wrapped in try/except with structured logging
- Graceful shutdown: finish the current action, don't start new ones

---

## Section D: Implementation Stages

### D.1. Stage Breakdown

**Stage 1: Foundation (Parser + DB + Accounts)**
After this stage: can parse the Binance Square feed, trending articles, fear & greed, hot hashtags, and market data. Data in SQLite. Account configs load from YAML. Credential capture works.

**Stage 2: Content Engine (Generation + Publishing)**
After this stage: can generate text content via AI (agent calls `ContentGenerator` as a tool) with persona styles and publish posts on Binance Square via Playwright CDP. Content queue in SQLite.

**Stage 3: Activity Engine (Likes + Comments + Follows)**
After this stage: can like posts via httpx, comment and follow via Playwright CDP. Limits are enforced. All actions are logged.

**Stage 4: Orchestration (Scheduler + Multi-account)**
After this stage: APScheduler (or agent directly) runs parsing→generation→publishing→engagement cycles across all 6 accounts. Anti-detect rules are followed (no overlaps, no cross-interactions).

**Stage 5: Media + Analytics (Phase 2-3)**
After this stage: media content generation (charts, images), analytics dashboard, A/B testing, revenue tracking.

### D.2. Module Specifications
Before implementing each stage, create specification documents (docs/spec_[module].md) with:
1. User Stories
2. Data Model
3. API (function signatures, inputs/outputs, error handling)
4. Business Logic (limits, validation, state transitions)
5. Edge Cases (expired credentials, API failures, concurrent access)

Note: no UI components — this is a headless toolkit.

### D.3. Priorities
1. Parser (foundation — everything depends on trend data)
2. Session manager + credential capture (needed for both httpx and CDP)
3. Content engine (core value — post generation and publishing)
4. Activity engine (engagement — likes, comments, follows)
5. Multi-account orchestration (scaling from 1 to 6 accounts)
6. Media generation (nice to have, Phase 2)
7. Analytics (optimization, Phase 3)

### D.4. "Done" Criteria by Stage

**Stage 1:** Run parser, see 100 feed posts + 100 articles + fear/greed + hashtags in SQLite. Account config loads without errors. Credential capture extracts cookies and headers from an AdsPower profile.

**Stage 2:** Run content generation for 1 account, see an AI-generated post with real market data and persona style. Post appears on Binance Square. Verify in browser.

**Stage 3:** Run activity cycle for 1 account, see 5-10 likes in actions_log, 2-4 published comments (visible on Binance Square), 1-2 completed follows.

**Stage 4:** Run scheduler (or agent runs cycles), leave for 24 hours. Verify: 6 accounts, each published 3-5 posts, liked 30-60 posts, commented 12-24 times. No bans, no errors in logs.

**Stage 5:** Posts include generated price charts. Dashboard shows engagement metrics by account.

---

## Section E: Acceptance and Quality Control

### E.1. How I verify the work
- Run the toolkit, check Binance Square in browser — posts appear in each account's profile
- Check SQLite — actions_log contains entries for each post/like/comment
- Check daily_stats — numbers in expected ranges (3-5 posts, 30-60 likes per account)
- Monitor accounts for 7 days — no bans, no warnings from Binance
- Check content quality — reads as human-written, with real numbers, matches persona style

### E.2. What counts as a bug
- Toolkit crashes without a clear error message
- Post is published but not visible on Binance Square
- Credentials expired but toolkit keeps trying with dead credentials instead of fail fast
- Limits exceeded (more actions than the configured maximum)
- Cross-interaction detected (account A liked account B's post)
- Content contains AI cliches ("in the ever-evolving world of", "it's worth noting that")
- Action logged as successful but actually failed on the Binance side

### E.3. What counts as success
- 6 accounts operating per agent commands for 7+ days without bans
- Each account publishes 3-5 posts/day with unique persona style and real market data
- Activity engine generates 30-60 likes and 12-24 comments per account per day
- All actions are logged, daily stats are aggregated, errors are traceable
- W2E revenue is measurable (even if initially small)
- Adding a 7th account requires only a new YAML config and an AdsPower profile

---
