begin;
create schema vcms_store;
revoke all on schema vcms_store from public, anon, authenticated;

create table vcms_store.assets (
    id uuid primary key,
    code text not null check (length(btrim(code)) between 1 and 60),
    name text not null check (length(btrim(name)) between 1 and 150),
    category text not null check (category in ('Machinery','Equipment','Tool')),
    equipment_type text,
    ownership text,
    lm_reference text,
    meter_reading text,
    condition text not null default 'Unverified' check (condition in ('Unverified','Good','Needs Repair','Out of Service')),
    notes text,
    purchase_date date,
    last_maintenance date,
    last_calibration date,
    last_repair date,
    brand text,
    model text,
    serial_number text,
    registration_number text,
    created_by uuid not null references public.users(id),
    created_at timestamptz not null default now()
);
create unique index store_code_unique on vcms_store.assets(lower(code));

-- A null site represents Main Store. Partial movements retain the same asset ID.
create table vcms_store.stock (
    asset_id uuid not null references vcms_store.assets(id),
    site_id uuid references public.sites(id),
    quantity integer not null check (quantity > 0),
    unique nulls not distinct (asset_id, site_id)
);
create index store_stock_site on vcms_store.stock(site_id);

create table vcms_store.movements (
    id uuid primary key,
    asset_id uuid not null references vcms_store.assets(id),
    from_site uuid references public.sites(id),
    to_site uuid references public.sites(id),
    from_name text not null,
    to_name text not null,
    quantity integer not null check (quantity > 0),
    moved_on date not null,
    handed_over text,
    received_by uuid not null references public.users(id),
    receiver_name text not null,
    requested_by uuid references public.users(id),
    requester_name text,
    notes text,
    created_by uuid not null references public.users(id),
    created_at timestamptz not null default now(),
    check (from_site is distinct from to_site),
    check (length(handed_over)<=100),
    check (length(notes)<=500)
);
create index store_movement_recent on vcms_store.movements(moved_on desc,created_at desc,id desc);

alter table vcms_store.assets enable row level security;
alter table vcms_store.stock enable row level security;
alter table vcms_store.movements enable row level security;

create function vcms_store.actor()
returns public.users language plpgsql stable set search_path = ''
as $$
declare
    profile public.users;
begin
    select * into profile from public.users where auth_uid=auth.uid() and status='active';
    if profile.id is null or profile.role not in (
        'admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','logistics_sup','site_sup'
    ) then
        raise exception using errcode='42501', message='Store access is unavailable for this account.';
    end if;
    return profile;
end;
$$;

create function vcms_store.can_see(profile public.users, location uuid)
returns boolean language sql stable set search_path = ''
as $$
    select profile.role <> 'site_sup' or exists (
        select 1 from public.site_supervisors s where s.user_id=profile.id and s.site_id=location
    );
$$;

create function vcms_store.location_name(location uuid)
returns text language plpgsql stable set search_path = ''
as $$
declare
    label text;
begin
    if location is null then return 'Main Store'; end if;
    select site_name into label from public.sites where id=location and status='active' and removed_at is null;
    if label is null then
        raise exception using errcode='22023', message='Choose an active VCMS site.';
    end if;
    return label;
end;
$$;

create view vcms_store.supervisors as
select u.id,u.name from public.users u where u.status='active'
  and (u.role in ('main_sup','site_sup','logistics_sup') or exists (
      select 1 from public.site_supervisors s where s.user_id=u.id
  ));

create function public.store_register()
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
    profile public.users := vcms_store.actor();
begin
    return jsonb_build_object(
        'can_move',profile.role <> 'site_sup',
        'locations',(
            select coalesce(jsonb_agg(jsonb_build_object('id',s.id,'name',s.site_name) order by s.site_name),'[]')
            from public.sites s where s.status='active' and s.removed_at is null and vcms_store.can_see(profile,s.id)
        ),
        'supervisors',(
            select coalesce(jsonb_agg(to_jsonb(s) order by s.name,s.id),'[]')
            from vcms_store.supervisors s where profile.role <> 'site_sup'
        ),
        'stock',(
            select coalesce(jsonb_agg(to_jsonb(a)-'created_by' || jsonb_build_object(
                'quantity',b.quantity,'site_id',b.site_id,'location',coalesce(s.site_name,'Main Store')
            ) order by a.name,a.code,s.site_name),'[]')
            from vcms_store.stock b join vcms_store.assets a on a.id=b.asset_id
            left join public.sites s on s.id=b.site_id
            where vcms_store.can_see(profile,b.site_id)
        )
    );
