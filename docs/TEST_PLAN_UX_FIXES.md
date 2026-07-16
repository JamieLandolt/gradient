# Test Plan — UX/Reliability Fixes (2026-07-13 batch)

Covers the 7 fixes made in this batch (see conversation/PR for the original
issue list). Each section lists the automated tests added and the manual
steps to re-verify against a live/connected run (`AI_PROVIDER=openai_compatible`,
`make wake`) since several of these paths (recommendations, ingestion) were
only exercised in mock mode here.

## 1. History tab styling

- **Automated:** `frontend/src/features/history/HistoryPage.test.tsx` — asserts
  in-progress/planned rows render as `.course-card` inside a `.card-list`, with
  a `.status-badge.status-{status}` element instead of plain text.
- **Manual:** log in, go to History with at least one `in_progress` and one
  `planned` enrolment. Confirm the cards visually match Dashboard's course
  cards (border, hover lift, wedge motif) and the status badge is legible.

## 2. Study/degree plan generation (Planner page)

- **2a/2b (layout + collapsible warnings) — Automated:**
  `frontend/src/features/planner/PlannerPage.test.tsx` ("generating a plan
  sends the selected study load, and hides warnings behind a toggle") —
  asserts `info`-severity diagnostics are visible immediately, `warning`-
  severity ones are hidden until the `<details>` toggle is opened (checked via
  `toBeVisible()`, since jsdom doesn't apply the UA stylesheet that hides
  `<details>` content — presence alone isn't a valid check here).
- **2c (full/part-time target) — Automated:**
  `backend/tests/unit/planning/test_scheduler.py::TestTargetCoursesPerSemester`
  (pure scheduler behavior: fills to target, shortfall diagnostic only fires
  when genuinely fewer courses were eligible, no diagnostic without a target)
  and `backend/tests/api/test_planner_api.py::test_sequence_study_load_changes_courses_placed_per_semester`
  (full_time vs part_time produce different, deterministic per-semester counts
  end-to-end).
- **Manual:** on Planner, generate a plan as Full-time vs Part-time for the
  same start date — confirm the part-time plan places at most 2 courses/semester
  and full-time at most 4, and that a semester with fewer eligible courses than
  the target shows the "Only N courses were eligible…" message rather than
  silently under-filling. Click the "N prerequisites need manual checking"
  toggle and confirm it expands/collapses.

## 3. Recommendation performance

- **Automated:** `backend/tests/unit/test_advisory_service.py` (pure
  `_bounded_candidate_pool`: under-cap passthrough, over-cap truncation,
  interest-matches survive capping) and
  `backend/tests/api/test_ai_endpoints.py::TestAdvisory::test_regenerating_with_unchanged_inputs_hits_the_cache`
  (same inputs twice → same persisted recommendation id; changed interests →
  different id). Note: `conftest.py` has an autouse fixture clearing the
  module-level recommend cache between tests — required since the cache is
  process-global, not per-service-instance.
- **Manual (connected run):** with `AI_PROVIDER=openai_compatible`, time a
  "Recommend courses" call on a full imported catalogue; confirm the prompt
  sent to Bailian (check request logs, or a temporary print) is capped at 60
  candidates regardless of catalogue size, and that clicking "Regenerate" with
  unchanged interests returns instantly (within the 5-minute cache TTL) instead
  of making a fresh LLM call.

## 4. Viewing saved study plans (StudyPlanPage)

- **Automated:** `frontend/src/features/study-plans/StudyPlanPage.test.tsx` —
  View opens the plan inline under the row (converted from a `useMutation`
  read to a `useQuery`, matching the pattern already proven on PlannerPage's
  saved-plans view); Hide collapses it.
- **Manual:** generate and save two study plans for different courses, reload
  the page, click View on each — confirm both render inline without needing a
  full page refresh, and that a simulated network hiccup (e.g. throttle in
  devtools) shows a loading/error state next to the clicked row rather than
  nothing.

## 5. Assistant "thinking" indicator

- **Automated:** `frontend/src/features/assistant/AssistantPage.test.tsx`
  ("shows a typing indicator that persists after the first chunk arrives") —
  uses a controlled `ReadableStream` with a gated second chunk to prove the
  indicator survives past the first token, not just the pre-first-chunk gap.
- **Manual:** ask the assistant a question on a connected run with a
  deliberately slow/streaming response; confirm the animated dots stay visible
  for the whole answer, not just the first instant, and that screen-reader
  output (VoiceOver/NVDA) announces "Assistant is responding…" while streaming.

## 6. Merged Discover (Search + Recommendations) page

- **Automated:** `frontend/src/features/discover/DiscoverPage.test.tsx` —
  defaults to Search mode, switching to "Recommend for me" swaps the result
  set and hides the previous mode's results.
- **Manual:** confirm the old `/recommendations` and `/search` nav entries are
  gone, `/discover` is reachable from the nav as a single "Discover" link, and
  both modes still work end-to-end (search returns real pgvector matches,
  recommend still persists/lists/reuses the cache from item 3).

## 7. ECP import via web scraping

- **Automated:**
  - `backend/tests/unit/test_uq_fetcher.py` — `find_current_ecp_url` picks the
    first non-archive offering link and returns `None` when only archived
    offerings exist; `ECPFetcher` fetches+cleans, respects robots.txt, raises
    `ECPNotFoundError` when no current link exists, caches to disk;
    `fetch_ecp_text` composes the catalogue-fetch + ECP-fetch correctly.
  - `backend/tests/api/test_ai_endpoints.py::TestIngestion` — three new tests:
    successful scrape→extract with the network fetch stubbed, a job that fails
    cleanly when no current profile is found, and a 422 on an invalid course
    code (schema-level `^[A-Za-z0-9]+$` pattern, since the code is interpolated
    into the scraped URL).
  - `frontend/src/features/import/ImportPage.test.tsx` — entering a course
    code posts to `/ingestion/from-url` and disables paste/upload.
- **Manual (connected run, real network):** on Import, enter a real, current
  UQ course code (e.g. `COMP3506`) with no paste/upload — confirm it queues,
  polls to `extracted`, and the curator queue shows a new draft with sane
  assessment data. Then try a course code with only archived offerings (or a
  nonexistent one) — confirm it fails cleanly with a readable error, not a
  raw exception. Re-submit the same real code twice in quick succession and
  confirm the second reuses the cached profile version (FR-3.5.6) rather than
  re-scraping — the site's actual HTML structure can drift over time, so if
  this manual check ever fails, re-inspect the real page's markup before
  assuming the code regressed (the `_ECP_LINK` regex in `uq_fetcher.py` is the
  single place that structure is assumed).

## Running everything

```bash
# backend
cd backend && .venv/bin/python -m ruff check app tests && .venv/bin/python -m pytest

# frontend
cd frontend && npx tsc -b && npm run lint && npx vitest run
```

Both were green as of this batch (187 backend tests, 24 frontend tests).

---

# Follow-up batch: scheduler fix, embedding resilience, weekly study plan rework

Three more fixes, on top of the batch above.

## 8. Degree-sequence generator wasn't scheduling non-required prerequisites

**The bug:** `PlannerService._run` built its candidate pool from `merged.required
- completed` only. If a required course's prerequisite was itself merely an
*elective* for the program (or not listed at all), it was never added to the
candidate pool — so it could never be completed/placed, so the dependent
required course could never become eligible. The plan came back infeasible
(or, in less obvious cases, simply placed fewer than the study-load target
per semester) even though the student absolutely *could* take that course if
they took its prerequisite first.

**The fix:** `app/services/planner.py` now transitively expands the "to
plan" set: starting from `required - completed`, it walks each course's
prerequisite tree (`collect_course_codes`, already existed in
`prereq_ast.py`) and pulls in any referenced course that exists in the
catalogue, isn't already completed, and isn't already in the set — repeating
until nothing new is added (`_expand_with_prerequisites`, breadth-first over
the prereq graph).

- **Automated:**
  `backend/tests/api/test_planner_api.py::test_sequence_schedules_a_non_required_prerequisite_of_a_required_course`
  — constructs a fake catalogue where a required course's prerequisite
  (CSSE2002) is only listed as an *elective*, and asserts the generated plan
  is feasible with CSSE2002 scheduled before its dependent (previously this
  came back infeasible).
- **Manual:** on Planner, pick a program where a required course's listed
  prerequisite isn't itself required (check `program_courses` for the
  program) and generate a sequence — confirm the prerequisite now appears in
  the plan ahead of its dependent, and that full-time sequences reliably hit
  4 courses/semester where enough eligible courses genuinely exist.

## 9. ECP embedding step could fail the whole import ("SSL: UNEXPECTED_EOF")

**The bug:** `IngestionService._extract_and_draft` called
`self._providers.embeddings.embed(...)` as the last step before marking a job
`extracted`; an unguarded exception there (e.g. Bailian's documented
intermittent `SSL: UNEXPECTED_EOF_WHILE_READING`) failed the *entire* job even
though extraction and drafting had already succeeded. `AI_MAX_RETRIES`
defaulted to 1 (2 attempts total), which wasn't always enough for this known
flaky failure mode.

**The fix:**
- `backend/app/config.py`: `ai_max_retries` default 1 → 3 (4 attempts total);
  `backend/.env`'s explicit `AI_MAX_RETRIES=1` override updated to match (it
  would otherwise have silently negated the new default).
