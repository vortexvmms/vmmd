"""Cloudflare R2 signing helpers used by the camera module."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import urllib.parse

from .settings import R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET


def _presign(key: str, method: str, expires: int = 600) -> str:
    host = f"{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    region, service = "auto", "s3"
    now = dt.datetime.now(dt.UTC)
    amzdate, datestamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    canon_uri = "/" + R2_BUCKET + "/" + urllib.parse.quote(key, safe="/~")
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{R2_ACCESS_KEY_ID}/{scope}",
        "X-Amz-Date": amzdate,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canon_query = "&".join(
        f"{urllib.parse.quote(k, safe='~')}={urllib.parse.quote(v, safe='~')}"
        for k, v in sorted(query.items())
    )
    canon_request = (
        f"{method}\n{canon_uri}\n{canon_query}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    )
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n"
        f"{hashlib.sha256(canon_request.encode()).hexdigest()}"
    )

    def sign(secret, message):
        return hmac.new(secret, message.encode(), hashlib.sha256).digest()

    date_key = sign(("AWS4" + R2_SECRET).encode(), datestamp)
    signing_key = sign(sign(sign(date_key, region), service), "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{canon_uri}?{canon_query}&X-Amz-Signature={signature}"


def r2_presign_put(key: str, expires: int = 600) -> str:
    return _presign(key, "PUT", expires)


def r2_presign_delete(key: str, expires: int = 600) -> str:
    return _presign(key, "DELETE", expires)
