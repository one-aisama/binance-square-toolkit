# Specification: Operator Control Plane

**Path:** `src/operator/`
**Entry point:** `scripts/run_operator.py`
**Dashboard:** `scripts/operator_status.py`

---

## Purpose

The top layer of the system. A single persistent process that manages all persona agents through slot-based scheduling. Replaces session_loop.py as the production path.

## State Machine

```
IDLE -> WORKING -> COOLDOWN -> WORKING -> ...
```

| State | Description |
|-------|-------------|
| IDLE | Initial / after error / after waking from cooldown |
| WORKING | Working cycle 25-40 min (N micro-cycles inside) |
| COOLDOWN | Pause 10-15 min (or short if queue pending) |
| BLOCKED_REPLY_LIMIT | All non-reply targets completed + reply limited |
| PAUSED_FOR_RESUME | Interrupted, checkpoint exists |
| PAUSED_ADSPOWER_DOWN | AdsPower unavailable |
| FAILED | Error with backoff |
| DISABLED | Disabled (3+ consecutive errors) |

## Micro-cycle (single pass within WORKING)

```
1. compile    -> MemoryCompiler assembles briefing_packet.md
2. strategize -> persona reads briefing + context -> strategic_directive.json
3. prepare    -> session_run.py --prepare (context + plan skeleton)
4. author     -> persona writes text based on plan
5. audit      -> PlanAuditor checks text
6. execute    -> session_run.py --execute (SDK publishes)
7. reflect    -> persona updates strategic_state.md, open_loops.md, intent.md
```

## Modules

| File | Purpose |
|------|---------|
| models.py | AgentState (8 states), Priority, AgentSlot, OperatorConfig |
| state_store.py | SQLite: operator_agents, operator_runs, operator_leases, operator_events |
| registry.py | Scanning active_agent*.yaml, deduplication by agent_id |
| scheduler.py | Priority queue, slot management, compute_next_run_at |
| loop.py | Persistent tick loop, time-based working cycles, dispatch |
| persona_bridge.py | Spawn persona subagent for writing text |
| strategic_bridge.py | Spawn persona for strategic decisions (directive) |
| reflection_bridge.py | Spawn persona for reflection (updating living memory) |
| auditor_bridge.py | Pre-execute audit via PlanAuditor |
| memory_compiler.py | Compilation of briefing_packet from 10 memory layers |
| leases.py | Exclusive locks on profiles (BEGIN IMMEDIATE, TTL) |
| recovery.py | Backoff, circuit breaker, AdsPower down/recovery, stuck detection |

## SQLite Tables

| Table | Purpose |
|-------|---------|
| operator_agents | State of each logical agent |
| operator_runs | Micro-cycle history (duration, status, errors) |
| operator_leases | Exclusive locks on profiles |
| operator_events | Audit trail of operator decisions |

## Scaling

- Logical agents: unlimited (as many YAML configs as needed)
- Active browser slots: `--max-slots N` (4-6 on a weak PC, 10-12 on a powerful one)
- The operator manages the queue: agents wait for a slot to free up

## Configuration

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

- Execute timeout -> PAUSED_FOR_RESUME (not immediately FAILED)
- 3 consecutive errors -> DISABLED (circuit breaker)
- Exponential backoff: 10, 20, 40 minutes
- AdsPower down -> all WORKING + COOLDOWN agents are paused
- Stuck detection every tick (2x timeout -> FAILED)

## Strategic Directive Format

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

## Briefing Packet (10 layers)

1. Identity (stable core)
2. Style
3. Strategic state (living -- agent updates)
4. Open loops (living)
5. Intent (living)
6. Recent lessons
7. Recent journal
8. Relationship priorities
9. Performance signals
10. Hard constraints
