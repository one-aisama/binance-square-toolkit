# Спецификация: Модуль Content

**Путь:** `src/content/`
**Файлы:** `generator.py`, `market_data.py`, `validator.py`, `technical_analysis.py`, `news.py`

---

## Описание

Модуль Content предоставляет данные и валидацию для контент-пайплайна. Текст генерирует persona-агент (не код). Модуль обеспечивает:
- Рыночные данные (`get_market_data`) — цены, объёмы, изменения 24h
- Новости (`get_crypto_news`, `get_article_content`) — RSS + парсинг
- Технический анализ (`get_ta_summary`) — RSI, MACD, SMA/EMA
- Валидация (`validate_post`, `validate_comment`) — banned phrases, длина, дубликаты
- Legacy: `ContentGenerator` для генерации через API (не используется в v4)

Модуль НЕ решает, что публиковать и когда. `ContentGenerator` и `ContentPublisher` — это инструменты, которые вызывает агент. Агент анализирует вывод парсера, выбирает темы для каждой персоны и вызывает эти функции для генерации и постановки контента в очередь.

---

## Пользовательские сценарии

- Как агент, я хочу сгенерировать текст поста в стиле конкретной персоны с реальными рыночными данными, чтобы контент каждого аккаунта соответствовал его нише и содержал конкретные числа.
- Как агент, я хочу поставить сгенерированный контент в очередь для конкретного аккаунта с опциональным расписанием, чтобы создавать контент пакетами и публиковать позже.
- Как агент, я хочу получить текущие цены монет (цена, изменение за 24ч, объём), чтобы включить точные данные в сгенерированный контент.
- Как агент, я хочу получить ожидающий контент из очереди, чтобы опубликовать его через `browser_actions.create_post()`.
- Как агент, я хочу пометить элементы очереди как опубликованные или неудачные, чтобы отслеживать жизненный цикл контента.

---

## Модель данных

Модуль не имеет собственных таблиц. Валидация работает in-memory. Рыночные данные, новости и TA запрашиваются из внешних API через httpx.

---

## API

### ContentGenerator (`src/content/generator.py`)

```python
class ContentGenerator:
    def __init__(self, provider: str, model: str, api_key: str)
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `generate` | `(persona_style: str, persona_topics: list[str], topic: dict, market_data: dict) -> str` | Сгенерированный текст поста |

**Провайдеры:** `"anthropic"` (Claude API) и `"openai"` (OpenAI API). Провайдер выбирается при создании экземпляра.

**Структура промпта:**
- Системный промпт: стиль персоны, тематические области, строгие правила написания (без AI-клише, разговорный тон, $CASHTAGS, и т.д.)
- Пользовательский промпт: название темы + трендовые хэштеги + связанные монеты + текущие рыночные данные (цены, изменение за 24ч)

Системный промпт содержит правила из `config/content_rules.yaml` inline (не загружаются из файла — правила вшиты в строку промпта).

---

### ContentPublisher (`src/content/publisher.py`)

```python
class ContentPublisher:
    def __init__(self, client: BapiClient, db_path: str)
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `publish` | `(text: str, hashtags: list[str] \| None = None) -> dict` | Вызывает `BapiClient.create_post()` — сейчас бросает `NotImplementedError` |
| `queue_content` | `(account_id: str, text: str, hashtags: list[str] \| None, topic: str, meta: dict \| None, scheduled_at: str \| None) -> int` | ID строки очереди |
| `get_pending` | `(account_id: str) -> list[dict]` | Ожидающие элементы где `scheduled_at <= now()` |
| `mark_published` | `(queue_id: int, post_id: str = "") -> None` | Устанавливает status='published' |
| `mark_failed` | `(queue_id: int, error: str) -> None` | Устанавливает status='failed' |

**Примечание:** `publish()` — это stub. Фактическая публикация идёт через `session.browser_actions.create_post()`, потому что Binance требует клиентский nonce + signature. Publisher управляет только очередью.

---

### get_market_data (`src/content/market_data.py`)

```python
async def get_market_data(symbols: list[str]) -> dict[str, dict[str, Any]]
```

Загружает данные тикера за 24ч с публичного API Binance (`https://api.binance.com/api/v3/ticker/24hr`) для каждого символа (например, `["BTC", "ETH"]`). Добавляет `USDT` к каждому символу для API-вызова.

**Возвращает:**
```python
{
    "BTC": {"price": 67500.0, "change_24h": 2.3, "volume": 15000.0},
    "ETH": {"price": 3800.0, "change_24h": -1.2, "volume": 8000.0},
}
```

Загружает все символы параллельно через `asyncio.gather()`. Неудачные загрузки логируются и исключаются из результатов.

---

## Бизнес-логика

### Актуальный пайплайн (v3, runtime)
```
SessionContextBuilder собирает контекст (market, news, TA, feed)
  -> DeterministicPlanGenerator генерирует план (brief_context, без текста)
     -> EditorialBrain выбирает family + brief (coin, angle, hooks)
  -> PlanAuditor валидирует (стиль, overlap, координация)
  -> Агент (Claude Code сессия) пишет текст постов и комментов
  -> PlanExecutor исполняет через SDK
     -> sdk.create_post(text, coin, sentiment, image_path)
     -> browser_actions.create_post(page=persistent_page, ...)
```