- `backend/app/services/ingestion.py`: the embedding call in
  `_extract_and_draft` is now wrapped in its own try/except — a failure there
  is logged and the draft is still saved/marked `extracted` (the course is
  just unsearchable via semantic search until a retry re-embeds it; nothing
  else depends on the embedding existing).
- **Automated:**
  `backend/tests/api/test_ai_endpoints.py::TestIngestion::test_embedding_failure_does_not_fail_the_ingestion_job`
  — monkeypatches the mock embedding provider to raise the exact reported SSL
  error, submits a real ECP paste, and asserts the job still reaches
  `extracted` with its draft version created.
  `backend/tests/unit/providers/test_openai_compatible.py::test_client_retries_then_raises_on_http_error`
  updated for the new attempt count (4, not 2).
- **Manual (connected run):** submit an ECP with `AI_PROVIDER=openai_compatible`
  during a period of known Bailian flakiness (or temporarily point
  `AI_BASE_URL` at an endpoint that resets connections) and confirm the job
  still reaches `extracted` — check server logs for the "Embedding failed for
  course ..." warning to confirm it degraded gracefully rather than silently
  succeeding by luck.

## 10. Weekly, multi-course study plan (replaces the old per-course generator)

**What changed:** the single-course, single-target-grade, linear-session
study plan generator is gone. In its place: a weekly time-block template
(`study_availability` — mark hours as `blocked` or `study`), per-assessment
target marks (`assessment_targets` — forward-looking, unlike `grades`) across
*every* in-progress course, and a deterministic weekly generator
(`app/domain/study/weekly_planner.py`) that places study blocks onto the
student's own `study` slots for one specific week, prioritising by weight ×
target × due-date urgency. No AI provider is involved (the old
`StudyPlanProvider` abstraction — mock and OpenAI-compatible implementations
— was removed entirely as part of this: see `git log` on
`app/providers/mock/study_plans.py`, now deleted).

