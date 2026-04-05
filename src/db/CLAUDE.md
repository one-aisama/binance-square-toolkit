# Модуль: db
# Назначение: SQLite схема и инициализация базы данных
# Спецификация: docs/design-spec.md (раздел Database)

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| database.py | 23 | init_db(db_path) — создание таблиц через SCHEMA_SQL, WAL mode; get_db_path() из env |
| models.py | 122 | SCHEMA_SQL — DDL для всех 10 таблиц |

## Таблицы (10)
| Таблица | Назначение |
|---------|------------|
| credentials | Cookies + headers по аккаунтам, срок, флаг valid |
| actions_log | Каждый like/comment/repost/post со статусом + ошибка |
| daily_stats | Агрегированные счётчики по аккаунту в день |
| parsed_trends | Снапшот тем + fear/greed за цикл парсинга |
| parsed_posts | Сырые распарсенные посты для дедупликации |
| discovered_endpoints | CDP-обнаруженные bapi endpoints с примерами |
| post_tracker | Трекинг постов всех агентов: ID, тип, engagement метрики |
| topic_reservations | Live locks на темы постов между агентами (2h TTL) |
| comment_locks | Предотвращение дублей комментов между агентами (30min TTL) |
| news_cooldowns | Cooldown на новости: 30min hard block + 60min soft penalty |

## Зависимости
- Внутренних импортов нет
- Используется: `session.credential_store`, `accounts.limiter`, `runtime.comment_coordination`, `runtime.news_cooldown`, `runtime.topic_reservation`

## Ключевые функции
- `init_db(db_path)` — идемпотентная (CREATE TABLE IF NOT EXISTS), безопасна при рестарте
- `get_db_path()` — читает DB_PATH env var, по умолчанию "data/bsq.db"

## Типичные задачи
- Добавить таблицу: DDL в SCHEMA_SQL в `models.py`, вызвать init_db (идемпотентно)
- Сменить путь к БД: переменная окружения DB_PATH
- Просмотреть данные: `sqlite3 data/bsq.db` — WAL mode, чтение неблокирующее

## Известные проблемы
- Нет системы миграций — изменения схемы через ручной ALTER TABLE или пересоздание БД
