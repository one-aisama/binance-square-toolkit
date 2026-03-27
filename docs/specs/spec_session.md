# Спецификация: Модуль Session

**Путь:** `src/session/`
**Файлы:** `adspower.py`, `harvester.py`, `credential_store.py`, `validator.py`, `browser_actions.py`, `page_map.py`

---

## Описание

Модуль Session управляет всей браузерной инфраструктурой: запуск и остановка AdsPower-профилей через локальный API, захват credentials сессии Binance (cookies + headers) через Playwright CDP, хранение credentials в SQLite, валидация их живости, и выполнение браузерных действий (публикация, комментирование, репост, подписка), которые невозможно выполнить через обычный HTTP, потому что Binance требует клиентскую подпись (nonce + signature) и DOM-ввод для создания контента.

---

## Пользовательские сценарии

- Как агент, я хочу запустить AdsPower-профиль для конкретного аккаунта, чтобы получить WebSocket-эндпоинт для подключения Playwright.
- Как агент, я хочу захватить cookies и bapi-заголовки из живой браузерной сессии, чтобы BapiClient мог делать аутентифицированные httpx-запросы без браузера.
- Как агент, я хочу сохранять и загружать захваченные credentials между перезапусками, чтобы не перезахватывать их каждый раз.
- Как агент, я хочу проверить, живы ли сохранённые credentials, прежде чем делать bapi-вызовы, чтобы обнаружить истечение и перезахватить проактивно.
- Как агент, я хочу создать пост, комментарий, подписку или репост через браузерную автоматизацию, чтобы выполнять действия, требующие клиентского nonce/signature от Binance.
- Как агент, я хочу обходить рекомендованную ленту и взаимодействовать с постами (лайк + комментарий + подписка) в одной браузерной сессии, чтобы эффективно проводить полный цикл активности.

---

## Модель данных

Credentials хранятся в SQLite (определены в `src/db/models.py`):

```sql
CREATE TABLE IF NOT EXISTS credentials (
    account_id TEXT PRIMARY KEY,
    cookies    TEXT NOT NULL,       -- JSON-serialized dict[str, str]
    headers    TEXT NOT NULL,       -- JSON-serialized dict[str, str]
    harvested_at TIMESTAMP NOT NULL,
    expires_at   TIMESTAMP,         -- NULL = no expiry
    valid        BOOLEAN DEFAULT TRUE
);
```

Дополнительных таблиц нет. `CredentialStore` — единственный читатель/писатель этой таблицы.

---

## API

### AdsPowerClient (`src/session/adspower.py`)

| Метод | Сигнатура | Возвращает | Примечания |
|-------|-----------|------------|------------|
| `__init__` | `(base_url="http://local.adspower.net:50325", timeout_start=60.0, timeout_stop=30.0, timeout_status=20.0, retry_attempts=2, retry_backoff=0.5)` | — | Все таймауты в секундах |
| `get_status` | `() -> dict` | Payload статуса AdsPower | Бросает `AdsPowerError` если недоступен |
| `start_browser` | `(user_id: str) -> dict` | `{"ws": str, "debug_port": str, "webdriver": str}` | `ws` — CDP-эндпоинт для Playwright |
| `stop_browser` | `(user_id: str) -> dict` | Ответ остановки AdsPower | |

**Ошибки:** `AdsPowerError` — бросается при HTTP-ошибке, ненулевом `code` в ответе или исчерпании retry. Retry использует экспоненциальный backoff: `retry_backoff * 2^(attempt-1)`.

---

### harvest_credentials (`src/session/harvester.py`)

```python
async def harvest_credentials(ws_endpoint: str) -> dict[str, Any]
```

Подключается через CDP к браузеру по `ws_endpoint`, переходит на `https://www.binance.com/en/square`, перехватывает все сетевые ответы `/bapi/`, извлекает следующие заголовки: `csrftoken`, `bnc-uuid`, `device-info`, `clienttype`, `lang`, `bnc-location`, `bnc-time-zone`, `fvideo-id`, `fvideo-token`, `versioncode`, `x-passthrough-token`, `x-trace-id`, `x-ui-request-trace`, плюс `user-agent` из `navigator.userAgent`.

