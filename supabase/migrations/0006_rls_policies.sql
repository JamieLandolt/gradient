-- Row-Level Security (FR-3.1.3, NFR-5.3.1).
--
-- Catalogue tables: public read, no client writes (backend writes via the
-- service role, which bypasses RLS).
-- Student-owned tables: a user can only ever touch rows where user_id = auth.uid().
-- The backend also filters every user-scoped query by the JWT's user id, so RLS
-- is defence-in-depth. Any future views must be created
-- `with (security_invoker = true)`.

-- ── Catalogue: enable RLS + public read ─────────────────────────────────────
alter table public.programs enable row level security;
alter table public.courses enable row level security;
alter table public.program_courses enable row level security;
alter table public.course_offerings enable row level security;
alter table public.prerequisite_nodes enable row level security;
alter table public.course_prerequisites_raw enable row level security;
alter table public.profile_versions enable row level security;
alter table public.grade_cutoffs enable row level security;
alter table public.assessments enable row level security;
alter table public.course_embeddings enable row level security;

create policy "public read programs" on public.programs for select using (true);
create policy "public read courses" on public.courses for select using (true);
create policy "public read program_courses" on public.program_courses for select using (true);
create policy "public read course_offerings" on public.course_offerings for select using (true);
create policy "public read prerequisite_nodes" on public.prerequisite_nodes for select using (true);
create policy "public read course_prerequisites_raw" on public.course_prerequisites_raw for select using (true);
create policy "public read profile_versions" on public.profile_versions for select using (true);
create policy "public read grade_cutoffs" on public.grade_cutoffs for select using (true);
create policy "public read assessments" on public.assessments for select using (true);
create policy "public read course_embeddings" on public.course_embeddings for select using (true);

-- ── Profiles: a user sees and edits only their own profile ──────────────────
alter table public.profiles enable row level security;

create policy "own profile select" on public.profiles
    for select using (auth.uid() = id);
create policy "own profile update" on public.profiles
    for update using (auth.uid() = id) with check (auth.uid() = id);

-- ── Student-owned tables: full CRUD on own rows only ────────────────────────
alter table public.user_interests enable row level security;
alter table public.user_programs enable row level security;
alter table public.enrolments enable row level security;
alter table public.custom_assessments enable row level security;
alter table public.grades enable row level security;
alter table public.recommendations enable row level security;
alter table public.study_plans enable row level security;
alter table public.degree_plans enable row level security;
alter table public.ingestion_jobs enable row level security;

create policy "own rows" on public.user_interests
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.user_programs
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.enrolments
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.custom_assessments
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.grades
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.recommendations
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.study_plans
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.degree_plans
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on public.ingestion_jobs
    for all using (auth.uid() = submitted_by) with check (auth.uid() = submitted_by);

-- ── Child tables owned via their parent ─────────────────────────────────────
alter table public.recommendation_items enable row level security;
alter table public.study_sessions enable row level security;
alter table public.degree_plan_entries enable row level security;
alter table public.degree_plan_diagnostics enable row level security;

create policy "own via recommendation" on public.recommendation_items
    for all using (
        exists (
            select 1 from public.recommendations r
            where r.id = recommendation_id and r.user_id = auth.uid()
        )
    );

create policy "own via study plan" on public.study_sessions
    for all using (
        exists (
            select 1 from public.study_plans p
            where p.id = study_plan_id and p.user_id = auth.uid()
        )
    );

create policy "own via degree plan" on public.degree_plan_entries
    for all using (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    );

create policy "own via degree plan" on public.degree_plan_diagnostics
    for all using (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    );
