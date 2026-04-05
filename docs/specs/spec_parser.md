# Спецификация: Модуль Parser

**Путь:** `src/parser/`
**Файлы:** `fetcher.py`, `aggregator.py`, `models.py`

---

## Описание

Модуль Parser забирает сырой контент с Binance Square (посты и статьи через bapi, индекс страха/жадности, горячие хэштеги), нормализует его в типизированные dataclass-ы и ранжирует трендовые темы по engagement score. Его выходные данные — основной источник информации для пайплайна генерации контента: он показывает агенту, о чём говорит сообщество и какие темы набирают наибольшую тягу.

---

## Пользовательские сценарии

- Как агент, я хочу получить все свежие посты из ленты и статьи одним вызовом, чтобы иметь единый список контента для анализа.
- Как агент, я хочу, чтобы посты были дедуплицированы по post_id, чтобы не обрабатывать один и тот же контент дважды.
- Как агент, я хочу, чтобы трендовые хэштеги были ранжированы по engagement score, чтобы выбирать тему с наибольшим сигналом для генерации контента.
- Как агент, я хочу, чтобы индекс страха/жадности и популярные монеты загружались вместе с постами, чтобы учитывать рыночный сентимент при создании контента.
- Как агент, я хочу, чтобы сырые данные bapi были нормализованы в типизированные dataclass-ы, чтобы нижестоящий код не парсил сырые словари.

---

## Модель данных

### ParsedPost (`src/parser/models.py`)

```python
@dataclass
class ParsedPost:
    post_id: str
    author_name: str = ""
    author_id: str = ""
    card_type: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    hashtags: list[str] = field(default_factory=list)
    trading_pairs: list[str] = field(default_factory=list)
    is_ai_created: bool = False
    created_at: int = 0   # Unix timestamp milliseconds
    text_preview: str = ""  # Truncated to 200 chars
```

### Topic (`src/parser/models.py`)

```python
@dataclass
class Topic:
    name: str
    hashtags: list[str] = field(default_factory=list)
    coins: list[str] = field(default_factory=list)
    engagement_score: float = 0.0
    post_count: int = 0
```

### Таблицы БД (записываются планировщиком/оркестратором, не самим модулем)

```sql
CREATE TABLE IF NOT EXISTS parsed_posts (
    id INTEGER PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    author_name TEXT,
    card_type TEXT,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    share_count INTEGER,
    hashtags TEXT,         -- JSON array
    trading_pairs TEXT,    -- JSON array
    is_ai_created BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cycle_id, post_id)
);

CREATE TABLE IF NOT EXISTS parsed_trends (
    id INTEGER PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    topics TEXT NOT NULL,          -- JSON array of Topic objects
    fear_greed_index INTEGER,
    popular_coins TEXT,            -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Модуль парсера возвращает Python-объекты; персистенция — ответственность вызывающего кода.

---

## API

### TrendFetcher (`src/parser/fetcher.py`)

```python
class TrendFetcher:
    def __init__(self, client: BapiClient)
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `fetch_all` | `(article_pages: int = 5, feed_pages: int = 5) -> list[ParsedPost]` | Дедуплицированный список ParsedPost |
| `fetch_fear_greed` | `() -> dict` | Сырой dict из `BapiClient.get_fear_greed()` |
| `fetch_hot_hashtags` | `() -> list[dict]` | Сырой список из `BapiClient.get_hot_hashtags()` |
| `_fetch_articles` | `(pages: int = 5) -> list[ParsedPost]` | Приватный — загружает топ-статьи по N страницам |
| `_fetch_feed` | `(pages: int = 5) -> list[ParsedPost]` | Приватный — загружает рекомендованную ленту по N страницам |

`fetch_all` вызывает `_fetch_articles` и `_fetch_feed`, объединяет результаты, дедуплицирует по `post_id` (статьи первые, лента вторая — при коллизии статьи имеют приоритет), и возвращает объединённый список.

---

### _extract_post (`src/parser/fetcher.py`)

```python
def _extract_post(raw: dict[str, Any]) -> ParsedPost | None
```

