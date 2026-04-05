from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_RUNS_DIR = Path("data/runs")
DEFAULT_REPORTS_DIR = Path("agents/supervisor/reports")
AGENTS_DIR = Path("agents")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def load_launch_metadata(path: Path | None) -> tuple[Path, list[dict[str, Any]]]:
    if path is None:
        candidates = sorted(DEFAULT_RUNS_DIR.glob("*_dual_launch.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not candidates:
            raise FileNotFoundError("No dual launch metadata found in data/runs")
        path = candidates[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    return path, data


def is_process_running(pid: int | None) -> bool:
    if not pid:
        return False
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout.strip()
    if not output or output.startswith("INFO:"):
        return False
    return f'"{pid}"' in output or f',{pid},' in output


def tail_lines(path: Path, limit: int = 20) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def pick_notable_line(lines: list[str]) -> str:
    for needle in ("ERROR", "Traceback", "WARNING", "Session complete", "Collected", "Connected", "created post", "Comment sent", "Liked post"):
        for line in reversed(lines):
            if needle in line:
                return line
    return lines[-1] if lines else "no log output yet"


def count_activity(lines: list[str]) -> dict[str, int]:
    return {
        "comments": sum(1 for line in lines if "Comment sent" in line),
        "likes": sum(1 for line in lines if "Liked post" in line),
        "posts": sum(1 for line in lines if "Post created" in line or "Created post" in line or "Published post" in line),
        "errors": sum(1 for line in lines if "ERROR" in line or "Traceback" in line),
    }


def read_agent_text(agent: str, filename: str) -> str:
    path = AGENTS_DIR / agent / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def build_growth_coaching(agent: str, notable: str, activity: dict[str, int]) -> list[str]:
    coaching: list[str] = []

    if activity["errors"] > 0:
        coaching.append("Fix session friction first. Repeated runtime errors reduce consistency and make the account look less human over time.")
    if activity["comments"] >= 2 and activity["posts"] == 0:
        coaching.append("Engagement is moving. The next improvement is stronger original posting so the account does not become comment-only in the feed.")
    if activity["comments"] == 0:
        coaching.append("Speed up first engagement. The account should reach visible threads faster instead of spending too much of the session in setup or parsing.")

    if agent == "aisama":
        coaching.append("Keep comments sharper and a bit more opinionated. The account already has enough data; the growth edge now is more personality and clearer disagreement.")
        coaching.append("Original posts should still use images or charts whenever possible. That remains one of the easiest visibility multipliers for this voice.")
        if "Follow & Reply" in notable:
            coaching.append("Use follow-driven replies selectively. Relationship building is useful, but too many auto-follows will dilute the account graph.")
    elif agent == "sweetdi":
        coaching.append("Keep SweetDi coin-specific. The strongest version of this account talks about Binance-traded alts, listings, rotation, and weak execution rather than generic BTC stress.")
        coaching.append("Graph building matters right now. A new account with no network should earn a few strategic follows instead of behaving like a pure publishing bot.")
        if "get_my_comment_replies" in notable or "Replies" in notable:
            coaching.append("Do not waste the whole session in reply archaeology. This profile is still building visibility and should stay focused on live altcoin conversations.")
    else:
        coaching.append("Keep the voice differentiated. Growth usually comes from a clear angle, not from sounding generally competent.")
        coaching.append("Balance engagement and original posting so the account can both join conversations and create its own gravity.")

    return coaching[:5]


def build_snapshot(runs: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot_runs: list[dict[str, Any]] = []
    for run in runs:
        stderr_path = Path(run["stderr"])
        stdout_path = Path(run["stdout"])
        stderr_tail = tail_lines(stderr_path)
        stdout_tail = tail_lines(stdout_path)
        running = is_process_running(run.get("pid"))
        status = "running" if running else "stopped"
        notable = pick_notable_line(stderr_tail or stdout_tail)
        activity = count_activity(stderr_tail)
        snapshot_runs.append(
            {
                "agent": run["agent"],
                "pid": run.get("pid"),
                "status": status,
                "stderr_path": str(stderr_path),
                "stdout_path": str(stdout_path),
                "stderr_tail": stderr_tail,
                "stdout_tail": stdout_tail,
                "notable": notable,
                "activity": activity,
                "coaching": build_growth_coaching(run["agent"], notable, activity),
            }
        )
    return {
        "observed_at": utc_now(),
        "all_completed": all(item["status"] != "running" for item in snapshot_runs),
        "runs": snapshot_runs,
    }


def render_report(snapshot: dict[str, Any], source_path: Path) -> str:
    lines = [
        f"# Supervisor Live Report — {snapshot['observed_at']}",
        "",
        f"Source launch metadata: `{source_path}`",
        "",
    ]
    for run in snapshot["runs"]:
        lines.extend(
            [
                f"## {run['agent']}",
                f"- status: {run['status']}",
                f"- pid: {run['pid']}",
                f"- notable: {run['notable']}",
                f"- activity: comments={run['activity']['comments']}, likes={run['activity']['likes']}, posts={run['activity']['posts']}, errors={run['activity']['errors']}",
                f"- stderr: `{run['stderr_path']}`",
                f"- stdout: `{run['stdout_path']}`",
                "- growth coaching:",
            ]
        )
        lines.extend([f"  - {item}" for item in run["coaching"]])
        lines.append("- recent log tail:")
        tail = run["stderr_tail"] or run["stdout_tail"] or ["no log output yet"]
        lines.extend([f"  {line}" for line in tail[-8:]])
        lines.append("")
    if snapshot["all_completed"]:
        lines.append("All observed agent runs have stopped.")
    else:
        lines.append("At least one observed agent run is still active.")
    lines.append("")
    return "\n".join(lines)


def write_agent_feedback(snapshot: dict[str, Any]) -> None:
    for run in snapshot["runs"]:
        agent_dir = AGENTS_DIR / run["agent"]
        if not agent_dir.exists():
            continue
        feedback_path = agent_dir / "supervisor_feedback.md"
        lines = [
            f"# Supervisor Feedback — {snapshot['observed_at']}",
            "",
            f"Status: {run['status']}",
            f"Notable: {run['notable']}",
            f"Activity: comments={run['activity']['comments']}, likes={run['activity']['likes']}, posts={run['activity']['posts']}, errors={run['activity']['errors']}",
            "",
            "## Coaching",
        ]
        lines.extend([f"- {item}" for item in run["coaching"]])
        lines.extend([
            "",
            "## Recent Log Tail",
        ])
        tail = run["stderr_tail"] or run["stdout_tail"] or ["no log output yet"]
        lines.extend([f"- {line}" for line in tail[-8:]])
        lines.append("")
        feedback_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only supervisor for Binance Square agent runs.")
    parser.add_argument("--launch", default=None, help="Path to *_dual_launch.json metadata file.")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds.")
    parser.add_argument("--max-cycles", type=int, default=240, help="Safety cap on polling cycles.")
    parser.add_argument("--tag", default="supervisor", help="Suffix for report and status artifacts.")
    args = parser.parse_args()

    DEFAULT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)

    source_path, runs = load_launch_metadata(Path(args.launch) if args.launch else None)
    launch_id = source_path.stem.replace("_dual_launch", "")
    report_path = DEFAULT_REPORTS_DIR / f"{launch_id}_{args.tag}.md"
    status_path = DEFAULT_RUNS_DIR / f"{launch_id}_{args.tag}.json"

    for _ in range(max(args.max_cycles, 1)):
        snapshot = build_snapshot(runs)
        report_path.write_text(render_report(snapshot, source_path), encoding="utf-8")
        status_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        write_agent_feedback(snapshot)
        if snapshot["all_completed"]:
            break
        time.sleep(max(args.interval, 1))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

