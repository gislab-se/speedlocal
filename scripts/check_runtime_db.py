from __future__ import annotations

import os
import sys


REQUIRED_TABLES = [
    "runtime.regions",
    "runtime.region_catalogs",
    "runtime.h3_display_cells",
    "runtime.landscape_cells",
    "meta.runtime_datasets",
]


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL is not set. Database check skipped.")
        return 0

    try:
        import psycopg  # type: ignore
    except Exception as exc:
        print(f"psycopg is not installed: {exc}")
        return 1

    with psycopg.connect(url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database()")
            print(f"database: {cur.fetchone()[0]}")
            for table in REQUIRED_TABLES:
                schema, name = table.split(".", 1)
                cur.execute(
                    """
                    select exists (
                        select 1
                        from information_schema.tables
                        where table_schema = %s and table_name = %s
                    )
                    """,
                    (schema, name),
                )
                exists = bool(cur.fetchone()[0])
                print(f"{table}: {'ok' if exists else 'missing'}")
                if not exists:
                    return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
