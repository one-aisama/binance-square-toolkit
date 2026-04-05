# Модуль: scheduler
# Назначение: опциональная оркестрация пайплайнов по расписанию (агент может управлять таймингом напрямую)
# Спецификация: отдельная спека отсутствует (см. docs/design-spec.md, раздел планировщик)

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| scheduler.py | 304 | CycleScheduler — APScheduler обёртка, запуск пайплайнов по аккаунтам |

## Зависимости
- Использует: все остальные модули (session, bapi, parser, content, activity, accounts, db)
- Entry point: `src/main.py` конструирует и запускает CycleScheduler

## Ключевые функции
- `CycleScheduler(settings, accounts, db_path)` — создаёт CredentialStore + ActionLimiter
- `CycleScheduler.start()` — запуск APScheduler, первый цикл через 5с если `first_run_immediate: true`
- `CycleScheduler.stop()` — остановка
- `_run_cycle()` — итерация по аккаунтам, вызов `_process_account()`
- `_process_account(account)` — пайплайн: валидация creds, парсинг, генерация, публикация, активность
- `_refresh_credentials(account)` — AdsPower start, harvest, save, stop
- `_generate_content(account, topics, bapi_client)` — выбор тем, market data, постановка в очередь
- `_run_activity(account, posts, bapi_client)` — ActivityExecutor + run_cycle

## Роль в системе
Scheduler опционален. Он выполняет заданные пайплайны по таймеру, но не принимает творческих решений.
Агент (Claude/Codex) может заменить scheduler полностью, вызывая функции софта напрямую.

## Типичные задачи
- Изменить частоту циклов: `cycle_interval_hours` в settings YAML
- Добавить шаг пайплайна: метод `_do_step()`, вызов в `_process_account()`
- Отладить цикл: искать "CYCLE STARTED" / "CYCLE COMPLETED" в логах

## Известные проблемы
- Activity loop вызывает bapi comment/repost (заглушки) — логирует warning, продолжает
- Publishing loop вызывает create_post (заглушка) — контент остаётся в очереди
- Аккаунты обрабатываются последовательно, нет параллелизма
