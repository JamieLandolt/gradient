-- Query-path indexes (FKs used in lookups) and the vector similarity index.

create index idx_program_courses_program on public.program_courses (program_id);
create index idx_course_offerings_course on public.course_offerings (course_id);
create index idx_prerequisite_nodes_course on public.prerequisite_nodes (course_id);
create index idx_prerequisite_nodes_parent on public.prerequisite_nodes (parent_id);
create index idx_profile_versions_course_status on public.profile_versions (course_id, status);
create index idx_grade_cutoffs_version on public.grade_cutoffs (profile_version_id);
create index idx_assessments_version on public.assessments (profile_version_id);

create index idx_user_programs_user on public.user_programs (user_id);
create index idx_enrolments_user on public.enrolments (user_id);
create index idx_enrolments_offering on public.enrolments (course_offering_id);
create index idx_custom_assessments_enrolment on public.custom_assessments (enrolment_id);
create index idx_grades_user on public.grades (user_id);
create index idx_grades_enrolment on public.grades (enrolment_id);

create index idx_recommendation_items_rec on public.recommendation_items (recommendation_id);
create index idx_study_sessions_plan on public.study_sessions (study_plan_id);
create index idx_degree_plan_entries_plan on public.degree_plan_entries (degree_plan_id);
create index idx_degree_plan_diagnostics_plan on public.degree_plan_diagnostics (degree_plan_id);
create index idx_ingestion_jobs_status on public.ingestion_jobs (status);

-- Approximate nearest-neighbour index for semantic search (NFR-5.1.3).
create index idx_course_embeddings_hnsw on public.course_embeddings
    using hnsw (embedding extensions.vector_cosine_ops);
