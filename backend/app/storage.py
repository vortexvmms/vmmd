"""Cloudflare R2 signing helpers used by the camera module."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import urllib.parse

from .settings import (
    PR_R2_ACCESS_KEY_ID, PR_R2_ACCOUNT_ID, PR_R2_BUCKET, PR_R2_SECRET,
    R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET,
)


def _presign(key: str, method: str, expires: int = 600, *, account_id: str = R2_ACCOUNT_ID,
             access_key_id: str = R2_ACCESS_KEY_ID, secret: str = R2_SECRET,
             bucket: str = R2_BUCKET) -> str:
    if not all((account_id, access_key_id, secret, bucket)):
        raise RuntimeError("R2 storage is not configured")
    host = f"{account_id}.r2.cloudflarestorage.com"
    region, service = "auto", "s3"
    now = dt.datetime.now(dt.UTC)
    amzdate, datestamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    canon_uri = "/" + bucket + "/" + urllib.parse.quote(key, safe="/~")
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key_id}/{scope}",
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

    date_key = sign(("AWS4" + secret).encode(), datestamp)
    signing_key = sign(sign(sign(date_key, region), service), "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{canon_uri}?{canon_query}&X-Amz-Signature={signature}"


def r2_presign_put(key: str, expires: int = 600) -> str:
    return _presign(key, "PUT", expires)


def r2_presign_delete(key: str, expires: int = 600) -> str:
    return _presign(key, "DELETE", expires)


def pr_r2_presign_put(key: str, expires: int = 900) -> str:
    return _presign(key, "PUT", expires, account_id=PR_R2_ACCOUNT_ID,
                    access_key_id=PR_R2_ACCESS_KEY_ID, secret=PR_R2_SECRET,
                    bucket=PR_R2_BUCKET)


def pr_r2_presign_get(key: str, expires: int = 600) -> str:
    return _presign(key, "GET", expires, account_id=PR_R2_ACCOUNT_ID,
                    access_key_id=PR_R2_ACCESS_KEY_ID, secret=PR_R2_SECRET,
                    bucket=PR_R2_BUCKET)


def pr_r2_presign_delete(key: str, expires: int = 600) -> str:
    return _presign(key, "DELETE", expires, account_id=PR_R2_ACCOUNT_ID,
                    access_key_id=PR_R2_ACCESS_KEY_ID, secret=PR_R2_SECRET,
                    bucket=PR_R2_BUCKET)
