"""Operator status dashboard: real-time terminal view of all agents.

Usage:
    python scripts/operator_status.py           # continuous refresh (5s)
    python scripts/operator_status.py --once    # single snapshot
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone

from src.db.database import get_db_path
from src.operator.state_store import (
    get_operator_metrics,
    get_recent_events,
    init_operator_tables,
    load_all_agents,
)

STATE_COLORS = {
    "idle": "\033[90m",        # gray
    "working": "\033[32m",     # green
    "cooldown": "\033[36m",    # cyan
    "blocked_reply_limit": "\033[31m",   # red
    "paused_for_resume": "\033[33m",     # yellow
    "paused_adspower_down": "\033[31m",  # red
    "failed": "\033[31m",      # red
    "disabled": "\033[90m",    # gray
}
RESET = "\033[0m"
BOLD = "\033[1m"
CLEAR = "\033[2J\033[H"


def _colorize(state: str) -> str:
    color = STATE_COLORS.get(state, "")
    display = state.replace("_", " ")
    return f"{color}{display}{RESET}"


def _format_time(iso_str: str | None) -> str:
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        diff = dt - now
        if diff.total_seconds() < 0:
            return dt.strftime("%H:%M")
        minutes = int(diff.total_seconds() / 60)
        if minutes < 1:
            return "< 1m"
        return f"in {minutes}m"
    except Exception:
        return iso_str[:16]


async def render_dashboard(db_path: str) -> str:
    """Build dashboard string from current state."""
    agents = await load_all_agents(db_path)
    metrics = await get_operator_metrics(db_path)
    events = await get_recent_events(db_path, limit=8)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"{BOLD}OPERATOR STATUS{RESET}  {now}",
        f"Slots: {metrics['busy_slots']}/{metrics['active_agents']} active  "
        f"Avg cycle: {metrics['avg_cycle_sec']}s  "
        f"Success: {metrics['success_rate_pct']}%  "
        f"Runs: {metrics['total_runs']}",
        "",
        f"{'Agent':<14} {'State':<22} {'Cycle':>6} {'Errors':>7} {'Next run':<12}",
        "-" * 65,
    ]

    for agent in agents:
        agent_id = agent["agent_id"]
        state = _colorize(agent.get("state", "?"))
        cycle = agent.get("cycle_count", 0)
        errors = agent.get("consecutive_errors", 0)
        next_run = _format_time(agent.get("next_run_at"))
        error_str = f"{errors}" if errors else "-"
        lines.append(f"{agent_id:<14} {state:<32} {cycle:>6} {error_str:>7} {next_run:<12}")

    if events:
        lines.extend(["", f"{BOLD}Recent events:{RESET}"])
        for event in events[:8]:
            ts = (event.get("created_at") or "")[:19]
            agent = event.get("agent_id") or ""
            msg = event.get("message") or ""
            lines.append(f"  {ts} {agent}: {msg[:60]}")

    return "\n".join(lines)


async def run_dashboard(once: bool = False, interval: int = 5) -> None:
    db_path = get_db_path()
    await init_operator_tables(db_path)

    if once:
        output = await render_dashboard(db_path)
        print(output)
        return

    try:
        while True:
            output = await render_dashboard(db_path)
            print(CLEAR + output, flush=True)
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Operator status dashboard.")
    parser.add_argument("--once", action="store_true", help="Print once and exit")
    parser.add_argument("--interval", type=int, default=5, help="Refresh interval (seconds)")
    args = parser.parse_args()
    asyncio.run(run_dashboard(once=args.once, interval=args.interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
