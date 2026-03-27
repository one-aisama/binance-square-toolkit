# Модуль: content
# Назначение: инструменты AI-генерации текстов для агента, очередь публикации, рыночные данные
# Спецификация: docs/specs/spec_content.md

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| generator.py | 125 | ContentGenerator — инструмент агента: строит промпт по персоне, вызывает Claude/OpenAI API |
| publisher.py | 88 | ContentPublisher — очередь контента в SQLite: добавить, получить pending, пометить published/failed |
| market_data.py | 45 | get_market_data(symbols) — цены + 24h изменение из Binance public API |
| validator.py | 250 | validate_post/comment/article/quote — banned phrases (из YAML), дубликаты, структура |
| technical_analysis.py | ~100 | get_ta_summary(symbol, timeframe) — RSI, MACD, MAs, support/resistance |
| news.py | ~80 | get_crypto_news(limit), get_article_content(url) — RSS новости + парсинг статей |

## Зависимости
- Использует: `bapi.client` (ContentPublisher вызывает BapiClient.create_post — заглушка)
- Использует: `db` (ContentPublisher читает/пишет таблицу content_queue)
- Используется: `scheduler` (_generate_content + _process_account)

## Ключевые функции
- `ContentGenerator(provider, model, api_key)` — поддерживает "anthropic" и "openai"
- `ContentGenerator.generate(persona_style, persona_topics, topic, market_data)` — возвращает текст поста
- `ContentPublisher.queue_content(account_id, text, hashtags, topic, meta, scheduled_at)` — ID записи
- `ContentPublisher.get_pending(account_id)` — список готовых к публикации
- `get_market_data(symbols)` — возвращает `{symbol: {price, change_24h, volume}}`

## Типичные задачи
- Настроить тон/стиль AI: `_build_system_prompt()` в `generator.py`
- Отладить очередь: таблица `content_queue`, статусы pending/published/failed
- Публикация: через `session.browser_actions.create_post()`, не через bapi (заглушка)

## Известные проблемы
- `publish()` бросает NotImplementedError — bapi endpoint для create_post не найден
- generator.py и comment_gen.py (в activity/) — это инструменты, которые вызывает агент; софт не решает что писать
