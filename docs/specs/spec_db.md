# Спецификация: db
# Модуль: src/db/
# Статус: реализован

## Назначение
SQLite хранилище runtime-данных: credentials, действия, очередь контента, парсинг.
YAML — источник истины для конфигов. SQLite — только runtime.

## Файлы
| Файл | Что делает |
|------|------------|
| database.py | `init_db(db_path)` — идемпотентное создание таблиц, WAL mode; `get_db_path()` из env |
| models.py | `SCHEMA_SQL` — DDL для всех 7 таблиц |

## Таблицы

### credentials
Cookies + headers авторизованных сессий.
- `account_id` TEXT PK — идентификатор аккаунта
- `cookies` TEXT — JSON cookies из CDP
- `headers` TEXT — JSON headers (csrftoken, fvideo-id, fvideo-token)
- `harvested_at` TIMESTAMP — когда захвачены
- `expires_at` TIMESTAMP — когда протухнут
- `valid` BOOLEAN — флаг валидности

### actions_log
Каждое действие (like, comment, repost, post) со статусом.
- `account_id`, `action_type`, `target_id`, `status`, `error_message`, `created_at`
- Индекс: `(account_id, action_type, created_at)` — для подсчёта лимитов

### daily_stats
Агрегированные счётчики по аккаунту в день.
- `account_id`, `date`, `posts_count`, `likes_count`, `comments_count`, `reposts_count`, `errors_count`
- UNIQUE: `(account_id, date)`

### content_queue
Сгенерированные посты ожидающие публикации.
- `account_id`, `text`, `hashtags`, `topic`, `generation_meta`, `status`, `scheduled_at`, `published_at`, `post_id`
- Индексы: `(account_id, status)`, `(status, scheduled_at)`

### parsed_trends
Снапшот тем + fear/greed за цикл парсинга.
- `cycle_id`, `topics` (JSON), `fear_greed_index`, `popular_coins`

### parsed_posts
Сырые распарсенные посты для дедупликации.
- `cycle_id`, `post_id`, `author_name`, `card_type`, метрики (views, likes, comments, shares), `hashtags`, `trading_pairs`, `is_ai_created`
- UNIQUE: `(cycle_id, post_id)`

### discovered_endpoints
CDP-обнаруженные bapi endpoints с примерами запросов/ответов.
- `method`, `path`, `purpose`, `request_headers`, `request_body`, `response_sample`
- UNIQUE: `(method, path)`

## Правила
- WAL mode обязателен
- Все запросы параметризованные — никаких f-строк в SQL
- `aiosqlite` для всех операций (async)
- Новая таблица: добавить DDL в `SCHEMA_SQL`, вызвать `init_db` (идемпотентно)
- Путь к БД: переменная `DB_PATH`, по умолчанию `data/bsq.db`

## Известные ограничения
- Нет системы миграций — изменения через ALTER TABLE или пересоздание БД
