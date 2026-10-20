# Worker document masking

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
a 4096-pixel longest edge; OCR uses overlapping 640-pixel tiles and batch size one.
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
