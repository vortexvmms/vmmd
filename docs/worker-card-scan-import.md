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
