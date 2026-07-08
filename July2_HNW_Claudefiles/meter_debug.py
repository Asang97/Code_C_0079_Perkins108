"""
debug_meter.py — isolate why the meter join returns 0 consumers.

Runs each link of the join chain separately and prints the row count at each
stage, so you see exactly where it drops to zero. Also dumps the real
readingdefinition vocabulary so you can compare against the SQL's string filters.

Run:  python debug_meter.py --as-of 2026-03-16
"""
from __future__ import annotations
import argparse, os

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

from milsoft_dss.io.connection import query

CAT = os.environ.get("MILSOFT_CATALOG", "prod")


def count(label, sql, params=None):
    try:
        rows = query(sql, params or {})
        n = rows[0].get("n") if rows else 0
        print(f"  {label}: {n}")
        return n
    except Exception as e:
        print(f"  {label}: ERROR - {type(e).__name__}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True)
    args = ap.parse_args()
    p = {"as_of": args.as_of}

    print(f"catalog={CAT}  as_of={args.as_of}\n")

    print("[1] network_consumers valid at as_of")
    count("count", f"""
        SELECT COUNT(*) AS n FROM {CAT}.silver.network_consumers
        WHERE VALID_FROM <= :as_of AND (VALID_TO > :as_of OR VALID_TO IS NULL)
    """, p)

    print("\n[2] + join netsense_device (SITE_LOCATION = node_id)")
    count("count", f"""
        SELECT COUNT(*) AS n
        FROM {CAT}.silver.network_consumers nc
        JOIN {CAT}.silver.netsense_device dev ON dev.SITE_LOCATION = nc.node_id
        WHERE nc.VALID_FROM <= :as_of AND (nc.VALID_TO > :as_of OR nc.VALID_TO IS NULL)
    """, p)

    print("\n[3] + join netsense_reading (DEVICE_NAME)")
    count("count", f"""
        SELECT COUNT(*) AS n
        FROM {CAT}.silver.network_consumers nc
        JOIN {CAT}.silver.netsense_device dev ON dev.SITE_LOCATION = nc.node_id
        JOIN {CAT}.bronze.netsense_reading r ON r.DEVICE_NAME = dev.DEVICE_NAME
        WHERE nc.VALID_FROM <= :as_of AND (nc.VALID_TO > :as_of OR nc.VALID_TO IS NULL)
    """, p)

    print("\n[4] + join readingdefinition (OBJECT_NUMBER = READING_TYPE_ID)")
    count("count", f"""
        SELECT COUNT(*) AS n
        FROM {CAT}.silver.network_consumers nc
        JOIN {CAT}.silver.netsense_device dev ON dev.SITE_LOCATION = nc.node_id
        JOIN {CAT}.bronze.netsense_reading r ON r.DEVICE_NAME = dev.DEVICE_NAME
        JOIN {CAT}.silver.netsense_readingdefinition rd ON rd.OBJECT_NUMBER = r.READING_TYPE_ID
        WHERE nc.VALID_FROM <= :as_of AND (nc.VALID_TO > :as_of OR nc.VALID_TO IS NULL)
    """, p)

    print("\n[5] actual readingdefinition vocabulary (UOM / TYPE / SUBTYPE):")
    try:
        rows = query(f"""
            SELECT DISTINCT UOM, TYPE, SUBTYPE
            FROM {CAT}.silver.netsense_readingdefinition
            ORDER BY UOM, TYPE, SUBTYPE LIMIT 60
        """)
        for r in rows:
            print(f"    UOM={r.get('uom')!r:12} TYPE={r.get('type')!r:20} SUBTYPE={r.get('subtype')!r}")
    except Exception as e:
        print(f"    ERROR: {e}")

    print("\n[6] sample netsense_device columns (check SITE_LOCATION / DEVICE_NAME):")
    try:
        rows = query(f"SELECT * FROM {CAT}.silver.netsense_device LIMIT 3")
        if rows:
            print("    columns:", list(rows[0].keys()))
            for r in rows:
                print("   ", {k: r[k] for k in list(r)[:6]})
    except Exception as e:
        print(f"    ERROR: {e}")

    print("\n[7] sample network_consumers node_id values:")
    try:
        rows = query(f"""SELECT node_id FROM {CAT}.silver.network_consumers
                         WHERE VALID_FROM <= :as_of LIMIT 5""", p)
        print("    node_ids:", [r.get("node_id") for r in rows])
    except Exception as e:
        print(f"    ERROR: {e}")


if __name__ == "__main__":
    main()