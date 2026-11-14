# VCMS image migration to Cloudflare R2

Use a dedicated R2 Standard bucket named `vcms-private-images`. Confirm that its
public development URL is disabled and no public custom domains are attached.
The existing public VCMS photo bucket is unsuitable for private worker and SIC images.

## Copy and verify

Run the copy job on a trusted host with outbound access to Supabase and R2.
Install boto3 and requests into an isolated Python environment. The job needs
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `R2_ACCOUNT_ID`,
`R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` in its environment.
Use a temporary R2 credential restricted to the dedicated bucket. Never put
credential values in a command, commit, or manifest.

```sh
python scripts/copy_supabase_images_to_r2.py --manifest verified-images.jsonl
```

The job walks the four Supabase image buckets and skips every non-image object.
It verifies the full contents and MIME type read back from R2. A retry uses a
new manifest and never overwrites an existing destination. Keep the manifests
private because they include object paths. Check the verified count and byte
total against a fresh read-only inventory. Resolve any differences before
cutover. Recheck the source ID, updated timestamp and digest at cutover to
exclude files changed since copy verification.

## Cutover and cleanup

1. Add R2 reads to the VCMS image consumers with the same existing authorization
   and test them before changing uploads. DPR and purchase-request links,
   signatures and branding, worker-document image and deletion routes, SIC
   attachments, and worker profile photos all need coverage. Use short-lived
   authorized reads for private files. Do not store expiring URLs in records.
2. Switch future uploads to R2 and reconcile images created or replaced during
   the copy. Verify existing report and purchase-request previews, exports,
   Training Records, SIC and worker profiles on desktop and mobile. Check that
   unauthorized users cannot fetch private objects.
3. Keep the original Supabase images while testing the switch. After successful
   verification, remove only the confirmed image objects through the Supabase
   Storage API, never by deleting rows from storage.objects. Leave PDFs and
   other non-image objects in place. Re-measure storage after cleanup.
