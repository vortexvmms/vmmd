begin;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
insert into public.sic_records(id,worker_id,site_id,name,fin,site_name,sic_date,expiry_date,created_by,updated_by,override_reason)
 values ('30000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',
         '20000000-0000-0000-0000-000000000001','QA Worker','QA01','QA Site',current_date,current_date+365,
         '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','Test expiry');
insert into public.private_r2_image_receipts values
 ('worker-cards','10000000-0000-0000-0000-000000000001/40000000-0000-0000-0000-000000000001.png',
  '00000000-0000-0000-0000-000000000001'),
 ('sic-cards','30000000-0000-0000-0000-000000000001/40000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001');
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
set local role authenticated;
insert into public.worker_cards(worker_id,image_path) values
 ('10000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001/40000000-0000-0000-0000-000000000001.png');
insert into public.sic_attachments(record_id,object_key,filename,mime_type,file_size) values
 ('30000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001/40000000-0000-0000-0000-000000000002','card.png','image/png',10);
do $$ begin
 begin
  insert into public.private_r2_image_receipts values
   ('worker-cards','forged','00000000-0000-0000-0000-000000000001');
  raise exception 'Users must not issue their own R2 receipts';
 exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000002',true);
do $$ begin
 if exists (select 1 from public.private_r2_image_receipts) then
  raise exception 'Another user can read an upload receipt';
 end if;
end $$;
rollback;
