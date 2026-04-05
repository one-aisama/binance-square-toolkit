# Модуль: session
# Назначение: управление браузерами AdsPower, CDP-автоматизация, захват и хранение credentials
# Спецификация: docs/specs/spec_session.md

## Файлы
| Файл | Строк | Что делает |
|------|-------|------------|
| adspower.py | 107 | AdsPowerClient — запуск/остановка браузерных профилей через Local API |
| harvester.py | 122 | harvest_credentials() — навигация на Square через CDP, захват cookies + bapi headers |
| credential_store.py | 80 | CredentialStore — SQLite CRUD для credentials (save, load, invalidate, is_expired) |
| validator.py | 58 | validate_credentials() — тестовый запрос к bapi для проверки живости |
| browser_actions.py | 588 | Publishing: create_post (с robust UI confirmation), create_article, repost + helpers |
| browser_engage.py | 430 | Engagement: like_post, comment_on_post, engage_post, follow_author |
| browser_data.py | 688 | Data collection: collect_feed_posts, get_user_profile, get_post_comments, get_my_comment_replies |
| credential_crypto.py | 99 | Шифрование/дешифрование credentials |
| web_visual.py | 250 | Визуальные утилиты: определение цвета, инспекция элементов |
| page_map.py | 79 | CSS-селекторы и URL Binance Square (обновлены 2026-03-24) |

## Зависимости
- Использует: `db` (CredentialStore читает/пишет таблицу credentials)
- Используется: `bapi` (BapiClient загружает credentials из CredentialStore)
- Используется: `activity` (browser_actions для комментов/репостов через CDP)
- Используется: `scheduler` (harvesting, валидация, вызов browser_actions)

## Ключевые функции
- `AdsPowerClient.start_browser(user_id)` — возвращает `{ws, debug_port, webdriver}`
- `harvest_credentials(ws_endpoint)` — возвращает `{cookies, headers, discovered_endpoints}`
- `CredentialStore.save/load/invalidate/is_expired(account_id)` — жизненный цикл credentials
- `validate_credentials(cookies, headers)` — возвращает bool
- `create_post(ws_endpoint, text, coin, sentiment, image_path)` — публикация через Playwright
- `comment_on_post(ws_endpoint, post_id, comment_text)` — обрабатывает "Follow & Reply" popup
- `collect_feed_posts(ws_endpoint, count, tab)` — сбор постов из ленты для агента

## Типичные задачи
- Добавить селектор: редактировать `page_map.py`, использовать в `browser_actions.py`
- Добавить browser-действие: добавить функцию в `browser_actions.py`, паттерн `_get_page()`
- Отладить протухание credentials: `credential_store.py` `is_expired()`, `validator.py`

## Известные проблемы
- Селекторы в `page_map.py` ломаются при обновлении UI Binance Square
