# Worker document masking

## Photo editor (23 October 2026)

Photo uploads open locally in an enlarged dialog, without waiting for OCR or a
backend preview request. The mobile editor uses the full viewport; the desktop
editor grows to 1600 pixels. Staff can draw masks, pan, pinch/zoom, fit the image,
rotate, crop, undo a mask and restore the source photo. Cropping intersects and
remaps existing masks; rotating remaps their coordinates. Cropped suffixes are
cleared so the uploader can review their visible ending again. Every image edit
invalidates the page's review. Cropping/rotation apply to photos, not PDF pages.

The front and back each accept file upload, drag/drop and clipboard image paste.
On phones/tablets, Take photo opens the native camera file picker; on desktop it
opens a getUserMedia camera preview with capture and camera-switch controls.
Desktop camera access requires HTTPS (or localhost), permission and a camera.
Streams stop on capture, close, page hide or tab hiding. Failed access leaves
file upload available. HEIC/HEIF conversion uses the existing bundled heic2any
library; unsupported photos produce an explicit error.

Images are oriented by browser decoding and reduced to at most four megapixels
and a 4096-pixel longest edge before editing. The edited, unmasked PNG is held in
memory and uploaded only after review, with a SHA-256-bound manifest. The existing
server checks and pixel-flattening still apply the masks before storage. Raw
source photos and edited unmasked copies are not saved in Storage. Only pressing
Suggest masks sends the edited image to the existing OCR preview endpoint;
its failure or timeout does not block manual photo review. PDF previews continue
to use the existing server-rendered, page-by-page workflow.

Browser regressions use fictional images and mocked API/storage responses. They
cover local preview with a failing OCR service, crop/rotation mask coordinates,
front/back uploads, digest matching against upload bytes where exposed by the
browser, drop/native camera selection, desktop synthetic camera capture and
track cleanup, review invalidation, PDF review and existing metadata/print flows.
Physical device cameras and HEIC conversion are not automated by these tests.


New or replacement uploads in Worker Cards require a page-by-page review before
the file is saved. The same policy applies to both card sides and certificate PDFs:

| Field | Visible ending |
| --- | --- |
| FIN | Last three digits and final letter |
| Date of birth | Nothing |
| Work Permit number | Last four digits |

The local OCR engine suggests black areas. Staff can remove incorrect suggestions,
draw additional areas and correct a visible ending before confirming each page.
Suggested identifier regions are fully blacked out and their permitted ending is
printed in white, avoiding estimated character-width masks that could expose a
prefix. Date-of-birth regions cannot have a visible ending.
Because OCR tiles may split a date, DOB suggestions cover the labelled row to
the page's right edge. Staff can remove an overbroad suggestion and draw a tighter
area when other information shares that row.

## Storage and access

Preview requests use the same role and worker-allocation checks as uploads and
return `Cache-Control: no-store`. They do not write files or OCR text to storage.
The service runs OCR locally using models included in the installed package;
document images are not sent to a third-party OCR API.

The upload API requires a review manifest bound to the source file's SHA-256 and
covering every page. It rebuilds the document from pixels and flattens the black
areas into those pixels. Images are stored as PNG; PDFs remain PDFs containing
page images. Original PDF text, removable annotations, attachments and metadata
are not included in the saved copy. This removes PDF text search/accessibility
from newly uploaded copies as a trade-off for irreversible masking.

Only the masked copy is saved by this upload flow. If the company needs an
unredacted source for an authorised HR purpose, retain it separately in approved
HR records before uploading. Earlier stored documents and their previous versions
are unchanged. They are not automatically reprocessed or certified as redacted.
No database or Storage policy change is needed; private immutable paths and
existing worker scopes are retained.

## Review limitations

Recognition is an aid, not proof that all personal data has been removed. It may
miss blurred, rotated, handwritten, differently formatted or split text. It does
not decode QR/barcodes: staff must mask codes exposing hidden information and
inspect the front, back and every PDF page. If recognition fails, the UI explicitly
requires manual masking. An empty box list is never described as an automatic
all-clear. The review manifest records staff confirmation; it cannot establish
that their visual check was correct, and this workflow is not a substitute for
the organisation's PDPA procedures.

