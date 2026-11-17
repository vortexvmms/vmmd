begin;
create table vcms_store.photos (
    id uuid primary key,
    asset_id uuid references vcms_store.assets(id),
    movement_id uuid references vcms_store.movements(id),
    object_key text not null unique,
    mime text not null check (mime in ('image/jpeg','image/png','image/webp')),
    created_by uuid not null references public.users(id),
    created_at timestamptz not null default now(),
    check (num_nonnulls(asset_id,movement_id)=1)
);
create index store_photos_asset on vcms_store.photos(asset_id);
create index store_photos_movement on vcms_store.photos(movement_id);
create table vcms_store.drivers (
    id uuid primary key,
    name text not null check (length(btrim(name)) between 1 and 100),
    active boolean not null default true
);
create unique index store_driver_name on vcms_store.drivers(lower(name)) where active;
create table vcms_store.reminders (
    id uuid primary key,
    asset_id uuid not null references vcms_store.assets(id),
    kind text not null check (length(btrim(kind)) between 1 and 100),
    due date not null,
    assignee uuid references public.users(id),
    status text not null default 'Open' check (status in ('Open','Booked','Out for service','Completed')),
    reference text,
    history jsonb not null default '[]',
    created_by uuid not null references public.users(id)
);
create index store_reminder_asset_due on vcms_store.reminders(asset_id,due);
alter table vcms_store.photos enable row level security;
alter table vcms_store.drivers enable row level security;
alter table vcms_store.reminders enable row level security;

create function vcms_store.asset_visible(profile public.users, target uuid)
returns boolean language sql stable set search_path=''
as $$ select exists (select 1 from vcms_store.stock s where s.asset_id=target and vcms_store.can_see(profile,s.site_id)); $$;

create function vcms_store.photo_access(profile public.users, asset uuid, movement uuid, writable boolean)
returns boolean language sql stable set search_path=''
as $$
    select case when asset is not null and movement is null then vcms_store.asset_visible(profile,asset)
        when movement is not null and asset is null then exists (
            select 1 from vcms_store.movements m where m.id=movement
            and (not writable or profile.role<>'site_sup')
            and (vcms_store.can_see(profile,m.from_site) or vcms_store.can_see(profile,m.to_site))
        ) else false end;
$$;

create function public.store_photo_list(p_asset uuid,p_movement uuid)
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare profile public.users := vcms_store.actor();
begin
    if not vcms_store.photo_access(profile,p_asset,p_movement,false) then
        raise exception using errcode='42501',message='Photo access is unavailable for this record.';
    end if;
    return (select coalesce(jsonb_agg(jsonb_build_object('id',p.id) order by p.created_at,p.id),'[]')
        from vcms_store.photos p where p.asset_id is not distinct from p_asset and p.movement_id is not distinct from p_movement);
end;
$$;

create function public.store_photo_attach(p_id uuid,p_asset uuid,p_movement uuid,p_mime text)
returns uuid language plpgsql security definer set search_path=''
as $$
declare profile public.users := vcms_store.actor();
begin
    if not vcms_store.photo_access(profile,p_asset,p_movement,true) then
        raise exception using errcode='42501',message='Photo uploads are unavailable for this record.';
    end if;
    -- Lock the parent row so two uploads cannot exceed the limit.
    if p_asset is not null then perform 1 from vcms_store.assets where id=p_asset for update;
    else perform 1 from vcms_store.movements where id=p_movement for update; end if;
    if not vcms_store.photo_access(profile,p_asset,p_movement,true) then
        raise exception using errcode='42501',message='Photo uploads are unavailable for this record.';
    end if;
    if (select count(*) from vcms_store.photos p where p.asset_id is not distinct from p_asset
        and p.movement_id is not distinct from p_movement)>=4 then
        raise exception using errcode='22023',message='Each record can have up to four photos.';
    end if;
    insert into vcms_store.photos(id,asset_id,movement_id,object_key,mime,created_by)
    values(p_id,p_asset,p_movement,coalesce('assets/'||p_asset,'movements/'||p_movement)||'/'||p_id,p_mime,profile.id);
    return p_id;
end;
$$;

create function public.store_photo_read(p_id uuid)
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare
    profile public.users := vcms_store.actor();
    photo vcms_store.photos;
