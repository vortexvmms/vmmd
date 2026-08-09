#!/usr/bin/env python3
"""Capture a sanitized live schema and compare its tables with backend usage.

Requires pg_dump and SUPABASE_DB_URL. The connection value is never printed or
written. Output contains schema only, never production rows.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" / "app" / "main.py"
OUTPUT = ROOT / "db" / "reconciliation" / "live_schema.sql"
REPORT = ROOT / "db" / "reconciliation" / "inventory.txt"


def table_names(sql: str) -> set[str]:
    return set(re.findall(r"create\s+table(?:\s+if\s+not\s+exists)?\s+(?:public\.)?([a-z_][a-z0-9_]*)", sql, re.I))


def backend_tables(source: str) -> set[str]:
    return set(re.findall(r'\{REST\}/([a-z_][a-z0-9_]*)', source))


def main() -> int:
    database_url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not database_url:
        print("SUPABASE_DB_URL is required; no live connection was attempted.", file=sys.stderr)
        return 2
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    command = ["pg_dump", "--schema-only", "--no-owner", "--no-privileges", database_url]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("pg_dump is not installed.", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print("Schema export failed; connection details were not displayed.", file=sys.stderr)
        return exc.returncode or 1

    OUTPUT.write_text(result.stdout, encoding="utf-8")
    live = table_names(result.stdout)
    used = backend_tables(BACKEND.read_text(encoding="utf-8"))
    lines = [
        "VCMS schema reconciliation inventory",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "Data exported: none (schema only)",
        "",
        "Tables in live schema:", *[f"- {name}" for name in sorted(live)],
        "", "Tables referenced by backend:", *[f"- {name}" for name in sorted(used)],
        "", "Backend references missing from live schema:",
        *([f"- {name}" for name in sorted(used - live)] or ["- none"]),
        "", "Live tables not referenced directly by backend:",
        *([f"- {name}" for name in sorted(live - used)] or ["- none"]),
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
