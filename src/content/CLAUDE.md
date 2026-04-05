# Модуль: content
# Назначение: валидация контента, рыночные данные, новости, технический анализ
# Спецификация: docs/specs/spec_content.md

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| generator.py | 124 | ContentGenerator — строит промпт по персоне, вызывает Claude/OpenAI API |
| market_data.py | 85 | get_market_data(symbols) — цены + 24h изменение из Binance public API |
| validator.py | 392 | validate_post/comment/article/quote — banned phrases (из YAML), дубликаты, структура |
| technical_analysis.py | 214 | get_ta_summary(symbol, timeframe) — RSI, MACD, MAs, support/resistance |
| news.py | 151 | get_crypto_news(limit), get_article_content(url) — RSS новости + парсинг статей |

## Зависимости
- Используется: `sdk` (SDK вызывает market_data, news, ta), `runtime.session_context`

## Ключевые функции
- `ContentGenerator(provider, model, api_key)` — поддерживает "anthropic" и "openai"
- `ContentGenerator.generate(persona_style, persona_topics, topic, market_data)` — возвращает текст поста
- `get_market_data(symbols)` — возвращает `{symbol: {price, change_24h, volume}}`
- `get_crypto_news(limit)` — RSS новости с парсингом
- `get_ta_summary(symbol, timeframe)` — технический анализ (RSI, MACD, SMA/EMA)
- `validate_post(text, ...)` — проверка banned phrases, длины, структуры

## Типичные задачи
- Настроить тон/стиль AI: `_build_system_prompt()` в `generator.py`
- Добавить banned phrase: `config/content_rules.yaml`
- Публикация: через `session.browser_actions.create_post()`, не через bapi
