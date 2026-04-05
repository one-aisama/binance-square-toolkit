# Binance Square Toolkit — Операционный гид

## Что это
SDK для автономной активности на Binance Square. Три слоя:
- **Софт (этот репозиторий)** — выполняет действия: посты, комменты, лайки, подписки
- **Оператор (Claude Code / Codex сессия)** — назначает субагентов на роли, управляет запуском
- **Субагенты** — выполняют конкретные роли (persona, auditor, supervisor)

## Как это работает
Claude Code или Codex сессия — это **оператор**. Она получает SDK и назначает субагентов:

| Роль | Что делает | Кто |
|------|-----------|-----|
| **persona-агент** | Работает на Binance Square: пишет посты, комменты, лайки, подписки. Сам генерирует текст | aisama (профиль 1), sweetdi (профиль 2) |
| **auditor** | Валидирует план и контент перед публикацией | agents/auditor/ |
| **supervisor** | Мониторинг, коучинг, обзор поведения всех persona-агентов | agents/supervisor/ |

Persona-агенты — это субагенты которые **сами пишут текст** (они LLM). Софт только выполняет их решения через SDK. Код не генерирует текст — никогда.

## Как запустить

### Production — через оператора
```bash
# 1. Убедись что AdsPower запущен
# 2. Запусти оператор:
python scripts/run_operator.py --max-slots 4

# 3. Статус в отдельном терминале:
python scripts/operator_status.py
```
Оператор сам сканирует `config/active_agent*.yaml`, планирует циклы, спавнит persona-субагентов для текста, выполняет через SDK.

### Ручной режим — prepare/execute
```bash
python session_run.py --prepare --config config/active_agent.yaml
# → Агент-сессия читает pending_plan.json, пишет текст, сохраняет
python session_run.py --execute --config config/active_agent.yaml
```

### Тесты
```bash
python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py
```

## Архитектура в двух словах

```
Агент (Claude Code сессия)
  ↓ решения
session_run.py --prepare / --execute
  ↓
SDK (src/sdk.py) — единый фасад
  ├── browser_actions.py  → посты, статьи, репосты (Playwright CDP)
  ├── browser_engage.py   → лайки, комменты, подписки (Playwright CDP)
  ├── browser_data.py     → сбор ленты, профиль, комменты
  └── bapi/               → httpx запросы к Binance API
```

Runtime framework (`src/runtime/`) управляет циклом:
```
prepare (context → plan → audit) → АГЕНТ ПИШЕТ ТЕКСТ → execute (audit → SDK → commit)
```

## Субагенты продукта

### Persona-агенты — работают на Binance Square
Каждый persona-агент — это субагент с уникальной личностью. Он сам пишет текст, сам принимает решения. Оператор (Claude Code/Codex) назначает его на профиль и запускает.

| Агент | Профиль | Фокус | Файлы |
|-------|---------|-------|-------|
| **aisama** | 1 | BTC/ETH, макро, рыночная структура | `agents/aisama/`, `config/persona_policies/aisama.yaml` |
| **sweetdi** | 2 | Альткоины, листинги, ротация секторов | `agents/sweetdi/`, `config/persona_policies/sweetdi.yaml` |
| *(новые)* | 3-6 | Добавляются по мере отладки | YAML + папка в agents/ |

Каждый persona-агент состоит из:
- `agents/{id}/prompt.md` — системный промпт (как работать, какие инструменты)
- `agents/{id}/identity.md, style.md, strategy.md` — характер и поведение
- `config/persona_policies/{id}.yaml` — числовые параметры (scoring, stages, templates)
- `config/active_agent.{id}.yaml` — привязка к AdsPower профилю

### Auditor — валидация плана и контента
Не постит. Проверяет планы persona-агентов перед публикацией: overlap, стиль, дубликаты.
Файлы: `agents/auditor/prompt.md`

### Supervisor — мониторинг и коучинг
Не постит. Наблюдает за всеми persona-агентами, даёт рекомендации, отслеживает метрики.
Файлы: `agents/supervisor/prompt.md`, `agents/supervisor/reports/`

### Субагенты разработки (не продукт)
Отдельная категория — помогают разрабатывать сам SDK. Не имеют отношения к Binance Square.

| Субагент | Роль | Файл |
|----------|------|------|
| database-architect | Схема БД, миграции | `.claude/agents/database-architect.md` |
| backend-engineer | Серверная логика | `.claude/agents/backend-engineer.md` |
| frontend-developer | UI компоненты | `.claude/agents/frontend-developer.md` |
| qa-reviewer | Ревью кода (read-only) | `.claude/agents/qa-reviewer.md` |
| spec-reviewer | Проверка спецификаций | `.claude/agents/spec-reviewer.md` |
| skeptic | Челлендж архитектурных решений | `.claude/agents/skeptic.md` |

