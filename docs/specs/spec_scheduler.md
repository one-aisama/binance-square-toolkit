# Спецификация: scheduler
# Модуль: src/scheduler/
# Статус: опционален

## Назначение
Оркестрация пайплайнов по расписанию через APScheduler.
**Опционален** — агент (Claude/Codex) может управлять таймингом напрямую, вызывая функции софта без scheduler.

## Файлы
| Файл | Что делает |
|------|------------|
| scheduler.py | `CycleScheduler` — APScheduler обёртка, запуск пайплайнов по аккаунтам |

## Класс CycleScheduler

### Конструктор
```python
CycleScheduler(settings: dict, accounts: list[AccountConfig], db_path: str)
```
Создаёт: `CredentialStore`, `ActionLimiter`, `AdsPowerClient`, `AsyncIOScheduler`.

### Методы
| Метод | Что делает |
|-------|------------|
| `start()` | Запуск APScheduler, первый цикл через 5с если `first_run_immediate: true` |
| `stop()` | Остановка |
| `_run_cycle()` | Итерация по аккаунтам, вызов `_process_account()` |
| `_process_account(account)` | Пайплайн: валидация creds → парсинг → генерация → публикация → активность |
| `_refresh_credentials(account)` | AdsPower start → harvest → save → stop |
| `_generate_content(account, topics, bapi_client)` | Выбор тем, market data, постановка в очередь |
| `_run_activity(account, posts, bapi_client)` | ActivityExecutor + run_cycle |

## Пайплайн одного аккаунта
```
1. Проверить credentials (valid + не протухли)
   → если протухли: _refresh_credentials()
2. Создать BapiClient с credentials
3. TrendFetcher.fetch_all() → темы
4. rank_topics() → отсортированные
5. _generate_content() → очередь
6. ContentPublisher.publish_pending() → публикация
7. _run_activity() → лайки, комменты, репосты
```

## Конфигурация
Настройки из `config/settings.yaml`:
- `cycle_interval_hours` — частота циклов
- `first_run_immediate` — запустить первый цикл сразу
- `adspower_base_url` — URL AdsPower API

## Зависимости
Использует ВСЕ модули: session, bapi, parser, content, activity, accounts, db.

## Роль в системе
Scheduler = конвейер для автономной работы. Не принимает творческих решений.
Агент может заменить scheduler полностью, вызывая функции софта напрямую по заданию человека.

## Известные проблемы
- Activity loop вызывает bapi comment/repost (заглушки) — логирует warning
- Publishing loop вызывает create_post (заглушка) — контент остаётся в очереди
- Аккаунты обрабатываются последовательно, нет параллелизма