end;
$$;

create function public.store_movement_log(p_from date,p_to date,p_page integer,p_location text,p_type text,p_search text)
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
    profile public.users := vcms_store.actor();
begin
    if p_from is null or p_to is null or p_to<p_from or p_to-p_from>366 or p_page is null or p_page not between 0 and 1000 then
        raise exception using errcode='22023', message='Choose a valid date range of up to one year.';
    end if;
    return (
        select coalesce(jsonb_agg(to_jsonb(log) order by log.moved_on desc,log.created_at desc,log.id desc),'[]')
        from (
            select m.id,m.moved_on,m.created_at,a.code,a.name,m.from_name,m.to_name,m.quantity,
                   m.handed_over,m.receiver_name,m.requester_name,m.notes,
                   count(*) over() as movement_count,sum(m.quantity) over() as units_moved,
                   count(*) filter(where m.from_site is null) over() as issues,
                   count(*) filter(where m.to_site is null) over() as returns,
                   count(*) filter(where m.from_site is not null and m.to_site is not null) over() as transfers,
                   case when m.from_site is null then 'Store issue' when m.to_site is null then 'Store return' else 'Site transfer' end as type
            from vcms_store.movements m join vcms_store.assets a on a.id=m.asset_id
            where m.moved_on between p_from and p_to
              and (vcms_store.can_see(profile,m.from_site) or vcms_store.can_see(profile,m.to_site))
              and (nullif(p_location,'') is null or (p_location='main' and (m.from_site is null or m.to_site is null))
                   or p_location=m.from_site::text or p_location=m.to_site::text)
              and (nullif(p_type,'') is null or p_type=case when m.from_site is null then 'Store issue'
                   when m.to_site is null then 'Store return' else 'Site transfer' end)
              and (nullif(p_search,'') is null or strpos(lower(concat_ws(' ',a.name,a.code,m.from_name,m.to_name,
                   m.handed_over,m.receiver_name,m.requester_name)),lower(p_search))>0)
            order by m.moved_on desc,m.created_at desc,m.id desc limit 51 offset p_page*50
        ) log
    );
end;
$$;

create function public.store_add_asset(p_id uuid,p_site uuid,p_quantity integer,p_asset jsonb)
returns uuid language plpgsql security definer set search_path = ''
as $$
declare
    profile public.users := vcms_store.actor();
    previous vcms_store.assets;
    new_code text := upper(btrim(p_asset->>'code'));
begin
    if p_id is null or p_quantity is null or p_quantity not between 1 and 9999 then
        raise exception using errcode='22023', message='Enter a quantity between 1 and 9999.';
    end if;
    if not vcms_store.can_see(profile,p_site) then
        raise exception using errcode='42501', message='You do not manage this store or site.';
    end if;
    perform vcms_store.location_name(p_site);
    if p_quantity<>1 and (p_asset->>'category'<>'Tool' or nullif(btrim(p_asset->>'serial_number'),'') is not null) then
        raise exception using errcode='22023', message='Only tools without a serial can be registered in bulk.';
    end if;
    insert into vcms_store.assets (id,code,name,category,brand,model,serial_number,registration_number,
                                  equipment_type,ownership,lm_reference,meter_reading,condition,notes,
                                  purchase_date,last_maintenance,last_calibration,last_repair,created_by) values (
        p_id,new_code,btrim(p_asset->>'name'),p_asset->>'category',
        nullif(btrim(p_asset->>'brand'),''),nullif(btrim(p_asset->>'model'),''),
        nullif(btrim(p_asset->>'serial_number'),''),nullif(btrim(p_asset->>'registration_number'),''),
        nullif(btrim(p_asset->>'equipment_type'),''),
        nullif(btrim(p_asset->>'ownership'),''),nullif(btrim(p_asset->>'lm_reference'),''),
        nullif(btrim(p_asset->>'meter_reading'),''),coalesce(p_asset->>'condition','Unverified'),
        nullif(btrim(p_asset->>'notes'),''),nullif(p_asset->>'purchase_date','')::date,
        nullif(p_asset->>'last_maintenance','')::date,nullif(p_asset->>'last_calibration','')::date,
        nullif(p_asset->>'last_repair','')::date,profile.id
    ) on conflict(id) do nothing;
    if not found then
        select * into previous from vcms_store.assets where id=p_id;
        if previous.created_by is distinct from profile.id or previous.code is distinct from new_code then
            raise exception using errcode='23505', message='This registration reference is already in use.';
        end if;
        return p_id;
    end if;
    insert into vcms_store.stock values(p_id,p_site,p_quantity);
    return p_id;
