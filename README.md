# Gradient

Grade tracking & degree planning for University of Queensland students.

Gradient lets a student record assessment marks in one dashboard, see exactly what
average they still need on remaining assessment to hit a target grade on the UQ 1–7
scale (including hurdle conditions), keep a history of completed courses with GPA/WGPA,
and plan a valid course sequence around prerequisites — including dual degrees.
AI-assisted features (course recommendations, study plans, ECP import, semantic search)
are advisory only; all grade arithmetic and prerequisite logic is deterministic code.

Built from `Gradient_SRS_Master.md` (IEEE-830 SRS).

> Gradient's outputs are **estimates to support your own decisions**. Your course's
> ECP and official university records remain authoritative.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React + Vite + TypeScript, React Router, TanStack Query, supabase-js (auth) |
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| Database | Supabase (PostgreSQL + pgvector, Auth, Storage, RLS) |
| AI providers | Pluggable (`AI_PROVIDER=mock` in v1 — deterministic mocks) |

## Getting started

Prerequisites: Python 3.11+, Node 20+, the Supabase CLI, and a Supabase project.

```bash
# 1. Install dependencies
make install

# 2. Configure environment
cp .env.example backend/.env    # fill in Supabase URL + keys
cp .env.example frontend/.env   # fill in the VITE_ values

# 3. Apply database migrations and seed sample UQ courses
supabase link --project-ref <your-project-ref>
make migrate
make seed

# 4. Run
make backend-dev    # http://localhost:8000 (API docs at /docs)
make frontend-dev   # http://localhost:5173
```

## Development

- `make test` — backend pytest with coverage + frontend vitest with coverage
- `make lint` — ruff + eslint
- `make ci` — the full local quality gate (run before every PR)
- `make promote-curator EMAIL=…` — grant the curator role for ECP review
- `make wake` — ping a paused free-tier Supabase project before a demo

Each development phase ships as its own pull request. See `docs/architecture.md`
for the system design and `docs/api.md` for the endpoint reference.
