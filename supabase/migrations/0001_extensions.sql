-- Enable pgvector (installs into the `extensions` schema on Supabase).
-- Vector columns must reference the type as extensions.vector(384).
create extension if not exists vector with schema extensions;
