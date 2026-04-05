# Спецификация: Runtime Framework
Статус: АКТУАЛЬНО (v3, 2026-04-03)

## Обзор

Runtime framework (`src/runtime/`) — автономный цикл агента. 25+ модулей, ~5800 строк кода.

Главный цикл: context → plan → audit → execute → commit → sleep → repeat.

Спецификации transport-слоя: spec_session.md, spec_bapi.md, spec_content.md, spec_activity.md.
Спецификация данных: spec_db.md.
Data pipeline: src/metrics/, src/memory/, src/strategy/, src/pipeline.py.

## Оркестрация

### session_loop.py — ContinuousSessionRunner
Главный цикл агента с checkpoint recovery.

**Контракт:**
- Загружает agent_config, persona_policy, daily_plan, checkpoint
- Цикл: collect context → build directive → generate plan → audit → execute → commit
- Checkpoint сохраняется после генерации плана; при рестарте — resume с точки остановки
- Graceful shutdown через stop file или max cycles/actions
- SessionReviewer вызывается после каждого цикла

**Зависимости:** все модули runtime, SDK, DB

### main.py — Глобальный оркестратор
CLI entry point. Загружает settings, инициализирует DB, запускает CycleScheduler для всех аккаунтов.

## Планирование

### deterministic_planner.py — DeterministicPlanGenerator
Генерация конкретного плана действий **без вызова LLM**.

**Контракт:**
- Вход: SessionContext, CycleDirective, PersonaPolicy, recent posts, other agent posts
- Выход: AgentPlan (JSON список действий: comment, like, follow, post)
- Комменты: tiered target selection (strong/fallback) по policy rules
- Посты: EditorialBrain (brief) → агент пишет текст сам (brief_context)
- 8 вариаций при audit feedback (RevisionHints)

**Зависимости:** EditorialBrain, TopicReservation, CommentCoordination, NewsCooldown, PlatformLimits

### editorial_brain.py — EditorialBrain
Выбор post family и генерация EditorialBrief.

**Контракт:**
- Family: market_chart, news_reaction, editorial_note
- Scoring: доступность данных + policy adjustments + overlap penalty
- Brief: coin, angle, structure, hooks, insights, closes, visual metadata
- Template resolution: {coin}, {symbol}, {title_trimmed}, {author}, {snippet}

**Зависимости:** PersonaPolicy, ContentFingerprint

### Текст генерируется агентом (не кодом)
Planner возвращает `brief_context` (для постов) и `target_text` (для комментов) вместо готового текста.
Агент (Claude Code сессия) сам пишет текст перед выполнением, заполняя `action.text`.
Executor проверяет наличие text перед вызовом SDK.

## Аудит

### plan_auditor.py — PlanAuditor
Детерминированная проверка плана после генерации. 9 слоёв:

1. **Stage rules** — enforce post-only, reply limits, min follows, max posts
2. **Text rules** — нет trailing period, структура абзацев
3. **Comment diversity** — similarity check (порог 0.82) между комментами в плане
4. **Agent style** — длина поста, количество абзацев, coin restrictions по family
5. **Media policy** — правила прикрепления картинок
6. **Self novelty** — overlap с собственными недавними постами
7. **Overlap** — overlap с постами других агентов
8. **Reservation conflicts** — конфликты topic lock
9. **Territory drift** — отклонение всех постов от ниши агента

**Контракт:**
- Вход: AgentPlan, PersonaPolicy, recent posts, other posts, reservations
- Выход: AuditResult (valid/invalid + список AuditIssue)
- При invalid: RevisionHints передаются обратно в planner

## Исполнение

### plan_executor.py — PlanExecutor
Последовательное исполнение плана через SDK.

**Контракт:**
- Вход: AgentPlan, SDK, start_index (для resume)
- Dispatch: comment → sdk.comment_on_post(), like → sdk.like_post(), follow → sdk.follow_user(), post → sdk.create_post(), quote_repost → sdk.quote_repost()
- VisualPipeline для разрешения картинок перед post
- Human delay (3-15s) между действиями
- Progress callback после каждого действия

**Зависимости:** SDK, VisualPipeline

### behavior.py — человечное поведение
- `warm_up()` — скролл страницы перед действиями
- `mouse_move_to()` — плавное движение мыши
- `delay_between_actions()` — weighted random: 60% light, 25% medium, 10% heavy, 5% quick
- `idle_visit()` — загрузить пост, поскроллить, уйти (25% шанс)

## Визуалы

### visual_pipeline.py — VisualPipeline
Разрешение или генерация картинок для постов.

**Контракт:**
- Dispatch по типу: image_path, chart_capture, page_capture, AI visual kinds
- AI visual kinds: market_visual, news_visual, meme_visual, personal_visual, article_cover
- Fallback: text card (PIL, 1600x800) если AI provider недоступен
- Выход: ResolvedVisual (path, kind, signature)

