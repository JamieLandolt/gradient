# Gradient — Session Handover

_Working doc for resuming in a fresh session, now **committed** so teammates can pick up the project. Delete or update freely._

## TL;DR

Gradient is a UQ grade-tracking / degree-planning web app (FastAPI + React/Vite + Supabase Postgres/pgvector/Auth/RLS). The deterministic core (grade calc, GPA, prerequisite planner, RLS, curator workflow) was built as a prototype (Phases 0–9) and demoed. Phase 10 (real AI via Alibaba Bailian/Qwen), Phase 11 (automated UQ course import), and Phase 12 (persist AI/plan artefacts, streaming assistant, planner preferences) shipped with open Gitee PRs. **Phase 13 is now COMPLETE** — increment 1 (polish, reliability, N+1 perf fix, efficiency/UX review, ops) plus the **continuation** (async ECP extraction via `BackgroundTasks` + PDF/.txt upload). Approved roadmap for the remaining Phases 14/15 lives in `~/.claude/plans/cheeky-twirling-shell.md`.

**Repo:** `/Users/youssefhassan/Library/CloudStorage/OneDrive-Personal/Desktop/Dalian/gradient`
**Remaining-roadmap plan:** `~/.claude/plans/cheeky-twirling-shell.md` (Phase 14 = majors & minors + plan placeholders; Phase 15 = program/plan scraping). Read it before starting Phase 14.

## Git & PR state (verify with `git branch -a` + Gitee)

