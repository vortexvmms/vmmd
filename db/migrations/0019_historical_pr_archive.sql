-- Historical PR PDF archive: private R2 object metadata, searchable page text,
-- structured price/material rows and resumable import tracking.
begin; set local check_function_bodies = off;

alter table public.purchase_requisitions
  add column if not exists source text not null default 'vcms'
    check (source in ('vcms','historical_pdf'));

create table if not exists public.pr_documents (
  id uuid primary key default gen_random_uuid(),
  pr_id uuid not null references public.purchase_requisitions(id) on delete cascade,
  original_filename text not null,
  object_key text not null unique,
  checksum_sha256 text not null unique,
  file_size bigint not null check (file_size > 0 and file_size <= 262144000),
  page_count integer check (page_count is null or page_count > 0),
  mime_type text not null default 'application/pdf' check (mime_type = 'application/pdf'),
  extraction_status text not null default 'pending'
    check (extraction_status in ('pending','processing','ready','needs_ocr','failed')),
  verification_status text not null default 'unverified'
    check (verification_status in ('unverified','verified','rejected')),
  uploaded_by uuid references public.users(id),
  uploaded_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_pr_documents_pr on public.pr_documents(pr_id);
create index if not exists idx_pr_documents_status on public.pr_documents(extraction_status, created_at desc);

create table if not exists public.pr_document_pages (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.pr_documents(id) on delete cascade,
  page_number integer not null check (page_number > 0),
  page_type text not null default 'attachment'
    check (page_type in ('pr_form','invoice','quotation','delivery_order','attachment')),
  extracted_text text,
  ocr_used boolean not null default false,
  ocr_confidence numeric(5,2),
  search_vector tsvector generated always as
    (to_tsvector('english', coalesce(extracted_text,''))) stored,
  created_at timestamptz not null default now(),
  unique(document_id, page_number)
);
create index if not exists idx_pr_pages_document on public.pr_document_pages(document_id, page_number);
create index if not exists idx_pr_pages_search on public.pr_document_pages using gin(search_vector);

create table if not exists public.pr_line_items (
  id uuid primary key default gen_random_uuid(),
  pr_id uuid not null references public.purchase_requisitions(id) on delete cascade,
  document_id uuid references public.pr_documents(id) on delete cascade,
  source_page integer check (source_page is null or source_page > 0),
  source_type text not null default 'pr_form'
    check (source_type in ('pr_form','invoice','quotation','attachment')),
  item_number text,
  description text not null,
  quantity numeric,
  unit text,
  unit_price numeric,
  amount numeric,
  vendor text,
  confidence numeric(5,2),
  verified boolean not null default false,
  search_vector tsvector generated always as
    (to_tsvector('english', coalesce(description,'') || ' ' || coalesce(vendor,''))) stored,
  created_at timestamptz not null default now()
);
create index if not exists idx_pr_lines_pr on public.pr_line_items(pr_id);
create index if not exists idx_pr_lines_search on public.pr_line_items using gin(search_vector);

create table if not exists public.pr_import_jobs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.pr_documents(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued','processing','ready','needs_ocr','failed')),
  progress integer not null default 0 check (progress between 0 and 100),
  attempts integer not null default 0,
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists idx_pr_jobs_status on public.pr_import_jobs(status, created_at);

create or replace function public.search_pr_archive(query_text text, result_limit integer default 500)
returns table(pr_id uuid)
language sql stable security invoker set search_path = public
as $$
  with query as (select websearch_to_tsquery('english', nullif(trim(query_text),'')) q)
  select distinct found.pr_id
  from (
    select d.pr_id from public.pr_document_pages p
      join public.pr_documents d on d.id=p.document_id, query
      where query.q is not null and p.search_vector @@ query.q
    union
    select l.pr_id from public.pr_line_items l, query
      where query.q is not null and l.search_vector @@ query.q
    union
    select r.id from public.purchase_requisitions r, query
      where query.q is not null and
        to_tsvector('english',coalesce(r.pr_no,'')||' '||coalesce(r.site_name,'')||' '||coalesce(r.remarks,'')) @@ query.q
  ) found
  limit least(greatest(result_limit,1),500);
$$;
grant execute on function public.search_pr_archive(text,integer) to authenticated;

do $$ begin
  if exists(select 1 from pg_proc where proname='set_updated_at') then
    drop trigger if exists trg_pr_documents_updated on public.pr_documents;
    create trigger trg_pr_documents_updated before update on public.pr_documents
      for each row execute function public.set_updated_at();
  end if;
end $$;

alter table public.pr_documents enable row level security;
alter table public.pr_document_pages enable row level security;
alter table public.pr_line_items enable row level security;
alter table public.pr_import_jobs enable row level security;

drop policy if exists pr_documents_read on public.pr_documents;
create policy pr_documents_read on public.pr_documents for select to authenticated
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','site_sup','safety_sup','wshc','logistics_sup'));
drop policy if exists pr_documents_manage on public.pr_documents;
create policy pr_documents_manage on public.pr_documents for all to authenticated
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

do $$ declare t text; begin
  foreach t in array array['pr_document_pages','pr_line_items','pr_import_jobs'] loop
    execute format('drop policy if exists %I_read on public.%I', t, t);
    execute format('create policy %I_read on public.%I for select to authenticated using (public.my_role() in (''admin'',''general_manager'',''operation_manager'',''hr_assistant'',''main_sup'',''wshc_lead'',''site_sup'',''safety_sup'',''wshc'',''logistics_sup''))', t, t);
    execute format('drop policy if exists %I_manage on public.%I', t, t);
    execute format('create policy %I_manage on public.%I for all to authenticated using (public.my_role() in (''admin'',''general_manager'',''operation_manager'',''hr_assistant'',''main_sup'',''wshc_lead'')) with check (public.my_role() in (''admin'',''general_manager'',''operation_manager'',''hr_assistant'',''main_sup'',''wshc_lead''))', t, t);
  end loop;
end $$;

insert into public.schema_migrations(version, description)
values('0019','Historical PR PDF archive and searchable document metadata')
on conflict(version) do nothing;
commit;
