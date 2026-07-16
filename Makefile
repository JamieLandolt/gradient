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

# Wake a paused free-tier Supabase project before a demo.
# Queries a real table: PostgREST's root returns 401 without an Authorization
# header even for a valid key, so `curl -sf` against it always failed and this
# check reported "asleep" on a perfectly healthy project.
wake:
	@test -n "$$SUPABASE_URL" || (echo "Set SUPABASE_URL" && exit 1)
	@test -n "$$SUPABASE_ANON_KEY" || (echo "Set SUPABASE_ANON_KEY" && exit 1)
	@curl -sf "$$SUPABASE_URL/rest/v1/courses?select=code&limit=1" \
		-H "apikey: $$SUPABASE_ANON_KEY" \
		-H "Authorization: Bearer $$SUPABASE_ANON_KEY" > /dev/null \
		&& echo "awake" \
		|| (echo "asleep or unreachable — open the Supabase dashboard" && exit 1)

# Promote a user to curator: make promote-curator EMAIL=someone@example.com
promote-curator:
	@test -n "$(EMAIL)" || (echo "Usage: make promote-curator EMAIL=…" && exit 1)
	$(PY) seed/promote_curator.py "$(EMAIL)"
