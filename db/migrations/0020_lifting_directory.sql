-- Additive lifting register. Originals, movements and packs are immutable.
begin;
create function public.lifting_can_read() returns boolean language sql stable security definer set search_path=public as $$ select exists(select 1 from public.users where auth_uid=auth.uid() and status='active' and role in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','site_sup','safety_sup','wshc','logistics_sup')) $$;
create function public.lifting_can_manage() returns boolean language sql stable security definer set search_path=public as $$ select exists(select 1 from public.users where auth_uid=auth.uid() and status='active' and role in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','logistics_sup')) $$;
create table public.lifting_machines (
 id uuid primary key default gen_random_uuid(), machine_id text not null unique check(length(trim(machine_id)) between 1 and 80),
 lm_number text unique, vehicle_number text not null default '', equipment text not null default '', swl_kg numeric check(swl_kg>0),
 examination_date date, certificate_expiry date, owner text not null default '', serial_number text not null default '', remarks text not null default '',
 current_document_id uuid, updated_at timestamptz not null default now(),
 check(certificate_expiry is null or examination_date is null or certificate_expiry>=examination_date)
);
create table public.lifting_gear_certificates (
 id uuid primary key default gen_random_uuid(), lg_number text not null unique, gear_type text not null,
 size text not null default '', length text not null default '', swl_kg numeric check(swl_kg>0), examination_date date, certificate_expiry date,
 renewal_months integer not null default 6 check(renewal_months in (6,12)), renewal_reason text not null default '', remarks text not null default '',
 current_document_id uuid, updated_at timestamptz not null default now(),
 check(certificate_expiry is null or examination_date is null or certificate_expiry>=examination_date)
);
create table public.lifting_gear_items (
 id uuid primary key default gen_random_uuid(), certificate_id uuid not null references public.lifting_gear_certificates(id),
 marking text not null check(length(trim(marking))>0), current_machine_id uuid references public.lifting_machines(id),
 condition text not null default 'available' check(condition in ('available','quarantined','retired')),
 unique(certificate_id,marking)
);
create table public.lifting_documents (
 id uuid primary key default gen_random_uuid(), kind text not null check(kind in ('lm','lg','load_chart','supporting')),
 original_filename text not null, object_key text not null unique, mime_type text not null check(mime_type in ('application/pdf','image/jpeg','image/png')),
 file_size integer not null check(file_size between 1 and 20971520), checksum text not null,
 machine_id uuid references public.lifting_machines(id), gear_certificate_id uuid references public.lifting_gear_certificates(id),
 extracted_text text not null default '', extracted_fields jsonb not null default '{}', ocr_used boolean not null default false,
 verified boolean not null default false, verified_by uuid, verified_at timestamptz,
 created_by uuid not null default auth.uid() check(created_by is not null), created_at timestamptz not null default now(),
 check(not(machine_id is not null and gear_certificate_id is not null))
);
alter table public.lifting_machines add foreign key(current_document_id) references public.lifting_documents(id);
alter table public.lifting_gear_certificates add foreign key(current_document_id) references public.lifting_documents(id);
create table public.lifting_movements (
 id uuid primary key default gen_random_uuid(), item_id uuid not null references public.lifting_gear_items(id),
 action text not null check(action in ('issue','borrow','return')), from_machine_id uuid references public.lifting_machines(id),
 to_machine_id uuid references public.lifting_machines(id), moved_at timestamptz not null default now(),
 issued_by text not null, received_by text not null, remarks text not null default '',
 recorded_by uuid not null default auth.uid()
);
create table public.lifting_packs (
 id uuid primary key default gen_random_uuid(), machine_id uuid not null references public.lifting_machines(id),
 snapshot jsonb not null, document_order jsonb not null, generated_by uuid not null default auth.uid(),
 generated_at timestamptz not null default now()
);
create index lifting_items_holder on public.lifting_gear_items(current_machine_id);
create index lifting_documents_machine on public.lifting_documents(machine_id,created_at desc);
create index lifting_documents_gear on public.lifting_documents(gear_certificate_id,created_at desc);
create index lifting_movements_item on public.lifting_movements(item_id,moved_at desc);

-- No direct mutations of registers: atomic RPCs below enforce review and history.
do $$ declare t text; begin foreach t in array array['lifting_machines','lifting_gear_certificates','lifting_gear_items','lifting_documents','lifting_movements','lifting_packs'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('grant select on public.%I to authenticated',t);
 execute format('revoke insert,update,delete on public.%I from anon,authenticated',t);
 execute format('create policy lifting_read on public.%I for select to authenticated using(public.lifting_can_read())',t);
end loop; end $$;
grant insert on public.lifting_documents to authenticated;
create policy lifting_document_insert on public.lifting_documents for insert to authenticated with check(public.lifting_can_manage() and created_by=auth.uid() and verified=false and verified_at is null and verified_by is null and machine_id is null and gear_certificate_id is null and object_key ~ '^originals/[0-9a-f-]{36}$' and exists(select 1 from storage.objects where bucket_id='lifting-documents' and name=object_key));

create function public.lifting_review(p_document_id uuid,p_data jsonb,p_target_id uuid default null) returns jsonb language plpgsql security definer set search_path=public as $$
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
  update lifting_machines set lm_number=upper(trim(p_data->>'lm_number')),vehicle_number=upper(trim(coalesce(p_data->>'vehicle_number',''))),equipment=coalesce(p_data->>'equipment',''),swl_kg=nullif(p_data->>'swl_kg','')::numeric, examination_date=nullif(p_data->>'examination_date','')::date,certificate_expiry=nullif(p_data->>'certificate_expiry','')::date, owner=coalesce(p_data->>'owner',''),serial_number=coalesce(p_data->>'serial_number',''),remarks=coalesce(p_data->>'remarks',''),current_document_id=d.id,updated_at=now() where id=m.id;
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

create function public.lifting_move(p_item_id uuid,p_from uuid,p_to uuid,p_action text,p_issued text,p_received text,p_remarks text default '') returns jsonb language plpgsql security definer set search_path=public as $$
declare i lifting_gear_items; r lifting_movements; begin
 if not lifting_can_manage() then raise exception 'Not authorised'; end if;
 select * into i from lifting_gear_items where id=p_item_id for update;
 if i.id is null or i.condition<>'available' then raise exception 'Gear is unavailable'; end if;
 if i.current_machine_id is distinct from p_from then raise exception 'Holder changed. Refresh before recording movement'; end if;
 if p_from is not distinct from p_to then raise exception 'Choose a different holder'; end if;
 if p_action not in ('issue','borrow','return') or trim(p_issued)='' or trim(p_received)='' then raise exception 'Action and issuing/receiving persons required'; end if;
 insert into lifting_movements(item_id,action,from_machine_id,to_machine_id,issued_by,received_by,remarks) values(i.id,p_action,p_from,p_to,trim(p_issued),trim(p_received),p_remarks) returning * into r;
 update lifting_gear_items set current_machine_id=p_to where id=i.id;
 return to_jsonb(r);
end $$;

-- Snapshot creation locks gear rows against simultaneous transfer and verifies scope.
create function public.lifting_freeze_pack(p_machine_id uuid,p_items uuid[],p_documents uuid[],p_order jsonb,p_ack boolean default false) returns jsonb language plpgsql security definer set search_path=public as $$
declare m lifting_machines; snap jsonb; r lifting_packs; begin
 if not lifting_can_manage() then raise exception 'Not authorised'; end if;
 select * into m from lifting_machines where id=p_machine_id for share;
 if m.id is null then raise exception 'Machine not found'; end if;
 perform 1 from lifting_gear_items where id=any(p_items) for share;
 perform 1 from lifting_gear_certificates where id in (select certificate_id from lifting_gear_items where id=any(p_items)) for share;
 if cardinality(p_items)<>(select count(*) from lifting_gear_items where id=any(p_items) and current_machine_id=m.id and condition='available') then raise exception 'Gear selection changed or is unavailable. Refresh'; end if;
 if cardinality(p_documents)<>(select count(*) from lifting_documents d where d.id=any(p_documents) and ((d.machine_id=m.id and (d.kind<>'lm' or d.id=m.current_document_id)) or exists(select 1 from lifting_gear_items i join lifting_gear_certificates c on c.id=i.certificate_id where i.id=any(p_items) and d.id=c.current_document_id))) then raise exception 'Document selection conflicts with current machine/gear versions'; end if;
 if not coalesce(p_ack,false) and (m.current_document_id is null or m.certificate_expiry is null or m.certificate_expiry<(now() at time zone 'Asia/Singapore')::date or not coalesce(m.current_document_id=any(p_documents),false) or not exists(select 1 from lifting_documents where id=any(p_documents) and kind='load_chart') or exists(select 1 from lifting_documents where id=any(p_documents) and not verified) or exists(select 1 from lifting_gear_items i join lifting_gear_certificates g on g.id=i.certificate_id where i.id=any(p_items) and (g.certificate_expiry is null or g.certificate_expiry<(now() at time zone 'Asia/Singapore')::date or (g.examination_date + make_interval(months=>g.renewal_months) - interval '1 day')::date<(now() at time zone 'Asia/Singapore')::date or not coalesce(g.current_document_id=any(p_documents),false)))) then raise exception 'Missing, expired or unverified documents. Review and acknowledge warnings'; end if;
 if jsonb_typeof(p_order)<>'array' or jsonb_array_length(p_order)<>cardinality(p_documents)+2 or not(p_order ? 'lm_log' and p_order ? 'lg_log') or exists(select 1 from unnest(p_documents) d where not p_order ? d::text) then raise exception 'Invalid document order'; end if;
 snap=jsonb_build_object('machine',to_jsonb(m),'items',coalesce((select jsonb_agg(to_jsonb(i)||jsonb_build_object('certificate',to_jsonb(g))) from lifting_gear_items i join lifting_gear_certificates g on g.id=i.certificate_id where i.id=any(p_items)),'[]'::jsonb),'documents',coalesce((select jsonb_agg(to_jsonb(d)) from lifting_documents d where id=any(p_documents)),'[]'::jsonb),'prepared_by',(select name from users where auth_uid=auth.uid()),'warnings_acknowledged',p_ack);
 insert into lifting_packs(machine_id,snapshot,document_order) values(m.id,snap,p_order) returning * into r;
 return to_jsonb(r);
end $$;
revoke all on function public.lifting_can_read(),public.lifting_can_manage(),public.lifting_review(uuid,jsonb,uuid),public.lifting_move(uuid,uuid,uuid,text,text,text,text),public.lifting_freeze_pack(uuid,uuid[],uuid[],jsonb,boolean) from public;
grant execute on function public.lifting_can_read(),public.lifting_can_manage(),public.lifting_review(uuid,jsonb,uuid),public.lifting_move(uuid,uuid,uuid,text,text,text,text),public.lifting_freeze_pack(uuid,uuid[],uuid[],jsonb,boolean) to authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('lifting-documents','lifting-documents',false,20971520,array['application/pdf','image/jpeg','image/png']);
create policy lifting_storage_read on storage.objects for select to authenticated using(bucket_id='lifting-documents' and public.lifting_can_read());
create policy lifting_storage_insert on storage.objects for insert to authenticated with check(bucket_id='lifting-documents' and name ~ '^originals/[0-9a-f-]{36}$' and public.lifting_can_manage());
insert into public.schema_migrations(version,description) values('0020','Lifting directory, logs, atomic movements and immutable client packs');
commit;
