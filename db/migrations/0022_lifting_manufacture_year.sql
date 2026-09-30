-- Preserve existing values/history while adding an optional four-digit manufacture year.
begin;
alter table public.lifting_machines add column year_of_manufacture integer check(year_of_manufacture between 1000 and 9999);

create or replace function public.lifting_review(p_document_id uuid,p_data jsonb,p_target_id uuid default null) returns jsonb language plpgsql security definer set search_path=public as $$
declare d lifting_documents; m lifting_machines; g lifting_gear_certificates; tag text; n integer; begin
 if not lifting_can_manage() then raise exception 'Not authorised'; end if;
 select * into d from lifting_documents where id=p_document_id for update;
 if d.id is null or d.verified then raise exception 'Document missing or already verified'; end if;
 if not coalesce((p_data->>'confirmed')::boolean,false) then raise exception 'Review and confirmation required'; end if;
 if d.kind in ('lm','lg') and (nullif(p_data->>'examination_date','') is null or nullif(p_data->>'certificate_expiry','') is null or coalesce(nullif(p_data->>'swl_kg','')::numeric,0)<=0) then raise exception 'Examination date, printed expiry and SWL required'; end if;
 if d.kind='lm' then
  if coalesce(trim(p_data->>'machine_id'),'')='' or coalesce(trim(p_data->>'lm_number'),'')='' then raise exception 'Machine ID and LM number required'; end if;
  select * into m from lifting_machines where lm_number=upper(trim(p_data->>'lm_number')) for update;
  if p_target_id is not null and (m.id is null or m.id<>p_target_id) then raise exception 'Renewal LM number conflicts with selected machine'; end if;
  if m.id is not null then
   if p_target_id is null then raise exception 'Existing LM found. Select it for renewal'; end if;
   if m.machine_id<>trim(p_data->>'machine_id') or (m.vehicle_number<>'' and m.vehicle_number<>upper(trim(p_data->>'vehicle_number'))) or (m.serial_number<>'' and m.serial_number<>trim(p_data->>'serial_number')) then raise exception 'Machine identifiers conflict; correct the review fields'; end if;
   if (p_data->>'examination_date')::date < m.examination_date then raise exception 'An older certificate cannot replace the current certificate'; end if;
  else insert into lifting_machines(machine_id) values(trim(p_data->>'machine_id')) returning * into m; end if;
  update lifting_machines set lm_number=upper(trim(p_data->>'lm_number')),vehicle_number=upper(trim(coalesce(p_data->>'vehicle_number',''))),equipment=coalesce(p_data->>'equipment',''),year_of_manufacture=case when p_data ? 'year_of_manufacture' then nullif(p_data->>'year_of_manufacture','')::integer else year_of_manufacture end, swl_kg=nullif(p_data->>'swl_kg','')::numeric, examination_date=nullif(p_data->>'examination_date','')::date,certificate_expiry=nullif(p_data->>'certificate_expiry','')::date, owner=coalesce(p_data->>'owner',''),serial_number=coalesce(p_data->>'serial_number',''),remarks=coalesce(p_data->>'remarks',''),current_document_id=d.id,updated_at=now() where id=m.id;
  update lifting_documents set machine_id=m.id where id=d.id;
 elsif d.kind='lg' then
  if coalesce(trim(p_data->>'lg_number'),'')='' or coalesce(trim(p_data->>'gear_type'),'')='' or coalesce(trim(p_data->>'renewal_reason'),'')='' then raise exception 'LG number, gear type and renewal interval reason required'; end if;
  n=jsonb_array_length(p_data->'markings'); if n is null or n<1 or n>100 then raise exception 'Confirm physical markings for each item (1–100)'; end if;
  if nullif(p_data->>'quantity','') is not null and (p_data->>'quantity')::integer<>n then raise exception 'Number of confirmed markings must match certificate quantity'; end if;
  select * into g from lifting_gear_certificates where lg_number=upper(trim(p_data->>'lg_number')) for update;
  if p_target_id is not null and (g.id is null or g.id<>p_target_id) then raise exception 'LG number conflicts with renewal selection'; end if;
  if g.id is not null then
   if p_target_id is null then raise exception 'Existing LG found. Select it for renewal'; end if;
   if (p_data->>'examination_date')::date < g.examination_date then raise exception 'An older certificate cannot replace the current certificate'; end if;
   if n<>(select count(*) from lifting_gear_items where certificate_id=g.id) or exists(select 1 from lifting_gear_items where certificate_id=g.id and not (p_data->'markings' ? marking)) then raise exception 'Physical markings conflict with existing items'; end if;
  else
   insert into lifting_gear_certificates(lg_number,gear_type) values(upper(trim(p_data->>'lg_number')),p_data->>'gear_type') returning * into g;
   for tag in select jsonb_array_elements_text(p_data->'markings') loop insert into lifting_gear_items(certificate_id,marking) values(g.id,trim(tag)); end loop;
  end if;
  update lifting_gear_certificates set gear_type=p_data->>'gear_type',size=coalesce(p_data->>'size',''),length=coalesce(p_data->>'length',''),swl_kg=nullif(p_data->>'swl_kg','')::numeric,examination_date=nullif(p_data->>'examination_date','')::date,certificate_expiry=nullif(p_data->>'certificate_expiry','')::date,renewal_months=coalesce((p_data->>'renewal_months')::integer,6),renewal_reason=p_data->>'renewal_reason',remarks=coalesce(p_data->>'remarks',''),current_document_id=d.id,updated_at=now() where id=g.id;
  update lifting_documents set gear_certificate_id=g.id where id=d.id;
 else
  select * into m from lifting_machines where id=p_target_id for update;
  if m.id is null then raise exception 'Choose the machine for this document'; end if;
  update lifting_documents set machine_id=m.id where id=d.id;
 end if;
 update lifting_documents set verified=true,verified_by=auth.uid(),verified_at=now(),ocr_used=coalesce((p_data->>'ocr_used')::boolean,false),extracted_text=left(coalesce(p_data->>'extracted_text',''),100000),extracted_fields=p_data-'extracted_text' where id=d.id returning * into d;
 return to_jsonb(d);
end $$;
revoke all on function public.lifting_review(uuid,jsonb,uuid) from public,anon;
grant execute on function public.lifting_review(uuid,jsonb,uuid) to authenticated;
insert into public.schema_migrations(version,description) values('0022','Optional lifting machine manufacture year');
commit;
