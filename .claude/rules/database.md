---
globs: ["src/db/**"]
---

# Правила базы данных

- SQLite с WAL mode. Без системы миграций — изменения схемы через ручной ALTER TABLE или пересоздание БД.
- Все таблицы определены в `src/db/models.py` как строка `SCHEMA_SQL`. `init_db()` идемпотентен (CREATE TABLE IF NOT EXISTS).
- YAML — источник истины для конфигов аккаунтов/персон. SQLite хранит только runtime-данные (credentials, действия, очередь контента, спарсенные данные).
- Всегда параметризованные запросы — никаких f-строк или конкатенации в SQL.
- Использовать `aiosqlite` для всех операций с БД (async context).
- При добавлении новой таблицы: добавить DDL в `SCHEMA_SQL` в `models.py`, отдельный файл миграции не нужен.
- 7 таблиц: credentials, actions_log, daily_stats, content_queue, parsed_trends, parsed_posts, discovered_endpoints.
- Путь к БД: из переменной `DB_PATH`, по умолчанию `data/bsq.db`.