begin
    select * into photo from vcms_store.photos where id=p_id;
    if not found or not vcms_store.photo_access(profile,photo.asset_id,photo.movement_id,false) then
        raise exception using errcode='42501',message='Photo access is unavailable for this record.';
    end if;
    return jsonb_build_object('key',photo.object_key,'mime',photo.mime);
end;
$$;

create function public.store_extras()
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare profile public.users := vcms_store.actor();
begin
    return jsonb_build_object(
        'can_manage_drivers',profile.role in ('admin','general_manager','operation_manager','main_sup','logistics_sup'),
        'drivers',(select coalesce(jsonb_agg(to_jsonb(d) order by d.name),'[]')
            from vcms_store.drivers d where d.active and profile.role<>'site_sup'),
        'reminders',(select coalesce(jsonb_agg(to_jsonb(r)-'created_by' || jsonb_build_object(
            'asset_name',a.name,'asset_code',a.code,'assignee_name',u.name
        ) order by r.due,r.id),'[]') from vcms_store.reminders r join vcms_store.assets a on a.id=r.asset_id
             left join public.users u on u.id=r.assignee where vcms_store.asset_visible(profile,r.asset_id))
    );
end;
$$;

create function public.store_save_driver(p_id uuid,p_name text,p_active boolean)
returns uuid language plpgsql security definer set search_path=''
as $$
declare profile public.users := vcms_store.actor();
begin
    if profile.role not in ('admin','general_manager','operation_manager','main_sup','logistics_sup') then
        raise exception using errcode='42501',message='Only managers and logistics can change drivers.';
    end if;
    insert into vcms_store.drivers values(p_id,btrim(p_name),p_active)
    on conflict(id) do update set name=excluded.name,active=excluded.active;
    return p_id;
end;
$$;

create function public.store_save_reminder(p_id uuid,p_asset uuid,p_kind text,p_due date,p_assignee uuid,p_status text,p_reference text)
returns uuid language plpgsql security definer set search_path=''
as $$
declare profile public.users := vcms_store.actor();
begin
    if not vcms_store.asset_visible(profile,p_asset) then
        raise exception using errcode='42501',message='You do not manage this asset.';
    end if;
    if p_assignee is not null and not exists(select 1 from vcms_store.supervisors where id=p_assignee) then
        raise exception using errcode='22023',message='Select an active supervisor.';
    end if;
    if p_status not in ('Open','Booked','Out for service') then
        raise exception using errcode='22023',message='Choose an active reminder status.';
    end if;
    insert into vcms_store.reminders(id,asset_id,kind,due,assignee,status,reference,created_by)
    values(p_id,p_asset,btrim(p_kind),p_due,p_assignee,p_status,p_reference,profile.id)
    on conflict(id) do update set kind=excluded.kind,due=excluded.due,assignee=excluded.assignee,
        status=excluded.status,reference=excluded.reference
    where vcms_store.reminders.asset_id=excluded.asset_id and vcms_store.reminders.status<>'Completed';
    if not found then raise exception using errcode='22023',message='This reminder can no longer be changed.'; end if;
    return p_id;
end;
$$;

create function public.store_complete_reminder(p_id uuid,p_completion uuid,p_done date,p_next date,p_reference text)
returns uuid language plpgsql security definer set search_path=''
as $$
declare
    profile public.users := vcms_store.actor();
    item vcms_store.reminders;
begin
    select * into item from vcms_store.reminders where id=p_id for update;
    if not found or not vcms_store.asset_visible(profile,item.asset_id) then
        raise exception using errcode='42501',message='You do not manage this reminder.';
    end if;
    if item.history @> jsonb_build_array(jsonb_build_object('id',p_completion)) then return p_id; end if;
    if p_completion is null or item.status='Completed' or p_done is null or p_done>(now() at time zone 'Asia/Singapore')::date
       or (p_next is not null and p_next<=p_done) then
        raise exception using errcode='22023',message='Enter a valid completion date and a later next due date.';
    end if;
    update vcms_store.reminders set due=coalesce(p_next,due),status=case when p_next is null then 'Completed' else 'Open' end,
        history=history || jsonb_build_array(jsonb_build_object('id',p_completion,'done',p_done,'next',p_next,'reference',p_reference,'by',profile.name))
    where id=p_id;
    if item.kind ilike '%calibration%' then
        update vcms_store.assets set last_calibration=greatest(last_calibration,p_done),updated_at=now() where id=item.asset_id;
    elsif item.kind ilike '%maintenance%' or item.kind ilike '%service%' then
        update vcms_store.assets set last_maintenance=greatest(last_maintenance,p_done),updated_at=now() where id=item.asset_id;
    end if;
    return p_id;
