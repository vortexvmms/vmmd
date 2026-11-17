begin;

alter table vcms_store.assets
    add column archived_at timestamptz,
    add column archived_by uuid references public.users(id),
    add column archived_stock jsonb;

create function public.store_archive_asset(p_id uuid)
returns uuid language plpgsql security definer set search_path=''
as $$
declare
    profile public.users := vcms_store.actor();
    asset vcms_store.assets;
    stock_snapshot jsonb;
begin
    if profile.role not in ('admin','general_manager','operation_manager') then
        raise exception using errcode='42501', message='Only administrators and operations managers can archive equipment.';
    end if;

    -- Serialize with transfers, edits and photo attachment for this asset.
    select * into asset from vcms_store.assets where id=p_id for update;
    if not found then
        raise exception using errcode='22023', message='Equipment was not found.';
    end if;
    if asset.archived_at is not null then
        return p_id;
    end if;

    select coalesce(jsonb_agg(jsonb_build_object('site_id',site_id,'quantity',quantity) order by site_id),'[]')
    into stock_snapshot from vcms_store.stock where asset_id=p_id;

    update vcms_store.assets
    set archived_at=now(), archived_by=profile.id, archived_stock=stock_snapshot, updated_at=now()
    where id=p_id;
    delete from vcms_store.stock where asset_id=p_id;
    return p_id;
end;
$$;

revoke all on function public.store_archive_asset(uuid) from public,anon;
grant execute on function public.store_archive_asset(uuid) to authenticated;

commit;
