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
| browser_actions.py | 652 | Все Playwright-действия: create_post, create_article, repost, comment_on_post, follow_author, browse_and_interact |
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
- `browse_and_interact(ws_endpoint, comment_generator, count)` — обход ленты + лайк/коммент/follow

## Типичные задачи
- Добавить селектор: редактировать `page_map.py`, использовать в `browser_actions.py`
- Добавить browser-действие: добавить функцию в `browser_actions.py`, паттерн `_get_page()`
- Отладить протухание credentials: `credential_store.py` `is_expired()`, `validator.py`

## Известные проблемы
- `browser_actions.py` — 652 строки, нужно разбить при добавлении новых действий
- Селекторы в `page_map.py` ломаются при обновлении UI Binance Square
