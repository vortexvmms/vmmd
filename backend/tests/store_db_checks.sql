insert into public.users values
('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','Store Manager','admin','active'),
('10000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000002','Site Supervisor','site_sup','active'),
('10000000-0000-0000-0000-000000000003','20000000-0000-0000-0000-000000000003','Payroll','payroll','active');
insert into public.sites values
('30000000-0000-0000-0000-000000000002','Assigned site','active',null),
('30000000-0000-0000-0000-000000000003','Other site','active',null);
insert into public.site_supervisors values ('30000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002');

set role authenticated;
select set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000001',false);
do $$
declare
    asset constant uuid := '40000000-0000-0000-0000-000000000001';
    move_id constant uuid := '50000000-0000-0000-0000-000000000001';
    photo constant uuid := '60000000-0000-0000-0000-000000000001';
    reminder constant uuid := '70000000-0000-0000-0000-000000000001';
    completion constant uuid := '80000000-0000-0000-0000-000000000001';
    site constant uuid := '30000000-0000-0000-0000-000000000002';
    receiver constant uuid := '10000000-0000-0000-0000-000000000002';
    sg_today constant date := (now() at time zone 'Asia/Singapore')::date;
begin
    perform public.store_add_asset(asset,null,6,'{"code":"TOOLS-1","name":"Tool set","category":"Tool"}');
    perform public.store_add_asset(asset,null,6,'{"code":"TOOLS-1","name":"Tool set","category":"Tool"}');
    perform public.store_move_asset(move_id,asset,null,site,4,sg_today,null,receiver,null,'Test move');
    perform public.store_move_asset(move_id,asset,null,site,4,sg_today,null,receiver,null,'Test move');
    begin
        perform public.store_move_asset(gen_random_uuid(),asset,null,site,3,sg_today,null,receiver,null,null);
        raise exception 'Excess quantity was accepted';
    exception when invalid_parameter_value then null; end;
    if (select sum((item->>'quantity')::integer) from jsonb_array_elements(public.store_register()->'stock') item)<>6 then
        raise exception 'Stock was lost or duplicated';
    end if;
    if jsonb_array_length(public.store_movement_log(sg_today,sg_today,0,'main','Store issue','TOOLS-1'))<>1 then
        raise exception 'Movement replay or filters were incorrect';
    end if;
    perform public.store_photo_attach(photo,null,move_id,'image/jpeg');
    if (public.store_photo_read(photo)->>'key') <> 'movements/'||move_id||'/'||photo then
        raise exception 'Private photo key was incorrect';
    end if;
    perform public.store_save_reminder(reminder,asset,'Monthly machinery maintenance',sg_today,receiver,'Open','test');
    perform public.store_complete_reminder(reminder,completion,sg_today,sg_today+31,'report');
    perform public.store_complete_reminder(reminder,completion,sg_today,sg_today+31,'report');
    if jsonb_array_length(public.store_extras()->'reminders'->0->'history')<>1 then
        raise exception 'Completion retry duplicated the history';
    end if;
    perform public.store_confirm_count(gen_random_uuid(),site,jsonb_build_object(asset,4));
    perform set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000002',true);
    if jsonb_array_length(public.store_register()->'stock')<>1 or (public.store_register()->>'can_move')::boolean then
        raise exception 'Site scope failed';
    end if;
    if public.store_photo_read(photo)->>'mime'<>'image/jpeg' then raise exception 'Assigned site lacks photo access'; end if;
    begin
        perform public.store_edit_asset(asset,'{"name":"Unauthorized"}');
        raise exception 'Shared asset edited by supervisor';
    exception when insufficient_privilege then null; end;
    perform set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000003',true);
    begin
        perform public.store_register();
        raise exception 'Unauthorized account read the register';
    exception when insufficient_privilege then null; end;
end $$;
reset role;
set role anon;
do $$
begin
    begin
        perform public.store_register();
        raise exception 'Anonymous caller read the register';
    exception when insufficient_privilege then null; end;
end $$;
