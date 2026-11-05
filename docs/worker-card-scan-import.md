# Scanned worker card import

Select a worker, choose Import scanned cards and upload a PDF up to 20 MB.
Select the front and back page numbers (back 0 for a single-sided document).
Draw each card rectangle on the front page; the same normalised rectangle is
used on the back. Create card pairs, then repeat for additional page pairs.
Full page card retains the complete page. Swap front/back if needed.

Select unwanted unsaved pairs and delete them; Undo restores the last deletion.
Existing saved cards keep their Admin/HR permanent-deletion process.

Read selected course details runs the existing pinned browser OCR library on
both sides. Explicit course/institute/expiry labels are parsed conservatively;
unrecognised values remain blank. Raw OCR text is visible in Edit for checking.
No expiry remains an explicit user choice. Verify the fields before saving.

Edit each pair using the established masking review: automatic suggestions,
manual masks, auto crop, free or standard card crop with corner/midpoint handles,
re-crop/reset to the imported crop, tilt, perspective correction, rotation and zoom.
Both uploaded sides must be reviewed. Existing server digest validation and
permanent masking apply. After saving, the importer returns to the remaining
pairs. The worker and private storage permissions are unchanged.

The current import queue is held in page memory; closing the importer retains it,
but reloading leaves the queue behind. The page warns while unsaved pairs exist.
No persistent original scan or cross-session draft is created by this feature.
OCR/PDF libraries require internet access; manual details remain available.

Rollback: revert the scan-import commit and deploy the preceding frontend.
No database migration or backend rollout is required.

## Automatic all-page review (November 2026 update)

Uploads now process every page (up to 30) sequentially in the browser. Local
segmentation detects each side independently; the previous coordinate-copy
assumption is removed. Adjacent pages are initially paired (1/2, 3/4, ...),
with cards sorted by approximate position. The pairs are suggestions, never
identity matches. An odd final page has no back; unmatched sides remain visible.

All pages appear in the left strip, including pages with no detected card. Add
missed card opens an original-page crop. Each pair provides independent source
selectors, original-page re-cropping, full-page crop, editable OCR fields, and an
explicit pairing check. Assigning an already-used side exchanges it with the
other unsaved pair. Saved sides cannot be reassigned. Masking, tilt, rotation and
perspective correction still use the existing reviewed editor before upload.
Automatic straightening is attempted when card edges are reliable; inspect all
results. Faint white borders and touching/overlapping cards may need manual crops.

The desktop worker name, tabs and actions occupy one row; the worker directory
fills the remaining viewport with its list scrolling inside the panel.

## Print sheet update

Print headers show the worker name, masked FIN ending (for example FIN: ***567X)
and employee code. The backend obtains FIN only for IDs already returned by the
scoped worker-directory RPC and returns only fin_last4 to this page. Missing FIN
is omitted, not guessed from another document. No database migration is required.

Card images have no added border in the preview or printed PDF. Existing image
contents, including physical card edges, remain intact. Preview preparation uses
at most four concurrent image requests, retains already decoded images while the
selection is open, and cancels outstanding requests on close. Changing order or
selection reuses ready images; unavailable sides still require explicit handling.
