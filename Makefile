.PHONY: backend-install frontend-install install backend-dev frontend-dev \
	backend-test frontend-test test lint ci seed migrate wake promote-curator

PYTHON := python3
BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv

# Cross-platform venv binary directory
ifeq ($(OS),Windows_NT)
	VENV_BIN := $(VENV)/Scripts
else
	VENV_BIN := $(VENV)/bin
endif

PY := $(VENV_BIN)/python

# ── Install ─────────────────────────────────────────────────────────────────
backend-install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r $(BACKEND)/requirements.txt

frontend-install:
	cd $(FRONTEND) && npm install

install: backend-install frontend-install

# ── Dev servers ─────────────────────────────────────────────────────────────
backend-dev:
	cd $(BACKEND) && $(PY) -m uvicorn app.main:app --reload --port 8000

frontend-dev:
	cd $(FRONTEND) && npm run dev

# ── Tests & quality gate ────────────────────────────────────────────────────
backend-test:
	cd $(BACKEND) && $(PY) -m pytest --cov=app --cov-report=term-missing

frontend-test:
	cd $(FRONTEND) && npx vitest run --coverage

test: backend-test frontend-test

lint:
	cd $(BACKEND) && $(PY) -m ruff check app tests
	cd $(FRONTEND) && npm run lint

# Full local CI gate — run before every phase PR
ci: lint test

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
