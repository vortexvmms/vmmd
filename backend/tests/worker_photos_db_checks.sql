-- Include a permissive legacy policy to prove the new restrictive guards still win.
create policy legacy_broad on storage.objects for all to public using(true) with check(true);
grant select on storage.objects to anon;
insert into storage.objects(bucket_id,name) values
('worker-photos','10000000-0000-0000-0000-000000000001/30000000-0000-0000-0000-000000000001.jpg'),
('worker-photos','10000000-0000-0000-0000-000000000002/30000000-0000-0000-0000-000000000001.jpg');
set role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000002',false);
do $$begin
 if (select count(*) from storage.objects where bucket_id='worker-photos')<>1 then raise exception 'Supervisor photo scope failed'; end if;
 begin
  insert into storage.objects(bucket_id,name) values('worker-photos','10000000-0000-0000-0000-000000000001/30000000-0000-0000-0000-000000000002.jpg');
  raise exception 'Supervisor upload was allowed';
 exception when insufficient_privilege then null; end;
end$$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000003',false);
do $$begin
 if exists(select 1 from storage.objects where bucket_id='worker-photos') then raise exception 'Payroll photo leak'; end if;
end$$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
insert into storage.objects(bucket_id,name) values('worker-photos','10000000-0000-0000-0000-000000000002/30000000-0000-0000-0000-000000000002.jpg');
do $$begin
 if (select count(*) from storage.objects where bucket_id='worker-photos')<>3 then raise exception 'Management photos unavailable'; end if;
 update storage.objects set name='changed' where bucket_id='worker-photos';
 if found then raise exception 'Immutable photo updated'; end if;
 delete from storage.objects where bucket_id='worker-photos';
 if found then raise exception 'Immutable photo deleted'; end if;
end$$;
reset role;
select set_config('request.jwt.claim.sub','',false);
insert into storage.objects(bucket_id,name) values('dpr-photos','public-test.jpg');
set role anon;
do $$begin
 if not exists(select 1 from storage.objects where bucket_id='dpr-photos') then raise exception 'Existing public image access changed'; end if;
 if exists(select 1 from storage.objects where bucket_id='worker-photos') then raise exception 'Anonymous photo leak'; end if;
end$$;
reset role;
