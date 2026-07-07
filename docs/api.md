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

## Planned surface (per SRS / implementation plan)

- Courses & programs (public read): `GET /courses`, `GET /courses/{code}`,
  `GET /courses/{code}/profile`, `GET /programs`, `GET /programs/{id}`
- Enrolments: `GET|POST /enrolments`, `PATCH|DELETE /enrolments/{id}`
- Assessments & grades: `POST /enrolments/{id}/assessments`,
  `PATCH|DELETE /assessments/custom/{id}`, `PUT /enrolments/{id}/grades`,
  `DELETE /grades/{id}`
- Calculation: `GET /enrolments/{id}/standing`,
  `POST /enrolments/{id}/required-marks`, `GET /me/gpa`, `GET /me/history`
- Guest what-if (public, stateless): `POST /calculator/what-if`
- Planner: `GET /planner/prereq-status`, `POST /planner/sequence`,
  `GET|POST /planner/plans`, `DELETE /planner/plans/{id}`
- Ingestion & curation: `POST /ingestion/jobs`, `GET /ingestion/jobs/{id}`,
  `GET /curator/profile-versions?status=draft`,
  `PATCH /curator/profile-versions/{id}`,
  `POST /curator/profile-versions/{id}/verify`
- AI (advisory): `POST /recommendations/generate`, `GET /recommendations/latest`,
  `POST /study-plans/generate`, `GET /study-plans`, `PATCH /study-plans/{id}`,
  `POST /assistant/ask`
- Search: `GET /search/courses?q=…`
- Account: `GET|PATCH|DELETE /me`