**Возвращает:**
```python
{
    "cookies": dict[str, str],           # только cookies binance.com
    "headers": dict[str, str],           # все захваченные bapi-заголовки
    "discovered_endpoints": list[dict],  # [{"method": str, "path": str}]
}
```

**Бросает:** `RuntimeError` при ошибке CDP-подключения. Ошибки навигации логируются как warning и не прерывают работу — возвращаются частичные данные.

**Важно:** НЕ закрывает браузер. Жизненным циклом браузера управляет AdsPower.

---

### CredentialStore (`src/session/credential_store.py`)

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `__init__` | `(db_path: str)` | — |
| `save` | `(account_id: str, cookies: dict, headers: dict, max_age_hours: float = 12.0) -> None` | Upsert — перезаписывает существующую строку |
| `load` | `(account_id: str) -> dict \| None` | `{account_id, cookies, headers, harvested_at, expires_at, valid}` или `None` |
| `invalidate` | `(account_id: str) -> None` | Устанавливает `valid = FALSE` |
| `is_valid` | `(account_id: str) -> bool` | `True` если строка существует и `valid == TRUE` |
| `is_expired` | `(account_id: str) -> bool` | `True` если `expires_at < utcnow()` или строка отсутствует |

---

### validate_credentials (`src/session/validator.py`)

```python
async def validate_credentials(cookies: dict[str, str], headers: dict[str, str]) -> bool
```

Делает POST на `https://www.binance.com/bapi/composite/v1/friendly/pgc/card/fearGreedHighestSearched` с предоставленными cookies и подмножеством заголовков (`csrftoken`, `bnc-uuid`, `device-info`, `user-agent`, `bnc-location`). Возвращает `True` если ответ HTTP 200 и `data.success == True` или `data.code == "000000"`. Возвращает `False` при любой ошибке или не-auth ответе.

---

### browser_actions (`src/session/browser_actions.py`)

Все функции подключаются к браузеру через `_get_page(ws_endpoint)`, который возвращает `(playwright, browser, page)` используя `context.pages[0]`. Все функции вызывают `await pw.stop()` в `finally`.

| Функция | Сигнатура | Возвращает |
|---------|-----------|------------|
| `create_post` | `(ws_endpoint, text, coin=None, sentiment=None, image_path=None) -> dict` | `{"success": bool, "post_id": str, ...}` |
| `create_article` | `(ws_endpoint, title, body, cover_path=None, image_paths=None) -> dict` | `{"success": bool, "post_id": str, ...}` |
| `repost` | `(ws_endpoint, post_id, comment="") -> dict` | `{"success": bool, "original_post_id": str}` |
| `comment_on_post` | `(ws_endpoint, post_id, comment_text) -> dict` | `{"success": bool, "post_id": str, "followed": bool}` |
| `follow_author` | `(ws_endpoint, post_id) -> dict` | `{"success": bool, "post_id": str, "action": str}` |
| `browse_and_interact` | `(ws_endpoint, comment_generator=None, count=5, skip_rate=0.3) -> dict` | `{"success": bool, "interacted": int, "skipped": int, "actions": list}` |

Значения `coin` для `create_post`: строка тикера вроде `"BTC"`, `"ETH"`. `sentiment`: `"bullish"` или `"bearish"`.

Значения `action` в `follow_author`: `"followed"`, `"already_following"`, `"skipped"`.

---

### page_map (`src/session/page_map.py`)

Только константы — функций нет. CSS-селекторы и шаблоны URL, используемые `browser_actions`. Ключевые селекторы:

