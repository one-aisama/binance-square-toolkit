# Спецификация: Модуль Activity

**Путь:** `src/activity/`
**Файлы:** `executor.py`, `target_selector.py`, `randomizer.py`, `comment_gen.py`

---

## Описание

Модуль Activity предоставляет инструменты для взаимодействия с постами Binance Square: лайки, комментарии, репосты и подписки. Включает выбор целей (какие посты для взаимодействия), человекоподобную рандомизацию (задержки и пропуски) и AI-генерацию комментариев. Агент вызывает эти функции для проведения циклов вовлечения — модуль НЕ решает автономно, с чем взаимодействовать.

`CommentGenerator` — это инструмент, который вызывает агент. Софт не генерирует контент самостоятельно: агент решает, какому посту нужен комментарий, и вызывает генератор для создания текста.

---

## Пользовательские сценарии

- Как агент, я хочу запустить цикл лайк/комментарий/репост на списке распарсенных постов, чтобы наращивать вовлечённость для аккаунта.
- Как агент, я хочу, чтобы посты фильтровались для исключения моих собственных аккаунтов и низкововлечённого контента, чтобы никогда не взаимодействовать со своими постами и фокусироваться на высоковидимом контенте.
- Как агент, я хочу человекоподобные случайные задержки между действиями и вероятностные пропуски, чтобы паттерны активности выглядели естественно.
- Как агент, я хочу AI-сгенерированные комментарии, которые звучат как реальный человек, отвечающий на конкретный пост, чтобы комментарии были релевантными, а не шаблонными.
- Как агент, я хочу, чтобы дневные лимиты применялись для каждого типа действий, чтобы аккаунты не превышали безопасные пороги активности.

---

## Модель данных

Собственных таблиц нет. Модуль читает/пишет через `ActionLimiter` (из `src/accounts/limiter.py`), который использует таблицы `actions_log` и `daily_stats`.

---

## API

### ActivityExecutor (`src/activity/executor.py`)

```python
class ActivityExecutor:
    def __init__(
        self,
        client: BapiClient,
        limiter: ActionLimiter,
        randomizer: HumanRandomizer,
        target_selector: TargetSelector,
        comment_generator=None,
    )
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `run_cycle` | `(account_id: str, posts: list[dict], limits: dict[str, list[int]]) -> dict[str, int]` | `{"likes": N, "comments": N, "reposts": N, "skipped": N, "errors": N}` |

**Поведение цикла:**
1. **Лайки:** Выбирает `random.randint(*limits["like"])` целей. Для каждой: проверить дневной лимит, возможно пропустить (randomizer), вызвать `BapiClient.like_post()`.
2. **Комментарии:** Выбирает `random.randint(*limits["comment"])` целей из высокововлечённых постов. Для каждой: проверить лимит, возможно пропустить, сгенерировать текст комментария через `CommentGenerator`, вызвать `BapiClient.comment_post()` (сейчас stub — бросает `NotImplementedError`).
3. **Репосты:** Выбирает `random.randint(*limits["repost"])` топ-постов. Тот же поток, что и комментарии, но вызывает `BapiClient.repost()` (stub).

Когда stub бросает `NotImplementedError`, цикл прерывается с warning в лог. Это ожидаемое поведение, пока комментарии/репосты не подключены к `browser_actions`.

---

### TargetSelector (`src/activity/target_selector.py`)

```python
class TargetSelector:
    def __init__(self, own_account_ids: set[str], min_views: int = 1000)
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `select_like_targets` | `(posts: list[dict], count: int) -> list[dict]` | Случайная выборка из подходящих постов |
| `select_comment_targets` | `(posts: list[dict], count: int) -> list[dict]` | Из верхней половины по просмотрам, перемешано |
| `select_repost_targets` | `(posts: list[dict], count: int) -> list[dict]` | Топ-посты по просмотрам |

