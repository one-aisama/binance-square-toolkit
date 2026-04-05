# Binance Square Toolkit
# Проект: личный | Статус: разработка | Обновлён: 2026-04-04
# Стандарт: standards/ | Workflow: standards/03_workflow.md

## Что это
SDK для управления активностью на Binance Square через AdsPower профили.
Софт = руки (выполняет действия). Агент = мозг (принимает решения, генерирует контент).

## КРИТИЧНО: Генерация текста
Агент — это Claude Code сессия. Он сам генерирует текст постов и комментариев.
НЕ нужен внешний API (Anthropic, OpenAI, DeepSeek) и НЕ нужен ChatGPT/Gemini в браузере.
Агент читает brief (тема, угол, контекст) + свои файлы (style.md, strategy.md) и сам пишет текст.
Готовый текст передаётся в SDK: `create_post(text=...)`, `comment_on_post(text=...)`.

## Стек
- Python 3.12
- httpx (async HTTP — парсинг, лайки)
- Playwright (CDP — посты, комменты, подписки, репосты)
- SQLite + aiosqlite (runtime data)
- AdsPower Local API (управление браузерными профилями)
- Pydantic v2 (валидация конфигов)

## Архитектура: Hybrid (httpx + Playwright CDP)
- **httpx** — парсинг, лайки, market data (быстро, без браузера)
- **Playwright CDP** — посты, комменты, репосты, подписки (требуют client-side signature или DOM)
- **Credentials** — захватываются через CDP один раз, используются httpx для парсинга/лайков

