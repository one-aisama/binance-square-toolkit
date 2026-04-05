from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RUNS_DIR = Path("data/runs")
DEFAULT_CONFIGS = (
    ("example_macro", "config/active_agent.yaml"),
    ("example_altcoin", "config/active_agent.example_altcoin.yaml"),
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def build_command(python_executable: str, config_path: str, post_count: int, delay_min: int, delay_max: int) -> list[str]:
    return [
        python_executable,
        "session_run.py",
        "--post-only",
        "--config",
        config_path,
        "--post-count",
        str(post_count),
        "--post-delay-min",
        str(delay_min),
        "--post-delay-max",
        str(delay_max),
    ]


def launch_process(command: list[str], stdout_path: Path, stderr_path: Path) -> subprocess.Popen[str]:
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        command,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        cwd=Path.cwd(),
    )


def write_metadata(path: Path, payload: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch both Binance Square agents in post-only validation mode.")
    parser.add_argument("--python", default=sys.executable, help="Python executable to use for background processes.")
    parser.add_argument("--post-count", type=int, default=3, help="Number of posts per agent.")
    parser.add_argument("--delay-min", type=int, default=45, help="Minimum delay in seconds between posts.")
    parser.add_argument("--delay-max", type=int, default=90, help="Maximum delay in seconds between posts.")
    args = parser.parse_args()

    DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    launch_id = utc_stamp()
    metadata_path = DEFAULT_RUNS_DIR / f"{launch_id}_post_only_launch.json"

    runs: list[dict[str, object]] = []
    for agent_id, config_path in DEFAULT_CONFIGS:
        stdout_path = DEFAULT_RUNS_DIR / f"{launch_id}_{agent_id}_post_only.stdout.log"
        stderr_path = DEFAULT_RUNS_DIR / f"{launch_id}_{agent_id}_post_only.stderr.log"
        command = build_command(args.python, config_path, args.post_count, args.delay_min, args.delay_max)
        process = launch_process(command, stdout_path, stderr_path)
        runs.append(
            {
                "agent": agent_id,
                "pid": process.pid,
                "config_path": config_path,
                "stdout": str(stdout_path.resolve()),
                "stderr": str(stderr_path.resolve()),
                "command": command,
            }
        )

    write_metadata(metadata_path, runs)
    print(json.dumps({"launch_file": str(metadata_path.resolve()), "runs": runs}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
