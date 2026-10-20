begin;
set local role authenticated;
set local request.jwt.claim.sub='00000000-0000-0000-0000-000000000002';
do $$declare v_id uuid; v_time timestamptz;begin
 if (select count(*) from public.worker_cards)<>1 then raise exception 'Supervisor card scope';end if;
 if (select count(*) from public.worker_documents_workers())<>1 then raise exception 'Supervisor worker scope';end if;
 if public.worker_documents_can_access('10000000-0000-0000-0000-000000000003') then raise exception 'Historical allocation grants access';end if;
 if public.worker_documents_object_access('invalid/file.png') then raise exception 'Malformed key accepted';end if;
 select id,updated_at into v_id,v_time from public.worker_cards;
 update public.worker_cards set label='Corrected course',expiry_date=current_date+90 where id=v_id;
 if (select updated_at from public.worker_cards where id=v_id)=v_time then raise exception 'Version not advanced';end if;
 begin
  update public.worker_cards set worker_id='10000000-0000-0000-0000-000000000002' where id=v_id;
  raise exception 'Identity changed';
 exception when check_violation or raise_exception then if sqlerrm='Identity changed' then raise;end if;end;
 begin
  insert into storage.objects(bucket_id,name) values('worker-cards','10000000-0000-0000-0000-000000000002/00000000-0000-0000-0000-000000000001.png');
  raise exception 'Foreign upload allowed';
 exception when insufficient_privilege then null;end;
 insert into storage.objects(bucket_id,name) values('worker-cards','10000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000001.png');
 update public.worker_cards set image_path='10000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000001.png' where id=v_id;
 begin
  update public.worker_cards set image_path='https://arbitrary.invalid/image.jpg' where id=v_id;
  raise exception 'Untrusted URL allowed';
 exception when raise_exception then if sqlerrm='Untrusted URL allowed' then raise;end if;end;
 begin delete from public.worker_cards where id=v_id;raise exception 'Delete allowed';exception when insufficient_privilege then null;end;
 insert into public.worker_certificates(worker_id,file_path,title) values('10000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000001.png','Certificate');
 update public.worker_certificates set title='Edited certificate';
 if exists(select 1 from public.worker_certificates where uploaded_by<>'00000000-0000-0000-0000-000000000002' or uploaded_by is null) then raise exception 'Uploader identity incorrect';end if;
 if (select count(*) from storage.objects)<>1 then raise exception 'Storage scope failed';end if;
end$$;
set local request.jwt.claim.sub='00000000-0000-0000-0000-000000000001';
do $$begin if (select count(*) from public.worker_cards)<>3 then raise exception 'Admin scope';end if;end$$;
set local request.jwt.claim.sub='00000000-0000-0000-0000-000000000003';
do $$begin if exists(select 1 from public.worker_cards) or exists(select 1 from public.worker_certificates) or exists(select 1 from storage.objects) then raise exception 'Payroll scope';end if;end$$;
set local request.jwt.claim.sub='00000000-0000-0000-0000-000000000002';
reset role;
delete from public.allocations where worker_id='10000000-0000-0000-0000-000000000001';
set local role authenticated;
do $$begin if exists(select 1 from public.worker_cards) or exists(select 1 from storage.objects) then raise exception 'Allocation removal did not revoke access';end if;end$$;
set local role anon;
do $$begin
 begin perform * from public.worker_cards;raise exception 'Anonymous access';exception when insufficient_privilege then null;end;
end$$;
rollback;