New tables (migration `0011_weekly_study_plans.sql`, **not yet applied to the
live Supabase project** — run it before testing this live):
`assessment_targets`, `study_availability`, `weekly_study_plans`,
`weekly_study_blocks`. The old `study_plans`/`study_sessions` tables are
dropped in the same migration.

- **Automated:**
  - `backend/tests/unit/study/test_weekly_planner.py` — the pure allocation
    engine: empty inputs, weight-proportional allocation, due-date urgency,
    default/explicit target marks in the focus text, never over-allocating
    beyond available slots, shortfall diagnostics when an item gets zero or
    partial hours, slot fill order.
  - `backend/tests/api/test_ai_endpoints.py::TestAdvisory` — end-to-end
    generation (availability + enrolment → `POST /study-plans/generate`
    returns blocks tagged with the right course), remaining-assessments
    excludes graded items and round-trips targets, generation fails cleanly
    (422) with no study slots set.
  - `backend/tests/api/test_ai_endpoints.py::TestPersistence` — saved weekly
    plans persist/list/fetch/delete, and are isolated per user.
  - `frontend/src/features/study-plans/StudyPlanPage.test.tsx` — View/Hide a
    saved plan inline; clicking a grid cell cycles free → study → blocked →
    free and saves; generating renders blocks and diagnostics.
- **Not yet verified:** a live browser check of the new weekly grid UI was
  deliberately skipped this session — it sits behind auth and would have
  required waking the live/connected Supabase project and creating a
  throwaway account just to reach it. Do this before considering the feature
  done:
  1. `supabase db push` (or equivalent) to apply migration `0011`.
  2. `make wake`, log in, enrol in an in-progress course with assessments.
  3. On the reworked Study Plan page: mark a few weekly slots as `study` and
     a few as `blocked`, save the template; set a target mark on a remaining
     assessment; generate a plan for the current week and confirm the grid
     renders sensibly (course codes in the right cells, no visual overlap,
     readable on a normal browser width); save it, reload the page, View it
     back, then Delete it.
  4. Confirm removing the old `/study-plans` behaviour didn't leave a stale
     nav link or dead route anywhere (`frontend/src/App.tsx`,
     `frontend/src/components/Layout.tsx` both already point at the same
     `StudyPlanPage` component, so nothing should need touching, but check).
