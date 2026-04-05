# Модуль: activity
# Назначение: оркестрация лайков, комментов, репостов с человекоподобным поведением
# Спецификация: docs/specs/spec_activity.md

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| executor.py | 132 | ActivityExecutor — цикл like/comment/repost, проверка лимитов, обработка заглушек |
| target_selector.py | 56 | TargetSelector — фильтрация постов, выбор таргетов по engagement |
| randomizer.py | 27 | HumanRandomizer — случайная задержка (30-120с), вероятностный пропуск (35%) |
| comment_gen.py | 132 | CommentGenerator — инструмент агента: AI-генерация комментов через DeepSeek/OpenAI/Anthropic |

## Зависимости
- Использует: `bapi.client` (like_post работает; comment_post/repost — заглушки)
- Использует: `accounts.limiter` (ActionLimiter — проверка и запись каждого действия)
- Используется: `scheduler` (_run_activity вызывает ActivityExecutor)
- Используется: `session.browser_actions` (comment_on_post, create_post через SDK)

## Ключевые функции
- `ActivityExecutor.run_cycle(account_id, posts, limits)` — возвращает `{likes, comments, reposts, skipped, errors}`
- `TargetSelector(own_account_ids, min_views=1000)` — никогда не взаимодействует со своими аккаунтами
- `HumanRandomizer.should_skip()` / `human_delay()` — рандомизация поведения
- `CommentGenerator(provider, model, api_key)` — инструмент для агента, генерирует 1-2 предложения
- `CommentGenerator.generate(post_text, author_name)` — возвращает текст комментария

## Типичные задачи
- Изменить задержки: `HumanRandomizer(delay_range=(min, max))` в scheduler
- Изменить skip rate: `HumanRandomizer(skip_rate=0.35)` в scheduler
- Добавить тип действия: метод в ActivityExecutor + селектор в TargetSelector

## Известные проблемы
- comment_post и repost в BapiClient — заглушки; реальные действия через `session.browser_actions`
- comment_gen загружает `config/content_rules.yaml`, но правила пока не используются в промптах
- Софт не генерирует контент самостоятельно — CommentGenerator это инструмент, который вызывает агент
