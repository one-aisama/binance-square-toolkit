# Модуль: bapi
# Назначение: HTTP-клиент к Binance bapi — инъекция credentials, rate limiting, retry, удобные методы
# Спецификация: docs/specs/spec_bapi.md

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| client.py | 194 | BapiClient — GET/POST с auth headers, лимит 30 RPM, retry на 429/5xx, авто-инвалидация на 401/403 |
| endpoints.py | 21 | URL-константы всех известных bapi endpoints (парсинг + активность) |
| models.py | 34 | Pydantic модели: BapiResponse, FeedPost |

## Зависимости
- Использует: `session.credential_store` (CredentialStore — загрузка cookies+headers)
- Используется: `parser` (TrendFetcher вызывает get_feed_recommend, get_top_articles и др.)
- Используется: `content` (ContentPublisher вызывает create_post — заглушка)
- Используется: `activity` (ActivityExecutor вызывает like_post)
- Используется: `scheduler` (создаёт BapiClient для каждого аккаунта)

## Ключевые функции
- `BapiClient(account_id, credential_store, rate_limit_rpm=30)` — конструктор
- `BapiClient.get_feed_recommend(page, page_size)` — список сырых постов
- `BapiClient.get_top_articles(page, page_size)` — список сырых статей
- `BapiClient.get_fear_greed()` — индекс страха/жадности + популярные монеты
- `BapiClient.get_hot_hashtags()` — список хэштегов
- `BapiClient.like_post(post_id, card_type)` — работает (endpoint найден)

## Типичные задачи
- Добавить endpoint: константа в `endpoints.py`, метод в `BapiClient`
- Отладить auth-ошибки: проверить `credential_store.load()`, искать 401/403 в логах

## Известные проблемы
- `create_post`, `comment_post`, `repost` — заглушки (endpoints не найдены, используется browser)
