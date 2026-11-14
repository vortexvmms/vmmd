#!/usr/bin/env python3
"""Copy and verify VCMS images in a dedicated private R2 bucket."""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryFile
from urllib.parse import quote

BUCKETS = ("dpr-photos", "worker-cards", "sic-cards", "worker-photos")
PAGE_SIZE = 100


def list_images(session, storage_url, bucket):
    folders = [""]
    while folders:
        prefix = folders.pop()
        offset = 0
        while True:
            response = session.post(
                f"{storage_url}/object/list/{bucket}",
                json={"prefix": prefix, "limit": PAGE_SIZE, "offset": offset,
                      "sortBy": {"column": "name", "order": "asc"}},
                timeout=60,
            )
            response.raise_for_status()
            rows = response.json()
            for row in rows:
                key = f"{prefix}/{row['name']}" if prefix else row["name"]
                if row.get("id") is None:
                    folders.append(key)
                elif (row.get("metadata") or {}).get("mimetype", "").startswith("image/"):
                    yield key, row
            if len(rows) < PAGE_SIZE:
                break
            offset += len(rows)


def stream_digest(chunks, destination=None):
    digest = hashlib.sha256()
    size = 0
    for chunk in chunks:
        size += len(chunk)
        digest.update(chunk)
        if destination is not None:
            destination.write(chunk)
    return size, digest.hexdigest()


def copy_image(session, s3, storage_url, bucket, key, row, target):
    from botocore.exceptions import ClientError

    target_key = f"supabase-images/{bucket}/{key}"
    meta = row["metadata"]
    with TemporaryFile() as source:
        with session.get(
            f"{storage_url}/object/authenticated/{bucket}/{quote(key, safe='/')}",
            stream=True, timeout=60,
        ) as response:
            response.raise_for_status()
            size, digest = stream_digest(response.iter_content(1024 * 1024), source)
        if size != int(meta["size"]):
            raise ValueError("Source changed while it was being copied")
        source.seek(0)
        try:
            s3.put_object(Bucket=target, Key=target_key, Body=source, ContentLength=size,
                          ContentType=meta["mimetype"], CacheControl="private, no-store",
                          IfNoneMatch="*")
        except ClientError as error:
            if error.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
                raise
        result = s3.get_object(Bucket=target, Key=target_key)
        with result["Body"] as body:
            destination_size, destination_digest = stream_digest(body.iter_chunks(1024 * 1024))
        if (size, digest, meta["mimetype"]) != (destination_size, destination_digest, result["ContentType"]):
            raise ValueError("R2 contents or content type did not match the source")
    return {"source_bucket": bucket, "source_key": key, "source_id": row["id"],
            "source_updated_at": row.get("updated_at"), "target_bucket": target,
            "target_key": target_key, "size": size, "sha256": digest,
            "verified_at": datetime.now(timezone.utc).isoformat()}


def main():
    import boto3
    import requests
    from botocore.config import Config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ["SUPABASE_URL"].rstrip("/")
    if not re.fullmatch(r"https://[a-z0-9]+\.supabase\.co", url):
        parser.error("SUPABASE_URL must be the HTTPS project URL")
    account = os.environ["R2_ACCOUNT_ID"]
    if not re.fullmatch(r"[0-9a-f]{32}", account):
        parser.error("R2_ACCOUNT_ID must be a Cloudflare account ID")
    target = "vcms-private-images"
    storage_url = f"{url}/storage/v1"
    s3 = boto3.client("s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                      aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                      region_name="auto", config=Config(signature_version="s3v4",
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required",
                      s3={"addressing_style": "path"}))
    secret = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    verified = 0
    failed = 0
    # Create a new private manifest on each run. Object keys are not logged.
    fd = os.open(args.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as manifest, requests.Session() as session:
        session.headers.update({"Authorization": f"Bearer {secret}", "apikey": secret})
        for bucket in BUCKETS:
            for key, row in list_images(session, storage_url, bucket):
                try:
                    entry = copy_image(session, s3, storage_url, bucket, key, row, target)
                except Exception as error:
                    failed += 1
                    print(f"{bucket}: verification failed ({type(error).__name__})", file=sys.stderr)
                    continue
                manifest.write(json.dumps(entry) + "\n")
                manifest.flush()
                verified += 1
    print(f"Verified {verified} copied images. Failed: {failed}. No source files deleted.")
    return 1 if failed or not verified else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        sys.exit(f"Migration stopped ({type(error).__name__}). No source files deleted.")
