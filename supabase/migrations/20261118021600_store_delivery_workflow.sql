begin;

alter table public.users drop constraint if exists users_role_check;
alter table public.users add constraint users_role_check check (role in (
    'admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead',
    'site_sup','safety_sup','wshc','logistics_sup','payroll','driver'
));

-- Driver accounts share Supabase's authenticated role. Fence off existing
-- modules, including permissive policies that only check for a signed-in user.
create function public.store_is_driver()
returns boolean language sql stable security definer set search_path=''
as $$ select exists (select 1 from public.users where auth_uid=auth.uid() and role='driver'); $$;
revoke all on function public.store_is_driver() from public, anon;
grant execute on function public.store_is_driver() to authenticated;

do $$
declare target record;
begin
    for target in
        select n.nspname, c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where c.relrowsecurity and c.relkind in ('r','p')
        and n.nspname in ('public','storage') and (n.nspname,c.relname) <> ('public','users')
    loop
        execute format('create policy store_driver_isolation on %I.%I as restrictive to authenticated
                        using (not (select public.store_is_driver()))
                        with check (not (select public.store_is_driver()))',target.nspname,target.relname);
    end loop;
end;
$$;

create table vcms_store.deliveries (
    id uuid primary key,
    reference bigint generated always as identity unique,
    asset_id uuid not null references vcms_store.assets(id),
    asset_name text not null,
    asset_code text not null,
    from_site uuid references public.sites(id),
    to_site uuid references public.sites(id),
    from_name text not null,
    to_name text not null,
    requested_by uuid not null references public.users(id),
    requested_quantity integer not null check (requested_quantity between 1 and 9999),
    needed_on date not null,
    request_note text,
    approved_quantity integer,
    released_by uuid references public.users(id),
    driver_id uuid references public.users(id),
    driver_name text,
    recipient text,
    delivered_at timestamptz,
    movement_id uuid unique references vcms_store.movements(id),
    state text not null default 'requested' check (state in (
        'requested','released','assigned','picked_up','delivered','received','cancelled','returned'
    )),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (from_site is distinct from to_site),
    check (approved_quantity between 1 and requested_quantity)
);
create index store_delivery_driver on vcms_store.deliveries(driver_id, reference desc);
create index store_delivery_reservation on vcms_store.deliveries(asset_id,from_site)
    where state in ('released','assigned','picked_up','delivered');

create table vcms_store.delivery_events (
    id uuid primary key,
    delivery_id uuid not null references vcms_store.deliveries(id),
    action text not null,
    actor_id uuid not null references public.users(id),
    actor_name text not null,
    detail jsonb not null,
    occurred_at timestamptz not null default clock_timestamp()
);
create index store_delivery_events_parent on vcms_store.delivery_events(delivery_id, occurred_at);
create table vcms_store.delivery_photos (
    id uuid primary key,
    delivery_id uuid not null unique references vcms_store.deliveries(id),
    mime text not null check (mime in ('image/jpeg','image/png','image/webp')),
    uploaded_by uuid not null references public.users(id),
    uploaded_at timestamptz not null default clock_timestamp()
);
alter table vcms_store.deliveries enable row level security;
alter table vcms_store.delivery_events enable row level security;
alter table vcms_store.delivery_photos enable row level security;

create function vcms_store.delivery_actor()
returns public.users language plpgsql stable set search_path=''
as $$
declare profile public.users;
begin
    select * into profile from public.users where auth_uid=auth.uid() and status='active';
    if profile.id is null then
        raise exception using errcode='42501',message='An active VCMS account is required.';
    end if;
    return profile;
end;
$$;

create function vcms_store.dispatches(profile public.users)
returns boolean language sql immutable set search_path=''
as $$ select profile.role in ('admin','general_manager','operation_manager','main_sup','logistics_sup'); $$;

create function vcms_store.delivery_site(profile public.users, location uuid)
returns boolean language sql stable set search_path=''
as $$
    select profile.role <> 'driver' and (
        vcms_store.dispatches(profile) or exists (
            select from public.site_supervisors where user_id=profile.id and site_id=location
        )
    );
$$;

create function vcms_store.delivery_custodian(profile public.users, location uuid)
returns boolean language sql stable set search_path=''
as $$
    select case when location is null then vcms_store.dispatches(profile)
        else profile.role <> 'driver' and exists (
            select from public.site_supervisors where user_id=profile.id and site_id=location
        ) end;
$$;

create function vcms_store.delivery_visible(profile public.users, job vcms_store.deliveries)
returns boolean language sql stable set search_path=''
as $$
    select case when profile.role='driver' then job.driver_id=profile.id
        else job.requested_by=profile.id or vcms_store.delivery_site(profile,job.from_site)
            or vcms_store.delivery_site(profile,job.to_site) end;
$$;

create function vcms_store.delivery_reserved(asset uuid, location uuid)
returns bigint language sql stable set search_path=''
as $$
    select coalesce(sum(approved_quantity),0) from vcms_store.deliveries
    where asset_id=asset and from_site is not distinct from location
      and state in ('released','assigned','picked_up','delivered');
$$;

create function vcms_store.guard_delivery_stock()
returns trigger language plpgsql set search_path=''
as $$
begin
    if (case when tg_op='DELETE' then 0 else new.quantity end)
       < vcms_store.delivery_reserved(old.asset_id,old.site_id) then
        raise exception using errcode='22023',message='Stock is reserved for an Equipment Store delivery.';
    end if;
    if tg_op='DELETE' then return old; end if;
    return new;
end;
$$;
create trigger guard_delivery_stock before update of quantity or delete on vcms_store.stock
for each row execute function vcms_store.guard_delivery_stock();

create function public.store_delivery_register(p_before bigint, p_state text)
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare profile public.users := vcms_store.delivery_actor();
begin
    if profile.role <> 'driver' and not vcms_store.dispatches(profile)
       and not exists(select from public.site_supervisors where user_id=profile.id) then
        raise exception using errcode='42501',message='Delivery access is for Logistics and assigned site supervisors.';
    end if;
    return jsonb_build_object(
        'role',profile.role,'can_request',profile.role <> 'driver','actor_id',profile.id,
        'rows',(select coalesce(jsonb_agg(to_jsonb(job) || jsonb_build_object(
            'can_release',profile.id<>job.requested_by and vcms_store.delivery_custodian(profile,job.from_site),
            'can_receive',vcms_store.delivery_custodian(profile,job.to_site),
            'can_return',vcms_store.delivery_custodian(profile,job.from_site),
            'can_dispatch',vcms_store.dispatches(profile),
            'photo_id',(select id from vcms_store.delivery_photos where delivery_id=job.id),
            'timeline',(select coalesce(jsonb_agg(to_jsonb(e)-'id'-'delivery_id' order by occurred_at,id),'[]')
                        from vcms_store.delivery_events e where e.delivery_id=job.id)
        ) order by job.reference desc),'[]')
            from (select d.* from vcms_store.deliveries d
                  where vcms_store.delivery_visible(profile,d)
                    and (p_before is null or d.reference<p_before)
                    and (p_state is null or d.state=p_state)
                  order by d.reference desc limit 31) job),
        'locations',(select coalesce(jsonb_agg(jsonb_build_object(
            'id',s.id,'name',s.site_name,'assigned',vcms_store.delivery_site(profile,s.id)
        ) order by s.site_name),'[]') from public.sites s
          where profile.role <> 'driver' and s.status='active' and s.removed_at is null),
        'drivers',(select coalesce(jsonb_agg(jsonb_build_object('id',u.id,'name',u.name) order by u.name),'[]')
          from public.users u where vcms_store.dispatches(profile)
          and u.role='driver' and u.status='active' and u.auth_uid is not null)
    );
end;
$$;

create function public.store_delivery_equipment(p_from uuid, p_search text)
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare profile public.users := vcms_store.delivery_actor();
begin
    if profile.role='driver' or (not vcms_store.dispatches(profile)
       and not exists(select from public.site_supervisors where user_id=profile.id)) then
        raise exception using errcode='42501',message='Equipment request access is unavailable.';
    end if;
    return (select coalesce(jsonb_agg(to_jsonb(item) order by item.name,item.code),'[]')
        from (select a.id,a.name,a.code,greatest(0,s.quantity-vcms_store.delivery_reserved(a.id,s.site_id)) as available
              from vcms_store.stock s join vcms_store.assets a on a.id=s.asset_id
              where s.site_id is not distinct from p_from and a.archived_at is null
                and (a.name ilike '%'||left(coalesce(p_search,''),80)||'%'
                     or a.code ilike '%'||left(coalesce(p_search,''),80)||'%')
              order by a.name,a.code limit 100) item);
end;
$$;

create function public.store_delivery_change(p_id uuid, p_event uuid, p_action text, p_detail jsonb)
returns uuid language plpgsql security definer set search_path=''
as $$
declare
    profile public.users := vcms_store.delivery_actor();
    job vcms_store.deliveries;
    prior vcms_store.delivery_events;
    asset vcms_store.assets;
    driver public.users;
    source_site uuid;
    destination_site uuid;
    approved integer;
    available integer;
    needed date;
    source_name text;
    destination_name text;
    note text := nullif(btrim(p_detail->>'note'),'');
    event_detail jsonb := coalesce(p_detail,'{}');
begin
    if p_id is null or p_event is null or jsonb_typeof(event_detail)<>'object'
       or octet_length(event_detail::text)>4096 or length(note)>500 then
        raise exception using errcode='22023',message='Check the delivery details.';
    end if;

    -- Requests have no existing row, so serialize identical retries before lookup.
    if p_action='request' then perform pg_advisory_xact_lock(hashtextextended(p_id::text,227)); end if;
    select * into job from vcms_store.deliveries where id=p_id for update;
    select * into prior from vcms_store.delivery_events where id=p_event;
    if prior.id is not null then
        if prior.delivery_id=p_id and prior.actor_id=profile.id and prior.action=p_action then
            return p_id;
        end if;
        raise exception using errcode='23505',message='This delivery action reference is already in use.';
    end if;

    if p_action='request' then
        if job.id is not null then raise exception using errcode='23505',message='This delivery already exists.'; end if;
        source_site := (p_detail->>'from_site')::uuid;
        destination_site := (p_detail->>'to_site')::uuid;
        approved := (p_detail->>'quantity')::integer;
        needed := (p_detail->>'needed_on')::date;
        if not (vcms_store.delivery_site(profile,source_site) or vcms_store.delivery_site(profile,destination_site)) then
            raise exception using errcode='42501',message='Request equipment for one of your assigned locations.';
        end if;
        if source_site is not distinct from destination_site or approved is null or approved not between 1 and 9999 or needed is null then
            raise exception using errcode='22023',message='Choose different locations, a quantity and a required date.';
        end if;
        source_name := vcms_store.location_name(source_site);
        destination_name := vcms_store.location_name(destination_site);
        select a.* into asset from vcms_store.assets a join vcms_store.stock s on s.asset_id=a.id
          where a.id=(p_detail->>'asset_id')::uuid and s.site_id is not distinct from source_site and a.archived_at is null;
        if asset.id is null then
            raise exception using errcode='22023',message='Select equipment currently listed at the pickup location.';
        end if;
        insert into vcms_store.deliveries(id,asset_id,asset_name,asset_code,from_site,to_site,from_name,to_name,
            requested_by,requested_quantity,needed_on,request_note)
        values(p_id,asset.id,asset.name,asset.code,source_site,destination_site,source_name,destination_name,
            profile.id,approved,needed,note);
        event_detail := jsonb_build_object('quantity',approved,'needed_on',needed,'note',note);
    else
        if job.id is null or vcms_store.delivery_visible(profile,job) is not true then
            raise exception using errcode='42501',message='This delivery is outside your assignments.';
        end if;
        case p_action
        when 'release' then
            if profile.id=job.requested_by or not vcms_store.delivery_custodian(profile,job.from_site) then
                raise exception using errcode='42501',message='A different supervisor at the pickup location must release this request.';
            end if;
            if job.state<>'requested' then raise exception using errcode='22023',message='Only pending requests can be released.'; end if;
            approved := (p_detail->>'quantity')::integer;
            if approved is null or approved not between 1 and job.requested_quantity then
                raise exception using errcode='22023',message='Enter a release quantity within the requested amount.';
            end if;
            select * into asset from vcms_store.assets where id=job.asset_id for update;
            select quantity into available from vcms_store.stock where asset_id=job.asset_id and site_id is not distinct from job.from_site;
            if asset.archived_at is not null or coalesce(available,0)-vcms_store.delivery_reserved(job.asset_id,job.from_site)<approved then
                raise exception using errcode='22023',message='The pickup location does not have enough unreserved stock.';
            end if;
            update vcms_store.deliveries set approved_quantity=approved,released_by=profile.id,state='released' where id=p_id;
            event_detail := jsonb_build_object('quantity',approved,'note',note);
        when 'assign' then
            if not vcms_store.dispatches(profile) then raise exception using errcode='42501',message='Logistics assigns drivers.'; end if;
            if job.state not in ('released','assigned') then
                raise exception using errcode='22023',message='Only released deliveries awaiting pickup can be assigned.';
            end if;
            select * into driver from public.users where id=(p_detail->>'driver_id')::uuid
              and role='driver' and status='active' and auth_uid is not null;
            if driver.id is null then raise exception using errcode='22023',message='Select an active Driver account.'; end if;
            if job.driver_id is distinct from driver.id and exists(select from vcms_store.delivery_photos where delivery_id=p_id) then
                raise exception using errcode='22023',message='This driver has uploaded the pickup photo. Cancel and create a new request to change drivers.';
            end if;
            update vcms_store.deliveries set driver_id=driver.id,driver_name=driver.name,state='assigned' where id=p_id;
            event_detail := jsonb_build_object('driver',driver.name,'note',note);
        when 'pickup' then
            if profile.role<>'driver' or job.driver_id is distinct from profile.id then
                raise exception using errcode='42501',message='Only the assigned driver can confirm pickup.';
            end if;
            if job.state<>'assigned' or not exists(select from vcms_store.delivery_photos where delivery_id=p_id and uploaded_by=profile.id) then
                raise exception using errcode='22023',message='Upload the pickup photo before confirming pickup.';
            end if;
            update vcms_store.deliveries set state='picked_up' where id=p_id;
            event_detail := jsonb_build_object('quantity',job.approved_quantity,'note',note);
        when 'deliver' then
            if profile.role<>'driver' or job.driver_id is distinct from profile.id then
                raise exception using errcode='42501',message='Only the assigned driver can record delivery.';
            end if;
            if job.state<>'picked_up' or coalesce(length(btrim(p_detail->>'recipient')),0) not between 1 and 100 then
                raise exception using errcode='22023',message='Record pickup first and enter the person who took delivery.';
            end if;
            update vcms_store.deliveries
            set state='delivered',recipient=btrim(p_detail->>'recipient'),delivered_at=clock_timestamp() where id=p_id;
            event_detail := jsonb_build_object('recipient',btrim(p_detail->>'recipient'),'note',note);
        when 'receive' then
            if not vcms_store.delivery_custodian(profile,job.to_site) then
                raise exception using errcode='42501',message='Only the receiving location can confirm receipt.';
            end if;
            if job.state<>'delivered' then raise exception using errcode='22023',message='The driver must record delivery before receipt.'; end if;
            approved := (p_detail->>'quantity')::integer;
            if approved is distinct from job.approved_quantity then
                raise exception using errcode='22023',message='Confirm the full released quantity or report a discrepancy for Logistics.';
            end if;
            perform 1 from vcms_store.assets where id=job.asset_id and archived_at is null for update;
            if not found then raise exception using errcode='22023',message='The equipment is archived.'; end if;
            select quantity into available from vcms_store.stock where asset_id=job.asset_id and site_id is not distinct from job.from_site;
            if coalesce(available,0)<approved then raise exception using errcode='22023',message='The reserved stock is unavailable.'; end if;
            -- Exclude this reservation before debiting stock. All writes roll back together.
            update vcms_store.deliveries set state='received' where id=p_id;
            if available=approved then
                delete from vcms_store.stock where asset_id=job.asset_id and site_id is not distinct from job.from_site;
            else
                update vcms_store.stock set quantity=quantity-approved
                where asset_id=job.asset_id and site_id is not distinct from job.from_site;
            end if;
            insert into vcms_store.stock as stock (asset_id,site_id,quantity) values(job.asset_id,job.to_site,approved)
            on conflict(asset_id,site_id) do update set quantity=stock.quantity+excluded.quantity;
            update vcms_store.assets set updated_at=now() where id=job.asset_id;
            insert into vcms_store.movements(
                id,asset_id,from_site,to_site,from_name,to_name,quantity,moved_on,handed_over,
                received_by,receiver_name,requested_by,requester_name,notes,created_by
            ) select p_id,job.asset_id,job.from_site,job.to_site,job.from_name,job.to_name,approved,
                (job.delivered_at at time zone 'Asia/Singapore')::date,left(job.driver_name,100),
                profile.id,left(profile.name,100),job.requested_by,left(u.name,100),left(note,500),profile.id
                from public.users u where u.id=job.requested_by;
            update vcms_store.deliveries set movement_id=p_id where id=p_id;
            event_detail := jsonb_build_object('quantity',approved,'note',note);
        when 'issue' then
            if job.state in ('received','cancelled','returned') or note is null then
                raise exception using errcode='22023',message='Enter an issue for an open delivery.';
            end if;
            event_detail := jsonb_build_object('note',note);
        when 'cancel' then
            if profile.role='driver' or (profile.id<>job.requested_by and not vcms_store.dispatches(profile)) then
                raise exception using errcode='42501',message='Only the requester or Logistics can cancel this request.';
            end if;
            if job.state not in ('requested','released','assigned') or note is null then
                raise exception using errcode='22023',message='Enter a reason to cancel before pickup.';
            end if;
            update vcms_store.deliveries set state='cancelled' where id=p_id;
            event_detail := jsonb_build_object('note',note);
        when 'return_to_source' then
            if not vcms_store.delivery_custodian(profile,job.from_site) then
                raise exception using errcode='42501',message='Only the pickup location can confirm a return to pickup.';
            end if;
            if job.state not in ('picked_up','delivered') or note is null then
                raise exception using errcode='22023',message='Confirm that all collected equipment is back at pickup and enter a reason.';
            end if;
            update vcms_store.deliveries set state='returned' where id=p_id;
            event_detail := jsonb_build_object('note',note);
        else
            raise exception using errcode='22023',message='Unknown delivery action.';
        end case;
    end if;

    update vcms_store.deliveries set updated_at=clock_timestamp() where id=p_id;
    insert into vcms_store.delivery_events(id,delivery_id,action,actor_id,actor_name,detail)
    values(p_event,p_id,p_action,profile.id,profile.name,event_detail);
    return p_id;
end;
$$;

create function public.store_delivery_photo(p_delivery uuid, p_write boolean)
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare
    profile public.users := vcms_store.delivery_actor();
    job vcms_store.deliveries;
begin
    select * into job from vcms_store.deliveries where id=p_delivery;
    if job.id is null or vcms_store.delivery_visible(profile,job) is not true
       or (p_write and (job.driver_id is distinct from profile.id or profile.role<>'driver'
                        or job.state not in ('assigned','picked_up'))) then
        raise exception using errcode='42501',message='Photo access is unavailable for this delivery.';
    end if;
    return (select jsonb_build_object('id',p.id,'mime',p.mime,
        'key','deliveries/'||p.delivery_id||'/'||p.id)
        from vcms_store.delivery_photos p where p.delivery_id=p_delivery);
end;
$$;

-- Called only after the API has saved and validated the private image.
create function public.store_delivery_photo_attach(p_delivery uuid, p_photo uuid, p_actor uuid, p_mime text)
returns uuid language plpgsql security definer set search_path=''
as $$
declare job vcms_store.deliveries;
begin
    select * into job from vcms_store.deliveries where id=p_delivery for update;
    if job.id is null or job.driver_id is distinct from p_actor or job.state not in ('assigned','picked_up')
       or not exists(select from public.users where id=p_actor and role='driver' and status='active') then
        raise exception using errcode='42501',message='Only the assigned active driver can upload the pickup photo.';
    end if;
    if exists(select from vcms_store.delivery_photos where id=p_photo and delivery_id=p_delivery) then
        return p_photo;
    end if;
    insert into vcms_store.delivery_photos(id,delivery_id,mime,uploaded_by) values(p_photo,p_delivery,p_mime,p_actor);
    insert into vcms_store.delivery_events(id,delivery_id,action,actor_id,actor_name,detail)
    select gen_random_uuid(),p_delivery,'photo',p_actor,name,jsonb_build_object('photo_id',p_photo)
    from public.users where id=p_actor;
    return p_photo;
end;
$$;

create or replace function vcms_store.actor()
returns public.users language plpgsql stable set search_path=''
as $$
declare profile public.users;
begin
    select * into profile from public.users where auth_uid=auth.uid() and status='active';
    if profile.id is null or profile.role='driver' or (
        not coalesce(profile.role in ('admin','general_manager','operation_manager','main_sup'),false)
        and not coalesce(profile.menu ? 'store.html',false)
    ) then
        raise exception using errcode='42501',message='Equipment Store access is limited to managers and selected users.';
    end if;
    return profile;
end;
$$;

revoke all on function public.store_delivery_register(bigint,text),public.store_delivery_equipment(uuid,text),
    public.store_delivery_change(uuid,uuid,text,jsonb),public.store_delivery_photo(uuid,boolean) from public,anon;
grant execute on function public.store_delivery_register(bigint,text),public.store_delivery_equipment(uuid,text),
    public.store_delivery_change(uuid,uuid,text,jsonb),public.store_delivery_photo(uuid,boolean) to authenticated;
revoke all on function public.store_delivery_photo_attach(uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.store_delivery_photo_attach(uuid,uuid,uuid,text) to service_role;

commit;