**Фильтрация (`_filter_eligible`):**
- Исключает посты, где `author_id` есть в `own_account_ids`
- Исключает посты с `view_count < min_views`

---

### HumanRandomizer (`src/activity/randomizer.py`)

```python
class HumanRandomizer:
    def __init__(self, delay_range: tuple[int, int] = (30, 120), skip_rate: float = 0.35)
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `should_skip` | `() -> bool` | `True` с вероятностью `skip_rate` |
| `human_delay` | `() -> None` | `await asyncio.sleep(random.uniform(*delay_range))` |

---

### CommentGenerator (`src/activity/comment_gen.py`)

```python
class CommentGenerator:
    def __init__(self, provider: str = "deepseek", model: str = "deepseek-chat", api_key: str = "")
```

| Метод | Сигнатура | Возвращает |
|-------|-----------|------------|
| `generate` | `(post_text: str, author_name: str = "") -> str` | Текст комментария (1-2 предложения) |
| `generate_comment` | `(post_text: str, persona_style: str = "", comment_type: str \| None = None) -> str` | Обратно-совместимый алиас для `generate()` |

**Провайдеры:** `"deepseek"` (через OpenAI-совместимый API на `api.deepseek.com`), `"openai"`, `"anthropic"`.

**Системный промпт** обеспечивает:
- Максимум 1-2 предложения
- Релевантность конкретному содержанию поста
- Разговорный, неформальный тон (обращение К автору)
- Никаких шаблонных комментариев ("Great post!", "Thanks for sharing!")
- Типы: согласие, вопрос, дополнение, мягкое несогласие

Убирает обрамляющие кавычки из AI-вывода. Возвращает пустую строку при ошибке генерации.

---

## Бизнес-логика

### Антидетект
- `TargetSelector` предотвращает взаимодействие с собственными аккаунтами
- `HumanRandomizer` добавляет задержку 30-120 секунд между действиями
- 35% действий случайно пропускается
- Комментарии только к постам с >1000 просмотров (настраивается)

### Контроль лимитов
`ActivityExecutor` проверяет `ActionLimiter.check_allowed()` перед каждым действием. Лимитер использует детерминированный дневной лимит: `hash(account_id:date:action_type)` задаёт seed для RNG, который выбирает число в настроенном диапазоне `[min, max]`. Один и тот же аккаунт+дата+тип всегда получает один и тот же лимит.

### Генерация комментариев vs browser_actions
Два пути для комментирования:
1. **ActivityExecutor** вызывает `BapiClient.comment_post()` — сейчас stub (NotImplementedError)
2. **browser_actions.browse_and_interact()** принимает экземпляр `CommentGenerator` и комментирует через DOM

Сейчас работает только путь 2. Путь 1 заработает, если/когда будет обнаружен bapi-эндпоинт для комментариев.

---

## Крайние случаи

| Ситуация | Ожидаемое поведение |
|----------|---------------------|
| Все посты отфильтрованы (свои аккаунты или мало просмотров) | `select_*_targets` возвращает пустой список, действия не выполняются |
| `CommentGenerator` возвращает пустую строку | Executor должен использовать fallback-текст или пропустить комментарий |
| `BapiClient.comment_post()` бросает NotImplementedError | Warning в лог, цикл комментариев прерывается, лайки всё ещё могут работать |
| Дневной лимит уже достигнут | `check_allowed` возвращает False, цикл прерывается для этого типа действия |
| Список `posts` пустой | Цели не выбираются, цикл возвращает все нули |
| AI API недоступен | `CommentGenerator.generate()` возвращает пустую строку, ошибка логируется |

---

## Приоритет и зависимости

- **Приоритет:** Средний (лайки работают через httpx; комментарии/репосты требуют интеграции с browser_actions)
- **Зависит от:** `src/bapi/client.py` (like_post), `src/accounts/limiter.py` (ActionLimiter), `src/session/browser_actions.py` (для комментариев/репостов через CDP)
- **Блокирует:** Полные циклы активности в планировщике
