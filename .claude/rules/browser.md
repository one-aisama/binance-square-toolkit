---
globs: ["src/session/browser_actions.py", "src/session/page_map.py"]
---

# Правила браузерной автоматизации

- Все браузерные действия подключаются к AdsPower профилям через Playwright CDP — никогда не запускать голый Playwright.
- CSS-селекторы в `page_map.py` хрупкие — обновления UI Binance Square могут сломать их в любой момент.
- На странице Square две кнопки Post: левая панель `.news-post-button` (открывает модальное окно) и inline кнопка публикации. Всегда использовать inline.
- Автокомплит хэштегов перекрывает кнопку Post — после каждого хэштега добавить пробел или нажать Escape.
- Popup "Follow & Reply" нужно обработать при комментировании — клик по нему подписывает + отправляет коммент одним действием. После этого НЕ писать коммент повторно.
- `follow_author()` должен проверять текст кнопки перед кликом: "Follow" = кликать, "Following"/"Unfollow" = НЕ кликать (отпишет).
- Комменты идут через DOM input `input[placeholder="Post your reply"]` + кнопка Reply, НЕ через bapi POST.
- Создание поста требует client-side nonce + signature — нельзя через httpx, только браузер.
- Спам-фильтр в `browse_and_interact`: пропускать посты с текстом < 50 символов, лайками < 3, или содержащие "gift", "giveaway", "airdrop", "copy trading".
- Человеческая задержка между действиями: `random.uniform(15, 35) + (interacted_count * 2)` секунд.
- Всегда вызывать `await pw.stop()` в finally-блоке после браузерных действий.
