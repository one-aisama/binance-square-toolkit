# Module: content
# Purpose: content validation, market data, news, technical analysis
# Specification: docs/specs/spec_content.md

## Files
| File | Lines | What it does |
|------|-------|--------------|
| generator.py | 124 | ContentGenerator — builds a prompt from persona, calls Claude/OpenAI API |
| market_data.py | 85 | get_market_data(symbols) — prices + 24h change from Binance public API |
| validator.py | 392 | validate_post/comment/article/quote — banned phrases (from YAML), duplicates, structure |
| technical_analysis.py | 214 | get_ta_summary(symbol, timeframe) — RSI, MACD, MAs, support/resistance |
| news.py | 151 | get_crypto_news(limit), get_article_content(url) — RSS news + article parsing |

## Dependencies
- Used by: `sdk` (SDK calls market_data, news, ta), `runtime.session_context`

## Key Functions
- `ContentGenerator(provider, model, api_key)` — supports "anthropic" and "openai"
- `ContentGenerator.generate(persona_style, persona_topics, topic, market_data)` — returns post text
- `get_market_data(symbols)` — returns `{symbol: {price, change_24h, volume}}`
- `get_crypto_news(limit)` — RSS news with parsing
- `get_ta_summary(symbol, timeframe)` — technical analysis (RSI, MACD, SMA/EMA)
- `validate_post(text, ...)` — checks banned phrases, length, structure

## Common Tasks
- Adjust AI tone/style: `_build_system_prompt()` in `generator.py`
- Add a banned phrase: `config/content_rules.yaml`
- Publishing: via `session.browser_actions.create_post()`, not through bapi
