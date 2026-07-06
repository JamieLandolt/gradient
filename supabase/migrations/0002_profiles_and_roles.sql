-- User profiles, roles, and interests.
-- A profile row is created automatically for every new auth user.

create table public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    display_name text not null default '',
    role text not null default 'student' check (role in ('student', 'curator', 'admin')),
    created_at timestamptz not null default now()
);

comment on table public.profiles is
    'One row per user; role governs curator/admin capabilities (checked in the backend).';

create table public.user_interests (
    id bigint generated always as identity primary key,
    user_id uuid not null references public.profiles (id) on delete cascade,
    interest text not null,
    unique (user_id, interest)
);

-- Create a profile automatically when a user registers (FR-3.1.1).
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, display_name)
    values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', ''))
    on conflict (id) do nothing;
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Prevent users from escalating their own role: role changes are allowed only
-- via the service role (backend / SQL console).
create or replace function public.prevent_role_self_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if new.role is distinct from old.role and auth.uid() is not null then
        raise exception 'role can only be changed by an administrator';
    end if;
    return new;
end;
$$;

create trigger profiles_role_guard
    before update on public.profiles
    for each row execute function public.prevent_role_self_change();