end;
$$;

create function public.store_move_asset(
    p_id uuid,p_asset uuid,p_from uuid,p_to uuid,p_quantity integer,p_date date,
    p_handed_over text,p_received uuid,p_requested uuid,p_notes text
)
returns uuid language plpgsql security definer set search_path = ''
as $$
declare
    profile public.users := vcms_store.actor();
    previous vcms_store.movements;
    available integer;
    source_name text;
    destination_name text;
    receiver text;
    requester text;
begin
    if profile.role='site_sup' then
        raise exception using errcode='42501', message='Store transfers are recorded by logistics or coordinators.';
    end if;
    if p_id is null or p_quantity is null or p_quantity not between 1 and 9999
       or p_from is not distinct from p_to or p_date is null
       or p_date>(now() at time zone 'Asia/Singapore')::date then
        raise exception using errcode='22023', message='Check the movement locations, quantity and date.';
    end if;

    -- Serialize movements for the same asset, including retries and opposite routes.
    perform 1 from vcms_store.assets where id=p_asset for update;
    if not found then raise exception using errcode='22023', message='Equipment was not found.'; end if;
    select * into previous from vcms_store.movements where id=p_id;
    if found then
        if row(previous.created_by,previous.asset_id,previous.from_site,previous.to_site,previous.quantity,
               previous.moved_on,previous.received_by,previous.requested_by,previous.handed_over,previous.notes)
           is distinct from row(profile.id,p_asset,p_from,p_to,p_quantity,p_date,p_received,p_requested,
                               nullif(btrim(p_handed_over),''),nullif(btrim(p_notes),'')) then
            raise exception using errcode='23505', message='This movement reference is already in use.';
        end if;
        return p_id;
    end if;

    select site_name into source_name from public.sites where id=p_from;
    destination_name := vcms_store.location_name(p_to);
    select name into receiver from vcms_store.supervisors where id=p_received;
    select name into requester from vcms_store.supervisors where id=p_requested;
    if nullif(btrim(p_handed_over),'') is not null and not exists (
        select 1 from vcms_store.drivers where name=btrim(p_handed_over) and active
    ) then
        raise exception using errcode='22023', message='Select an active driver.';
    end if;
    if receiver is null or (p_requested is not null and requester is null) then
        raise exception using errcode='22023', message='Select an active VCMS supervisor.';
    end if;
    select quantity into available from vcms_store.stock where asset_id=p_asset and site_id is not distinct from p_from;
    if coalesce(available,0)<p_quantity then
        raise exception using errcode='22023', message='The source no longer has enough stock. Refresh and retry.';
    end if;
    if available=p_quantity then
        delete from vcms_store.stock where asset_id=p_asset and site_id is not distinct from p_from;
    else
        update vcms_store.stock set quantity=quantity-p_quantity where asset_id=p_asset and site_id is not distinct from p_from;
    end if;
    insert into vcms_store.stock as stock values(p_asset,p_to,p_quantity)
    on conflict(asset_id,site_id) do update set quantity=stock.quantity+excluded.quantity;
    insert into vcms_store.movements(
        id,asset_id,from_site,to_site,from_name,to_name,quantity,moved_on,handed_over,
        received_by,receiver_name,requested_by,requester_name,notes,created_by
    ) values(
        p_id,p_asset,p_from,p_to,coalesce(source_name,'Main Store'),destination_name,p_quantity,p_date,
        nullif(btrim(p_handed_over),''),p_received,receiver,p_requested,requester,nullif(btrim(p_notes),''),profile.id
    );
    return p_id;
end;
$$;

revoke all on function public.store_register(),public.store_movement_log(date,date,integer,text,text,text),
    public.store_add_asset(uuid,uuid,integer,jsonb),
    public.store_move_asset(uuid,uuid,uuid,uuid,integer,date,text,uuid,uuid,text) from public,anon;
grant execute on function public.store_register(),public.store_movement_log(date,date,integer,text,text,text),
    public.store_add_asset(uuid,uuid,integer,jsonb),
    public.store_move_asset(uuid,uuid,uuid,uuid,integer,date,text,uuid,uuid,text) to authenticated;
commit;
