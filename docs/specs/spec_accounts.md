# Спецификация: Модуль Accounts

**Путь:** `src/accounts/`
**Файлы:** `manager.py`, `limiter.py`, `anti_detect.py`

---

## Описание

Модуль Accounts предоставляет инструменты для загрузки конфигураций аккаунтов/персон из YAML, контроля дневных лимитов действий и предотвращения перекрёстных взаимодействий между аккаунтами. Агент использует этот модуль чтобы знать какие аккаунты существуют, какие у них персоны и лимиты, и проверять разрешено ли действие перед выполнением.

---

## Пользовательские сценарии

- Как агент, я хочу загрузить все конфиги аккаунтов с объединёнными данными персон, чтобы знать стиль, темы и лимиты каждого аккаунта.
- Как агент, я хочу проверить разрешено ли конкретное действие для аккаунта сегодня, чтобы не превышать безопасные дневные пороги.
- Как агент, я хочу чтобы каждое действие (успех или ошибка) записывалось в БД, чтобы можно было отслеживать активность и дебажить.
- Как агент, я хочу проверять что целевой пост не написан одним из моих аккаунтов, чтобы никогда не создавать само-взаимодействия.

---

## Модель данных

### Pydantic модели конфигов (`src/accounts/manager.py`)

```python
class ProxyConfig(BaseModel):
    host: str
    port: int

class LimitsConfig(BaseModel):
    posts_per_day: list[int] = [3, 5]
    likes_per_day: list[int] = [30, 60]
    comments_per_day: list[int] = [12, 24]
    min_interval_sec: int = 90

class PersonaConfig(BaseModel):
    id: str
    name: str
    topics: list[str]
    style: str
    language: str = "en"

class AccountConfig(BaseModel):
    account_id: str
    persona_id: str
    binance_uid: str = ""
    adspower_profile_id: str
    proxy: ProxyConfig | None = None
    limits: LimitsConfig = LimitsConfig()
    persona: PersonaConfig | None = None  # Заполняется после merge
```

### Таблицы БД (читает/пишет ActionLimiter)

```sql
CREATE TABLE IF NOT EXISTS actions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    action_type TEXT NOT NULL,       -- post | like | comment | repost | follow
    target_id TEXT,
    status TEXT DEFAULT 'success',   -- success | failed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    posts_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    reposts_count INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    UNIQUE(account_id, date)
);
```

---

## API

### load_accounts / load_personas (`src/accounts/manager.py`)

```python
def load_personas(personas_path: str) -> dict[str, PersonaConfig]
def load_accounts(accounts_dir: str, personas_path: str) -> list[AccountConfig]
```

`load_accounts` читает все `*.yaml` файлы из `accounts_dir` (пропуская файлы начинающиеся с `_` или `.`), парсит каждый в `AccountConfig` и объединяет с соответствующей персоной из `personas_path`. Возвращает список полностью сконфигурированных аккаунтов.

---

### ActionLimiter (`src/accounts/limiter.py`)

```python
class ActionLimiter:
    def __init__(self, db_path: str)
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `check_allowed` | `(account_id: str, action_type: str, daily_limit: list[int]) -> bool` | True если сегодняшний счёт < детерминированного дневного лимита |
| `record_action` | `(account_id: str, action_type: str, target_id: str \| None, status: str, error: str \| None) -> None` | Пишет в actions_log + upsert в daily_stats |
| `get_today_count` | `(account_id: str, action_type: str) -> int` | Количество успешных действий за сегодня |

**Детерминированный дневной лимит:** для каждой тройки `(account_id, date, action_type)` seed-хеш определяет точный лимит в диапазоне `[min, max]`. Один аккаунт получает одинаковый лимит весь день, но разные лимиты в разные дни. Предотвращает предсказуемые паттерны.

---

### anti_detect (`src/accounts/anti_detect.py`)

```python
def are_own_accounts(account_id_1: str, account_id_2: str, all_account_ids: set[str]) -> bool
def should_skip_post_by_author(post_author_id: str, own_account_ids: set[str]) -> bool
```

Простые проверки принадлежности к множеству. `should_skip_post_by_author` возвращает `True` если автор поста — один из наших аккаунтов.

---

## Бизнес-логика

### Конвейер загрузки конфигов
```
config/personas.yaml  ->  load_personas()  ->  dict[str, PersonaConfig]
config/accounts/*.yaml  ->  load_accounts()  ->  list[AccountConfig]
                                                    (каждый с объединённой персоной)
```

Файлы начинающиеся с `_` (например `_example.yaml`) пропускаются. Если persona_id из конфига аккаунта не существует в personas.yaml — логируется предупреждение, но аккаунт загружается (с `persona = None`).

### Контроль дневных лимитов
```
Агент хочет лайкнуть пост для аккаунта X
  -> вызывает limiter.check_allowed("X", "like", [30, 60])
  -> limiter считает сегодняшние успешные лайки для X
  -> limiter вычисляет детерминированный лимит на сегодня (напр. 47)
  -> возвращает True если count < 47, False иначе
  -> после успешного лайка: limiter.record_action("X", "like", target_id="post123")
```

### Upsert дневной статистики
`record_action` пишет в обе таблицы: `actions_log` (отдельная строка) и `daily_stats` (upsert инкремент). Обновляемая колонка зависит от `action_type` (маппится в `{type}s_count`), а `status` failed инкрементирует `errors_count`.

---

## Крайние случаи

| Ситуация | Ожидаемое поведение |
|----------|-------------------|
| Нет YAML-файлов аккаунтов в директории | `load_accounts` возвращает пустой список, логирует предупреждение |
| Аккаунт ссылается на несуществующий persona_id | Предупреждение в логе, аккаунт загружается с `persona = None` |
| Невалидный формат YAML | Pydantic validation error |
| `daily_limit` с [min > max] | `random.randint` бросает ValueError |
| `check_allowed` при пустом actions_log | Счёт = 0, всегда разрешено (если лимит не [0, 0]) |
| `record_action` без существующей строки daily_stats | INSERT создаёт новую строку через UPSERT |
| Несколько вызовов `check_allowed` между действиями | Счёт не меняется пока не вызван `record_action` |

---

## Приоритет и зависимости

- **Приоритет:** Высокий (все модули зависят от конфигов аккаунтов и лимитов)
- **Зависит от:** `src/db/` (таблицы actions_log и daily_stats должны существовать)
- **Блокирует:** `src/activity/` (ActivityExecutor использует ActionLimiter), `src/scheduler/` (загружает аккаунты при старте)
