---
globs: ["tests/**"]
---

# Правила тестирования

- Использовать pytest с pytest-asyncio для async тестов.
- Мокать внешние сервисы (Binance bapi, AI API, AdsPower) — никогда не делать live-вызовы в тестах.
- Имена тестов описывают ЧТО проверяется, не детали реализации.
- Один assert на тест где это практично.
- Использовать фикстуры для общей подготовки (mock BapiClient, mock CredentialStore, тестовая БД).
- Интеграционные тесты с live-сервисами (напр. `test_harvester_integration.py`) — в отдельных файлах, исключены из дефолтного запуска.
- Запуск тестов: `python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py`
- Текущее количество тестов: 390 (обновлено 2026-04-04).