| Константа | Значение | Используется для |
|-----------|----------|-----------------|
| `SQUARE_URL` | `"https://www.binance.com/en/square"` | Навигация |
| `POST_URL_TEMPLATE` | `"https://www.binance.com/en/square/post/{post_id}"` | Навигация |
| `COMPOSE_EDITOR` | `"div.ProseMirror[contenteditable='true']"` | Ввод текста |
| `COMPOSE_INLINE_POST_BUTTON` | `"button[data-bn-type='button']:not(.news-post-button):has-text('Post')"` | Публикация |
| `POST_REPLY_INPUT` | `'input[placeholder="Post your reply"]'` | Ввод комментария |
| `POST_FOLLOW_REPLY_POPUP` | `"button:has-text('Follow & Reply')"` | Popup ограниченного комментирования |
| `FOLLOW_BUTTON` | `"button:has-text('Follow')"` | Подписка |

---

## Бизнес-логика

### Жизненный цикл credentials
```
[отсутствуют] → harvest_credentials() → save() → [валидны, не истекли]
[валидны, не истекли] → is_expired() == True → harvest_credentials() → save() → [валидны, обновлены]
[валидны] → bapi возвращает 401/403 → invalidate() → [невалидны]
[невалидны] → harvest_credentials() → save() → [валидны]
```

### Обработка автодополнения хэштегов
При вводе текста поста, содержащего `#hashtag`, popup автодополнения Binance блокирует кнопку Post. `_type_with_hashtag_handling()` разделяет текст по `#`, вводит каждое слово хэштега, затем нажимает `Escape` для закрытия popup-а перед продолжением.

### Правило безопасности подписки
`follow_author` читает `text_content()` кнопки. Если текст `"Following"` или `"Unfollow"`, клик **не** выполняется (клик привёл бы к отписке). Кликает только если текст ровно `"Follow"`.

### Различение кнопок Post
На странице Square существуют две кнопки Post: `.news-post-button` (левая панель, открывает модальное окно) и inline кнопка публикации. Всегда используется inline кнопка: `button[data-bn-type='button']:not(.news-post-button):has-text('Post')`.

### Фильтрация спама в browse_and_interact
Посты пропускаются если: длина текста < 50 символов, лайков < 3, или текст содержит любое из `{"gift", "giveaway", "airdrop", "copy trading"}`. Человекоподобная задержка между постами: `random.uniform(15, 35) + (interacted_count * 2)` секунд.

### Заголовки валидации
`fvideo-id` и `fvideo-token` обязательны для того, чтобы bapi возвращал ненулевые `data`. Без них bapi возвращает `data: null` даже при HTTP 200.

---

## Крайние случаи

| Ситуация | Ожидаемое поведение |
|----------|---------------------|
| AdsPower не запущен | `AdsPowerError` бросается после `retry_attempts` с экспоненциальным backoff |
| CDP-подключение не удалось | `RuntimeError` из `harvest_credentials` |
| Навигация на Square по таймауту | Warning в лог, возвращаются частичные credentials (что было перехвачено до таймаута) |
| Не перехвачено ни одного bapi-запроса | Возвращается dict `cookies` из хранилища браузера; `headers` могут быть пустыми или частичными |
| Credentials истекли (is_expired=True) | Вызывающий код должен перезахватить; `CredentialStore` не обновляет автоматически |
| Popup "Follow & Reply" появляется при комментировании | Popup кликается — это одновременно подписывает на автора И отправляет оригинальный комментарий. Второй комментарий не пишется. |
| Кнопка Post не найдена в течение 5 секунд | `TimeoutError` пробрасывается, `create_post` возвращает `{"success": False, "error": str}` |
| `browse_and_interact` при пустой ленте | Возвращает `{"success": True, "interacted": 0, "skipped": 0, "actions": []}` |
| `create_article` — не тестировано live | Может молча упасть; кнопка публикации статьи должна быть прокручена в видимую область перед кликом |

---

## Приоритет и зависимости

- **Приоритет:** Высокий (фундаментальный — все остальные модули зависят от него)
- **Зависит от:** `src/db/` (SQLite-схема должна быть инициализирована до того, как `CredentialStore` сможет писать)
- **Блокирует:** `src/bapi/` (BapiClient нуждается в `CredentialStore`), `src/content/publisher.py` (нуждается в `browser_actions`), `src/activity/executor.py` (нуждается в `browser_actions` для комментариев/репостов)
