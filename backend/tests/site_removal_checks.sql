select set_config('request.jwt.claim.sub',current_setting('sic.test_admin'),true);
set local role authenticated;
do $$
declare target uuid; r public.sites;
begin
 select id into target from public.sites where status='archived' and removed_at is null order by id limit 1;
 if target is null then raise exception 'No archived test site';end if;
 r:=public.site_set_removed(target,true);
 if r.removed_at is null or r.removed_by<>auth.uid() then raise exception 'Removal stamp missing';end if;
 if not exists(select 1 from public.site_removal_events where site_id=target and action='removed' and actor=auth.uid()) then raise exception 'Removal audit missing';end if;
 r:=public.site_set_removed(target,false);
 if r.removed_at is not null or r.status<>'archived' then raise exception 'Restore did not retain archived status';end if;
 if not exists(select 1 from public.site_removal_events where site_id=target and action='restored') then raise exception 'Restore audit missing';end if;
 if current_setting('sic.test_scoped_user')<>'' then
  perform set_config('request.jwt.claim.sub',current_setting('sic.test_scoped_user'),true);
  begin perform public.site_set_removed(target,true);raise exception 'Non-management removal accepted';exception when insufficient_privilege then null;end;
 end if;
 perform set_config('request.jwt.claim.sub',current_setting('sic.test_admin'),true);
end $$;
reset role;
select 'Recoverable site removal, restore and management-only access passed' as result;
