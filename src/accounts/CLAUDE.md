# Модуль: accounts
# Назначение: загрузка конфигов аккаунтов/персон из YAML, дневные лимиты, анти-детект
# Спецификация: docs/specs/spec_accounts.md

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| manager.py | 94 | load_accounts() + load_personas() — чтение YAML, слияние персоны в AccountConfig через Pydantic |
| limiter.py | 87 | ActionLimiter — проверка дневных счётчиков vs рандомизированный лимит, запись в actions_log + daily_stats |
| anti_detect.py | 16 | are_own_accounts() + should_skip_post_by_author() — предотвращение кросс-аккаунтных взаимодействий |

## Зависимости
- Использует: `db` (ActionLimiter читает/пишет actions_log и daily_stats)
- Используется: `scheduler` (load_accounts при старте, ActionLimiter проверяется при каждом действии)
- Используется: `activity` (ActivityExecutor получает ActionLimiter, TargetSelector использует ID аккаунтов)

## Ключевые функции
- `load_accounts(accounts_dir, personas_path)` — возвращает `list[AccountConfig]`
- `ActionLimiter(db_path)` — конструктор
- `ActionLimiter.check_allowed(account_id, action_type, daily_limit)` — детерминированный лимит через seed hash
- `ActionLimiter.record_action(account_id, action_type, target_id, status, error)` — запись в БД
- `should_skip_post_by_author(post_author_id, own_account_ids)` — возвращает bool

## Типичные задачи
- Добавить аккаунт: создать YAML в `config/accounts/`, указать persona_id из personas.yaml
- Изменить лимиты: блок `limits` в YAML аккаунта или дефолты `LimitsConfig`
- Отладить лимиты: seed = hash(f"{account_id}:{date}:{action_type}") — детерминированный

## Известные проблемы
- Нет валидации что `adspower_profile_id` реально существует в AdsPower
- 2 бага в подсчёте лимитов в ActionLimiter
