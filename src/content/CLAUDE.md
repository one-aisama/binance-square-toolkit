# Module: content
# Purpose: AI text generation tools for the agent, publishing queue, market data
# Specification: docs/specs/spec_content.md

## Files
| File | Lines | What it does |
|------|-------|------------|
| generator.py | 125 | ContentGenerator — agent tool: builds prompt per persona, calls Claude/OpenAI API |
| publisher.py | 88 | ContentPublisher — content queue in SQLite: add, get pending, mark published/failed |
| market_data.py | 45 | get_market_data(symbols) — prices + 24h change from Binance public API |
| validator.py | 250 | validate_post/comment/article/quote — banned phrases (from YAML), duplicates, structure |
| technical_analysis.py | ~100 | get_ta_summary(symbol, timeframe) — RSI, MACD, MAs, support/resistance |
| news.py | ~80 | get_crypto_news(limit), get_article_content(url) — RSS news + article parsing |

## Dependencies
- Uses: `bapi.client` (ContentPublisher calls BapiClient.create_post — stub)
- Uses: `db` (ContentPublisher reads/writes the content_queue table)
- Used by: `scheduler` (_generate_content + _process_account)

## Key Functions
- `ContentGenerator(provider, model, api_key)` — supports "anthropic" and "openai"
- `ContentGenerator.generate(persona_style, persona_topics, topic, market_data)` — returns post text
- `ContentPublisher.queue_content(account_id, text, hashtags, topic, meta, scheduled_at)` — row ID
- `ContentPublisher.get_pending(account_id)` — list of items ready for publishing
- `get_market_data(symbols)` — returns `{symbol: {price, change_24h, volume}}`

## Common Tasks
- Adjust AI tone/style: `_build_system_prompt()` in `generator.py`
- Debug queue: `content_queue` table, statuses pending/published/failed
- Publishing: via `session.browser_actions.create_post()`, not via bapi (stub)

## Known Issues
- `publish()` raises NotImplementedError — bapi endpoint for create_post not found
- generator.py and comment_gen.py (in activity/) are tools that the agent calls; the software does not decide what to write