В этом пайплайне `ContentGenerator` и `ContentPublisher` **не используются**. Текст генерирует агент (Claude Code сессия) сам, используя brief_context из плана и свои файлы (style.md, strategy.md). Рыночные данные (`get_market_data`, `get_crypto_news`, `get_ta_summary`) используются `SessionContextBuilder` для построения контекста.

### Legacy пайплайн (scheduler)
> Используется только в `src/scheduler/scheduler.py`. Не активен в текущем deployment.

```
Агент решает создать пост для аккаунта X
  -> ContentGenerator.generate(style, topics, topic, market_data)
  -> ContentPublisher.queue_content(account_id, text, ...)
  -> ContentPublisher.get_pending(account_id)
  -> browser_actions.create_post(ws, text, coin, sentiment)
  -> ContentPublisher.mark_published(queue_id, post_id)
```

### Построение промпта
Системный промпт включает:
- Стиль и темы персоны
- Правила написания (разговорный стиль, без AI-клише, $CASHTAGS, конкретные числа)
- Список запрещённых фраз (17 фраз)
- Хорошие и плохие примеры
- Рекомендации по длине: 100-280 символов для коротких заметок, до 1000 для аналитики

Пользовательский промпт включает:
- Название темы
- До 5 трендовых хэштегов (с префиксом #)
- До 5 связанных монет (с префиксом $)
- Текущие рыночные данные в формате `$COIN: $price (+/-change% 24h)`

### Расписание очереди
Элементы с `scheduled_at = NULL` сразу доступны для публикации. Элементы с будущим `scheduled_at` становятся доступными после наступления времени. `get_pending()` проверяет `scheduled_at <= utcnow()`.

---

## Крайние случаи

| Ситуация | Ожидаемое поведение |
|----------|---------------------|
| AI API возвращает пустой ответ | `generate()` возвращает пустую строку — агент должен проверить и повторить или пропустить |
| AI API rate limited или недоступен | Исключение пробрасывается вызывающему коду (агент управляет логикой retry) |
| `market_data` — пустой dict | Пользовательский промпт пропускает секцию рынка — AI генерирует без конкретных цен |
| Символ не найден на Binance | `_fetch_ticker` бросает исключение, логируется как warning, символ исключается из результатов |
| В очереди нет ожидающих элементов | `get_pending()` возвращает пустой список |
| Вызван `publish()` | Бросает `NotImplementedError` — используйте `browser_actions.create_post()` |
| Дублирующийся контент в очереди | Дедупликации нет — один и тот же текст можно поставить в очередь несколько раз |

---

## Приоритет и зависимости

- **Приоритет:** Высокий
- **Зависит от:** `src/bapi/client.py` (market_data, news используют httpx)
- **Блокирует:** Пайплайн публикации в планировщике (контент должен быть сгенерирован прежде чем его можно опубликовать)

---

## Дополнительные модули (добавлены в v3)

### news.py (151 строк) — Крипто-новости из RSS

```python
async def get_crypto_news(limit: int = 10) -> list[dict]
async def get_article_content(url: str) -> dict
```

Источники RSS: CoinDesk, CoinTelegraph, Decrypt. Ручной парсинг XML (regex, без XML-библиотек).

**Возвращает:** `[{"title": str, "source": str, "url": str, "published_at": str, "summary": str}]`

`get_article_content()` скрейпит полный текст статьи по URL. Фильтрует шум: таблицы цен, SVG/CSS, навигация.

### technical_analysis.py (214 строк) — Технический анализ

```python
async def get_ta_summary(symbol: str, timeframe: str = "1d") -> dict
```

Pure Python реализация без внешних TA-библиотек:
- SMA, EMA (произвольный период)
- RSI (14 периодов)
- MACD + signal line + cross detection
- Support / Resistance (по recent highs/lows)

Данные: 200 свечей с Binance API (`/api/v3/klines`). Минимум 50 свечей для расчёта.

### validator.py (392 строк) — Валидация контента

Правила валидации перед публикацией:

| Функция | Что проверяет |
|---------|---------------|
| `validate_post(text, recent_posts)` | banned phrases, min 2 абзаца, min 80 chars, дубликаты (порог 0.65), topic repeat |
| `validate_comment(text)` | 5-500 chars, нет generic комментов, banned phrases |
| `validate_article(title, body)` | title 10-200 chars, body 300+ chars, 3+ абзацев |
| `validate_quote(comment)` | как пост: 2 абзаца, 80+ chars |
| `verify_prices(text, market_data)` | цены в тексте в пределах ±10% от реальных |

Banned phrases загружаются из `config/content_rules.yaml` с fallback на хардкод.
Интегрирован в SDK: `create_post`, `create_article`, `quote_repost`, `comment_on_post`.