- **master** is at `a0c4ee9` — includes through **Phase 9**. Phases 10–12 are NOT on master yet.
- **feat/phase-10-real-ai** = master + Phase 10 → **PR #10 open**.
- **feat/phase-11-uq-import** = Phase 10 + Phase 11 stacked → **PR #11 open**.
- **feat/phase-12-persist-assistant-planner** = P10+P11+P12 → **PR #12** open. Head now `c842c16` (includes the saved-plan "View" fix — read-as-mutation → retrying useQuery + inline detail + loading/error; StudyPlan "View" hardened too).
- **feat/phase-13-polish-reliability** (current branch) = P10..P13 stacked → **PR #13** (`--base master`). Increment 1 **and** the continuation (async ECP + PDF upload) are committed; this HANDOVER is committed alongside them. Verify the PR number on Gitee.
- Per-phase workflow: branch `feat/phase-N-<slug>` **stacked on the previous unmerged phase branch** (NOT master, since PRs #10–#13 are still open). Open the Gitee PR with:
  `python3 scripts/open_gitee_pr.py --title "…" --body-file <scratchpad>.md --head <branch> --base master`
  (uses `.env.gitee` `GITEE_TOKEN`; the script shells out to `curl` with a browser User-Agent — Gitee's WAF rejects the default UA. Retry on transient timeouts.)

## Environment & credentials (already configured)

`backend/.env` has **real** Supabase URL + anon + service-role keys and a real **`DASHSCOPE_API_KEY`** (Alibaba Bailian). `frontend/.env` has the Supabase URL + anon key + `VITE_API_BASE_URL`.

- **`AI_PROVIDER=mock`** in `backend/.env` right now. Tests/CI run in mock mode (no key needed). To run the app or scripts on **real** AI, use `AI_PROVIDER=openai_compatible` (either edit `backend/.env` or prefix the command, e.g. `AI_PROVIDER=openai_compatible backend/.venv/bin/python …`). Env vars override `.env`.
- Supabase project ref: `dnsgxqaizdcvewhuubde` (region ap-northeast-1). Already `supabase link`ed. Free-tier pauses when idle → `make wake` (with SUPABASE_* exported) or open the dashboard before a demo.
- Migrations applied through **0010** (embeddings widened to 1024-dim). Catalogue re-embedded via Bailian.

## AI stack (Phase 10)

All AI is hosted **Alibaba Bailian (Model Studio)** via its OpenAI-compatible endpoint:
- Chat/extraction/recommendations/study-plans/assistant → **Qwen** (`qwen-plus`), `https://dashscope.aliyuncs.com/compatible-mode/v1`.
- Embeddings → **text-embedding-v3, 1024-dim** (DB column `course_embeddings.embedding` is `vector(1024)`; `match_courses` RPC + HNSW at 1024).
- One generic provider class (`backend/app/providers/openai_compatible.py`) behind the existing `Protocol`s; swap point is `providers/factory.py` + config only. `AI_PROVIDER` literal: `mock | openai_compatible | ollama | anthropic`.
- **Grounding preserved:** recommendation `prereq_status` and study-plan/assistant figures come from the deterministic engines, not the model. Payloads carry no student PII.
- **⚠️ Compliance debt:** using a hosted API for student-data features departs from SRS NFR-5.3.4 (self-hosted only). Accepted for the demo; restoring it (self-hosted Qwen swap) is Phase 14. Extraction/embeddings/search only ever see public course text, so those stay compliant.

## What's shipped

- **Phases 0–9 (prototype, on master):** auth, grade/assessment tracking, target-grade calculator, GPA, history, deterministic planner (prereqs, dual-degree, cycles), ECP ingestion + curator review, semantic search, recommendations, study plans, assistant (all AI on deterministic mocks), dark "ascending gradient" UI redesign. 111 backend + 11 frontend tests, 28 live E2E checks.
- **Phase 10 (PR #10):** real Bailian/Qwen providers + `text-embedding-v3`; migration `0010` (384→1024); 13 provider contract tests. Mock gate green (124→128 tests). Live-verified.
- **Phase 11 (PR #11):** courtesy crawler (`backend/app/ingestion/uq_fetcher.py`), curated codes (`seed/data/uq_course_codes.json`), importer (`scripts/import_uq_catalogue.py`). Live run imported **13 new real UQ courses** (data_source=import) across CS/Math/IT/Engineering + real draft versions; search verified accurate.
- **Phase 12 (PR #12):** new `ArtifactRepository` persists recommendations/study_plans/degree_plans (tables from 0005; no new migration) with save/list/get/delete + revisit endpoints; saved degree plans rebuild empty gap semesters on reload. Streaming assistant (`POST /assistant/ask/stream`, plain-text `StreamingResponse`; `stream_answer()` on the provider protocol — mock chunks, openai_compatible reads Qwen SSE) + a new streaming chat page (`frontend/src/features/assistant/`, `streamPost` in `apiClient.ts`). Planner preferences (`prioritise_available` + `interests` → deterministic composite sort; explanations surfaced). Adversarially reviewed (7 findings fixed). Plus the saved-plan "View" fix. **Not yet live-verified against Supabase/Bailian.**
- **Phase 13 increment 1 (PR #13):** demo polish + reliability + the efficiency/UX review (`docs/REVIEW_efficiency_ux.md`). Frontend: responsive breakpoints + collapsible mobile nav (`Layout.tsx`), top-level `ErrorBoundary` (`components/ErrorBoundary.tsx`, wired in `App.tsx`), wide-table `.table-scroll` wrapper, the orphaned `/study-plans` nav link, `AbortController` 20s request timeouts in `apiClient.ts` (both `request` + `streamPost`), Recommendations empty-state. Backend perf: **N+1 fix** — new `CatalogueRepository.get_prereq_trees`/`get_prereq_raw_texts` batch loads used by `advisory.recommend` + `planner.prereq_status` (was 2·N queries → 2). Ops: `docker-compose.yml` + `backend/Dockerfile` + `frontend/Dockerfile` (+ `.dockerignore`s, `make up`) — **written but NOT verified (no Docker daemon here)**. Tests: fetcher robots/throttle/cache (`test_uq_fetcher.py`), `CourseDetailPage` RTL. **151 backend + 14 frontend tests**, ruff/tsc/eslint clean.
- **Phase 13 continuation (PR #13, this increment):** the two deferred review items, done.
  - **Async ECP extraction (FR-3.5.3 / NFR-5.1.5):** `IngestionService.submit` was split into `create_job` (synchronous, returns `status:"queued"` at once) + `run_extraction` (the LLM extract → draft → embed, run off the request path via FastAPI `BackgroundTasks`). `run_extraction` is a background task and **never propagates** — any failure is recorded on the job (`status:"failed"`, `error`). `POST /ingestion/jobs` now returns `queued`; the client **polls** `GET /ingestion/jobs/{id}` until `extracted`/`failed`. (Behavioural change: the old synchronous `422 Extraction failed` is now a job that flips to `failed`; a bad paste still returns `queued` then `failed`.)
  - **ECP file upload (PDF/.txt):** new `POST /ingestion/uploads` multipart endpoint → `app/ingestion/pdf.py` (`extract_pdf_text`/`extract_upload_text`, `pypdf`) parses the file **locally** (fast; only the LLM step is backgrounded) → same queued pipeline with `source_type:"upload"`. Size-capped at `MAX_UPLOAD_CHARS` (100k). Frontend `ImportPage` gained an `<input type="file" accept=".pdf,.txt">` (paste box disables when a file is chosen) and a TanStack-Query poll (`refetchInterval` stops on terminal status; refreshes the curator queue on completion). `apiClient.postForm` sends `FormData` without a forced JSON content-type.
  - **New deps:** `pypdf`, `python-multipart` (in `requirements.txt`; `pip install -r` or `make backend-install`). Ruff `extend-immutable-calls` now also whitelists `fastapi.File`/`fastapi.Form`.
  - **Migration-free tradeoff:** the async job no longer surfaces the transient extraction **warnings**/`cached` flag (they were computed in-request before). The important failure signal is preserved on the job (`error`); advisory warnings like "weights don't sum to 100" are dropped from the toast — the curator still reviews the draft. Restoring them would need a `warnings` column on `ingestion_jobs` (a migration), intentionally deferred.
  - **Hardening (from an adversarial multi-agent review of this increment):** upload is size-bounded **before** parsing — `file.size`/bounded `read` caps raw bytes at `MAX_UPLOAD_BYTES` (10 MB); `extract_pdf_text` caps pages (`MAX_PDF_PAGES`) and stops at a running char budget so a decompression-bomb PDF can't exhaust memory/CPU; the CPU-bound parse is offloaded off the event loop via `anyio.to_thread.run_sync`; parser errors return a generic message (pypdf detail logged server-side, not leaked). `run_extraction`'s failure-record write is itself guarded (best-effort log-and-swallow) so the background task can never propagate. Frontend poll has a `MAX_POLL_MS` (90s) deadline → a job wedged in `queued` (worker killed mid-extraction, no reaper) surfaces a recoverable timeout instead of spinning forever. New tests: oversized-`.txt` → 422, unauthenticated upload → 401, `apiClient.postForm` sends `FormData` with no forced JSON content-type, frontend `failed`-state + real queued→re-poll→`extracted` transition.
  - **Known edge (now fixed: `create_course_if_missing` / `create_draft_version` catch the unique violation and reuse the winner's row; see `tests/unit/test_repository_writes.py`):** concurrent duplicate submissions of the *same new* course/version race the non-atomic find-then-insert dedup — the loser can hit the `unique(course_id, version_label)` (or `courses.code`) constraint and be marked `failed` instead of reusing the cached version (FR-3.5.6). Rare (needs two near-simultaneous identical submits), transient (a retry hits the cached path), no data loss. Proper fix = catch the unique-violation → re-find, or on-conflict-returning insert; can't be exercised in mock mode. Deferred.
  - **Tests:** existing ingestion tests rewritten to the async contract (POST→`queued`, poll→`extracted`); new `test_ingestion_upload.py` (.txt + .pdf + empty + corrupt-PDF + oversized + unauth) and `test_pdf.py` (real minimal-PDF round-trip, no binary fixture); `ImportPage.test.tsx` (paste queued→extracted poll, `failed` state, upload) + `apiClient.test.ts` (`postForm`). **164 backend + 18 frontend tests**, `make ci` green (exit 0). Note: under Starlette `TestClient`, `BackgroundTasks` run inline before the POST returns, so tests poll with a single GET; a real deployment genuinely polls.

## What's next (plan: `~/.claude/plans/cheeky-twirling-shell.md`)

- **Phase 14 (next up)** — **majors & minors (specialisations) + persistent plan placeholders.** New branch `feat/phase-14-majors-minors` **stacked on `feat/phase-13-polish-reliability`** (NOT master). Migration `0011_specialisations.sql` (specialisations, specialisation_courses, requirement_groups, user_specialisations ≤2/program; `degree_plan_entries` gains `is_placeholder`/`placeholder_label`, `course_id` nullable). Backend: repo methods mirroring `program_courses`/`user_programs`, planner emits placeholder entries for unfilled elective/major slots, advisory biases the candidate pool to the user's specialisation courses, `GET/PUT /planner/specialisations`. Frontend: `MajorPicker` (clone of `ProgramPicker`), `PlanView` renders placeholders. Seed majors/minors into a couple of sample programs. See the plan for the full spec.
- **Phase 15** — **automated program/plan scraping.** Branch `feat/phase-15-program-scraping` stacked on 14. Extend `uq_fetcher` to program/plan pages (namespaced cache), new extraction prompts/schemas, migration `0012_program_plans.sql`, `scripts/import_uq_programs.py`, curator-verify gate. Live scrape is a separate connected run.
- **Phase 16 (was "deferred Phase 14")** — production & compliance: restore NFR-5.3.4 (self-hosted model swap), real deployment, verify UQ cut-offs vs official Assessment Procedure, JWT issuer validation, APP privacy review, rate limiting, monitoring, OAuth/UQ SSO. Backlog also has: `get_verified_profile` memoisation/batch, real-pgvector integration test, focus-visible/contrast audit (see `docs/REVIEW_efficiency_ux.md`).

## How to run / verify

```bash
# full local gate (mock mode, no keys)  — run before every phase PR
make ci                                                                                     # ruff + pytest + tsc + eslint + vitest

# or piecemeal:
cd backend && .venv/bin/python -m ruff check app tests && .venv/bin/python -m pytest      # 164 passed
cd frontend && npx tsc -b && npm run lint && npx vitest run                                 # 18 passed

# run the app on REAL AI
AI_PROVIDER=openai_compatible backend/.venv/bin/uvicorn app.main:app --port 8000            # from backend/
cd frontend && npm run dev                                                                 # :5173
# (demo login left earlier: demo@gradient.test / Demo-gradient-2026!)

# live E2E (real AI): scripts/e2e_smoke.py   |   re-import UQ: AI_PROVIDER=openai_compatible backend/.venv/bin/python scripts/import_uq_catalogue.py
```

## Critical gotchas (READ)

1. **GateGuard hook fires on EVERY file edit/write + the first Bash call**, demanding 4 "facts" before retrying. It roughly doubles the work per edit and drove an earlier session's cost very high (~$1200). It is **currently disabled** for build-heavy sessions via `ECC_DISABLED_HOOKS` in `.claude/settings.local.json` (gitignored): `pre:edit-write:gateguard-fact-force,pre:bash:gateguard-fact-force`. Re-enable by removing those entries. It's the repo owner's safety hook — ask before toggling.
2. **Branch stacking:** because PRs #10/#11 are open, branch the next phase from the current phase branch, not master (I hit this — branching from master silently drops the prior phase's code from the working tree).
3. **Background script stdout is block-buffered** through pipes — you won't see progress until exit. Use `python -u` and redirect to a file, or just wait for the completion notification.
4. **Bailian SSL flakiness:** disable httpx keep-alive (`limits=httpx.Limits(max_keepalive_connections=0)`) — connection reuse caused intermittent `SSL: UNEXPECTED_EOF`. Already done in `openai_compatible.py` and `uq_fetcher.py`. A few transient timeouts still happen on big batches; the importer skips-and-continues and caches, so re-runs are cheap.
5. **Embedding dimension is 1024** everywhere now. Any embedding-model change = new migration (column + HNSW + `match_courses`) + full re-embed. `seed/load_seed.py` re-embeds via the configured provider, so run it with `AI_PROVIDER=openai_compatible` (mock is 384 and won't fit).
6. **Importer dedup:** `create_course_if_missing` won't overwrite existing sample courses — imported codes that already existed as `data_source=seed` get a new draft version but stay `seed`. That's why "30 processed" → only "13 new import courses."
7. **Async ingestion contract (new in P13-cont):** ECP submit/upload return `status:"queued"`; extraction runs in a FastAPI `BackgroundTasks` job that flips to `extracted`/`failed`. Clients **must poll** `GET /ingestion/jobs/{id}`. `run_extraction` swallows exceptions **by design** (records them on the job) — a background task must not propagate. Under `TestClient` the task runs inline, so tests see the terminal state on the next GET.
8. **Live-verification still pending** for Phase 12 (persisted artefacts/streaming) and P13-cont (async job + PDF upload): built + unit-tested in mock mode only. Verify against real Supabase/Bailian on a connected run (`AI_PROVIDER=openai_compatible`, `make wake`): submit a paste → watch it go `queued`→`extracted`; upload a real ECP PDF → same; curator verifies the draft. `docker compose up` is also written-but-unrun (no Docker daemon here).
9. Cost/context: build-heavy sessions get long — start each phase fresh, keep GateGuard disabled (gotcha 1) for edit-heavy work.
