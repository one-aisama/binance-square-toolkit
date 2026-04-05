# Спецификация: Operator Control Plane

**Путь:** `src/operator/`
**Entry point:** `scripts/run_operator.py`
**Dashboard:** `scripts/operator_status.py`

---

## Назначение

Верхний слой системы. Единый persistent процесс который управляет всеми persona-агентами через slot-based scheduling. Заменяет session_loop.py как production path.

## State machine

```
IDLE -> WORKING -> COOLDOWN -> WORKING -> ...
```

| Состояние | Описание |
|-----------|----------|
| IDLE | Начальное / после ошибки / после пробуждения из cooldown |
| WORKING | Рабочий цикл 25-40 мин (N micro-cycles внутри) |
| COOLDOWN | Пауза 10-15 мин (или короткая если очередь) |
| BLOCKED_REPLY_LIMIT | Все non-reply targets выполнены + reply limited |
| PAUSED_FOR_RESUME | Прерван, есть checkpoint |
| PAUSED_ADSPOWER_DOWN | AdsPower недоступен |
| FAILED | Ошибка с backoff |
| DISABLED | Отключён (3+ ошибок подряд) |

## Micro-cycle (один проход внутри WORKING)

```
1. compile    -> MemoryCompiler собирает briefing_packet.md
2. strategize -> persona читает briefing + контекст -> strategic_directive.json
3. prepare    -> session_run.py --prepare (контекст + план-скелет)
4. author     -> persona пишет текст по plan
5. audit      -> PlanAuditor проверяет текст
6. execute    -> session_run.py --execute (SDK публикует)
7. reflect    -> persona обновляет strategic_state.md, open_loops.md, intent.md
```

## Модули

| Файл | Назначение |
|------|------------|
| models.py | AgentState (8 состояний), Priority, AgentSlot, OperatorConfig |
| state_store.py | SQLite: operator_agents, operator_runs, operator_leases, operator_events |
| registry.py | Сканирование active_agent*.yaml, дедупликация по agent_id |
| scheduler.py | Priority queue, slot management, compute_next_run_at |
| loop.py | Persistent tick loop, time-based working cycles, dispatch |
| persona_bridge.py | Spawn persona субагента для написания текста |
| strategic_bridge.py | Spawn persona для стратегических решений (directive) |
| reflection_bridge.py | Spawn persona для рефлексии (обновление живой памяти) |
| auditor_bridge.py | Pre-execute аудит через PlanAuditor |
| memory_compiler.py | Компиляция briefing_packet из 10 слоёв памяти |
| leases.py | Exclusive locks на профили (BEGIN IMMEDIATE, TTL) |
| recovery.py | Backoff, circuit breaker, AdsPower down/recovery, stuck detection |

## SQLite таблицы

| Таблица | Назначение |
|---------|------------|
| operator_agents | Состояние каждого логического агента |
| operator_runs | История micro-cycles (длительность, статус, ошибки) |
| operator_leases | Exclusive locks на профили |
| operator_events | Аудит-трейл решений оператора |

## Масштабирование

- Logical agents: неограниченно (сколько YAML конфигов)
- Active browser slots: `--max-slots N` (4-6 на слабом ПК, 10-12 на сильном)
- Оператор управляет очередью: агенты ждут когда слот освободится

## Конфигурация

```python
OperatorConfig(
    max_slots=4,                    # concurrent browser sessions
    tick_interval_sec=5,            # operator loop frequency
    cycle_duration_min=(25, 40),    # working cycle length (random)
    cooldown_min=(10, 15),          # pause between cycles
    prepare_timeout_sec=300,        # subprocess timeout
    author_timeout_sec=600,         # persona subagent timeout
    execute_timeout_sec=900,        # execute subprocess timeout
    lease_ttl_sec=3600,             # exclusive lock TTL
    max_consecutive_errors=3,       # circuit breaker threshold
    error_backoff_minutes=10,       # exponential backoff base
)
```

## Recovery

- Execute timeout -> PAUSED_FOR_RESUME (не сразу FAILED)
- 3 consecutive errors -> DISABLED (circuit breaker)
- Exponential backoff: 10, 20, 40 минут
- AdsPower down -> все WORKING + COOLDOWN агенты паузятся
- Stuck detection каждый tick (2x timeout -> FAILED)

## Strategic directive формат

```json
{
  "focus_summary": "...",
  "preferred_coins": ["SOL", "LINK"],
  "avoid_coins": ["DOGE"],
  "post_direction": "...",
  "comment_direction": "...",
  "skip_families": ["news_reaction"],
  "tone": "..."
}
```

## Briefing packet (10 слоёв)

1. Identity (стабильное ядро)
2. Style
3. Strategic state (живое — агент обновляет)
4. Open loops (живое)
5. Intent (живое)
6. Recent lessons
7. Recent journal
8. Relationship priorities
9. Performance signals
10. Hard constraints
