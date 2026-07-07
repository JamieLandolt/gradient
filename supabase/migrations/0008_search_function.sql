-- Semantic course search over pgvector (FR-3.9.1, NFR-5.1.3).
-- Catalogue tables are public-read, so this runs as security invoker.

create or replace function public.match_courses(
    query_embedding extensions.vector(384),
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
-- pgvector lives in the extensions schema; make its <=> operator resolvable.
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
