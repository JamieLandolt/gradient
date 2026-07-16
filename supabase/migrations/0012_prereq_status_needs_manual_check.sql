-- PrereqStatus gained a 4th value (NEEDS_MANUAL_CHECK) to distinguish "genuinely
-- not met" from "blocked only by an unparseable prerequisite fragment" (see
-- app/domain/planning/prereq_ast.py). recommendation_items.prereq_status still
-- only allowed the original 3 values, so recommending a course in that state
-- violated the check constraint and 500'd the whole request.

alter table public.recommendation_items
    drop constraint recommendation_items_prereq_status_check;

alter table public.recommendation_items
    add constraint recommendation_items_prereq_status_check
    check (prereq_status in ('met', 'partially_met', 'not_met', 'needs_manual_check'));