**Зависимости:** VisualPromptBuilder, VisualProviders, ImageNormalizer, SDK

### visual_prompt_builder.py — промпты для AI-визуалов
Сборка LLM-промпта: agent identity + action context + style guide.

### visual_providers.py — провайдеры визуалов
Factory: build_visual_provider() по provider_url из agent config.

### image_normalizer.py — нормализация
PIL resize/padding в landscape формат.

## Политики и конфигурация

### persona_policy.py — PersonaPolicy
Загрузка YAML → frozen dataclasses.

**Ключевые структуры:**
- CoinBias — preferred/excluded coins, bonus/penalty
- MarketAngleRules — выбор angle по price change + coin type
- StageConfig — target actions per stage (comments, likes, posts, follows)
- StageSelectionRule — ordered conditions (reply_limited, bootstrap, default)
- AuditStyle — post length, paragraph count, coin restrictions
- CommentStanceConfig — stance selection mode
- FeedScoring — keyword bonuses/penalties
- CommentTierRule — tiered comment targeting

### cycle_policy.py — CycleDirective
Stage selection + sleep timing на основе daily progress.

**Контракт:**
- `build_cycle_directive()` → CycleDirective (targets, stage, style/source notes)
- `choose_sleep_seconds()` → int (следующий цикл)
- Overflow: если daily plan выполнен → переключение на overflow stage

### agent_config.py — ActiveAgentConfig
Runtime binding: agent_id, AdsPower profile, feed tab, action limits, session minimums, market symbols, visual config, cycle intervals, timezone.

## State management

### daily_plan.py — дневные цели
Per-agent tracking: targets (like, comment, post) vs completed. Timezone-aware.

### platform_limits.py — лимиты платформы
Reply limit tracking с 7-дневным окном. Автоматическое снятие при истечении.

### post_registry.py — реестр постов
72-часовое окно. Метаданные: text, coin, angle, chart_symbol, visual_type, post_family, opening_signature, format_signature. Multi-agent overlap avoidance.

### topic_reservation.py — блокировка тем
SQLite-based. Key: "{COIN}:{angle}:{md5(source)[:8]}". TTL 2 часа. reserve → confirm/release.

### execution_checkpoint.py — чекпоинты
Persist/load execution state для resumable cycles. JSON в data/runtime/{agent_id}/.

## Безопасность

### guard.py — ActionGuard
Программные guardrails.

**5 слоёв:**
1. Global stop: 3+ action types circuit-broken → SESSION_OVER
2. Session limit: max 80 actions (configurable)
3. Circuit breaker: 2 consecutive failures → action type blocked
4. Daily limits: per action type (из ActionLimiter)
5. Cooldowns: post=60s, comment=30s, like=15s, follow=30s, repost=60s

**Verdict:** ALLOW / WAIT / DENIED / SESSION_OVER

### media_policy.py
Стабы для решений о прикреплении картинок. Требует реализации.

## Контент-утилиты

### content_fingerprint.py
Извлечение семантических сигналов из текста.

**Функции:**
- `extract_primary_coin()` — primary ticker из текста
- `infer_angle()` — macro, rotation, ta, psychology, security, education, general
- `similarity_ratio()` — SequenceMatcher (0-1)
- `opening_signature()` — первые 50 символов
- `format_signature()` — нормализованная структура абзацев
- `add_cashtags()` — inject $ перед тикерами

## Data pipeline (отдельные модули)

### metrics/ (src/metrics/)
- **store.py** — 5 SQLite таблиц: agent_actions, outcomes, insights, profile_snapshots, session_stats
- **collector.py** — отложенный сбор outcomes (6h+ после действия): views, likes, comments, author_reply_rate
- **scorer.py** — агрегация insights по dimensions (author, content_type, hour, topic, has_image) + auto-lessons

### memory/ (src/memory/)
- **compactor.py** — генерация performance.md и relationships.md из insights. Архивация journal (max 5 сессий). Cleanup lessons (TTL 30 дней).

### strategy/ (src/strategy/)
- **feed_filter.py** — спам-фильтр: keywords, token promo patterns, min chars, min likes
- **planner.py** — bootstrap plan (детерминированный) + prepare_context() для агента
- **analyst.py** — обновление strategy.md по накопленным данным (каждые 7 сессий)
- **reviewer.py** — session stats + journal append + lessons preparation

### pipeline.py
Оркестрация: collector → scorer → compactor → [analyst].
CLI: `python src/pipeline.py <agent_id> <agent_dir> [db_path]`
Каждый шаг в try/except — один сбой не блокирует остальные.
