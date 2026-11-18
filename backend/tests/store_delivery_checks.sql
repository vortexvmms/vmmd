reset role;
begin;
insert into public.users(id,auth_uid,name,role,status,menu) values
('d1000000-0000-0000-0000-000000000001','d2000000-0000-0000-0000-000000000001','Receiving Supervisor','site_sup','active',null),
('d1000000-0000-0000-0000-000000000002','d2000000-0000-0000-0000-000000000002','Pickup Supervisor','site_sup','active',null),
('d1000000-0000-0000-0000-000000000003','d2000000-0000-0000-0000-000000000003','Dispatcher','logistics_sup','active',null),
('d1000000-0000-0000-0000-000000000004','d2000000-0000-0000-0000-000000000004','Assigned Driver','driver','active','["store.html"]'),
('d1000000-0000-0000-0000-000000000005','d2000000-0000-0000-0000-000000000005','Other Driver','driver','active',null);
insert into public.sites(id,site_name,status,removed_at) values
('d3000000-0000-0000-0000-000000000001','Receiving Site','active',null),
('d3000000-0000-0000-0000-000000000002','Pickup Site','active',null);
insert into public.site_supervisors(site_id,user_id) values
('d3000000-0000-0000-0000-000000000001','d1000000-0000-0000-0000-000000000001'),
('d3000000-0000-0000-0000-000000000002','d1000000-0000-0000-0000-000000000002');
insert into vcms_store.assets(id,code,name,category,created_by) values
('d4000000-0000-0000-0000-000000000001','DEL-1','Compactor','Tool','d1000000-0000-0000-0000-000000000003');
insert into vcms_store.stock(asset_id,site_id,quantity) values
('d4000000-0000-0000-0000-000000000001','d3000000-0000-0000-0000-000000000002',3);

set local role authenticated;
do $$
declare
    job constant uuid := 'd5000000-0000-0000-0000-000000000001';
    rival constant uuid := 'd5000000-0000-0000-0000-000000000002';
    asset constant uuid := 'd4000000-0000-0000-0000-000000000001';
    pickup constant uuid := 'd3000000-0000-0000-0000-000000000002';
    destination constant uuid := 'd3000000-0000-0000-0000-000000000001';
    driver constant uuid := 'd1000000-0000-0000-0000-000000000004';
    request_data jsonb := jsonb_build_object('asset_id',asset,'from_site',pickup,'to_site',destination,
        'quantity',2,'needed_on',current_date);
begin
    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000001',true);
    if (select count(*) from public.store_isolation_fixture)<>1 then raise exception 'Staff access changed'; end if;
    perform public.store_delivery_change(job,job,'request',request_data);
    perform public.store_delivery_change(job,job,'request',request_data);
    perform public.store_delivery_change(rival,rival,'request',request_data);
    begin
        perform public.store_delivery_change(job,gen_random_uuid(),'release','{"quantity":2}');
        raise exception 'Requester released own request';
    exception when insufficient_privilege then null; end;

    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000002',true);
    perform public.store_delivery_change(job,gen_random_uuid(),'release','{"quantity":2}');
    begin
        perform public.store_delivery_change(rival,gen_random_uuid(),'release','{"quantity":2}');
        raise exception 'Over-reservation accepted';
    exception when invalid_parameter_value then null; end;

    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000003',true);
    perform public.store_delivery_change(job,gen_random_uuid(),'assign',jsonb_build_object('driver_id',driver));
    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000005',true);
    if jsonb_array_length(public.store_delivery_register(null,null)->'rows')<>0 then
        raise exception 'Another driver can see the job';
    end if;
    begin
        perform public.store_delivery_photo(job,false);
        raise exception 'Another driver can read the proof';
    exception when insufficient_privilege then null; end;
    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000004',true);
    if (select count(*) from public.store_isolation_fixture)<>0 then raise exception 'Driver can read unrelated data'; end if;
    begin
        perform public.store_register();
        raise exception 'Driver can open the Store stock register through a menu grant';
    exception when insufficient_privilege then null; end;
    begin
        perform public.store_delivery_photo_attach(job,gen_random_uuid(),driver,'image/jpeg');
        raise exception 'Driver can forge a photo receipt';
    exception when insufficient_privilege then null; end;
    begin
        perform public.store_delivery_change(job,gen_random_uuid(),'pickup','{}');
        raise exception 'Assigned driver can skip photo';
    exception when invalid_parameter_value then null; end;
end;
$$;

reset role;
do $$
begin
    begin
        update vcms_store.stock set quantity=1 where asset_id='d4000000-0000-0000-0000-000000000001';
        raise exception 'Stock reservation did not protect legacy stock adjustments';
    exception when invalid_parameter_value then null; end;
end;
$$;
set local role service_role;
select public.store_delivery_photo_attach('d5000000-0000-0000-0000-000000000001',
    'd6000000-0000-0000-0000-000000000001','d1000000-0000-0000-0000-000000000004','image/jpeg');
set local role authenticated;
do $$
declare
    job constant uuid := 'd5000000-0000-0000-0000-000000000001';
    receipt constant uuid := 'd7000000-0000-0000-0000-000000000001';
    return_job constant uuid := 'd5000000-0000-0000-0000-000000000003';
begin
    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000004',true);
    perform public.store_delivery_change(job,gen_random_uuid(),'pickup','{}');
    perform public.store_delivery_change(job,gen_random_uuid(),'deliver','{"recipient":"Site recipient"}');
    begin
        perform public.store_delivery_change(job,gen_random_uuid(),'receive','{"quantity":2}');
        raise exception 'Driver can post stock';
    exception when insufficient_privilege then null; end;
    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000003',true);
    begin
        perform public.store_delivery_change(job,gen_random_uuid(),'receive','{"quantity":2}');
        raise exception 'Dispatcher received on behalf of an unassigned site';
    exception when insufficient_privilege then null; end;
    perform set_config('request.jwt.claim.sub','d2000000-0000-0000-0000-000000000001',true);
    perform public.store_delivery_change(job,receipt,'receive','{"quantity":2}');
    perform public.store_delivery_change(job,receipt,'receive','{"quantity":2}');
    perform public.store_delivery_change(return_job,return_job,'request',jsonb_build_object(
        'asset_id','d4000000-0000-0000-0000-000000000001','from_site','d3000000-0000-0000-0000-000000000001',
        'to_site',null,'quantity',1,'needed_on',current_date));
    if public.store_delivery_photo(job,false)->>'mime' <> 'image/jpeg' then raise exception 'Proof missing after receipt'; end if;
end;
$$;
reset role;
do $$
declare
    job constant uuid := 'd5000000-0000-0000-0000-000000000001';
    asset constant uuid := 'd4000000-0000-0000-0000-000000000001';
begin
    if (select count(*) from vcms_store.delivery_events where delivery_id=job)<>7
        or (select count(*) from vcms_store.movements where id=job and quantity=2)<>1
        or (select quantity from vcms_store.stock where asset_id=asset and site_id='d3000000-0000-0000-0000-000000000001')<>2
        or (select quantity from vcms_store.stock where asset_id=asset and site_id='d3000000-0000-0000-0000-000000000002')<>1 then
        raise exception 'Movement, proof, timeline or stock is inconsistent after replay';
    end if;
end;
$$;
rollback;
