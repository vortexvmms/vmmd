begin;
alter table public.sites add column removed_at timestamptz, add column removed_by uuid;
alter table public.sites add constraint removed_sites_stay_archived check(removed_at is null or status='archived');
create table public.site_removal_events(id uuid primary key default gen_random_uuid(),site_id uuid not null references public.sites(id),action text not null check(action in ('removed','restored')),actor uuid not null default auth.uid(),created_at timestamptz not null default now());
alter table public.site_removal_events enable row level security;
revoke all on public.site_removal_events from anon;
grant select,insert on public.site_removal_events to authenticated;
create policy site_removal_events_read on public.site_removal_events for select to authenticated using(public.is_full());
create policy site_removal_events_write on public.site_removal_events for insert to authenticated with check(public.is_full() and actor=auth.uid() and pg_trigger_depth()>0);
create function public.site_removal_guard() returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if new.removed_at is distinct from old.removed_at then
  if not coalesce(public.is_full(),false) then raise insufficient_privilege using message='Only management can remove or restore sites';end if;
  if new.removed_at is not null and old.status<>'archived' then raise exception 'Archive this site before removing it';end if;
  new.removed_at:=case when new.removed_at is null then null else now() end;
  new.removed_by:=case when new.removed_at is null then null else auth.uid() end;
 else new.removed_by:=old.removed_by;end if;
 return new;
end $$;
create trigger site_removal_guard before update on public.sites for each row execute function public.site_removal_guard();
create function public.site_removal_audit() returns trigger language plpgsql security invoker set search_path='' as $$
begin
 insert into public.site_removal_events(site_id,action) values(new.id,case when new.removed_at is null then 'restored' else 'removed' end);return new;
end $$;
create trigger site_removal_audit after update on public.sites for each row when(old.removed_at is distinct from new.removed_at) execute function public.site_removal_audit();
create function public.site_set_removed(p_site_id uuid,p_removed boolean) returns public.sites language plpgsql security invoker set search_path='' as $$
declare r public.sites;
begin
 if not coalesce(public.is_full(),false) then raise insufficient_privilege using message='Only management can remove or restore sites';end if;
 select * into r from public.sites where id=p_site_id for update;
 if not found then raise exception 'Site not found';end if;
 if p_removed and r.status<>'archived' then raise exception 'Archive this site before removing it';end if;
 update public.sites set removed_at=case when p_removed then now() else null end where id=p_site_id returning * into r;
 return r;
end $$;
revoke execute on function public.site_removal_guard(),public.site_removal_audit(),public.site_set_removed(uuid,boolean) from public,anon;
grant execute on function public.site_removal_guard(),public.site_removal_audit(),public.site_set_removed(uuid,boolean) to authenticated;
notify pgrst,'reload schema';
commit;
