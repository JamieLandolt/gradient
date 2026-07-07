-- Search embeddings, AI advisory artefacts (recommendations, study plans,
-- degree plans), and the ECP ingestion queue. Fully relational.

-- Vector representation of a course description for semantic search (FR-3.9.1).
create table public.course_embeddings (
    course_id bigint primary key references public.courses (id) on delete cascade,
    embedding extensions.vector(384) not null,
    model text not null,
    updated_at timestamptz not null default now()
);

-- AI course recommendations, regenerable on demand (FR-3.7.x).
create table public.recommendations (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    provider text not null,
    generated_at timestamptz not null default now()
);

create table public.recommendation_items (
    id bigint generated always as identity primary key,
    recommendation_id bigint not null references public.recommendations (id) on delete cascade,
    course_id bigint not null references public.courses (id) on delete cascade,
    rank smallint not null,
    reason text not null,
    prereq_status text not null check (prereq_status in ('met', 'partially_met', 'not_met')),
    unique (recommendation_id, course_id)
);

comment on column public.recommendation_items.prereq_status is
    'Supplied by the deterministic planning engine, never by the model (FR-3.7.2).';

-- AI study plans and their sessions (FR-3.8.x).
create table public.study_plans (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    enrolment_id bigint references public.enrolments (id) on delete cascade,
    target_grade smallint not null check (target_grade between 1 and 7),
    provider text not null,
    generated_at timestamptz not null default now()
);

create table public.study_sessions (
    id bigint generated always as identity primary key,
    study_plan_id bigint not null references public.study_plans (id) on delete cascade,
    assessment_id bigint references public.assessments (id) on delete cascade,
    custom_assessment_id bigint references public.custom_assessments (id) on delete cascade,
    session_date date not null,
    duration_minutes smallint not null check (duration_minutes > 0),
    focus text not null,
    sort_order smallint not null default 0,
    check (num_nonnulls(assessment_id, custom_assessment_id) <= 1)
);

-- Saved degree-plan sequences produced by the deterministic planner (FR-3.6.2).
create table public.degree_plans (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    name text not null default 'My plan',
    feasible boolean not null,
    generated_at timestamptz not null default now()
);

create table public.degree_plan_entries (
    id bigint generated always as identity primary key,
    degree_plan_id bigint not null references public.degree_plans (id) on delete cascade,
    semester_index smallint not null check (semester_index >= 0),
    semester_label text not null,
    course_id bigint not null references public.courses (id) on delete cascade,
    explanation text not null default '',
    unique (degree_plan_id, course_id)
);

create table public.degree_plan_diagnostics (
    id bigint generated always as identity primary key,
    degree_plan_id bigint not null references public.degree_plans (id) on delete cascade,
    severity text not null check (severity in ('info', 'warning', 'error')),
    message text not null
);

-- ECP ingestion queue: student/curator submissions awaiting extraction and review.
create table public.ingestion_jobs (
    id bigint generated always as identity primary key,
    submitted_by uuid not null references public.profiles (id) on delete cascade,
    course_code text not null,
    source_type text not null check (source_type in ('url', 'upload', 'text')),
    source_ref text not null default '',
    payload text not null default '',
    status text not null default 'queued' check (status in ('queued', 'extracted', 'failed')),
    profile_version_id bigint references public.profile_versions (id) on delete set null,
    error text not null default '',
    created_at timestamptz not null default now()
);
