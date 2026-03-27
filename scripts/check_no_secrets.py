"""Scan Python and YAML files for hardcoded secrets.

Usage: python scripts/check_no_secrets.py
Exit code: 1 if potential secrets found, 0 otherwise.
"""

import os
import re
import sys

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")

# Patterns that indicate hardcoded secrets
SECRET_PATTERNS = [
    # API keys with actual values (not placeholders)
    (r'(?:api_key|apikey|api[-_]?token)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{20,}["\']', "API key"),
    # Bearer tokens
    (r'[Bb]earer\s+[a-zA-Z0-9_\-\.]{20,}', "Bearer token"),
    # Anthropic API keys
    (r'sk-ant-[a-zA-Z0-9_\-]{20,}', "Anthropic API key"),
    # OpenAI API keys
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key"),
    # Generic secret/password assignments with actual values
    (r'(?:secret|password|passwd)\s*[=:]\s*["\'][^"\']{8,}["\']', "Password/secret"),
    # Hardcoded csrftoken values
    (r'csrftoken\s*[=:]\s*["\'][a-f0-9]{20,}["\']', "CSRF token"),
    # Private keys
    (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', "Private key"),
]

# Directories and files to skip
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "data", "logs"}
SKIP_FILES = {".env", ".env.example", "check_no_secrets.py"}
EXTENSIONS = {".py", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini"}


def scan_file(filepath: str) -> list[tuple[int, str, str]]:
    """Scan a single file for secret patterns. Returns list of (line_num, pattern_name, line_text)."""
    findings = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments and env var references
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                # Skip os.environ and os.getenv references
                if "os.environ" in line or "os.getenv" in line or "environ.get" in line:
                    continue
                # Skip placeholder values
                if any(p in line.lower() for p in ["<your", "xxx", "placeholder", "example", "changeme"]):
                    continue

                for pattern, name in SECRET_PATTERNS:
                    if re.search(pattern, line):
                        findings.append((line_num, name, stripped[:120]))
    except (OSError, UnicodeDecodeError):
        pass
    return findings


def main() -> int:
    all_findings = []

    for root, dirs, files in os.walk(PROJECT_DIR):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            if filename in SKIP_FILES:
                continue
            ext = os.path.splitext(filename)[1]
            if ext not in EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            findings = scan_file(filepath)
            if findings:
                rel_path = os.path.relpath(filepath, PROJECT_DIR)
                for line_num, pattern_name, line_text in findings:
                    all_findings.append((rel_path, line_num, pattern_name, line_text))

    if all_findings:
        print(f"\n POTENTIAL SECRETS FOUND ({len(all_findings)} occurrences):\n")
        for path, line_num, pattern_name, line_text in all_findings:
            print(f"  {path}:{line_num} [{pattern_name}]")
            print(f"    {line_text}")
            print()
        return 1

    print("No hardcoded secrets detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
