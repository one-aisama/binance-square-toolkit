# Спецификация: Модуль Bapi Client

**Путь:** `src/bapi/`
**Файлы:** `client.py`, `endpoints.py`, `models.py`

---

## Описание

Модуль Bapi — единый HTTP-шлюз между тулкитом и внутренним bapi API Binance. Он инжектирует захваченные credentials (cookies + headers) в каждый запрос, обеспечивает rate limit на уровне аккаунта, делает retry при транзиентных ошибках и автоматически инвалидирует credentials при ошибках аутентификации. Также предоставляет типизированные Pydantic-модели для ответов bapi и центральный файл констант со всеми известными путями эндпоинтов.

---

## Пользовательские сценарии

- Как агент, я хочу вызывать `get_feed_recommend()`, `get_top_articles()`, `get_fear_greed()` и `get_hot_hashtags()` без ручного управления HTTP-заголовками, чтобы сосредоточиться на обработке данных.
- Как агент, я хочу, чтобы bapi-запросы автоматически использовали правильные credentials для конкретного аккаунта, чтобы работать с несколькими аккаунтами без путаницы.
- Как агент, я хочу, чтобы неудачные запросы из-за rate limiting или серверных ошибок автоматически повторялись, чтобы транзиентные сбои не прерывали сессию.
- Как агент, я хочу, чтобы при ошибках аутентификации (HTTP 401/403) credentials немедленно инвалидировались и возвращалась понятная ошибка, чтобы я знал, что нужно перезахватить credentials, а не продолжать повторять запросы.
- Как агент, я хочу иметь центральный файл констант эндпоинтов, чтобы никогда не хардкодить пути в бизнес-логике.

---

## Модель данных

Собственных таблиц нет. `BapiClient` читает из таблицы `credentials` через `CredentialStore`. Сам ничего не записывает.

Pydantic-модели в `src/bapi/models.py`:

### BapiResponse
```python
class BapiResponse(BaseModel):
    code: str = ""          # "000000" = success
    message: str | None = None
    data: Any = None
    success: bool = False

    @property
    def is_ok(self) -> bool: ...  # code == "000000" or success == True
```

### FeedPost
```python
class FeedPost(BaseModel):
    post_id: str = ""
    author_name: str = ""
    author_role: str = ""
    card_type: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    hashtags: list[str] = []
    trading_pairs: list[str] = []
    is_ai_created: bool = False
    created_at: int = 0     # Unix timestamp ms
    text_preview: str = ""
```

---

## API

### BapiClient (`src/bapi/client.py`)

```python
class BapiClient:
    def __init__(
        self,
        account_id: str,
        credential_store: CredentialStore,
        base_url: str = "https://www.binance.com",
        rate_limit_rpm: int = 30,
        retry_attempts: int = 3,
        retry_backoff: float = 1.0,
    )
```

`rate_limit_rpm` преобразуется в `min_interval = 60 / rate_limit_rpm` секунд между запросами.

#### Низкоуровневые методы

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `get` | `(path: str, params: dict \| None = None) -> dict` | Сырой dict ответа bapi |
| `post` | `(path: str, data: dict \| None = None) -> dict` | Сырой dict ответа bapi |

Оба делегируют в `_request(method, path, params, json_data)`, который:
1. Применяет rate limiting (засыпает, если `elapsed < min_interval`)
2. Загружает credentials через `CredentialStore.load(account_id)`
3. Собирает заголовки: `content-type: application/json`, сериализованная строка `cookie`, затем все захваченные заголовки
4. Выполняет запрос через `httpx.AsyncClient`, timeout=30s
5. При HTTP 401/403: вызывает `CredentialStore.invalidate()`, бросает `BapiCredentialError`
6. При HTTP 429/500/502/503: retry до `retry_attempts` с экспоненциальным backoff (`retry_backoff * 2^(attempt-1)`)
7. При `httpx.TimeoutException` / `httpx.NetworkError`: retry аналогично

#### Удобные методы парсинга

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `get_feed_recommend` | `(page: int = 1, page_size: int = 20) -> list[dict]` | Посты из `data.vos` или `data.list` |
| `get_top_articles` | `(page: int = 1, page_size: int = 20) -> list[dict]` | Статьи из `data.vos` или `data.list` |
| `get_fear_greed` | `() -> dict` | Данные страха/жадности из `data` |
| `get_hot_hashtags` | `() -> list[dict]` | Список хэштегов из `data` |
| `like_post` | `(post_id: str, card_type: str = "BUZZ_SHORT") -> dict` | Сырой ответ bapi |

#### Stub-методы (не реализованы)

