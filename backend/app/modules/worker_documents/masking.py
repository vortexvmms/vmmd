"""Local OCR suggestions and irreversible, raster-only document copies.

OCR is an aid: every page still requires the uploader's visual review. Neither
source bytes nor OCR text are persisted by this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import io
import math
import re
import threading

import fitz
from fastapi import HTTPException

POLICY = 'fin-dob-wp-v1'
MAX_PIXELS = 4_000_000  # Bound each rendered page before allocation.
_ocr_lock = threading.Lock()
_ocr = None
_processing = threading.BoundedSemaphore(1)


def process(fn, *args):
    if not _processing.acquire(blocking=False):
        raise HTTPException(429, 'Another document is being prepared. Please try again shortly.')
    try:
        return fn(*args)
    finally:
        _processing.release()


def open_document(data, mime):
    return fitz.open(stream=data, filetype={'application/pdf': 'pdf', 'image/png': 'png', 'image/jpeg': 'jpeg'}[mime])


def raster(page):
    if page.parent.is_pdf:
        images = {image[0]: image[2]*image[3] for image in page.get_images(full=True)}
        if sum(images.values()) > 25_000_000:
            raise HTTPException(413, 'This PDF page contains oversized scans. Reduce the scan resolution before uploading.')
    area = page.rect.width * page.rect.height
    if not math.isfinite(area) or area <= 0:
        raise HTTPException(400, 'Document page dimensions are invalid')
    scale = min(2.5, math.sqrt(MAX_PIXELS / area), 4096/max(page.rect.width, page.rect.height))
    return page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)


def recognise(png):
    global _ocr
    # One CPU inference at a time; do not grow a pool of large model instances.
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1,
                            det_limit_side_len=480, det_limit_type='min',
                            rec_batch_num=1, cls_batch_num=1)
        from PIL import Image
        import numpy as np
        # The detector's "min" option is a minimum, not a maximum. Send only
        # bounded, overlapping tiles, retaining native text size on large scans.
        with Image.open(io.BytesIO(png)) as loaded:
            image = loaded.convert('RGB')
        tile_size, stride = 640, 480
        def starts(length):
            return sorted(set(min(i, max(0,length-tile_size)) for i in range(0,length,stride)))
        # A bounded overview preserves complete labels/values that span tiles.
        # Tiles then recover smaller text without running a full-resolution page
        # through the detector. Keep all coordinates in the original raster.
        overview = image.copy()
        overview.thumbnail((tile_size, tile_size), Image.Resampling.LANCZOS)
        padded = Image.new('RGB', (tile_size, tile_size), 'white')
        padded.paste(overview, (0, 0))
        result, _ = _ocr(np.asarray(padded))
        sx, sy = image.width/overview.width, image.height/overview.height
        lines = [[[[p[0]*sx, p[1]*sy] for p in points], text, score]
                 for points, text, score in result or []]
        for y in starts(image.height):
            for x in starts(image.width):
                tile = Image.new('RGB', (tile_size,tile_size), 'white')
                tile.paste(image.crop((x,y,min(x+tile_size,image.width),min(y+tile_size,image.height))), (0,0))
                result, _ = _ocr(np.asarray(tile))
                for points, text, score in result or []:
                    translated = [[p[0]+x,p[1]+y] for p in points]
                    # Discard only duplicate observations of the same line.
                    cx = sum(p[0] for p in translated)/4
                    cy = sum(p[1] for p in translated)/4
                    height = max(p[1] for p in translated)-min(p[1] for p in translated)
                    # Overview lines own contained tile fragments. Comparing both
                    # text and position avoids dropping repeated values elsewhere.
                    normal = re.sub(r'\s', '', str(text)).casefold()
                    if not any(normal in re.sub(r'\s', '', str(old[1])).casefold()
                               and min(p[0] for p in old[0])-height <= cx <= max(p[0] for p in old[0])+height
                               and abs(sum(p[1] for p in old[0])/4-cy)<height for old in lines):
                        lines.append([translated,text,score])
                    if len(lines)>2000:
                        raise ValueError('Too many text regions; use manual review')
        lines.sort(key=lambda item:(min(p[1] for p in item[0]),min(p[0] for p in item[0])))
        return lines


def suggestions(lines, width, height):
    found = []
    fin = re.compile(r'(?<![A-Z0-9])([FGM](?:\s*\d){7}\s*[A-Z])(?![A-Z0-9])', re.I)
    birth = re.compile(r'\b(?:D\.?O\.?B\.?|date\s*of\s*birth|birth\s*date)\b', re.I)
    permit = re.compile(r'\b(?:work\s*permit|W\.?P\.?)\s*(?:no\.?|number|#)', re.I)
    date_value = re.compile(r'\b\d{1,2}[ /.-](?:\d{1,2}|[A-Z]{3,9})[ /.-]\d{2,4}\b|\b\d{4}[/-]\d{2}[/-]\d{2}\b', re.I)
    number = re.compile(r'(?<!\d)(\d(?:[ -]?\d){5,11})(?!\d)')

    def box(item, field, suffix='', birth_row=False):
        points = item[0]
        xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
        x0, y0 = max(0, min(xs)-3), max(0, min(ys)-3)
        x1, y1 = min(width, max(xs)+3), min(height, max(ys)+3)
        if birth_row:
            # A tile boundary can split the date into fragments that do not
            # independently match a date pattern. Cover the labelled row to its
            # right edge rather than leave an unrecognised trailing year exposed.
            x1 = width
            row_top, row_bottom = y0, y1
            for other in lines:
                top, bottom = min(p[1] for p in other[0]), max(p[1] for p in other[0])
                if top < row_bottom and bottom > row_top and min(p[0] for p in other[0]) >= x0:
                    y0, y1 = max(0,min(y0,top-3)), min(height,max(y1,bottom+3))
        if x1 > x0 and y1 > y0:
            found.append({'x': x0/width, 'y': y0/height, 'w': (x1-x0)/width, 'h': (y1-y0)/height,
                          'field': field, 'suffix': suffix})

    # OCR returns reading order. A labelled value may be on the following line;
    # constrain that association spatially rather than hiding any next number.
    def nearby(index):
        item = lines[index]
        bottom = max(p[1] for p in item[0]); left = min(p[0] for p in item[0])
        line_height = max(p[1] for p in item[0])-min(p[1] for p in item[0])
        for other in lines[index+1:index+3]:
            top = min(p[1] for p in other[0]); x = min(p[0] for p in other[0])
            if -line_height <= top-bottom <= 2*line_height+10 and abs(x-left) < width*.35:
                yield other

    for i, item in enumerate(lines):
        text = str(item[1])
        match = fin.search(text)
        if match:
            box(item, 'FIN', re.sub(r'\s', '', match[1]).upper()[-4:])
            continue
        if birth.search(text):
            box(item, 'Date of birth', birth_row=True)
            if not date_value.search(text):
                for other in nearby(i):
                    if date_value.search(str(other[1])):
                        box(other, 'Date of birth', birth_row=True); break
        elif permit.search(text):
            match = number.search(text)
            if match:
                box(item, 'Work Permit number', re.sub(r'\D', '', match[1])[-4:])
            else:
                for other in nearby(i):
                    match = number.search(str(other[1]))
                    if match and not date_value.search(str(other[1])):
                        box(other, 'Work Permit number', re.sub(r'\D', '', match[1])[-4:]); break
    # A line can be associated with more than one label. Prefer hiding all of it
    # rather than printing a suffix over an independently detected DOB region.
    unique = {}
    for b in found:
        key = tuple(round(b[k], 5) for k in ('x', 'y', 'w', 'h'))
        if key not in unique or not b['suffix']:
            unique[key] = b
    return list(unique.values())


def prepare(data, mime, page_number):
    with open_document(data, mime) as doc:
        if not 0 <= page_number < len(doc):
            raise HTTPException(422, 'Choose an existing document page')
        pix = raster(doc[page_number]); png = pix.tobytes('png')
        try:
            boxes = suggestions(recognise(png), pix.width, pix.height)
            status = 'suggested'
        except Exception:
            # Recognition failure is explicit. Manual review is still possible,
            # but must never be presented as an automatic all-clear.
            boxes, status = [], 'manual_required'
        return {'policy': POLICY, 'sha256': hashlib.sha256(data).hexdigest(), 'page': page_number,
                'pages': len(doc), 'width': pix.width, 'height': pix.height,
                'image': base64.b64encode(png).decode('ascii'), 'boxes': boxes, 'recognition': status}


def checked_plan(header, data, count):
    if not header or len(header) > 48000:
        raise HTTPException(422, 'Review the masking on every page before saving')
    try:
        plan = json.loads(header)
        if (plan['policy'] != POLICY or plan['sha256'] != hashlib.sha256(data).hexdigest()
                or not isinstance(plan['pages'], list) or len(plan['pages']) != count):
            raise ValueError()
        for page in plan['pages']:
            if page.get('reviewed') is not True or not isinstance(page.get('boxes'), list) or len(page['boxes']) > 100:
                raise ValueError()
            for b in page['boxes']:
                if any(type(b.get(k)) not in (int, float) or not math.isfinite(b[k]) for k in ('x', 'y', 'w', 'h')):
                    raise ValueError()
                if not (0 <= b['x'] < 1 and 0 <= b['y'] < 1 and 0 < b['w'] <= 1 and 0 < b['h'] <= 1
                        and b['x']+b['w'] <= 1.000001 and b['y']+b['h'] <= 1.000001):
                    raise ValueError()
                if not re.fullmatch(r'(?:\d{3}[A-Z]|\d{4})?', b.get('suffix', '')):
                    raise ValueError()
                if b.get('field') == 'Date of birth' and b.get('suffix'):
                    raise ValueError()
                if b.get('field') == 'FIN' and not re.fullmatch(r'(?:\d{3}[A-Z])?', b.get('suffix', '')):
                    raise ValueError()
                if b.get('field') == 'Work Permit number' and not re.fullmatch(r'(?:\d{4})?', b.get('suffix', '')):
                    raise ValueError()
        return plan['pages']
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(422, 'The masking review is incomplete or the file changed. Review it again.')


def apply(data, mime, header, max_output):
    # Always rebuild from pixels, even on reviewed pages without boxes: this
    # drops hidden PDF text, attachments, layers, EXIF and removable annotations.
    with open_document(data, mime) as source, fitz.open() as output:
        pages = checked_plan(header, data, len(source))
        encoded_size = 0
        for i, page in enumerate(source):
            pix = raster(page)
            with fitz.open() as canvas:
                target = canvas.new_page(width=pix.width, height=pix.height)
                target.insert_image(target.rect, stream=pix.tobytes('png'))
                for b in pages[i]['boxes']:
                    rect = fitz.Rect(b['x']*pix.width, b['y']*pix.height,
                                     min(1,b['x']+b['w'])*pix.width, min(1,b['y']+b['h'])*pix.height)
                    target.draw_rect(rect, color=None, fill=(0,0,0), overlay=True)
                    if b.get('suffix'):
                        size = min(rect.height*.65, rect.width/(len(b['suffix'])*.7))
                        target.insert_text((rect.x1-fitz.get_text_length(b['suffix'], fontsize=size)-2, rect.y0+rect.height*.78),
                                           b['suffix'], fontsize=size, color=(1,1,1), overlay=True)
                clean = target.get_pixmap(colorspace=fitz.csRGB, alpha=False)
                if mime != 'application/pdf':
                    result = clean.tobytes('png')
                    if len(result) > max_output:
                        raise HTTPException(413, 'Masked image exceeds 20 MB. Upload a smaller scan.')
                    return result, 'image/png'
                encoded = clean.tobytes('png')
                encoded_size += len(encoded)
                if encoded_size > max_output:
                    raise HTTPException(413, 'Masked PDF exceeds 20 MB. Split it into smaller documents.')
                dest = output.new_page(width=page.rect.width, height=page.rect.height)
                dest.insert_image(dest.rect, stream=encoded)
            # Bound accumulated encoded images as well as the finished output.
        result = output.tobytes(garbage=4, deflate=True)
        if len(result) > max_output:
            raise HTTPException(413, 'Masked PDF exceeds 20 MB. Split it into smaller documents.')
        return result, 'application/pdf'