Функция уровня модуля. Нормализует сырой dict поста из bapi в `ParsedPost`. Возвращает `None`, если `post_id` не удаётся извлечь.

Пути разрешения полей (пробует несколько ключей, т.к. структура ответа bapi отличается между лентой и статьями):

| Поле ParsedPost | Порядок поиска |
|-----------------|----------------|
| `post_id` | `contentDetail.id` → `contentDetail.contentId` |
| `author_name` | `contentDetail.authorName` → `contentDetail.nickname` |
| `author_id` | `contentDetail.authorId` → `contentDetail.userId` |
| `card_type` | `contentDetail.cardType` → `contentDetail.type` |
| `text_preview` | `contentDetail.title` → `contentDetail.text` (обрезается до 200) |
| `hashtags` | `contentDetail.hashtagList[].name` или `hashtagName` или raw str |
| `trading_pairs` | `contentDetail.tradingPairs[].symbol` или `name`; или `contentDetail.cashtagList` |

Если в сыром dict нет обёртки `contentDetail`, используется сам dict.

---

### rank_topics / compute_engagement (`src/parser/aggregator.py`)

```python
def compute_engagement(post: ParsedPost) -> float
```
Формула: `view_count * 0.3 + like_count * 0.5 + comment_count * 0.2`

```python
def rank_topics(posts: list[ParsedPost], top_n: int = 10) -> list[Topic]
```

Группирует посты по хэштегу (нормализованному: lowercase, `#` убран). Накапливает `engagement_score` и `post_count` для каждого хэштега. Собирает `trading_pairs` для каждого хэштега в `set`. Сортирует по суммарному engagement по убыванию. Возвращает топ `top_n` Topic-ов.

Посты без хэштегов группируются под `"_untagged"` внутренне и исключаются из возвращаемого списка.

---

## Бизнес-логика

### Пагинация
`_fetch_articles` и `_fetch_feed` итерируют страницы от 1 до N включительно. Ошибка на странице (любое исключение от BapiClient) логируется как warning, итерация продолжается — возвращаются частичные данные вместо полного прерывания.

### Дедупликация
В `fetch_all`: после конкатенации статей + постов из ленты используется `seen: set[str]` по значениям `post_id`. Побеждает первое вхождение. Поскольку статьи идут первыми в конкатенации, они имеют приоритет над дубликатами из ленты.

### Веса engagement score
```
view_count   × 0.3  (охват)
like_count   × 0.5  (прямое вовлечение — наибольший вес)
comment_count × 0.2  (качество обсуждения)
```
`share_count` не включён в формулу (присутствует в модели, но не используется в скоринге).

### Сбор монет для темы
Каждая монета из `post.trading_pairs` добавляется в `set` для каждого хэштега этого поста. Итоговый `Topic.coins` — это `sorted(set)` для детерминированного вывода.

### Нормализация хэштегов
`tag.lower().strip("#")` — убирает ведущий `#` и приводит к lowercase. Пустые теги после очистки пропускаются.

---

## Крайние случаи

| Ситуация | Ожидаемое поведение |
|----------|---------------------|
| BapiClient возвращает пустой список для страницы | Страница пропускается молча, пробуется следующая |
| `_extract_post` не может найти post_id | Возвращает `None`, пост отбрасывается молча |
| Все страницы упали (сеть недоступна) | `fetch_all` возвращает пустой список `[]` |
| Пост без хэштегов | Считается в `"_untagged"` внутренне, исключается из вывода `rank_topics` |
| `rank_topics([])` | Сразу возвращает `[]` |
| Два поста с одинаковым post_id | Сохраняется первое вхождение (статьи перед лентой) |
| `top_n` больше количества уникальных хэштегов | Возвращаются все доступные темы (меньше чем `top_n`) |
| Источник `text_preview` слишком длинный | Обрезается до 200 символов через срез `[:200]` |

---

## Приоритет и зависимости

- **Приоритет:** Высокий
- **Зависит от:** `src/bapi/client.py` (BapiClient должен быть создан с валидными credentials перед парсингом)
- **Блокирует:** `src/content/generator.py` (нужны Topic + market_data для генерации постов), `src/activity/target_selector.py` (нужен список ParsedPost для выбора целей)