| Метод | Бросает |
|-------|---------|
| `create_post(text, hashtags)` | `NotImplementedError` — используйте `browser_actions.create_post()` |
| `comment_post(post_id, text)` | `NotImplementedError` — используйте `browser_actions.comment_on_post()` |
| `repost(post_id)` | `NotImplementedError` — используйте `browser_actions.repost()` |

---

### Endpoints (`src/bapi/endpoints.py`)

| Константа | Путь | Метод |
|-----------|------|-------|
| `FEED_RECOMMEND` | `/bapi/composite/v9/friendly/pgc/feed/feed-recommend/list` | POST |
| `TOP_ARTICLES` | `/bapi/composite/v3/friendly/pgc/content/article/list` | GET |
| `FEAR_GREED` | `/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched` | POST |
| `HOT_HASHTAGS` | `/bapi/composite/v2/public/pgc/hashtag/hot-list` | GET |
| `CONTENT_PRE_CHECK` | `/bapi/composite/v1/private/pgc/content/pre-check` | POST |
| `CREATOR_CONTENT_LIST` | `/bapi/composite/v5/private/pgc/creator/content/list` | POST |
| `DRAFT_COUNT` | `/bapi/composite/v1/private/pgc/content/draft/count` | POST |
| `USER_PROFILE` | `/bapi/composite/v4/private/pgc/user` | GET |
| `SUGGESTED_CREATORS` | `/bapi/composite/v1/friendly/pgc/suggested/creator/list` | POST |
| `LIKE_POST` | `/bapi/composite/v1/private/pgc/content/like` | POST |

Эндпоинты для комментариев и репостов пока не обнаружены.

---

## Бизнес-логика

### Тело запроса для FEED_RECOMMEND
Должно содержать `scene: "web-homepage"` и `contentIds: []` в теле POST-запроса, иначе эндпоинт возвращает пустые результаты. Данные ответа находятся в `data.vos`, не в `data.list`.

### Fear & Greed — это POST, не GET
`FEAR_GREED` требует `POST` с пустым JSON-телом `{}`. `GET`-запрос возвращает ошибку.

### Тело запроса лайка
`LIKE_POST` требует `{"id": "<post_id>", "cardType": "BUZZ_SHORT"}`. Поле `cardType` обязательно.

### Заголовки fvideo обязательны
Без `fvideo-id` и `fvideo-token` в заголовках запроса bapi возвращает `data: null` даже при HTTP 200. Они должны присутствовать в захваченных заголовках.

### Поток инъекции credentials
```
_request() вызван
  → CredentialStore.load(account_id)
  → если None → бросить BapiCredentialError
  → собрать строку cookie из dict cookies
  → скопировать все захваченные заголовки (кроме "cookie") в request_headers
  → выполнить httpx-запрос
  → если 401/403 → CredentialStore.invalidate() → бросить BapiCredentialError
  → если retryable статус → retry с backoff
  → вернуть распарсенный JSON dict
```

### Rate limiting
`_last_request_time` — переменная экземпляра. Каждый запрос проверяет `time.monotonic() - _last_request_time` и засыпает, если интервал не прошёл. Это на уровне экземпляра (на аккаунт), не глобально.

---

## Крайние случаи

| Ситуация | Ожидаемое поведение |
|----------|---------------------|
| `CredentialStore.load()` возвращает None | `BapiCredentialError` бросается сразу, HTTP-запрос не выполняется |
| HTTP 401 или 403 | Credentials инвалидируются через `CredentialStore.invalidate()`, бросается `BapiCredentialError` |
| HTTP 429 (rate limit от Binance) | Retry до `retry_attempts` с экспоненциальным backoff, затем бросается `BapiRequestError` |
| HTTP 500/502/503 | Такое же поведение retry как при 429 |
| Таймаут сети | `BapiRequestError` после `retry_attempts` повторов |
| `data.vos` и `data.list` отсутствуют в ответе | Возвращает пустой список `[]` |
| `get_fear_greed` возвращает не-dict `data` | Возвращает пустой dict `{}` |
| `get_hot_hashtags` возвращает не-list `data` | Возвращает пустой список `[]` |
| `like_post` вызван с несуществующим post_id | Bapi возвращает код ошибки в теле ответа; сырой dict возвращается, исключения нет |

---

## Приоритет и зависимости

- **Приоритет:** Высокий
- **Зависит от:** `src/session/credential_store.py` (должен быть инициализирован до создания `BapiClient`), `src/db/` (SQLite-схема для таблицы credentials)
- **Блокирует:** `src/parser/fetcher.py` (TrendFetcher), `src/activity/executor.py` (like_post)
