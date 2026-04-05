> **Status: OUTDATED (pre-v3)**
> This document describes the original vision for a multi-account farm (6+ accounts).
> Current architecture: policy-driven v3 (CLAUDE.md, docs/design-spec.md).
> Current operating mode: single-agent (docs/SINGLE_AGENT_OPERATIONS.md).

# PROJECT_IDEA — Binance Square Toolkit
# Version: 1.0 | Date: 2026-03-25

---

## 1. Problem

Managing 6+ Binance Square accounts manually is impossible. Each account requires:
- 3-5 unique posts per day (18-30 posts total)
- 30-60 likes per day per account
- 12-24 comments per day per account
- Trend monitoring every 2-4 hours
- Unique writing style for each persona

Manual work per account: ~2-3 hours/day. For 6 accounts: 12-18 hours/day — unrealistic for one person.

Current situation: manual posting from 1-2 accounts, missing peak windows, no systematic trend analysis, no activity engine (likes/comments). Result: low reach, minimal W2E revenue.

If not solved: the Write to Earn opportunity (5% commission from readers' trading fees) remains untapped. Each account with quality content generates passive income from readers' trading activity. 6 accounts with different niches cover more audience segments.

---

## 2. Solution

The toolkit is a set of Python functions managed by an AI agent (Claude, Codex, etc.). **The software does not make decisions** — the agent decides what to post, when, and how. Software = hands, agent = brain.

- Step 1: Agent calls parser functions → gets top 10 trending topics (hashtags, coins, engagement scores) from Binance Square feed and articles
- Step 2: Agent selects topics for each account based on persona config (DeFi Analyst gets DeFi topics, Crypto Trader gets price topics)
- Step 3: Agent gets fresh market data (prices, 24h change, volume) via Binance public API
- Step 4: Agent generates content via AI (Claude/OpenAI) — using `ContentGenerator` and `CommentGenerator` as tools. Persona style, real numbers, trending cashtags and hashtags
- Step 5: Agent calls publishing functions — text posts via Playwright CDP (requires client-side signatures), likes via httpx
- Step 6: Agent runs activity cycle — liking trending posts, commenting on high-reach posts (>1000 views), following relevant authors
- Step 7: All actions logged to SQLite (actions_log, daily_stats) for tracking and limit enforcement

---

## 3. Why Now

- **Write to Earn is active**: Binance pays 5% base trading commission from readers who trade after reading content. The program is running and accepting authors.
- **Binance Square is growing**: Binance is actively promoting Square as its social layer. More users = more potential readers = more commission.
- **AI content generation is mature**: Claude and GPT-4 generate content indistinguishable from human-written, with proper prompting using real data and persona constraints.
- **Technical feasibility confirmed**: Spike testing (2026-03-24) validated all critical paths — parsing, posting, liking, commenting, following all work. Architecture (httpx + Playwright CDP) validated.
- **Low automation competition**: Most Binance Square bots are primitive (template-based, no persona variation, obvious AI patterns). A toolkit with diverse personas and real market data has a quality advantage.

---

## 4. Target Audience

**Personal project**
- Role: sole operator of 6+ Binance Square accounts
- Task: automate content creation and engagement to maximize W2E revenue
- Current tools: manual posting, no automation
- Willingness to pay: N/A (building it myself)

**Secondary: crypto content makers (future potential)**
- Role: authors monetizing via W2E with multiple accounts
- Task: scale content without losing quality and without bans
- Current tools: manual posting, universal schedulers (don't support Binance Square)
- Willingness to pay: $50-200/month per managed account (if productized)

---

## 5. Architecture

```
AGENT (Claude / Codex / any AI)
  │ gets assignment from human
  │ analyzes trends, generates content
  │ calls toolkit functions:
  │
  ├── PARSING (httpx + captured cookies)
  │     ├── get_feed_recommend()       — recommended feed
  │     ├── get_top_articles()         — trending articles
  │     ├── get_fear_greed()           — fear & greed index
  │     ├── get_hot_hashtags()         — hot hashtags
  │     └── get_market_data()          — coin prices (Binance public API)
  │
  ├── ACTIONS via httpx
  │     └── like_post()                — like a post
  │
  ├── ACTIONS via Playwright CDP (AdsPower browser)
  │     ├── create_post()              — post: text + chart + sentiment
  │     ├── create_article()           — article with cover
  │     ├── repost()                   — quote/repost
  │     ├── comment_on_post()          — comment (handles Follow & Reply)
  │     ├── follow_author()            — follow (state check)
  │     └── browse_and_interact()      — feed browsing + interaction
  │
  ├── SESSION MANAGER
  │     ├── AdsPowerClient             — start/stop profiles
  │     ├── harvester                  — credential capture via CDP
  │     ├── credential_store           — CRUD in SQLite for cookies/headers
  │     └── validator                  — credential liveness check
  │
  ├── ACCOUNTS
  │     ├── manager                    — load YAML configs
  │     ├── limiter                    — daily action limits
  │     └── anti_detect                — account isolation
  │
  └── DB (SQLite, WAL mode)
        └── credentials, actions_log, daily_stats, content_queue,
            parsed_trends, parsed_posts, discovered_endpoints
```

**Stack with justification:**
- **Python 3.12** — mature async ecosystem, best AI SDK support (anthropic, openai)
- **httpx** — async HTTP client, faster than requests, HTTP/2 support
- **Playwright CDP** — connects to AdsPower profiles via Chrome DevTools Protocol. Required for posting (client-side nonce + signature) and commenting (DOM-based input)
- **SQLite (WAL mode)** — zero-config, single file, sufficient for 6 accounts (~200 actions/day)
- **APScheduler** — lightweight cron-like scheduler, runs in-process. Optional — agent can run cycles itself
- **AdsPower** — anti-detect browser with separate profiles (unique fingerprint, proxy, cookies)
- **YAML** — human-readable configs for accounts and personas

---

## 6. Monetization

This is a personal tool, not SaaS. Revenue comes from Binance Write to Earn.

| Source | Mechanism | Expected Revenue |
|--------|----------|-----------------|
| Write to Earn | 5% of readers' base trading commission | Depends on reader activity |
| Per account | 3-5 posts/day, each post reaches readers | Unknown until live testing |
| 6 accounts | 6 niches covering a wide audience | 6x revenue of a single account |

Revenue model is commission-based: more quality content → more readers → more trading activity → more commission. No upfront costs other than infrastructure (proxies, AI API).

**Cost structure:**
- AI API: ~$5-15/day (Claude/OpenAI for 20-30 posts + 70-140 comments)
- Proxies (iProxy): ~$30/month for 6 mobile proxies
- AdsPower: ~$10/month (basic plan)
- Total: ~$200-500/month

Break-even: ~$200-500/month in W2E commissions from 6 accounts.

---

## 7. Competitors

| Competitor | What It Does | What's Missing | Our Advantage |
|-----------|-------------|----------------|---------------|
| Manual posting | Human writes and publishes | Doesn't scale beyond 1-2 accounts, misses trends | Full automation, 6+ accounts, real-time trend data |
| Universal schedulers (Buffer, Hootsuite) | Post scheduling across platforms | No Binance Square support, no content generation | Native Binance Square integration, AI content |
| Template bots | Auto-posting from templates | Repetitive content, no persona variation, easily detected | 6 unique personas, real market data, human-like style |
| ChatGPT manually | Human uses ChatGPT for drafts | Still manual publishing, no trend analysis, no activity | End-to-end: parsing → generation → publishing → engagement |

---

## 8. Launch Plan

| Phase | Goal | Success Metric | Timeline |
|-------|------|---------------|----------|
| MVP (Phase 1) | Parser + Content engine (text) + Account manager + Scheduler on 1 account | 1 account publishes 3-5 posts/day automatically for 7 days without ban | 2 weeks |
| Phase 2 | Media posts + Activity engine + AdsPower multi-profile + scale to 6 accounts | 6 accounts running simultaneously, each with likes/comments/posts | 3-4 weeks after MVP |
| Phase 3 | Analytics, A/B testing, optimization | Dashboard with engagement by account, revenue tracking, auto-adjust posting frequency | 2-3 weeks after Phase 2 |

**MVP Scope (Phase 1):**
- Parser: feed recommend, top articles, fear & greed, hot hashtags, market data
- Content engine: AI text generation via `ContentGenerator` (agent tool) with persona styles, publishing via Playwright CDP
- Account manager: YAML config loading, SQLite logging, daily limits
- Scheduler: APScheduler for parsing→generation→publishing cycles every 2 hours (optional — agent can manage cycles directly)
- Testing on 1 account

---

## 9. Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Account ban for automation | Medium | High — loss of account + W2E access | Conservative limits, human-like delays (30-120s between actions), unique proxies, diverse content styles, no interactions between own accounts |
| W2E terms change or program closure | Medium | High — entire revenue model collapses | Monitor announcements, diversify (don't rely solely on W2E), keep costs low |
| bapi endpoint changes without notice | High | Medium — parser breaks | Modular parser with discovered endpoints table, credential harvester can recapture, fallback to CDP for all actions |
| AI content flagged by Binance | Medium | Medium — posts hidden or account flagged (Binance tracks `isCreatedByAI`) | Real market data, persona-specific prompts, sentence structure variation, no AI cliches, manual review of first batch |
| Cross-account pattern detection | Low | High — all 6 accounts banned | Separate proxies (iProxy mobile), separate AdsPower profiles, no content overlap, different posting schedules, no cross-interactions |
| Unit economics don't work (5% too low) | Medium | Medium — project not worth the effort | Test on 1 account (MVP), measure actual W2E revenue before scaling |
| AdsPower API instability | Low | Low — can switch to direct Playwright | Browser management abstracted behind interface, supports both AdsPower and direct launch |

---

## 10. Technical Details

### Repository Structure
```
binance_square/
  docs/              — specifications, design documents
  src/
    main.py          — entry point, lifecycle
    parser/          — bapi parsing (feed, articles, trends, market data)
    content/         — AI content generation (agent tools) + publishing
    activity/        — likes, comments, reposts, follows
    accounts/        — account manager, limiter, anti-detect
    session/         — AdsPower client, harvester, browser_actions, validator
    bapi/            — BapiClient (httpx + credentials + retry + rate limit)
    db/              — SQLite models, initialization
    scheduler/       — APScheduler (optional)
  config/
    accounts/        — YAML account configs
    personas.yaml    — 6 persona definitions
    settings.yaml    — global settings
    content_rules.yaml — content generation rules (for the agent)
  tests/             — pytest tests (~67)
  .env               — API keys (not committed)
```

### Key DB Tables (SQLite)

| Table | Key Fields | Purpose |
|-------|-----------|---------|
| credentials | account_id, cookies, headers, harvested_at, expires_at | Captured bapi credentials |
| actions_log | account_id, action_type, target_id, status, created_at | Every action for audit + limit enforcement |
| daily_stats | account_id, date, posts, likes, comments, errors | Daily statistics |
| content_queue | account_id, content, topic, status, scheduled_at | Content queued for publishing |
| parsed_trends | hashtag, coin, engagement_score, parsed_at | Aggregated trend data |
| parsed_posts | post_id, author, views, likes, comments, card_type, parsed_at | Raw parsed posts |
| discovered_endpoints | url, method, headers, body_schema, discovered_at | Discovered bapi endpoints |

### External APIs

| API | Purpose | Authentication |
|-----|---------|----------------|
| Binance bapi (internal) | Feed parsing, likes | Captured cookies + headers (csrftoken, bnc-uuid, fvideo-id, fvideo-token) |
| Binance public market API | Coin prices, volume, 24h change | None (public) |
| Claude API (Anthropic) | Content generation (agent tool) | ANTHROPIC_API_KEY |
| OpenAI API | Content generation (fallback) | OPENAI_API_KEY |
| AdsPower local API | Start/stop browser profiles | Local HTTP (localhost:50325) |

### Special Requirements
- **Anti-detect**: each account must use a unique proxy (iProxy mobile), unique AdsPower profile (fingerprint), unique posting schedule
- **Limit enforcement**: daily limits per account (posts: 3-5, likes: 30-60, comments: 12-24) with minimum 90s between actions
- **Credential lifecycle**: capture via CDP → store in SQLite → use in httpx → periodic validation → recapture on expiry
- **10 required bapi headers**: csrftoken, bnc-uuid, device-info, fvideo-id, fvideo-token, clienttype, lang, bnc-location, versioncode, user-agent. Without fvideo-* headers, bapi returns `data: null`.

---
