# Модуль: db
# Назначение: SQLite схема и инициализация базы данных
# Спецификация: docs/design-spec.md (раздел Database)

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| database.py | 23 | init_db(db_path) — создание таблиц через SCHEMA_SQL, WAL mode; get_db_path() из env |
| models.py | 90 | SCHEMA_SQL — DDL для всех таблиц |

## Таблицы
| Таблица | Назначение |
|---------|------------|
| credentials | Cookies + headers по аккаунтам, срок, флаг valid |
| actions_log | Каждый like/comment/repost/post со статусом + ошибка |
| daily_stats | Агрегированные счётчики по аккаунту в день |
| content_queue | Сгенерированные посты ожидающие публикации |
| parsed_trends | Снапшот тем + fear/greed за цикл парсинга |
| parsed_posts | Сырые распарсенные посты для дедупликации |
| discovered_endpoints | CDP-обнаруженные bapi endpoints с примерами |

## Зависимости
- Внутренних импортов нет
- Используется: `session.credential_store`, `accounts.limiter`, `content.publisher`, `scheduler`

## Ключевые функции
- `init_db(db_path)` — идемпотентная (CREATE TABLE IF NOT EXISTS), безопасна при рестарте
- `get_db_path()` — читает DB_PATH env var, по умолчанию "data/bsq.db"

## Типичные задачи
- Добавить таблицу: DDL в SCHEMA_SQL в `models.py`, вызвать init_db (идемпотентно)
- Сменить путь к БД: переменная окружения DB_PATH
- Просмотреть данные: `sqlite3 data/bsq.db` — WAL mode, чтение неблокирующее

## Известные проблемы
- Нет системы миграций — изменения схемы через ручной ALTER TABLE или пересоздание БД
