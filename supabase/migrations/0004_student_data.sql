-- Student-owned data: program links, enrolments, custom assessment items,
-- and recorded marks. Every table carries user_id for RLS ownership.

create table public.user_programs (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    program_id bigint not null references public.programs (id) on delete cascade,
    position smallint not null check (position in (1, 2)),
    unique (user_id, position),
    unique (user_id, program_id)
);

comment on table public.user_programs is
    'A student linked to one program (single degree) or two (dual degree, FR-3.6.3).';

-- A student's link to a concrete course offering (FR-3.2.1).
create table public.enrolments (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    course_offering_id bigint not null references public.course_offerings (id) on delete restrict,
    status text not null default 'planned' check (status in ('planned', 'in_progress', 'completed')),
    profile_version_id bigint references public.profile_versions (id) on delete set null,
    final_grade smallint check (final_grade between 1 and 7),
    final_percent numeric(5, 2) check (final_percent between 0 and 100),
    is_transfer boolean not null default false,
    created_at timestamptz not null default now(),
    unique (user_id, course_offering_id)
);

-- User-defined assessment items where no verified profile exists (FR-3.2.2).
create table public.custom_assessments (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    enrolment_id bigint not null references public.enrolments (id) on delete cascade,
    name text not null,
    weight numeric(5, 2) not null check (weight >= 0 and weight <= 100),
    max_mark numeric(7, 2) not null default 100 check (max_mark > 0),
    due_date date,
    hurdle_min_percent numeric(5, 2) check (hurdle_min_percent between 0 and 100),
    hurdle_description text,
    sort_order smallint not null default 0
);

-- A student's recorded raw mark on exactly one assessment item (FR-3.2.3).
create table public.grades (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    enrolment_id bigint not null references public.enrolments (id) on delete cascade,
    assessment_id bigint references public.assessments (id) on delete cascade,
    custom_assessment_id bigint references public.custom_assessments (id) on delete cascade,
    score numeric(7, 2) not null check (score >= 0),
    updated_at timestamptz not null default now(),
    check (num_nonnulls(assessment_id, custom_assessment_id) = 1),
    unique (enrolment_id, assessment_id),
    unique (enrolment_id, custom_assessment_id)
);
