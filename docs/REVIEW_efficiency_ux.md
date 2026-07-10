# Gradient — Efficiency & UX Review (Phase 13)

A full read-through of the app for performance, UX consistency, accessibility, and
reliability. Items marked **✅ fixed in Phase 13** were applied on this branch; the rest
are a prioritised backlog. Severity: **P1** ship-blocking-ish, **P2** should-fix, **P3** nice.

## Performance / efficiency

1. **N+1 prerequisite loads (P1) — ✅ fixed.** `AdvisoryService.recommend` and
   `PlannerService.prereq_status` called `CatalogueRepository.get_prereq_tree(course_id)`
   **once per course** (each = a `prerequisite_nodes` query + a `courses` lookup), so
   generating recommendations over a growing catalogue was O(N) round-trips (2N+). Added
   `get_prereq_trees(course_ids)` / `get_prereq_raw_texts(course_ids)` that load everything
   in **two queries total**; `recommend` and `prereq_status` now use them. `prereq_status`
   also dropped a per-code `get_course` call in favour of one `list_courses()` map.
2. **Repeated `get_verified_profile` (P2).** `TrackingService` re-fetches the verified
   profile (version + assessments + cut-offs) separately in `assessment_rows`, `grade_cutoffs`,
   and again per standing/required-marks call. For a dashboard rendering many courses this
   repeats. *Fix:* memoise per request, or batch-load verified profiles for a set of course ids.
3. **Search embeds every query live (P2).** `/search/courses` calls the embedding provider on
   each keystroke-driven request with no debounce server-side and no caching of common queries.
   *Fix:* short-TTL cache on `(query → embedding)`, and debounce on the client.
4. **Client over-fetch (P3).** Several pages fetch `/enrolments` independently
   (Dashboard, StudyPlan, Assistant). TanStack Query already dedupes within `staleTime` (30s),
   so this is minor, but a shared `useEnrolments()` hook would make it explicit.

## Reliability

5. **Client request timeouts (P2) — ✅ fixed.** `apiClient.request` and `streamPost` had no
   timeout, so a hung Bailian call froze the UI forever. Added a 20s `AbortController` guard on
   the connection/headers phase (cleared once the Response arrives, so long assistant streams
   are never cut off).
6. **Top-level error boundary (P2) — ✅ fixed.** A render throw previously produced a blank
   white screen. Added `ErrorBoundary` around the router with a friendly reload card.
7. **Sync-in-request ECP extraction (P1) — deferred to Phase 13-cont.** `IngestionService.submit`
   runs the LLM extraction inline in the POST handler (can exceed the NFR-5.1.5 15s budget and
   ties up a worker). *Fix:* FastAPI `BackgroundTasks`; return `queued`; `ImportPage` polls
   `GET /ingestion/jobs/{id}` (needs a client poll loop added — it currently reads the terminal
   job once).
8. **No backend rate limiting (P2).** The unauthenticated `/search/courses` and the auth
   endpoints are unbounded. *Fix (Phase 16):* slowapi / a reverse-proxy limiter.

## UX & consistency

9. **Responsive / mobile (P1) — ✅ fixed.** Zero breakpoints existed; the 8-link nav wrapped
   into stacked rows and wide tables clipped on phones. Added breakpoints (≤900/≤640px), a
   collapsible hamburger nav, single-column stacking of forms/plan grids, and an
   `overflow-x:auto` wrapper around the CourseDetail assessment table.
10. **Orphaned route (P2) — ✅ fixed.** `/study-plans` had no nav link (reachable only by URL).
    Added a **Study plans** nav link.
11. **Saved-plan "View" was a read-as-mutation (P1) — ✅ fixed on PR #12 branch.** It used
    `useMutation` (no retry, no cache, no loading UI) so a transient hiccup failed silently.
    Converted to a retrying `useQuery`, rendered inline with loading/error/Hide feedback.
12. **Thin AI empty-states (P3) — partly ✅.** Recommendations now shows a "no matches" empty
    state. Search already had one; a shared loading/empty/error pattern would reduce drift.
13. **ECP file upload (P2) — deferred to Phase 13-cont.** Import is paste-only; ECPs are PDFs.
    Add a file input + a backend `upload` path (pypdf), wiring the already-defined
    `source_type:"upload"`.

## Accessibility (WCAG 2.2 AA spot-check)

14. **Good:** form controls are labelled (`aria-label`), errors use `role="alert"`, the
    assistant announces its finished answer once via an `sr-only role="status"` (fixed in P12),
    live regions on results.
15. **Gaps (P2/P3):** the hamburger toggle now sets `aria-expanded`/`aria-controls` (✅); colour
    contrast of `--muted` on `--surface` should be checked against 4.5:1; focus-visible styling
    is browser-default (add a visible focus ring for keyboard users).

## Testing gaps (see Phase 13 tests)

16. **✅ added:** `uq_fetcher` robots/throttle/cache tests; a `CourseDetailPage` RTL test.
17. **Deferred:** a real-Postgres/pgvector integration test (the `match_courses` RPC + 1024-dim
    column are only exercised by an in-memory cosine fake), `ImportPage` upload/poll tests, and
    Planner/Recommendations RTL. Recommend gating the pgvector test on a `GRADIENT_TEST_DB` env
    var so the mock CI stays green.

## Ops

18. **docker-compose (P2) — added, not locally verified.** `docker compose up` for backend +
    frontend against hosted Supabase. Written to standard patterns but not run here (no Docker
    daemon in the dev environment); verify on a machine with Docker before relying on it.

---

### Prioritised backlog after this phase
1. Async ECP extraction + `ImportPage` polling (P1, item 7).
2. ECP PDF upload (P2, item 13).
3. `get_verified_profile` memoisation / batch (P2, item 2).
4. Real-pgvector integration test (item 17).
5. Rate limiting + focus-visible + contrast audit (Phase 16).