end;
$$;
create function public.store_edit_asset(p_id uuid,p_asset jsonb)
returns uuid language plpgsql security definer set search_path=''
as $$
declare profile public.users := vcms_store.actor();
begin
    perform 1 from vcms_store.assets where id=p_id for update;
    if not found or not vcms_store.asset_visible(profile,p_id) or exists (
        select 1 from vcms_store.stock where asset_id=p_id and not vcms_store.can_see(profile,site_id)
    ) then
        raise exception using errcode='42501',message='Only coordinators can edit an asset shared with other sites.';
    end if;
    if (p_asset->>'category'<>'Tool' or nullif(btrim(p_asset->>'serial_number'),'') is not null)
       and (select sum(quantity) from vcms_store.stock where asset_id=p_id)>1 then
        raise exception using errcode='22023',message='An individually tracked item cannot have multiple units.';
    end if;
    update vcms_store.assets set
        code=upper(btrim(p_asset->>'code')),name=btrim(p_asset->>'name'),category=p_asset->>'category',
        brand=nullif(btrim(p_asset->>'brand'),''),model=nullif(btrim(p_asset->>'model'),''),
        serial_number=nullif(btrim(p_asset->>'serial_number'),''),
        registration_number=nullif(btrim(p_asset->>'registration_number'),''),
        equipment_type=nullif(btrim(p_asset->>'equipment_type'),''),ownership=nullif(btrim(p_asset->>'ownership'),''),
        lm_reference=nullif(btrim(p_asset->>'lm_reference'),''),meter_reading=nullif(btrim(p_asset->>'meter_reading'),''),
        condition=p_asset->>'condition',notes=nullif(btrim(p_asset->>'notes'),''),
        purchase_date=nullif(p_asset->>'purchase_date','')::date,
        last_maintenance=nullif(p_asset->>'last_maintenance','')::date,
        last_calibration=nullif(p_asset->>'last_calibration','')::date,
        last_repair=nullif(p_asset->>'last_repair','')::date,updated_at=now()
    where id=p_id;
    return p_id;
end;
$$;

create table vcms_store.counts (
    id uuid primary key,
    site_id uuid references public.sites(id),
    quantities jsonb not null,
    verified_by uuid not null references public.users(id),
    verified_at timestamptz not null default now()
);
alter table vcms_store.counts enable row level security;

create function public.store_confirm_count(p_id uuid,p_site uuid,p_quantities jsonb)
returns jsonb language plpgsql security definer set search_path=''
as $$
declare
    profile public.users := vcms_store.actor();
    expected jsonb;
begin
    if not vcms_store.can_see(profile,p_site) then
        raise exception using errcode='42501',message='You do not manage this location.';
    end if;
    perform vcms_store.location_name(p_site);
    select coalesce(jsonb_object_agg(asset_id,quantity),'{}') into expected
    from vcms_store.stock where site_id is not distinct from p_site;
    if expected is distinct from p_quantities then
        raise exception using errcode='22023',message='Stock changed after loading. Refresh and verify the physical count again.';
    end if;
    insert into vcms_store.counts values(p_id,p_site,expected,profile.id,now()) on conflict(id) do nothing;
    return jsonb_build_object('id',p_id,'verified_by',profile.name);
end;
$$;

revoke all on function public.store_photo_list(uuid,uuid),public.store_photo_attach(uuid,uuid,uuid,text),
    public.store_photo_read(uuid),public.store_extras(),public.store_save_driver(uuid,text,boolean),
    public.store_save_reminder(uuid,uuid,text,date,uuid,text,text),
    public.store_complete_reminder(uuid,uuid,date,date,text),public.store_edit_asset(uuid,jsonb),
    public.store_confirm_count(uuid,uuid,jsonb) from public,anon;
grant execute on function public.store_photo_list(uuid,uuid),public.store_photo_attach(uuid,uuid,uuid,text),
    public.store_photo_read(uuid),public.store_extras(),public.store_save_driver(uuid,text,boolean),
    public.store_save_reminder(uuid,uuid,text,date,uuid,text,text),
    public.store_complete_reminder(uuid,uuid,date,date,text),public.store_edit_asset(uuid,jsonb),
    public.store_confirm_count(uuid,uuid,jsonb) to authenticated;
commit;