## Карта модулей
| Модуль | Путь | Назначение | Статус |
|--------|------|------------|--------|
| **sdk** | **src/sdk.py** | **Единый фасад для агента — connect, get_feed, comment, post, like, follow** | **работает** |
| session | src/session/ | AdsPower, CDP harvesting, browser-действия, credentials, web_visual (ChatGPT/Manus/Gemini image gen) | работает |
| bapi | src/bapi/ | httpx-клиент к Binance bapi, retry, rate limit | работает |
| parser | src/parser/ | Парсинг фида, статей, ранжирование трендов | работает |
| content | src/content/ | AI-генерация текстов (инструмент агента), очередь, market data | работает |
| activity | src/activity/ | Лайки, комменты, репосты — оркестрация и таргетинг | работает |
| **runtime** | **src/runtime/** | **29 модулей: guard, behavior, agent_config/plan, session_loop/context, editorial_brain, visual_pipeline/providers/prompt_builder, plan_executor/planner/auditor, media_policy, comment_coordination, news_cooldown, post_registry, persona_policy, и др.** | **работает** |
| **operator** | **src/operator/** | **Control plane: loop, scheduler, state machine, leases, recovery, persona/auditor/strategic/reflection bridges, memory_compiler** | **работает** |
| **metrics** | **src/metrics/** | **MetricsStore, Collector, Scorer — сбор и агрегация метрик** | **новый** |
| **memory** | **src/memory/** | **Compactor — генерация performance.md, relationships.md из данных** | **новый** |
| **strategy** | **src/strategy/** | **Planner, Analyst, Reviewer, FeedFilter — стратегия агента** | **новый** |
| **pipeline** | **src/pipeline.py** | **Один скрипт: collector → scorer → compactor → analyst** | **новый** |
| accounts | src/accounts/ | YAML конфиги аккаунтов, лимиты, анти-детект | работает |
| db | src/db/ | SQLite схема и инициализация (10 runtime + 4 operator таблиц) | работает |
| scheduler | src/scheduler/ | Опциональная оркестрация (агент может заменить) | опционален |
| main | src/main.py | Entry point, lifecycle | работает |

## Спецификации
- docs/specs/spec_session.md — Session (AdsPower, harvester, browser_actions)
- docs/specs/spec_bapi.md — Bapi client (httpx gateway, credentials, retry)
- docs/specs/spec_parser.md — Parser (feed, articles, trends, ranking)
- docs/specs/spec_content.md — Content (AI generation, queue, market data)
- docs/specs/spec_activity.md — Activity (likes, comments, reposts, targeting)
- docs/specs/spec_accounts.md — Accounts (config, limits, anti-detect)
- docs/design-spec.md — Общая архитектура
- docs/PROJECT_IDEA.md — Идея проекта
- docs/PROJECT_BRIEF.md — Бриф проекта

## Связи между модулями
- session -> db (CredentialStore использует SQLite)
- bapi -> session (BapiClient загружает credentials из CredentialStore)
- parser -> bapi (TrendFetcher вызывает методы BapiClient)
- content -> bapi, db (ContentPublisher использует очередь в SQLite)
- activity -> bapi, accounts (ActivityExecutor использует BapiClient + ActionLimiter)
- scheduler -> все модули (оркестрирует пайплайн)

## Стандарт кода (императивы)
- Файл: 200-300 строк, max 500. Больше — разбивай
- Функция: 20-40 строк, max 100
- Типизация на всех публичных функциях
- Именование: глагол + объект (send_email, get_user). Без utils/helpers/misc
- Один файл = одна ответственность. Если описание содержит "и" — разбивай
- Все импорты в начале файла. Нет динамических импортов
- Конфигурация только через .env + единая точка чтения
- Секреты НИКОГДА в коде

## Обработка ошибок
- Формат: ГДЕ + ЧТО + КОНТЕКСТ
- Пример: "BapiClient.like_post: 403 forbidden, post_id=12345"
- Запрещено: пустые except, "something went wrong"
- Структурированное логирование через logging, не print

## Процесс работы
- Одна задача за сессию. Ориентир: 3-5 файлов
- Коммит после каждого логического изменения
- ПЕРЕД изменением — тесты проходят. ПОСЛЕ — тесты проходят
- Если файл > 400 строк — предупреди и предложи разбить

## Выбор технологий
- ОБЯЗАТЕЛЬНО: 2-3 варианта с таблицей сравнения
- ОБЯЗАТЕЛЬНО: рекомендация с обоснованием
- ЗАПРЕЩЕНО: один вариант без альтернатив

## Субагенты
- .claude/agents/database-architect.md — схема БД, миграции
- .claude/agents/backend-engineer.md — API, серверная логика
- .claude/agents/frontend-developer.md — UI, компоненты
- .claude/agents/qa-reviewer.md — ревью по чеклисту (Read-only)
- .claude/agents/spec-reviewer.md — проверка полноты спецификации
- .claude/agents/skeptic.md — верификация архитектурных решений

## Quality Gate
- После каждого субагента: scripts/quality_gate.py
- GO = продолжаем. CONDITIONAL = продолжаем с замечаниями. NO-GO = СТОП
- Финальный: scripts/quality_gate.py --tier=all

## Handoffs
- Каждый субагент создаёт артефакт в docs/handoffs/[модуль]/
- Следующий субагент ОБЯЗАН прочитать предыдущий handoff
- Формат: docs/handoffs/[модуль]/[номер]_[что]_done.md

## Маршрутизация по проблемам
- "Браузер не запускается" -> src/session/adspower.py, config/accounts/*.yaml
- "Credentials протухли" -> src/session/harvester.py, src/session/validator.py
- "Селекторы сломались" -> src/session/page_map.py, src/session/browser_actions.py
- "Пост не публикуется" -> src/session/browser_actions.py `create_post()`
- "Лайк не работает" -> src/bapi/client.py `like_post()`
- "Парсинг пустой" -> src/parser/fetcher.py, src/bapi/endpoints.py
- "Лимиты не считаются" -> src/accounts/limiter.py
- "AI генерация падает" -> src/content/generator.py, .env
- "Агент скроллит без действий" -> agents/example_macro/prompt.md, src/strategy/planner.py
- "Guard блокирует действия" -> src/runtime/guard.py, config/accounts/*.yaml (лимиты)
- "Метрики не собираются" -> src/pipeline.py, src/metrics/collector.py
- "performance.md пустой" -> src/memory/compactor.py, src/metrics/scorer.py
- "Directive не генерируется" -> src/operator/strategic_bridge.py, agents/{id}/briefing_packet.md
- "Агент не рефлексирует" -> src/operator/reflection_bridge.py, agents/{id}/strategic_state.md
- "Briefing пустой" -> src/operator/memory_compiler.py, agents/{id}/

## Точка входа
- **Оператор (production):** `python scripts/run_operator.py --max-slots 4`
- **Статус dashboard:** `python scripts/operator_status.py`
- Подготовка: `python session_run.py --prepare --config config/active_agent.yaml`
- Выполнение: `python session_run.py --execute --config config/active_agent.yaml`
- Legacy continuous: `python session_run.py --continuous`
- Legacy scheduler: `python src/main.py`
- Pipeline (метрики): `python src/pipeline.py <agent_id> <agent_dir> [db_path]`
- Тесты: `python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py`
- Quality gate: `python scripts/quality_gate.py --tier=all`

## При сомнениях
- Спроси оператора, не угадывай
- Лучше меньше но правильно, чем много но сломано
- Если не знаешь — скажи "не знаю"

## Текущий статус
- **SDK фасад: работает** (src/sdk.py — единая точка входа для агента)
- **Все методы SDK протестированы live 2026-03-27:**
  - connect/disconnect — подключение к AdsPower профилю
  - get_feed_posts — сбор постов из рекомендованной ленты
  - get_market_data — цены, объёмы, изменение 24h
  - like_post — лайк через браузер
  - comment_on_post — коммент с обработкой Follow popup
  - create_post — текст + $CASHTAGS + chart + sentiment + картинка
  - create_article — заголовок + body + обложка
  - quote_repost — цитата поста с комментарием
  - follow_user — подписка с проверкой уже подписан
  - take_screenshot — скриншот любой страницы/элемента
  - screenshot_chart — скриншот графика Binance (16:9, по селектору)
  - download_image — скачивание картинки из интернета
- ActionLimiter: **починен** (хардкод дефолтов, col overwrite, UTC/localtime)
- **Новые Data методы:** get_trending_coins, get_crypto_news, get_article_content, get_ta_summary
- **browse_and_interact() удалён** — агент сам решает, SDK только выполняет
- **Content validator:** src/content/validator.py — валидация постов, комментов, статей, цитат (banned phrases из YAML, дубликаты, структура). Интегрирован в SDK create_post/create_article/quote_repost/comment_on_post
- **Supervisor агент:** agents/supervisor/ — мониторинг, компактификация памяти, post tracker
- **Post tracker:** таблица post_tracker в SQLite — трекинг всех постов всех агентов
- **Policy migration: завершена** (0 hardcoded agent_id веток в src/runtime/)

## Спецификации
- docs/specs/spec_session.md — Session (AdsPower, harvester, browser_actions)
- docs/specs/spec_bapi.md — Bapi client (httpx gateway, credentials, retry)
- docs/specs/spec_parser.md — Parser (feed, articles, trends, ranking)
- docs/specs/spec_content.md — Content (AI generation, queue, market data)
- docs/specs/spec_activity.md — Activity (likes, comments, reposts, targeting)
- docs/specs/spec_accounts.md — Accounts (config, limits, anti-detect)
- docs/design-spec.md — Общая архитектура
- docs/agent_api.md — **API документация для агента (SDK методы, примеры)**
- docs/PROJECT_IDEA.md — Идея проекта
- docs/PROJECT_BRIEF.md — Бриф проекта

## Архитектура агента v2 (2026-03-28)
4-слойная система по иерархии надёжности:
1. **Runtime (код):** guard.py (лимиты, circuit breaker по типам), behavior.py (человечность)
2. **Metrics (код):** collector → scorer → insights. Pipeline.py запускается cron-ом
3. **Memory (код):** compactor генерирует performance.md, relationships.md из insights
4. **Strategy (LLM):** analyst (по триггеру) → planner (каждую сессию) → reviewer (после сессии)
- Guard контролирует: дневные лимиты, cooldown, circuit breaker по типу действия, fallback-цепочки
- Feed filter убирает спам и посты с 0 лайков ДО того как агент их видит
- Planner генерирует JSON план с fallback для каждого действия
- Scorer агрегирует метрики без весов (первые 30 сессий), автогенерирует lessons
- Документ-основа: скваер_идея.md

## Архитектура v3: Policy-Driven Runtime (2026-04-01)
Один runtime framework + N policy profiles. Новый агент = YAML + persona файлы, ноль Python.

### Слои
| Слой | Что | Shared/Per-agent |
|------|-----|-----------------|
| Transport | SDK, browser_actions, AdsPower, publish | Shared |
| Coordination | topic_reservations, comment_locks, news_cooldowns (SQLite), post_registry.json | Shared |
| Runtime framework | orchestration, plan execution, guard | Shared |
| Policy | selection, framing, authoring, audit thresholds, visual | Per-agent (YAML) |
| State | checkpoint, daily_plan, status, visuals | Per-agent (files) |

### Ключевые файлы
- `src/runtime/persona_policy.py` — PersonaPolicy dataclass + YAML loader
- `config/persona_policies/{agent_id}.yaml` — все behavioral параметры агента
- `src/runtime/topic_reservation.py` — live topic lock (SQLite, reserve/confirm/release)
- Runtime файлы: `data/runtime/{agent_id}/` (checkpoint, daily_plan, status)
- Visuals: `data/generated_visuals/{agent_id}/`

### Shared SQLite = Control Plane
`data/bsq.db` — это coordination layer, НЕ per-agent state:
- `topic_reservations` — live locks на темы постов (2h TTL)
- `comment_locks` — предотвращение дублей комментов (30min TTL)
- `news_cooldowns` — cooldown на новости (30min hard block + 60min soft penalty)
- `credentials` — per account_id
- `actions_log`, `daily_stats`, `post_tracker` — partitioned by account_id
- Per-agent state живёт в файлах: `data/runtime/{agent_id}/`

### Добавление нового агента
1. `config/persona_policies/{id}.yaml` — behavioral policy
2. `config/active_agent.{id}.yaml` — runtime binding (AdsPower, symbols, visual)
3. `config/accounts/{id}.yaml` — account credentials
4. `agents/{id}/` — identity, style, strategy, prompt, visual_profile
5. Ноль изменений в Python коде

### Режимы работы агента (2026-04-03)
- `mode: "standard"` — текущее поведение (default)
- `mode: "individual"` — overlay-конфиг (market_symbols, coin_bias, targets, expires_at)
- `mode: "test"` — dry-run без SDK, план генерируется и аудитируется но не выполняется

### Координация агентов (2026-04-03)
- Comment locks — SQLite, 30min TTL, предотвращают дубли комментов
- News cooldowns — SQLite, 90min TTL (30min hard block), предотвращают news-гонки
- Territory drift — auditor отклоняет план если ВСЕ посты вне ниши агента
- Timing stagger — детерминированный offset 0-300s per agent_id через MD5

## Архитектура v4: Strategic Control (2026-04-04)
Агент — стратег, не копирайтер. Три persona-spawn'а за micro-cycle:

### Micro-cycle flow
```
1. COMPILE    → MemoryCompiler собирает briefing_packet.md из 10 слоёв памяти
2. STRATEGIZE → persona читает briefing + контекст → strategic_directive.json
3. PREPARE    → context + plan skeleton (planner использует directive)
4. AUTHOR     → persona пишет текст по плану + directive
5. AUDIT      → проверка текста
6. EXECUTE    → SDK выполняет
7. REFLECT    → persona обновляет strategic_state.md, open_loops.md, intent.md
```

### Ключевые новые файлы
- `src/operator/strategic_bridge.py` — spawn persona для стратегических решений
- `src/operator/reflection_bridge.py` — spawn persona для рефлексии после execute
- `src/operator/memory_compiler.py` — компиляция briefing_packet из 10 слоёв памяти

### Strategic directive (data/runtime/{id}/strategic_directive.json)
```json
{
  "focus_summary": "...", "preferred_coins": [...], "avoid_coins": [...],
  "post_direction": "...", "comment_direction": "...",
  "skip_families": [...], "tone": "..."
}
```

### Файлы агента (living documents)
```
agents/{id}/
  identity.md          — стабильное (пишет человек)
  style.md             — стабильное (пишет человек)
  strategic_state.md   — живое (пишет агент через reflect)
  open_loops.md        — живое (пишет агент через reflect)
  intent.md            — живое (пишет агент через reflect)
  briefing_packet.md   — компилированное (пишет MemoryCompiler)
  journal.md           — сырое (пишет автоматика)
  relationships.md     — сырое (пишет pipeline)
  lessons.md           — сырое (пишет агент + supervisor)
  performance.md       — сырое (пишет pipeline)
```

### Как directive влияет на planner
- `preferred_coins` → +80 к score символа в EditorialBrain
- `avoid_coins` → фильтрация из кандидатов
- `skip_families` → -500 к score семейства поста
- Порядок кандидатов переупорядочивается по preferred_coins

## Последние изменения
- 2026-04-04 (v4): **Strategic Control** — strategic_bridge.py (persona directs planner), reflection_bridge.py (persona updates living memory), memory_compiler.py (briefing packet from 10 layers). Micro-cycle: compile → strategize → prepare → author → audit → execute → reflect. EditorialBrain accepts strategic_directive (preferred_coins, avoid_coins, skip_families). 390 тестов зелёные
- 2026-04-04: session_run.py --prepare/--execute + continuous mode с polling. plan_io.py — save/load pending_plan.json. Continuous: plan → save → ждёт текст от агента (poll 10s) → execute. Агент-сессия пишет текст в pending_plan.json. **Operator control plane:** src/operator/ — persistent loop, slot scheduler, state machine (14 states), leases, recovery, persona/auditor bridges. scripts/run_operator.py + operator_status.py. 359 тестов зелёные
- 2026-04-03: Удалены post_author.py и web_author.py — агент сам генерирует текст (brief_context/target_text). Аудитор пропускает text-based проверки когда текста нет. Режимы (standard/individual/test), координация (comment_locks, news_cooldowns, territory drift, stagger), media_policy, RuntimeTuning (hardcoded → YAML), browser_actions split. 307 тестов зелёные
- 2026-04-01 (v3): Policy-Driven Runtime — PersonaPolicy, topic_reservation, все if agent_id ветки заменены на YAML config, per-agent state isolation (files), 249 тестов зелёные
- 2026-03-28 (v2): Agent System v2 — 4 новых модуля (runtime, metrics, memory, strategy), pipeline.py, переписан prompt.md, 159 тестов зелёные
- 2026-03-28: Content validator (src/content/validator.py), интеграция в SDK, supervisor агент (agents/supervisor/), post_tracker таблица в SQLite, 145 тестов зелёные
- 2026-03-27 (сессия 3): Удалён browse_and_interact() (агент сам решает), обновлён agent_api.md (все новые методы), техдолг закрыт, 106 тестов зелёные
- 2026-03-27 (сессия 2): Фикс $CASHTAGS (re.split на # и $), фикс ActionLimiter (4 бага), фикс quote_repost (селектор detail-quote-button), переписан create_article (textarea title, article-editor-main Publish, нормализация \n), добавлены take_screenshot/screenshot_chart/download_image, 87 тестов зелёные, все методы SDK протестированы live
- 2026-03-27: Создан src/sdk.py — единый фасад для агента. Добавлен collect_feed_posts(), починен парсинг текста (cookie-баннеры). Протестировано live: 5 комментов + 2 поста. docs/agent_api.md
- 2026-03-26: Реструктуризация по стандарту, добавлены секции CLAUDE.md
- 2026-03-25: CLAUDE.md приведены к шаблонам, переведены на русский
- 2026-03-24: Обновлены CSS-селекторы в page_map.py
