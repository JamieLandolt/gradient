#!/usr/bin/env python3
"""Promote a registered user to the curator role.

Usage:  backend/.venv/bin/python seed/promote_curator.py someone@example.com
Requires backend/.env with the service-role key (bypasses the role-change guard).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "seed"))

from load_seed import load_backend_env  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: promote_curator.py <email>")
    email = sys.argv[1]

    env = load_backend_env()
    from supabase import create_client

    db = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])

    users = db.auth.admin.list_users()
    match = next((u for u in users if u.email == email), None)
    if match is None:
        sys.exit(f"error: no registered user with email {email}")

    db.table("profiles").update({"role": "curator"}).eq("id", match.id).execute()
    print(f"{email} is now a curator.")


if __name__ == "__main__":
    main()
