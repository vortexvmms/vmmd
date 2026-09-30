-- Supabase default privileges explicitly grant anon access to new objects.
-- Remove those defaults from the lifting register; authenticated RLS and RPC checks remain.
begin;
revoke all on public.lifting_machines,public.lifting_gear_certificates,public.lifting_gear_items,public.lifting_documents,public.lifting_movements,public.lifting_packs from anon;
revoke all on function public.lifting_can_read(),public.lifting_can_manage(),public.lifting_review(uuid,jsonb,uuid),public.lifting_move(uuid,uuid,uuid,text,text,text,text),public.lifting_freeze_pack(uuid,uuid[],uuid[],jsonb,boolean) from anon;
insert into public.schema_migrations(version,description) values('0021','Remove Supabase default anonymous grants from lifting objects');
commit;
