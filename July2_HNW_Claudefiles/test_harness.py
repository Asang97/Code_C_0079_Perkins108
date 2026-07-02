"""
test_harness.py — drive the Feeder from CSV exports of your silver tables.

This is a TEST bridge (a mini query layer) so you can validate the pipeline on
REAL data before building the full query/io layer. Export a few CSVs from
Databricks, point this at them, and it assembles one feeder -> emits .dss ->
solves -> reports.

------------------------------------------------------------------------------
CSV FILES EXPECTED (export these from silver, scoped to ONE snapshot):

1. edges.csv        (from network_edges)
   columns: target_node_id, source_node_id, edge_type,
            has_phase_a, has_phase_b, has_phase_c, VALID_FROM, VALID_TO

2. lines.csv        (from network_lines)
   columns: node_id (= element_name), line_type,
            conductor_eqdb_label_a, conductor_eqdb_label_b,
            conductor_eqdb_label_c, conductor_eqdb_label_neutral,
            impedance_length_ft, neutral_impedance_length_ft

3. transformers.csv (from network_transformers)
   columns: node_id, rated_voltage_srcside, rated_voltage_loadside,
            capacity_kva_a, capacity_kva_b, capacity_kva_c,
            TRANSFORMER_PHASE, USAGE_POINT_PHASE

4. substations.csv  (from network_substations)
   columns: node_id, nominal_voltage, voltage_bus_ratio,
            has_phase_a, has_phase_b, has_phase_c

5. region_voltage.csv (from the voltage-region SQL; node -> base_kv)
   columns: node, region_kv

------------------------------------------------------------------------------
USAGE:
   python test_harness.py --dir ./feeder_csvs --source SUB_NODE_ID [--solve]

The --source is the substation node_id that roots the feeder you want to build.
Elements are filtered to those reachable from that source (simple: everything in
the CSVs; export per-feeder CSVs, or the harness takes all rows given).
"""
from __future__ import annotations
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from milsoft_dss.feeder import Feeder


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _num(v):
    """Best-effort numeric coercion; leave strings/None alone."""
    if v in (None, "", "NULL", "null"):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return v


def _bool(v):
    if v in (None, "", "NULL"):
        return None
    return str(v).strip().lower() in ("1", "true", "t", "yes", "y")


def build_feeder_from_csvs(csv_dir: str, source_node: str, snapshot: str) -> Feeder:
    edges = read_csv(os.path.join(csv_dir, "edges.csv"))
    lines_attr = read_csv(os.path.join(csv_dir, "lines.csv"))
    xfmr_attr = read_csv(os.path.join(csv_dir, "transformers.csv"))
    subs_attr = read_csv(os.path.join(csv_dir, "substations.csv"))
    region_rows = read_csv(os.path.join(csv_dir, "region_voltage.csv"))

    # index attributes by node id for joining to edges
    lines_by_node = {r["node_id"]: r for r in lines_attr}
    xfmr_by_node = {r["node_id"]: r for r in xfmr_attr}
    subs_by_node = {r["node_id"]: r for r in subs_attr}
    region_voltage = {r["node"]: _num(r["region_kv"]) for r in region_rows}

    # split edges by type, joining each to its attribute row
    line_rows, transformer_rows = [], []
    source_rows = None

    for e in edges:
        etype = (e.get("edge_type") or "").strip().lower()
        node = e.get("target_node_id") or e.get("element_name")

        # normalize edge fields
        edge = {
            "target_node_id": e.get("target_node_id"),
            "source_node_id": e.get("source_node_id"),
            "element_name": e.get("target_node_id"),
            "has_phase_a": _bool(e.get("has_phase_a")),
            "has_phase_b": _bool(e.get("has_phase_b")),
            "has_phase_c": _bool(e.get("has_phase_c")),
            "VALID_FROM": e.get("VALID_FROM"),
            "VALID_TO": e.get("VALID_TO"),
        }

        if etype in ("overhead_line", "underground_line") or node in lines_by_node:
            attr = lines_by_node.get(node)
            if attr:
                attr = {k: _num(v) if "length" in k else v for k, v in attr.items()}
                line_rows.append({"edge": edge, "attr": attr})
        elif etype == "step_transformer" or node in xfmr_by_node:
            attr = xfmr_by_node.get(node)
            if attr:
                attr = {k: _num(v) if ("voltage" in k or "kva" in k) else v
                        for k, v in attr.items()}
                transformer_rows.append({"edge": edge, "attr": attr})
        elif etype in ("source", "substation") or node == source_node:
            attr = subs_by_node.get(node)
            if attr:
                attr = {k: (_num(v) if ("voltage" in k or "ratio" in k) else v)
                        for k, v in attr.items()}
                attr["has_phase_a"] = _bool(attr.get("has_phase_a"))
                attr["has_phase_b"] = _bool(attr.get("has_phase_b"))
                attr["has_phase_c"] = _bool(attr.get("has_phase_c"))
                source_rows = {"edge": edge, "attr": attr}

    if source_rows is None:
        # fall back: build source directly from substations.csv for source_node
        sub = subs_by_node.get(source_node)
        if sub:
            source_rows = {
                "edge": {"target_node_id": source_node, "source_node_id": "ROOT",
                         "element_name": source_node},
                "attr": {k: (_num(v) if ("voltage" in k or "ratio" in k) else v)
                         for k, v in sub.items()},
            }
        else:
            raise SystemExit(f"source node {source_node!r} not found in substations.csv")

    return Feeder.build(
        name=f"feeder_{source_node}",
        snapshot=snapshot,
        source_rows=source_rows,
        line_rows=line_rows,
        transformer_rows=transformer_rows,
        region_voltage=region_voltage,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="folder with the CSV exports")
    ap.add_argument("--source", required=True, help="substation node_id rooting the feeder")
    ap.add_argument("--snapshot", default="260316_std")
    ap.add_argument("--solve", action="store_true", help="also solve with OpenDSS")
    ap.add_argument("--out", default="feeder.dss", help="write the .dss here")
    args = ap.parse_args()

    feeder = build_feeder_from_csvs(args.dir, args.source, args.snapshot)
    dss_text = feeder.to_dss()

    with open(args.out, "w") as f:
        f.write(dss_text)
    print(f"wrote {args.out}")

    rep = feeder.report()
    print(f"\nFeeder {rep['feeder']}: lines={rep['n_lines']} "
          f"xfmrs={rep['n_transformers']} linecodes={rep['n_linecodes']}")
    print(f"assumptions={len(rep['assumptions'])}  flags={len(rep['flags'])}")
    if rep["flags"]:
        print("\n--- FLAGS (data-quality issues to review) ---")
        for fl in rep["flags"][:30]:
            print("  ", fl)

    if args.solve:
        try:
            import opendssdirect as dss
        except ImportError:
            print("\nopendssdirect not installed; skipping solve.")
            return
        dss.Text.Command("Clear")
        for stmt in dss_text.splitlines():
            if stmt.strip() and not stmt.startswith("!"):
                dss.Text.Command(stmt)
        dss.Solution.Solve()
        print(f"\n--- SOLVE ---\nConverged: {dss.Solution.Converged()}")
        buses = dss.Circuit.AllBusNames()
        print(f"buses: {len(buses)}")
        # show voltage range
        vmin, vmax = 9, 0
        for b in buses:
            dss.Circuit.SetActiveBus(b)
            v = dss.Bus.puVmagAngle()
            if v:
                vmin = min(vmin, v[0]); vmax = max(vmax, v[0])
        print(f"pu voltage range: {vmin:.4f} - {vmax:.4f}")


if __name__ == "__main__":
    main()
