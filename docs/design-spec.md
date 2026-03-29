# Binance Square Toolkit — Design Specification
Date: 2026-03-25
Status: Current (after testing)

## Overview

SDK / toolkit for managing activity on Binance Square through AdsPower profiles.
The software does NOT make decisions — it is controlled by an AI agent (Claude, Codex, etc.).
The agent receives tasks from a human, analyzes, generates content, and calls toolkit functions.

**Software = hands. Agent = brain.**

Monetization through Write to Earn (5% base trading commission from readers).

## Architecture: Hybrid (httpx + Playwright CDP)

After testing, the architecture evolved from pure CDP-First:
- **httpx** — parsing (feed, articles, trends, market data), likes. Fast, no browser needed.
- **Playwright CDP** — posting, commenting, reposts, follows. Required because Binance uses client-side signatures for content creation and DOM-based inputs for comments.
- **Credentials** — captured once via CDP, stored in SQLite, used by httpx for parsing/likes. Refreshed on expiration.

```
AGENT (Claude / Codex / any AI)
  │ receives task from human
  │ analyzes, generates content
  │ calls toolkit functions:
  │
  ├── PARSING (httpx + captured cookies)
  │     ├── get_feed_recommend()    — recommended feed
  │     ├── get_top_articles()      — trending articles
  │     ├── get_fear_greed()        — fear/greed index
  │     ├── get_hot_hashtags()      — hot hashtags
  │     └── get_market_data()       — coin prices from Binance API
  │
  ├── ACTIONS via httpx
  │     └── like_post()             — like a post
  │
  ├── ACTIONS via Playwright CDP (browser)
  │     ├── create_post()           — post: text + chart + sentiment + image
  │     ├── create_article()        — article: title + body + cover
  │     ├── repost()                — quote/repost
  │     ├── comment_on_post()       — comment (Follow & Reply popup handling)
  │     ├── follow_author()         — follow (check if already following)
  │     └── browse_and_interact()   — feed browsing: like + comment + follow
  │
  ├── SESSION MANAGER
  │     ├── AdsPowerClient          — start/stop profiles
  │     ├── harvester               — credential capture via CDP
  │     ├── credential_store        — CRUD in SQLite for cookies/headers
  │     └── validator               — credential liveness check
  │
  ├── ACCOUNTS
  │     ├── manager                 — YAML config loading (accounts + personas)
  │     ├── limiter                 — daily action limit control
  │     └── anti_detect             — account isolation rules
  │
  └── DB (SQLite)
        └── credentials, actions_log, daily_stats, content_queue,
            parsed_trends, parsed_posts, discovered_endpoints
```

## Scheduler (optional)

APScheduler can run parsing→generation→publishing→engagement cycles on a schedule. But this is optional — the agent decides when and what to run. The scheduler is one possible orchestration method, not a required component.

## Content Generation

Content generation is the agent's task, not the software's. The toolkit provides:
- `ContentGenerator` — a tool for sending a prompt to an AI API and receiving text. The agent decides what to generate.
- `CommentGenerator` — a tool for generating short comments (uses a cheap model, DeepSeek by default). The agent decides which post and what context to pass.
- `get_market_data()` — real coin prices for use in content.

Content rules are defined in `config/content_rules.yaml` — the agent follows them when constructing prompts.

## Tested and Working (live testing 2026-03-24)

| Action | Method | Status | Notes |
|--------|--------|--------|-------|
| Credential capture | CDP | working | 32 cookies, 13 headers |
| Recommended feed parsing | httpx | working | 21 posts per page |
| Top articles parsing | httpx | working | |
| Fear/greed index | httpx | working | POST, not GET (discovered during spike) |
| Hot hashtags | httpx | working | |
| Market data (prices) | httpx | working | Binance public API |
| Post like | httpx | working | `POST /bapi/composite/v1/private/pgc/content/like` |
| Post creation | CDP browser | working | Text + chart + bullish/bearish |
| Post comment | CDP browser | working | Handles "Follow & Reply" popup |
| Author follow | CDP browser | working | Checks "Follow" vs "Following" |
| Feed browsing + interaction | CDP browser | working | Scroll, filter, like+comment+follow |

## Key Technical Discoveries (from spike + testing)

1. **Feed recommend** requires `scene: "web-homepage"` and `contentIds: []` in the POST body. Data is in `data.vos`, not `data.list`.

2. **Fear & Greed** is a POST, not GET (specification was incorrect).

3. **Like endpoint**: `POST /bapi/composite/v1/private/pgc/content/like` with body `{"id": "<post_id>", "cardType": "BUZZ_SHORT"}`.

4. **Post creation** requires client-side `nonce` + `signature` — cannot be done via httpx. Browser only.

5. **Comments** go through the DOM input `input[placeholder="Post your reply"]` + Reply button. Not via bapi POST.

6. **Hashtag autocomplete** blocks the Post button — need to press Escape after entering a hashtag.

7. **Two Post buttons** on the Square page: left panel button (opens a modal) and inline button (publishes). Must use inline: `button[data-bn-type='button']:not(.news-post-button)`.

8. **Follow & Reply popup** — some authors restrict comments to followers. Clicking "Follow & Reply" follows and submits the comment simultaneously.

9. **Follow vs Following** — clicking the "Following" button will UNFOLLOW. Must check button text before clicking.

10. **Required bapi headers**: `csrftoken`, `bnc-uuid`, `device-info`, `fvideo-id`, `fvideo-token`, `clienttype`, `lang`, `bnc-location`, `versioncode`, `user-agent`. Without `fvideo-*` headers, bapi returns `data: null`.

## Content Rules (config/content_rules.yaml)

- Language: English only
- Style: casual, human, conversational. No AI cliches.
- Posts and quote reposts: minimum 2 paragraphs, $CASHTAGS for coins
- Comments: 1-2 sentences, relevant to the post content, like a conversation with the author
- Quote reposts: $CASHTAGS only if the original post is about a specific coin
- All content is generated by the controlling agent through toolkit tools (`ContentGenerator`, `CommentGenerator`), not by the software autonomously

## Database (SQLite + WAL mode)

7 tables: credentials, actions_log, daily_stats, content_queue, parsed_trends, parsed_posts, discovered_endpoints.

YAML is the source of truth for account/persona configs. SQLite stores only runtime data.

## Configuration

- `config/accounts/{id}.yaml` — account infrastructure (adspower_profile_id, proxy, limits)
- `config/personas.yaml` — 6 personas (style, topics, language)
- `config/settings.yaml` — global settings (intervals, limits, AI provider)
- `config/content_rules.yaml` — content generation rules (for the agent)
- `.env` — API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY)

## Known Issues

1. **ActionLimiter** — 2 bugs in daily limit counting logic (2 failing tests)
2. **ActivityExecutor** — tries to use httpx for comments/reposts instead of browser_actions
3. **Article creation** — not tested live
4. **Repost** — not tested live
5. **Image attachment** — not tested live
6. **Author profile viewing** — not implemented
7. **Post/comment deletion** — not implemented
8. **Multi-profile orchestration** — not tested (only one profile so far)

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
