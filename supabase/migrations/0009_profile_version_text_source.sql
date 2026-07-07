-- Ingestion accepts pasted ECP text (source_type 'text'), but the original
-- constraint only allowed url/upload/seed — creating the draft version then
-- failed with a check violation. Align the constraint with the API contract.

alter table public.profile_versions
    drop constraint profile_versions_source_type_check;

alter table public.profile_versions
    add constraint profile_versions_source_type_check
    check (source_type in ('url', 'upload', 'text', 'seed'));
