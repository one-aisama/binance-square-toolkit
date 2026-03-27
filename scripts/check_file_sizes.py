"""Check that no Python file exceeds 500 lines.

Usage: python scripts/check_file_sizes.py
Exit code: 1 if any file exceeds the limit, 0 otherwise.
"""

import os
import sys

MAX_LINES = 500
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
WARN_THRESHOLD = 400


def count_lines(filepath: str) -> int:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def main() -> int:
    violations = []
    warnings = []

    for root, _dirs, files in os.walk(SRC_DIR):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(root, filename)
            lines = count_lines(filepath)
            rel_path = os.path.relpath(filepath, os.path.join(SRC_DIR, ".."))

            if lines > MAX_LINES:
                violations.append((rel_path, lines))
            elif lines > WARN_THRESHOLD:
                warnings.append((rel_path, lines))

    if warnings:
        print(f"\n WARNING: {len(warnings)} file(s) approaching limit ({WARN_THRESHOLD}+ lines):")
        for path, lines in sorted(warnings, key=lambda x: -x[1]):
            print(f"  {path}: {lines} lines")

    if violations:
        print(f"\n VIOLATION: {len(violations)} file(s) exceed {MAX_LINES} lines:")
        for path, lines in sorted(violations, key=lambda x: -x[1]):
            print(f"  {path}: {lines} lines (over by {lines - MAX_LINES})")
        return 1

    total_files = len(warnings) + len(violations)
    if total_files == 0:
        print(f"All Python files in src/ are under {MAX_LINES} lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
