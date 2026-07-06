"""
test_io.py — staged test of the io layer against real Databricks data.

Run on YOUR machine (needs .env + databricks-sql-connector + network):
    python test_io.py                       # uses first snapshot, first feeder
    python test_io.py --snapshot 260316_std --feeder rclsr_123

Tests in dependency order and STOPS at the first failing stage, so a failure
points at exactly one layer (env / connection / discovery / load / assemble).
"""
from __future__ import annotations
import argparse, os, sys, traceback


def stage(n, name):
    print(f"\n[{n}] {name}")
    print("-" * 50)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--feeder", default=None)
    ap.add_argument("--write", action="store_true", help="write the .dss file")
    args = ap.parse_args()

    # ---- Stage 0: environment --------------------------------------------
    stage(0, "Environment (.env credentials)")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("  note: python-dotenv not installed; relying on shell env")
    missing = [k for k in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH",
                           "DATABRICKS_ACCESS_TOKEN") if not os.environ.get(k)]
    if missing:
        print(f"  FAIL: missing env vars: {missing}")
        print("  -> add them to your .env")
        return 1
    print("  OK: all three credentials present")

    # ---- Stage 1: connection + trivial query -----------------------------
    stage(1, "Connection (list_snapshots)")
    try:
        from milsoft_dss.io.loaders import list_snapshots
        snaps = list_snapshots()
        print(f"  OK: {len(snaps)} snapshots: {snaps[:5]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        if "databricks" in str(e).lower() and "install" in str(e).lower():
            print("  -> pip install databricks-sql-connector")
        elif "param" in str(e).lower() or "inline" in str(e).lower():
            print("  -> your DBR may be <14.2; add use_inline_params=True in connection.py")
        traceback.print_exc()
        return 1

    snapshot = args.snapshot or (snaps[0] if snaps else None)
    if not snapshot:
        print("  FAIL: no snapshot to use"); return 1
    print(f"  using snapshot: {snapshot}")

    # ---- Stage 2: feeder discovery ---------------------------------------
    stage(2, "Feeder discovery (list_feeders)")
    try:
        from milsoft_dss.io.loaders import list_feeders
        feeders = list_feeders(snapshot)
        print(f"  OK: {len(feeders)} feeders (expect ~212)")
        print(f"  sample: {feeders[:3]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        print("  -> check list_feeders.sql (table names, is_feeder flag)")
        traceback.print_exc()
        return 1
    if not feeders:
        print("  FAIL: no feeders found"); return 1

    feeder_id = args.feeder or feeders[0]["feeder_id"]
    print(f"  using feeder: {feeder_id}")

    # ---- Stage 3: load one feeder's data ---------------------------------
    stage(3, "Load feeder data (load_feeder_data)")
    try:
        from milsoft_dss.io.loaders import load_feeder_data
        data = load_feeder_data(snapshot, feeder_id)
        print(f"  OK:")
        print(f"    source:        {bool(data['source_rows'].get('attr'))}")
        print(f"    lines:         {len(data['line_rows'])}")
        print(f"    transformers:  {len(data['transformer_rows'])}")
        print(f"    consumers:     {len(data['consumer_rows'])}")
        print(f"    region_voltage:{len(data['region_voltage'])} nodes")
        if len(data["consumer_rows"]) == 0:
            print("    WARN: 0 consumers - meter join may need vocabulary tuning")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        print("  -> check feeder_*.sql / meter_loads.sql (table names, vocabulary)")
        traceback.print_exc()
        return 1

    # ---- Stage 4: assemble + report --------------------------------------
    stage(4, "Assemble feeder + report")
    try:
        from milsoft_dss.feeder import Feeder
        feeder = Feeder.build(feeder_id, snapshot, **data)
        rep = feeder.report()
        print(f"  OK: built feeder")
        print(f"    lines={rep['n_lines']} xfmrs={rep['n_transformers']} "
              f"consumers={rep['n_consumers']} linecodes={rep['n_linecodes']}")
        print(f"    total_load_kw={rep['total_load_kw']}")
        print(f"    assumptions={len(rep['assumptions'])}  flags={len(rep['flags'])}")
        if rep["flags"]:
            print("    --- FLAGS (first 15) ---")
            for fl in rep["flags"][:15]:
                print("     ", fl)
        if args.write:
            from milsoft_dss.io.dss_output import write_feeder_dss
            path = write_feeder_dss(feeder)
            print(f"    wrote: {path}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    print("\n" + "=" * 50)
    print("ALL STAGES PASSED — io layer works against real data")
    return 0


if __name__ == "__main__":
    sys.exit(main())