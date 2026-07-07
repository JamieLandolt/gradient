-- Shared course catalogue: programs, courses, offerings, prerequisites,
-- profile versions (ECP provenance), grade cut-offs, and assessment items.
-- All fully relational — no json/jsonb columns.

create table public.programs (
    id bigint generated always as identity primary key,
    code text not null unique,
    title text not null,
    total_units numeric(5, 1) not null check (total_units > 0),
    is_sample boolean not null default false,
    created_at timestamptz not null default now()
);

create table public.courses (
    id bigint generated always as identity primary key,
    code text not null unique,
    title text not null,
    units numeric(4, 1) not null default 2 check (units > 0),
    description text not null default '',
    data_source text not null default 'import' check (data_source in ('seed', 'import')),
    created_at timestamptz not null default now()
);

create table public.program_courses (
    id bigint generated always as identity primary key,
    program_id bigint not null references public.programs (id) on delete cascade,
    course_id bigint not null references public.courses (id) on delete cascade,
    requirement_kind text not null check (requirement_kind in ('required', 'elective')),
    elective_group text,
    unique (program_id, course_id)
);

-- Concrete offering instances (a course offered in a specific study period).
-- Enrolments reference these; the planner derives offering patterns from them.
create table public.course_offerings (
    id bigint generated always as identity primary key,
    course_id bigint not null references public.courses (id) on delete cascade,
    year smallint not null check (year between 2000 and 2100),
    semester text not null check (semester in ('S1', 'S2', 'SUMMER')),
    unique (course_id, year, semester)
);

-- Prerequisite boolean expression tree, one tree per course (FR-3.5.4, FR-3.6.1).
-- Internal nodes: and / or. Leaves: course (references the required course) or
-- note (unparseable fragment -> "check manually", never silently satisfied).
create table public.prerequisite_nodes (
    id bigint generated always as identity primary key,
    course_id bigint not null references public.courses (id) on delete cascade,
    parent_id bigint references public.prerequisite_nodes (id) on delete cascade,
    node_type text not null check (node_type in ('and', 'or', 'course', 'note')),
    child_course_id bigint references public.courses (id) on delete restrict,
    note_text text,
    sort_order smallint not null default 0,
    check (
        (node_type = 'course' and child_course_id is not null and note_text is null)
        or (node_type = 'note' and note_text is not null and child_course_id is null)
        or (node_type in ('and', 'or') and child_course_id is null and note_text is null)
    )
);

comment on table public.prerequisite_nodes is
    'Adjacency-list boolean expression tree; the row with parent_id null is the root.';

-- Raw prerequisite text kept for provenance and curator review.
create table public.course_prerequisites_raw (
    course_id bigint primary key references public.courses (id) on delete cascade,
    raw_text text not null
);

-- One row per extracted/imported ECP version (FR-3.5.2: provenance + verification).
create table public.profile_versions (
    id bigint generated always as identity primary key,
    course_id bigint not null references public.courses (id) on delete cascade,
    version_label text not null,
    source_type text not null check (source_type in ('url', 'upload', 'seed')),
    source_ref text not null default '',
    extracted_at timestamptz not null default now(),
    extraction_provider text not null default 'manual',
    status text not null default 'draft' check (status in ('draft', 'verified', 'rejected')),
    verified_by uuid references public.profiles (id) on delete set null,
    verified_at timestamptz,
    unique (course_id, version_label)
);

-- Per-version grade cut-offs; a version with no rows uses the default bands
-- defined in the application (SRS 1.2).
create table public.grade_cutoffs (
    id bigint generated always as identity primary key,
    profile_version_id bigint not null references public.profile_versions (id) on delete cascade,
    grade smallint not null check (grade between 1 and 7),
    min_percent numeric(5, 2) not null check (min_percent between 0 and 100),
    unique (profile_version_id, grade)
);

-- Assessment items belonging to a profile version (FR-3.5.1).
create table public.assessments (
    id bigint generated always as identity primary key,
    profile_version_id bigint not null references public.profile_versions (id) on delete cascade,
    name text not null,
    weight numeric(5, 2) not null check (weight >= 0 and weight <= 100),
    max_mark numeric(7, 2) not null default 100 check (max_mark > 0),
    due_date date,
    hurdle_min_percent numeric(5, 2) check (hurdle_min_percent between 0 and 100),
    hurdle_description text,
    sort_order smallint not null default 0
);
