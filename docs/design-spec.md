# Binance Square Toolkit — Дизайн-спецификация
Дата: 2026-04-03
Статус: АКТУАЛЬНО (v3, policy-driven)

## Обзор

SDK / тулкит для управления активностью на Binance Square через AdsPower профили.
**Софт = руки. Агент = мозг. Runtime = координация.**

- Софт (SDK) выполняет действия: постинг, лайки, комменты, подписки
- Агент (Claude session) принимает решения и генерирует контент
- Runtime framework координирует: планирование, аудит, исполнение, метрики

Монетизация через Write to Earn (5% базовой торговой комиссии от читателей).

## Архитектура по слоям

```
┌─────────────────────────────────────────────────────┐
│  Entry points: session_run.py / main.py             │
├─────────────────────────────────────────────────────┤
│  Runtime framework (src/runtime/, 29 модулей)      │
│  session_loop → planner → auditor → executor        │
├─────────────────────────────────────────────────────┤
│  Data pipeline                                       │
│  metrics/ → memory/ → strategy/                     │
├─────────────────────────────────────────────────────┤
│  SDK facade (src/sdk.py)                            │
├──────────┬──────────┬───────────┬───────────────────┤
│ session/ │ bapi/    │ content/  │ activity/         │
├──────────┴──────────┴───────────┴───────────────────┤
│  accounts/ │ db/ (SQLite WAL) │ config/ (YAML)      │
└─────────────────────────────────────────────────────┘
```

### Transport
- **sdk.py** — единый фасад для агента: connect, create_post, comment, like, follow, feed, market data
- **session/** — AdsPower CDP, browser_actions (publishing), browser_engage (engagement), browser_data (парсинг), harvester (credentials)
- **bapi/** — httpx клиент к Binance bapi с retry и rate limit (30 RPM)

### Coordination
- **topic_reservations** (SQLite) — кросс-агентная блокировка тем (coin+angle+source), TTL 2 часа
- **post_registry** — реестр опубликованных постов (72-часовое окно) для overlap avoidance

### Runtime framework
Автономный цикл агента:
1. **SessionContextBuilder** → сбор контекста (рынок, новости, TA, фид, реплаи)
2. **CyclePolicy** → выбор stage (bootstrap / default / overflow / reply_limited)
3. **DeterministicPlanGenerator** → JSON план (comment, like, follow, post) без LLM
4. **EditorialBrain** → brief для поста (family, coin, angle, hooks, insights)
5. **Агент** (Claude Code сессия) → пишет текст сам, используя brief_context и свои файлы
6. **PlanAuditor** → детерминированная валидация (8 слоёв: стиль, дубликаты, overlap, reservations)
7. **PlanExecutor** → исполнение через SDK + VisualPipeline (картинки)
8. **Commit** → daily_plan, post_registry, topic_reservation, journal

### Policy (per-agent)
- **persona_policies/{agent_id}.yaml** — все behavioral параметры: content mix, coin bias, angle rules, stages, audit style, comment stance, feed scoring
- **active_agent.{agent_id}.yaml** — runtime binding: AdsPower profile, symbols, session limits, visual config
- **accounts/{agent_id}.yaml** — daily limits, proxy, credentials

### Data pipeline
- **metrics/** — store (SQLite), collector (отложенный сбор outcomes 6h+), scorer (агрегация insights + auto-lessons)
- **memory/** — compactor: генерация performance.md, relationships.md из insights
- **strategy/** — analyst (обновление strategy.md), reviewer (session stats + journal), feed_filter (спам-фильтр)
- **pipeline.py** — оркестрация: collector → scorer → compactor → analyst

### State (per-agent files)
- `data/runtime/{agent_id}/` — checkpoint.json, daily_plan.json, status.json
- `data/generated_visuals/{agent_id}/` — AI-сгенерированные картинки
- `agents/{agent_id}/` — identity, style, strategy, lessons, journal, performance, relationships

## Hybrid Transport (httpx + Playwright CDP)

- **httpx** — парсинг (лента, статьи, тренды, рыночные данные), лайки. Быстро, без браузера.
- **Playwright CDP** — постинг, комментирование, репосты, подписки. Требуется client-side signature.
- **Credentials** — захватываются через CDP, хранятся в SQLite (зашифрованы), используются httpx.

## Карта модулей

| Модуль | Путь | Назначение |
|--------|------|------------|
| sdk | src/sdk.py | Единый фасад для агента |
| session | src/session/ | AdsPower, CDP, browser actions/data, web authoring |
| bapi | src/bapi/ | httpx клиент к Binance bapi |
| parser | src/parser/ | Парсинг фида, статей, тренды |
| content | src/content/ | AI-генерация, валидация, market data, news, TA |
| activity | src/activity/ | Лайки, комменты, репосты (оркестрация) |
| runtime | src/runtime/ | 29 модулей: планирование, аудит, исполнение, guard |
| metrics | src/metrics/ | MetricsStore, Collector, Scorer |
| memory | src/memory/ | Compactor (performance.md, relationships.md) |
| strategy | src/strategy/ | Planner, Analyst, Reviewer, FeedFilter |
| pipeline | src/pipeline.py | Оркестрация data pipeline |
| accounts | src/accounts/ | YAML конфиги, лимиты, анти-детект |
| db | src/db/ | SQLite схема (10 таблиц), инициализация |

## База данных (SQLite + WAL mode)

10 таблиц: credentials, actions_log, daily_stats, parsed_trends, parsed_posts, discovered_endpoints, post_tracker, topic_reservations, comment_locks, news_cooldowns.

YAML — источник истины для конфигов. SQLite хранит runtime-данные.

## Добавление нового агента

1. `config/persona_policies/{id}.yaml` — behavioral policy
2. `config/active_agent.{id}.yaml` — runtime binding (AdsPower, symbols, visual)
3. `config/accounts/{id}.yaml` — account credentials и daily limits
4. `agents/{id}/` — identity.md, style.md, strategy.md, prompt.md, visual_profile.md
5. Ноль изменений в Python коде

## Известные ограничения

1. **create_post() confirmation** — подтверждение публикации через network response (`content/add`). При отсутствии — `publish_unconfirmed`. Нужен robust fallback (composer cleared, success toast, URL change).
2. **BapiClient stubs** — `comment_post()`, `repost()`, `create_post()` через httpx — stubs (NotImplementedError). Реальный путь: browser_actions (CDP).
3. **Селекторы** — CSS-селекторы в page_map.py хрупкие. Обновления UI Binance Square могут сломать.

## Зависимости

```
httpx>=0.27
playwright>=1.40
anthropic>=0.40
openai>=1.50
apscheduler>=3.10,<4.0
aiosqlite>=0.20
pyyaml>=6.0
pydantic>=2.5
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.23
```
