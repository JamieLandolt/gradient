-- Security and data-integrity hardening (audit fixes).
--
-- 1. Add WITH CHECK to child-table RLS policies (defence-in-depth).
-- 2. Add CHECK constraints for data validation.
-- 3. Add missing indexes for high-frequency query paths.

-- ── DB-1: Add WITH CHECK to child-table RLS policies ────────────────────────
-- PostgreSQL defaults WITH CHECK to USING for ALL policies, but explicit
-- declaration is clearer and guards against future drift.

-- recommendation_items: insert/update only if parent recommendation belongs to user
create policy "own via recommendation insert" on public.recommendation_items
    for insert with check (
        exists (
            select 1 from public.recommendations r
            where r.id = recommendation_id and r.user_id = auth.uid()
        )
    );

create policy "own via recommendation update" on public.recommendation_items
    for update using (
        exists (
            select 1 from public.recommendations r
            where r.id = recommendation_id and r.user_id = auth.uid()
        )
    ) with check (
        exists (
            select 1 from public.recommendations r
            where r.id = recommendation_id and r.user_id = auth.uid()
        )
    );

-- study_sessions: insert/update only if parent study_plan belongs to user
create policy "own via study plan insert" on public.study_sessions
    for insert with check (
        exists (
            select 1 from public.study_plans p
            where p.id = study_plan_id and p.user_id = auth.uid()
        )
    );

create policy "own via study plan update" on public.study_sessions
    for update using (
        exists (
            select 1 from public.study_plans p
            where p.id = study_plan_id and p.user_id = auth.uid()
        )
    ) with check (
        exists (
            select 1 from public.study_plans p
            where p.id = study_plan_id and p.user_id = auth.uid()
        )
    );

-- degree_plan_entries: insert/update only if parent degree_plan belongs to user
create policy "own via degree plan insert" on public.degree_plan_entries
    for insert with check (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    );

create policy "own via degree plan update" on public.degree_plan_entries
    for update using (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    ) with check (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    );

-- degree_plan_diagnostics: insert/update only if parent degree_plan belongs to user
create policy "own via degree plan insert" on public.degree_plan_diagnostics
    for insert with check (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    );

create policy "own via degree plan update" on public.degree_plan_diagnostics
    for update using (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    ) with check (
        exists (
            select 1 from public.degree_plans p
            where p.id = degree_plan_id and p.user_id = auth.uid()
        )
    );

-- ── DB-3: Add upper-bound constraint on grades.score ─────────────────────────
alter table public.grades drop constraint if exists grades_score_check;
alter table public.grades add constraint grades_score_check
    check (score >= 0 and score <= 100);

-- ── DB-5: Add length constraints on business fields ─────────────────────────
alter table public.courses drop constraint if exists courses_code_length;
alter table public.courses add constraint courses_code_length
    check (char_length(code) <= 20);

alter table public.courses drop constraint if exists courses_title_length;
alter table public.courses add constraint courses_title_length
    check (char_length(title) <= 500);

alter table public.enrolments drop constraint if exists enrolments_semester_label_length;
alter table public.enrolments add constraint enrolments_semester_label_length
    check (char_length(semester_label) <= 20);

-- ── DB-6: Add missing indexes for high-frequency query paths ────────────────
-- study_plans(user_id) — each "list study plans" query filters by user
create index if not exists idx_study_plans_user on public.study_plans (user_id);

-- recommendations(user_id) — each "list recommendations" query filters by user
create index if not exists idx_recommendations_user on public.recommendations (user_id);

-- degree_plans(user_id) — each "list degree plans" query filters by user
create index if not exists idx_degree_plans_user on public.degree_plans (user_id);
