"""Environment-backed settings shared by all VCMS backend modules."""
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
REST = f"{SUPABASE_URL}/rest/v1"

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET = os.environ.get("R2_BUCKET", "").strip()
R2_PUBLIC_BASE = os.environ.get("R2_PUBLIC_BASE", "").strip().rstrip("/")
R2_ENABLED = all((R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET, R2_BUCKET, R2_PUBLIC_BASE))

