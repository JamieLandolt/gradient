.PHONY: backend-install frontend-install install backend-dev frontend-dev \
	backend-test frontend-test test lint ci seed migrate wake promote-curator up down

PYTHON := python3
BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

# ── Install ─────────────────────────────────────────────────────────────────
backend-install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND)/requirements.txt

frontend-install:
	cd $(FRONTEND) && npm install

install: backend-install frontend-install

# ── Dev servers ─────────────────────────────────────────────────────────────
backend-dev:
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend-dev:
	cd $(FRONTEND) && npm run dev

# ── Tests & quality gate ────────────────────────────────────────────────────
backend-test:
	cd $(BACKEND) && .venv/bin/python -m pytest --cov=app --cov-report=term-missing

frontend-test:
	cd $(FRONTEND) && npx vitest run --coverage

test: backend-test frontend-test

lint:
	cd $(BACKEND) && .venv/bin/python -m ruff check app tests
	cd $(FRONTEND) && npm run lint

# Full local CI gate — run before every phase PR
ci: lint test

# ── Containers (one-command demo against hosted Supabase) ───────────────────
up:
	docker compose up --build

down:
	docker compose down

# ── Database ────────────────────────────────────────────────────────────────
migrate:
	supabase db push

seed:
	$(PY) seed/load_seed.py

# Wake a paused free-tier Supabase project before a demo
wake:
	@test -n "$$SUPABASE_URL" || (echo "Set SUPABASE_URL" && exit 1)
	curl -sf "$$SUPABASE_URL/rest/v1/" -H "apikey: $$SUPABASE_ANON_KEY" > /dev/null && echo "awake"

# Promote a user to curator: make promote-curator EMAIL=someone@example.com
promote-curator:
	@test -n "$(EMAIL)" || (echo "Usage: make promote-curator EMAIL=…" && exit 1)
	$(PY) seed/promote_curator.py "$(EMAIL)"
