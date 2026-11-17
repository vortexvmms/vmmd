begin;

create or replace function vcms_store.actor()
returns public.users language plpgsql stable set search_path = ''
as $$
declare
    profile public.users;
begin
    select * into profile from public.users where auth_uid=auth.uid() and status='active';
    if profile.id is null or (
        not coalesce(profile.role in ('admin','general_manager','operation_manager','main_sup'),false)
        and not coalesce(profile.menu ? 'store.html',false)
    ) then
        raise exception using errcode='42501', message='Equipment Store access is limited to managers and selected users.';
    end if;
    return profile;
end;
$$;

create function vcms_store.can_coordinate(profile public.users)
returns boolean language sql stable set search_path = ''
as $$ select profile.role in ('admin','general_manager','operation_manager','main_sup','hr_assistant','wshc_lead','logistics_sup'); $$;

create or replace function vcms_store.can_see(profile public.users, location uuid)
returns boolean language sql stable set search_path = ''
as $$
    select vcms_store.can_coordinate(profile) or exists (
        select 1 from public.site_supervisors s where s.user_id=profile.id and s.site_id=location
    );
$$;

create or replace function public.store_register()
returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
    profile public.users := vcms_store.actor();
begin
    return jsonb_build_object(
        'actor_id',profile.id,
        'can_move',vcms_store.can_coordinate(profile),
        'locations',(
            select coalesce(jsonb_agg(jsonb_build_object('id',s.id,'name',s.site_name) order by s.site_name),'[]')
            from public.sites s where s.status='active' and s.removed_at is null and vcms_store.can_see(profile,s.id)
        ),
        'supervisors',(
            select coalesce(jsonb_agg(to_jsonb(s) order by s.name,s.id),'[]')
            from vcms_store.supervisors s where vcms_store.can_coordinate(profile)
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

create or replace function public.store_move_asset(
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
    if not vcms_store.can_coordinate(profile) then
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
    update vcms_store.assets set updated_at=now() where id=p_asset;
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

create or replace function vcms_store.photo_access(profile public.users, asset uuid, movement uuid, writable boolean)
returns boolean language sql stable set search_path=''
as $$
    select case when asset is not null and movement is null then vcms_store.asset_visible(profile,asset)
        when movement is not null and asset is null then exists (
            select 1 from vcms_store.movements m where m.id=movement
            and (not writable or vcms_store.can_coordinate(profile))
            and (vcms_store.can_see(profile,m.from_site) or vcms_store.can_see(profile,m.to_site))
        ) else false end;
$$;

create or replace function public.store_extras()
returns jsonb language plpgsql stable security definer set search_path=''
as $$
declare profile public.users := vcms_store.actor();
begin
    return jsonb_build_object(
        'can_manage_drivers',profile.role in ('admin','general_manager','operation_manager','main_sup','logistics_sup'),
        'drivers',(select coalesce(jsonb_agg(to_jsonb(d) order by d.name),'[]')
            from vcms_store.drivers d where d.active and vcms_store.can_coordinate(profile)),
        'reminders',(select coalesce(jsonb_agg(to_jsonb(r)-'created_by' || jsonb_build_object(
            'asset_name',a.name,'asset_code',a.code,'assignee_name',u.name
        ) order by r.due,r.id),'[]') from vcms_store.reminders r join vcms_store.assets a on a.id=r.asset_id
             left join public.users u on u.id=r.assignee where vcms_store.asset_visible(profile,r.asset_id))
    );
end;
$$;

create function vcms_store.guard_store_menu_grant()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare
    previously_granted boolean := false;
    newly_granted boolean := coalesce(new.menu ? 'store.html',false);
begin
    if tg_op = 'UPDATE' then
        previously_granted := coalesce(old.menu ? 'store.html',false);
    end if;
    if newly_granted <> previously_granted and auth.uid() is not null and not exists (
        select 1 from public.users u where u.auth_uid=auth.uid() and u.status='active'
        and u.role in ('admin','general_manager','operation_manager')
    ) then
        raise exception using errcode='42501',message='Only administrators and management can change Equipment Store access.';
    end if;
    return new;
end;
$$;

revoke all on function vcms_store.guard_store_menu_grant() from public,anon,authenticated;
create trigger guard_store_menu_grant before insert or update of menu on public.users
for each row execute function vcms_store.guard_store_menu_grant();

commit;
