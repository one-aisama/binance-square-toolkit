# Спецификация: Модуль Content

**Путь:** `src/content/`
**Файлы:** `generator.py`, `publisher.py`, `market_data.py`

---

## Описание

Модуль Content предоставляет инструменты для AI-генерации текстов и управления очередью контента. Агент вызывает `ContentGenerator.generate()` для создания текста поста в стиле конкретной персоны, затем `ContentPublisher.queue_content()` для сохранения в SQLite для последующей публикации. `get_market_data()` загружает реальные цены монет с публичного API Binance, чтобы агент мог вставить конкретные числа в контент.

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

### Таблица очереди контента (определена в `src/db/models.py`)

```sql
CREATE TABLE IF NOT EXISTS content_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    text TEXT NOT NULL,
    hashtags TEXT,              -- JSON array
    topic TEXT,
    generation_meta TEXT,       -- JSON dict with generation params
    scheduled_at TEXT,          -- ISO timestamp, NULL = publish immediately
    status TEXT DEFAULT 'pending',  -- pending | published | failed
    post_id TEXT,               -- Binance post ID after publishing
    published_at TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Дополнительных таблиц нет. Модуль читает/пишет только `content_queue`.

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

### Пайплайн генерации контента (управляется агентом)
```
Агент решает создать пост для аккаунта X
  -> Агент выбирает тему из вывода парсера
  -> Агент вызывает get_market_data(coins) для реальных цен
  -> Агент вызывает ContentGenerator.generate(style, topics, topic, market_data)
  -> Агент вызывает ContentPublisher.queue_content(account_id, text, ...)
  -> Агент вызывает ContentPublisher.get_pending(account_id)
  -> Агент вызывает browser_actions.create_post(ws, text, coin, sentiment)
  -> Агент вызывает ContentPublisher.mark_published(queue_id, post_id)
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
- **Зависит от:** `src/bapi/client.py` (ContentPublisher хранит ссылку на BapiClient, хотя publish — stub), `src/db/` (таблица content_queue)
- **Блокирует:** Пайплайн публикации в планировщике (контент должен быть сгенерирован прежде чем его можно опубликовать)
