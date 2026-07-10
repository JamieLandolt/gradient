-- Move course embeddings from 384 dims (mock hashed-bag-of-words) to 1024 dims
-- (Alibaba Bailian text-embedding-v3). Existing 384-d vectors are cleared; the
-- catalogue is re-embedded by seed/load_seed.py after this migration.
-- Keep EMBEDDING_DIM (backend config, default 1024) in sync with this width.

drop index if exists public.idx_course_embeddings_hnsw;

-- The catalogue is small and re-embedded immediately; clearing avoids a
-- dimension-cast error when widening the column.
delete from public.course_embeddings;

alter table public.course_embeddings
    alter column embedding type extensions.vector(1024);

create index idx_course_embeddings_hnsw on public.course_embeddings
    using hnsw (embedding extensions.vector_cosine_ops);

-- Replace the search RPC at the new dimension. Drop the old 384-d overload
-- first — a differing parameter type would otherwise create a second, ambiguous
-- function of the same name.
drop function if exists public.match_courses(extensions.vector(384), int);

create or replace function public.match_courses(
    query_embedding extensions.vector(1024),
    match_count int default 10
)
returns table (
    course_id bigint,
    code text,
    title text,
    description text,
    similarity double precision
)
language sql
stable
set search_path = public, extensions
as $$
    select
        c.id,
        c.code,
        c.title,
        c.description,
        1 - (e.embedding operator(extensions.<=>) query_embedding) as similarity
    from public.course_embeddings e
    join public.courses c on c.id = e.course_id
    order by e.embedding operator(extensions.<=>) query_embedding
    limit match_count;
$$;
