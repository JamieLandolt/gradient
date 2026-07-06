#!/usr/bin/env python3
"""Open a pull request on Gitee for the current branch.

Usage:
    python3 scripts/open_gitee_pr.py --title "feat: …" --body-file pr_body.md \
        [--head <branch>] [--base master]

Reads GITEE_TOKEN from the environment or from a gitignored `.env.gitee` file
in the repo root (format: GITEE_TOKEN=…). The token never appears in argv.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

GITEE_API = "https://gitee.com/api/v5"
REPO_OWNER = "start-up-china-2025"
REPO_NAME = "gradient"


def load_token(repo_root: Path) -> str:
    token = os.environ.get("GITEE_TOKEN", "").strip()
    if token:
        return token
    env_file = repo_root / ".env.gitee"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "GITEE_TOKEN" and value.strip():
                return value.strip()
    print(
        "error: GITEE_TOKEN not found. Set the env var or create .env.gitee "
        "with GITEE_TOKEN=… in the repo root.",
        file=sys.stderr,
    )
    sys.exit(1)


def current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def open_pull_request(token: str, title: str, body: str, head: str, base: str) -> dict:
    """POST via curl (urllib is unreliable against gitee.com); token goes via stdin."""
    url = f"{GITEE_API}/repos/{REPO_OWNER}/{REPO_NAME}/pulls"
    payload = json.dumps(
        {"access_token": token, "title": title, "body": body, "head": head, "base": base}
    )
    result = subprocess.run(
        [
            "curl", "-sS", "-X", "POST", url,
            "-H", "Content-Type: application/json",
            "-w", "\n%{http_code}",
            "-d", "@-",
        ],
        input=payload,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"error: curl failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    response_body, _, status_code = result.stdout.rpartition("\n")
    if not status_code.startswith("2"):
        print(f"error: Gitee API returned {status_code}: {response_body}", file=sys.stderr)
        sys.exit(1)
    return json.loads(response_body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body-file", required=True, type=Path)
    parser.add_argument("--head", default=None, help="source branch (default: current)")
    parser.add_argument("--base", default="master")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    token = load_token(repo_root)
    head = args.head or current_branch()
    if not head:
        print("error: could not determine current branch", file=sys.stderr)
        sys.exit(1)
    body = args.body_file.read_text()

    result = open_pull_request(token, args.title, body, head, args.base)
    print(f"PR #{result.get('number')}: {result.get('html_url')}")


if __name__ == "__main__":
    main()
