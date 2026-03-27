# Binance Square Toolkit
# Проект: личный | Статус: разработка | Обновлён: 2026-03-27
# Стандарт: standards/ | Workflow: standards/03_workflow.md

## Что это
SDK для управления активностью на Binance Square через AdsPower профили.
Софт = руки (выполняет действия). Агент = мозг (принимает решения, генерирует контент).

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
| session | src/session/ | AdsPower, CDP harvesting, browser-действия, credentials | работает |
| bapi | src/bapi/ | httpx-клиент к Binance bapi, retry, rate limit | работает |
| parser | src/parser/ | Парсинг фида, статей, ранжирование трендов | работает |
| content | src/content/ | AI-генерация текстов (инструмент агента), очередь, market data | работает |
| activity | src/activity/ | Лайки, комменты, репосты — оркестрация и таргетинг | работает |
| accounts | src/accounts/ | YAML конфиги аккаунтов, лимиты, анти-детект | работает |
| db | src/db/ | SQLite схема и инициализация (8 таблиц вкл. post_tracker) | работает |
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

## Точка входа
- Запуск: `python src/main.py`
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

## Последние изменения
- 2026-03-28: Content validator (src/content/validator.py), интеграция в SDK, supervisor агент (agents/supervisor/), post_tracker таблица в SQLite, 145 тестов зелёные
- 2026-03-27 (сессия 3): Удалён browse_and_interact() (агент сам решает), обновлён agent_api.md (все новые методы), техдолг закрыт, 106 тестов зелёные
- 2026-03-27 (сессия 2): Фикс $CASHTAGS (re.split на # и $), фикс ActionLimiter (4 бага), фикс quote_repost (селектор detail-quote-button), переписан create_article (textarea title, article-editor-main Publish, нормализация \n), добавлены take_screenshot/screenshot_chart/download_image, 87 тестов зелёные, все методы SDK протестированы live
- 2026-03-27: Создан src/sdk.py — единый фасад для агента. Добавлен collect_feed_posts(), починен парсинг текста (cookie-баннеры). Протестировано live: 5 комментов + 2 поста. docs/agent_api.md
- 2026-03-26: Реструктуризация по стандарту, добавлены секции CLAUDE.md
- 2026-03-25: CLAUDE.md приведены к шаблонам, переведены на русский
- 2026-03-24: Обновлены CSS-селекторы в page_map.py
