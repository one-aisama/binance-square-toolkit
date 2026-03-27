# Модуль: parser
# Назначение: получение постов из bapi, парсинг сырых ответов, ранжирование трендов по engagement
# Спецификация: docs/specs/spec_parser.md

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| fetcher.py | 114 | TrendFetcher — загрузка статей + фида через BapiClient, дедупликация по post_id |
| aggregator.py | 59 | rank_topics() — группировка по хэштегу, скоринг: views*0.3 + likes*0.5 + comments*0.2 |
| models.py | 32 | ParsedPost и Topic dataclasses |

## Зависимости
- Использует: `bapi.client` (BapiClient — все данные идут через него)
- Используется: `content` (темы подаются в ContentGenerator)
- Используется: `activity` (посты используются как таргеты)
- Используется: `scheduler` (вызывает TrendFetcher.fetch_all + rank_topics)

## Ключевые функции
- `TrendFetcher(client: BapiClient)` — конструктор
- `TrendFetcher.fetch_all(article_pages=5, feed_pages=5)` — возвращает `list[ParsedPost]`
- `TrendFetcher.fetch_fear_greed()` — возвращает dict
- `TrendFetcher.fetch_hot_hashtags()` — возвращает список dict
- `rank_topics(posts, top_n=10)` — возвращает `list[Topic]`
- `compute_engagement(post)` — возвращает float score

## Типичные задачи
- Изменить формулу ранжирования: `compute_engagement()` в `aggregator.py`
- Исправить парсинг bapi: `_extract_post()` в `fetcher.py` — обрабатывает вложенный `contentDetail`
- Добавить источник данных: добавить метод в TrendFetcher, вызвать в `fetch_all()`

## Известные проблемы
- Структура ответов bapi различается между feed и article endpoints — `_extract_post()` пробует несколько путей
- Посты без хэштегов (`_untagged`) исключаются из ранжирования тем
