---
globs: ["src/db/**"]
---

# Правила базы данных

- SQLite с WAL mode. Без системы миграций — изменения схемы через ручной ALTER TABLE или пересоздание БД.
- Все таблицы определены в `src/db/models.py` как строка `SCHEMA_SQL`. `init_db()` идемпотентен (CREATE TABLE IF NOT EXISTS).
- YAML — источник истины для конфигов аккаунтов/персон. SQLite хранит только runtime-данные (credentials, действия, координация, спарсенные данные).
- Всегда параметризованные запросы — никаких f-строк или конкатенации в SQL.
- Использовать `aiosqlite` для всех операций с БД (async context).
- При добавлении новой таблицы: добавить DDL в `SCHEMA_SQL` в `models.py`, отдельный файл миграции не нужен.
- 10 runtime таблиц: credentials, actions_log, daily_stats, parsed_trends, parsed_posts, discovered_endpoints, post_tracker, topic_reservations, comment_locks, news_cooldowns.
- 4 operator таблицы (в src/operator/state_store.py): operator_agents, operator_runs, operator_leases, operator_events.
- Путь к БД: из переменной `DB_PATH`, по умолчанию `data/bsq.db`.
