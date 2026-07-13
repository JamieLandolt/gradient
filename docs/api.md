# Gradient — API Reference

> All endpoints are under `/api/v1` and return the envelope
> `{"success": bool, "data": …, "error": str|null, "meta": …}`.
> Authenticated endpoints require `Authorization: Bearer <supabase access token>`.
> Interactive docs: `http://localhost:8000/docs` when the backend is running.
> This file is updated as each phase lands.

## Health

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | none | Liveness check |

## Catalogue (public)

| Method | Path | Description |
| --- | --- | --- |
| GET | `/courses` | List the course catalogue |
| GET | `/courses/{code}` | Course with offering periods + raw prerequisite text |
| GET | `/courses/{code}/profile` | Latest **verified** profile (assessments, cut-offs); 404 if none |
| GET | `/programs` | Programs with required/elective course codes |

## Guest calculator (public, stateless — FR-3.1.5)

| Method | Path | Description |
| --- | --- | --- |
| POST | `/calculator/what-if` | `{items:[{name,weight,max_mark?,score?,hurdle_min_percent?}], target_grade, grade_cutoffs?}` → required average, boundary status, per-item breakdown, hurdle warnings, standing |

## Enrolments, grades, calculation (auth)

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/enrolments` | List / add (`course_code, year, semester, status, is_transfer…`) |
| PATCH/DELETE | `/enrolments/{id}` | Update status/final grade, remove |
| GET | `/enrolments/{id}/standing` | Secured %, best/worst case, projected grade, items with scores |
| POST | `/enrolments/{id}/required-marks` | `{target_grade, what_if_scores?}` → FR-3.3.x result |
| POST | `/enrolments/{id}/assessments` | Add a custom item (no verified profile) |
| PATCH/DELETE | `/assessments/custom/{id}` | Edit/remove a custom item |
| PUT | `/enrolments/{id}/grades` | Upsert a mark (`assessment_id` xor `custom_assessment_id`, `score`) |
| DELETE | `/grades/{id}` | Remove a mark |
| GET | `/me/gpa` · `/me/history` | Unit-weighted GPA · full course record |

## Planner (auth)

| Method | Path | Description |
| --- | --- | --- |
| GET/PUT | `/planner/programs` | Get/set the student's 1–2 programs |
| GET | `/planner/prereq-status` | met / partially_met / not_met per program course |
| POST | `/planner/sequence` | `{start_year, start_semester, max_units_per_semester?, prioritise_available?, interests?[]}` → semester plan + diagnostics (preferences re-order deterministically; explanations surfaced per course — FR-3.6.6) |
| GET | `/planner/plans` | List the student's saved degree plans (FR-3.6.2) |
| POST | `/planner/plans` | Generate a sequence (same body as `/sequence` + `name`) and save it |
| GET/DELETE | `/planner/plans/{id}` | Fetch / delete a saved degree plan |

## Ingestion & curation

| Method | Path | Description |
| --- | --- | --- |
| POST | `/ingestion/jobs` | Submit ECP **text** → returns `status:"queued"`; extraction runs in the background (poll the job) |
| POST | `/ingestion/uploads` | Submit an ECP **PDF/.txt** (multipart `file`, optional `source_ref`) → parsed locally → same queued pipeline |
| GET | `/ingestion/jobs/{id}` | Poll job status (own jobs only): `queued` → `extracted` \| `failed` |
| GET | `/curator/profile-versions` | Draft queue (curator role) |
| POST | `/curator/profile-versions/{id}/verify` · `/reject` | Review actions (curator role) |

## Advisory & search

| Method | Path | Description |
| --- | --- | --- |
| POST | `/recommendations/generate` | `{interests[], limit}` → ranked advisory suggestions (persisted) |
| GET | `/recommendations/latest` | Most recent saved recommendation set (or `null`) |
| GET/DELETE | `/recommendations` · `/recommendations/{id}` | List saved sets / delete one |
| POST | `/study-plans/generate` | `{enrolment_id, target_grade, start_date?}` → study sessions (persisted) |
| GET | `/study-plans` · `/study-plans/{id}` | List saved plans / fetch one with sessions |
| DELETE | `/study-plans/{id}` | Delete a saved study plan |
| GET | `/search/courses?q=…` | Semantic search over course descriptions (public) |
| POST | `/assistant/ask` | Grounded Q&A over the student's own figures |
| POST | `/assistant/ask/stream` | Same, streamed token-by-token as `text/plain` (FR-3.9.3) |

## Account (auth)

| Method | Path | Description |
| --- | --- | --- |
| GET/PATCH | `/me` | Profile + programs / update display name |
| DELETE | `/me` | Delete account and all owned data (FR-3.1.4) |
