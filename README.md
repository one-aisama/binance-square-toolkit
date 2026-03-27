# Binance Square Toolkit

SDK / toolkit for managing Binance Square activity through AdsPower browser profiles, controlled by an AI agent (Claude, Codex, or any AI).

**Software = hands. Agent = brain.**

The software does not make decisions about what to post, when to post, or which posts to interact with. The AI agent receives tasks from a human, analyzes trends, generates content, and calls toolkit functions to execute actions on Binance Square.

## How It Works

```
Human gives task to Agent
  -> Agent calls parse functions     -> receives trending topics
  -> Agent calls market data         -> receives current prices
  -> Agent generates content text    -> using AI (Claude/OpenAI)
  -> Agent calls create_post()       -> toolkit publishes via browser
  -> Agent calls like/comment/follow -> toolkit executes via httpx or browser
```

## Requirements

- Python 3.12+
- AdsPower anti-detect browser (running locally)
- Playwright (installed via `playwright install chromium`)
- API keys: Anthropic and/or OpenAI (for content generation)

## Setup

1. Clone the repository and install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

2. Create `.env` file in project root:

```
ANTHROPIC_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
DEEPSEEK_API_KEY=your-key-here
DB_PATH=data/bsq.db
```

3. Configure accounts:

- Copy `config/accounts/_example.yaml` to `config/accounts/your_account.yaml`
- Set `adspower_profile_id` to your AdsPower profile ID
- Set `persona_id` to match one from `config/personas.yaml`
- Adjust limits as needed

4. Start AdsPower and ensure at least one browser profile is configured.

## Project Structure

```
binance_square/
  config/
    accounts/           Per-account YAML configs
    personas.yaml       6 persona definitions (style, topics)
    settings.yaml       Global settings (intervals, AI provider)
    content_rules.yaml  Content generation rules (for agent to follow)
  src/
    session/            AdsPower client, credential harvesting, browser actions
    bapi/               HTTP client for Binance bapi (parsing, likes)
    parser/             Feed parsing, trend ranking
    content/            AI content generation, publish queue, market data
    activity/           Likes, comments, reposts, target selection
    accounts/           Config loading, daily limits, anti-detection
    db/                 SQLite schema and init
    scheduler/          APScheduler orchestration (optional)
    main.py             Entry point
  docs/                 Specifications and design docs
  tests/                67 pytest tests
  scripts/              Utility scripts
```

## Toolkit Functions

### Parsing (httpx, no browser needed)

| Function | Description |
|----------|-------------|
| `BapiClient.get_feed_recommend(page)` | Recommended feed posts |
| `BapiClient.get_top_articles(page)` | Trending articles |
| `BapiClient.get_fear_greed()` | Fear & greed index |
| `BapiClient.get_hot_hashtags()` | Hot hashtags |
| `TrendFetcher.fetch_all()` | All posts (feed + articles), deduplicated |
| `rank_topics(posts)` | Top-N trending topics by engagement |
| `get_market_data(symbols)` | Coin prices from Binance public API |

### Actions via httpx

| Function | Description |
|----------|-------------|
| `BapiClient.like_post(post_id)` | Like a post |

### Actions via Playwright CDP (browser)

| Function | Description |
|----------|-------------|
| `create_post(ws, text, coin, sentiment, image)` | Create post with chart + sentiment |
| `comment_on_post(ws, post_id, text)` | Comment (handles Follow & Reply popup) |
| `follow_author(ws, post_id)` | Follow (checks if already following) |
| `repost(ws, post_id, comment)` | Quote/repost |
| `browse_and_interact(ws, comment_gen, count)` | Browse feed + like/comment/follow |

### Infrastructure

| Function | Description |
|----------|-------------|
| `AdsPowerClient.start_browser(user_id)` | Start AdsPower browser profile |
| `harvest_credentials(ws)` | Capture cookies + bapi headers |
| `validate_credentials(cookies, headers)` | Check if credentials are alive |

## Running Tests

```bash
python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py
```

## Validation Scripts

```bash
python scripts/check_file_sizes.py    # Check no .py file > 500 lines
python scripts/check_no_secrets.py    # Scan for hardcoded API keys
```

## Architecture Notes

- **httpx** handles parsing, likes, and market data (fast, no browser needed)
- **Playwright CDP** handles posting, commenting, following, reposting (requires client-side signatures or DOM input)
- **Credentials** are harvested once via CDP, stored in SQLite, and used by httpx for authenticated requests
- **AdsPower** provides anti-detect browser profiles with unique fingerprints and proxies per account
