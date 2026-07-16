-- Weekly, multi-course study planning (FR-3.8.x rework) — replaces the old
-- single-course study_plans/study_sessions model. Three new concepts:
--   1. assessment_targets  — a target mark per assessment item (forward-
--      looking; can exist before the item is due, unlike `grades`).
--   2. study_availability  — a reusable weekly time-block template: which
--      hour-slots are blocked (classes/commitments) vs available for study.
--   3. weekly_study_plans/weekly_study_blocks — a generated plan for one
--      specific week, placing assessment-driven study blocks onto the
--      student's own 'study' slots. Purely deterministic (no AI provider
--      involved) — see app/domain/study/weekly_planner.py.

drop table if exists public.study_sessions;
drop table if exists public.study_plans;

-- A student's target mark for one specific assessment item. Distinct from
-- `grades` (an already-received mark): this drives how much study time the
-- weekly planner allocates to that item, and can be set before it's due.
create table public.assessment_targets (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    enrolment_id bigint not null references public.enrolments (id) on delete cascade,
    assessment_id bigint references public.assessments (id) on delete cascade,
    custom_assessment_id bigint references public.custom_assessments (id) on delete cascade,
    target_percent numeric(5, 2) not null check (target_percent between 0 and 100),
    updated_at timestamptz not null default now(),
    check (num_nonnulls(assessment_id, custom_assessment_id) = 1),
    unique (enrolment_id, assessment_id),
    unique (enrolment_id, custom_assessment_id)
);

-- A student's recurring weekly time-block template: which hour slots
-- (day_of_week 0=Monday..6=Sunday, start_hour 0-23) are blocked (classes,
-- commitments) vs marked available for study. Freely editable at any time;
-- each "generate" run uses whatever is currently saved.
create table public.study_availability (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    day_of_week smallint not null check (day_of_week between 0 and 6),
    start_hour smallint not null check (start_hour between 0 and 23),
    slot_type text not null check (slot_type in ('blocked', 'study')),
    updated_at timestamptz not null default now(),
    unique (user_id, day_of_week, start_hour)
);

-- A generated weekly plan: this week's assessment-driven study blocks, placed
-- onto the student's 'study' slots across all their in-progress courses.
create table public.weekly_study_plans (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    week_start date not null,
    generated_at timestamptz not null default now(),
    unique (user_id, week_start)
);

create table public.weekly_study_blocks (
    id bigint generated always as identity primary key,
    weekly_study_plan_id bigint not null references public.weekly_study_plans (id) on delete cascade,
    day_of_week smallint not null check (day_of_week between 0 and 6),
    start_hour smallint not null check (start_hour between 0 and 23),
    enrolment_id bigint references public.enrolments (id) on delete set null,
    assessment_id bigint references public.assessments (id) on delete set null,
    custom_assessment_id bigint references public.custom_assessments (id) on delete set null,
    focus text not null,
    sort_order smallint not null default 0,
    check (num_nonnulls(assessment_id, custom_assessment_id) <= 1)
);

-- ── RLS ──────────────────────────────────────────────────────────────────────
alter table public.assessment_targets enable row level security;
alter table public.study_availability enable row level security;
alter table public.weekly_study_plans enable row level security;
alter table public.weekly_study_blocks enable row level security;

create policy "own rows" on public.assessment_targets
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.study_availability
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.weekly_study_plans
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own via weekly study plan" on public.weekly_study_blocks
    for all using (
        exists (
            select 1 from public.weekly_study_plans p
            where p.id = weekly_study_plan_id and p.user_id = auth.uid()
        )
    );

-- ── Indexes ──────────────────────────────────────────────────────────────────
create index idx_assessment_targets_enrolment on public.assessment_targets (enrolment_id);
create index idx_study_availability_user on public.study_availability (user_id);
create index idx_weekly_study_plans_user on public.weekly_study_plans (user_id);
create index idx_weekly_study_blocks_plan on public.weekly_study_blocks (weekly_study_plan_id);