## Навигация по коду

| Задача | Куда смотреть |
|--------|--------------|
| **Запуск (production)** | `scripts/run_operator.py` |
| **Статус всех агентов** | `scripts/operator_status.py` |
| Operator loop и scheduling | `src/operator/loop.py`, `scheduler.py`, `models.py` |
| Operator leases и recovery | `src/operator/leases.py`, `recovery.py` |
| Persona/auditor bridges | `src/operator/persona_bridge.py`, `auditor_bridge.py` |
| Понять что умеет SDK | `src/sdk.py`, `docs/agent_api.md` |
| Как агент планирует действия | `src/runtime/deterministic_planner.py` |
| Как выбирается тема поста | `src/runtime/editorial_brain.py` |
| Как проверяется план | `src/runtime/plan_auditor.py` |
| Как выполняется план | `src/runtime/plan_executor.py` |
| Лимиты и безопасность | `src/runtime/guard.py` |
| Координация между агентами | `src/runtime/comment_coordination.py`, `news_cooldown.py`, `topic_reservation.py` |
| Поведение (человечность) | `src/runtime/behavior.py` |
| CSS-селекторы Binance | `src/session/page_map.py` |
| Настройки персоны | `config/persona_policies/{id}.yaml` |
| Runtime привязка | `config/active_agent.{id}.yaml` |

## Навигация по документации

| Документ | Что внутри |
|----------|-----------|
| `CLAUDE.md` | Главный справочник: стек, модули, архитектура, статус |
| `docs/agent_api.md` | Все методы SDK с примерами |
| `docs/design-spec.md` | Общая архитектура, слои, таблицы |
| `docs/specs/spec_operator.md` | Operator control plane: state machine, scheduling, bridges |
| `docs/specs/spec_runtime.md` | Детали runtime: planner, auditor, executor |
| `docs/specs/spec_session.md` | Browser automation: AdsPower, harvester, actions |
| `docs/specs/spec_bapi.md` | httpx клиент к Binance API |
| `src/*/CLAUDE.md` | Модульные справочники (файлы, функции, зависимости) |

## Координация агентов

При запуске нескольких агентов одновременно работают 4 механизма:

| Механизм | Что делает | TTL |
|----------|-----------|-----|
| Topic reservations | Блокирует тему поста на время планирования | 2 часа |
| Comment locks | Предотвращает комментирование одного поста двумя агентами | 30 мин |
| News cooldowns | Не даёт всем агентам кинуться на одну новость | 90 мин |
| Territory drift | Отклоняет план если все посты вне ниши агента | — |
| Timing stagger | Разносит циклы агентов по времени (0-300с offset) | — |

## Режимы работы

В `config/active_agent.{id}.yaml`:
```yaml
mode: "standard"      # default — штатная работа по stages
mode: "individual"    # override — временная кампания (expires_at)
mode: "test"          # dry-run — всё кроме реального выполнения
```

## Принцип: Софт = руки, Агент = мозг

Persona-агент участвует в трёх местах каждого micro-cycle:

1. **STRATEGIZE** — persona читает briefing_packet + контекст → выдаёт strategic_directive
   (какие монеты, какой угол, что пропустить)
2. **AUTHOR** — persona читает plan с brief → пишет текст постов и комментов
3. **REFLECT** — persona обновляет strategic_state.md, open_loops.md, intent.md

Код **никогда** не генерирует текст и не принимает стратегические решения. Код только:
- Собирает контекст (prepare)
- Компилирует briefing_packet из памяти (memory_compiler)
- Конкретизирует указания persona в план (editorial_brain + planner)
- Валидирует (auditor)
- Выполняет через SDK (executor)

Если где-то в коде есть вызов LLM для генерации контента или стратегических решений — это баг.

## Рекомендации

- SDK (`src/sdk.py`) — единственный способ взаимодействия с Binance Square. Все действия через него
- Конфигурация поведения — через YAML (`persona_policies/`, `active_agent.`), не через Python
- Добавление нового агента — создать YAML файлы и папку в `agents/`, ноль изменений в коде
- Перед изменением runtime-модулей — прогнать тесты (390 тестов, ~20 секунд)
- SQLite (`data/bsq.db`) — coordination layer. Per-agent state в файлах: `data/runtime/{id}/`
- Селекторы в `page_map.py` хрупкие — UI Binance может сломать их в любой момент

## Текущий статус
- 390 тестов зелёные
- 29 runtime модулей
- 14 SQLite таблиц (10 runtime + 4 operator)
- 2 активные персоны (aisama, sweetdi)
- Обновлено: 2026-04-04
