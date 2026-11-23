"""Private lifting-original URL signing: no public bucket or arbitrary object access."""
from urllib.parse import urlsplit

import pytest
from app import storage


def test_lifting_original_uses_private_r2_namespace(monkeypatch):
    monkeypatch.setattr(storage, "PRIVATE_IMAGES_R2_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(storage, "PRIVATE_IMAGES_R2_ACCESS_KEY_ID", "test-key")
    monkeypatch.setattr(storage, "PRIVATE_IMAGES_R2_SECRET", "test-secret")
    monkeypatch.setattr(storage, "PRIVATE_IMAGES_R2_BUCKET", "vcms-private-images")
    for method in ("PUT", "GET"):
        url = storage.private_image_url("lifting-documents", "originals/12345", method)
        parsed = urlsplit(url)
        assert parsed.scheme == "https"
        assert parsed.hostname == "test-account.r2.cloudflarestorage.com"
        assert parsed.path == "/vcms-private-images/supabase-images/lifting-documents/originals/12345"
        assert "X-Amz-Signature=" in parsed.query
        assert "X-Amz-Expires=60" in parsed.query


def test_lifting_signing_rejects_unapproved_namespace(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported"):
        storage.private_image_url("lifting-public", "originals/12345", "GET")