One document-processing operation runs at a time per application process. Other
operations receive a retry message. Pages are rendered at up to 4 megapixels and
a 4096-pixel longest edge; OCR uses a 640-pixel square overview, overlapping 640-pixel tiles and batch size one. The overview preserves complete labels and numbers that span tile boundaries; tile fragments contained in an overview line are discarded at the OCR boundary.
The existing 20 MB input/output and 150-page input limits apply. Oversized masked
PDFs must be split rather than saved partially.

## Deployment

Deploy the backend before the frontend; older frontends receive a clear review
requirement rather than silently storing an unreviewed original. Publish the new
masking script and service-worker cache version together. Python 3.12 is already
selected in `backend/.python-version`. RapidOCR is pinned in requirements. The
Render build command installs the pinned headless OpenCV wheel last so runtime
OCR does not depend on desktop OpenGL libraries. Ensure the existing Render
service's build command is updated when deploying; changing a blueprint file alone
does not demonstrate that an existing service has adopted it.

## Validation evidence

API tests exercise the actual local OCR engine with synthetic FIN, DOB and Work
Permit text, then inspect/re-recognise the saved PDF. They check that only the
permitted endings remain, expiry dates survive, hidden PDF text/attachments and
metadata are removed, every page is required, bad/changed manifests are rejected,
manual fallback is explicit, and worker access checks remain active.

Browser tests cover desktop Chromium and mobile WebKit, front/back uploads,
multi-page certificate review, manual rectangle drawing and correction, changed
files requiring a fresh review, and existing metadata/printing flows. Browser API
responses are mocked; API tests use actual rendering/OCR with mocked Storage.
No live personnel document has been processed for these tests.

Local macOS measurements on a synthetic one-page A4 file (two preview calls plus
one save, one Python process): before tiling, cold/warm previews 1.73/1.10 seconds,
save 0.16 seconds, CPU 3.11 seconds, peak process memory 1125.9 MiB; after tiling,
2.35/2.06 seconds, save 0.16 seconds, CPU 4.86 seconds, peak 362.7 MiB. These are
sample measurements, not Render/Linux capacity verification. Agent token cost and
browser process-family memory were not measured.

A live fictional 1400×840 PNG exposed a tiling gap: all three fields crossed
tile boundaries and produced no masks. The overview correction detects FIN
567X, DOB (fully hidden), and Work Permit ending 5678. The same API regression
also uploads and re-recognises the flattened result with mocked Storage.
Sequential local macOS measurements on that PNG (one process per version,
two previews): before, cold/warm 3.20/2.83 seconds, CPU 3.18/2.83 seconds,
peak 351.7 MiB, zero masks; after, 3.50/3.20 seconds, CPU 3.49/3.20 seconds,
peak 355.3 MiB, three masks. This is process peak memory, not process-family
or Render/Linux capacity evidence. Agent tokens were not measured.


## Selected card print packs (23 October 2026)

Print card sheet opens an ordered selection dialog. Front and back are independent
checkboxes; Select all, Fronts only and Clear selection apply across the list.
Use Move up/down on mobile or drag rows on desktop to arrange the client's pack.
Selection and ordering apply only to this print session and do not change worker
records. Use clear card labels for otherwise unnamed course cards.

Prepare preview fetches only selected sides through the existing authenticated,
worker-scoped file endpoint. Ready images are cached in memory for the dialog,
with thumbnails and an ordered sheet preview. Missing, unreadable and timed-out
images are named by card, sequence number and side. Print is disabled until all
selected sides are ready. The user can retry, change the selection or explicitly
Exclude unavailable sides; incomplete packs are never printed silently.

Changing selection/order invalidates the prepared sheet. Closing the dialog or
leaving the page revokes its object URLs and clears the pack. Print selected /
Save PDF uses the browser's print dialog and the existing A4 card sizing, keeping
front and back together and labelling each side. Previously stored missing files
are retained as records; unavailable originals still need recovery or replacement.
