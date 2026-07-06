"""
io/loaders.py — the functions FastAPI (and the Feeder) call.

Public API (parameterized by snapshot + feeder_id, read-only, stateless,
returns plain data):
    list_snapshots()                      -> [snapshot, ...]
    list_feeders(snapshot)                -> [{feeder_id, n_elements}, ...]
    load_feeder_data(snapshot, feeder_id) -> dict ready for Feeder.build()

load_feeder_data returns:
    {
      "source_rows":      {"edge":{...}, "attr":{...}},
      "line_rows":        [{"edge":{...}, "attr":{...}}, ...],
      "transformer_rows": [{"edge":{...}, "attr":{...}}, ...],
      "consumer_rows":    [{"edge":{...}, "attr":{...}}, ...],   # metered loads
      "region_voltage":   {node: base_kv_LL, ...},
    }

Bronze/silver only. Consumer phasing comes from network_consumers has_phase_*;
consumer loads come from the meter join (meter_loads.build_all_consumer_attrs).
"""
from __future__ import annotations
from math import sqrt

from .connection import query
from . import queries as Q
from .meter_loads import build_all_consumer_attrs


class FeederNotFound(Exception):
    pass


# ---------------------------------------------------------------- #
def list_snapshots() -> list[str]:
    return [r["snapshot"] for r in query(Q.LIST_SNAPSHOTS)]


def list_feeders(snapshot: str) -> list[dict]:
    return query(Q.LIST_FEEDERS, {"snapshot": snapshot})


# ---------------------------------------------------------------- #
def load_feeder_data(snapshot: str, feeder_id: str,
                     period_hours: float | None = None) -> dict:
    params = {"snapshot": snapshot, "feeder_id": feeder_id}

    elements = query(Q.FEEDER_ELEMENTS, params)
    if not elements:
        raise FeederNotFound(f"no elements for feeder {feeder_id} in {snapshot}")

    lines_attr = {r["node_id"]: r for r in query(Q.FEEDER_LINES, params)}
    xfmr_attr = {r["node_id"]: r for r in query(Q.FEEDER_TRANSFORMERS, params)}
    source_rows_raw = query(Q.FEEDER_SOURCE, params)

    # meter loads for this feeder's consumers (keyed by node_id)
    meter_rows = query(Q.METER_LOADS, {"snapshot": snapshot})
    consumer_attrs = build_all_consumer_attrs(meter_rows, period_hours=period_hours)

    elem_by_name = {e["element_name"]: e for e in elements}

    line_rows, transformer_rows, consumer_rows = [], [], []
    for name, e in elem_by_name.items():
        edge = _edge_from_path_row(e)
        if name in xfmr_attr:
            transformer_rows.append({"edge": edge, "attr": dict(xfmr_attr[name])})
        elif name in lines_attr:
            line_rows.append({"edge": edge, "attr": dict(lines_attr[name])})
        elif name in consumer_attrs:
            # metered consumer -> attach its per-phase load values
            consumer_rows.append({"edge": edge, "attr": consumer_attrs[name]})

    # source
    if not source_rows_raw:
        raise FeederNotFound(f"no substation for feeder {feeder_id}")
    src_attr = source_rows_raw[0]
    src_name = src_attr["node_id"]
    src_edge = _edge_from_path_row(elem_by_name.get(src_name, {"element_name": src_name}))
    src_edge.setdefault("source_node_id", "ROOT")
    source_rows = {"edge": src_edge, "attr": src_attr}

    region_voltage = _derive_region_voltage(elem_by_name, xfmr_attr, src_attr)

    return {
        "source_rows": source_rows,
        "line_rows": line_rows,
        "transformer_rows": transformer_rows,
        "consumer_rows": consumer_rows,
        "region_voltage": region_voltage,
    }


# ---------------------------------------------------------------- #
def _edge_from_path_row(e: dict) -> dict:
    return {
        "target_node_id": e.get("element_name") or e.get("current_node_id"),
        "source_node_id": e.get("pre_node_id"),
        "element_name": e.get("element_name"),
        "edge_type": e.get("edge_type"),
        "has_phase_a": e.get("has_phase_a"),
        "has_phase_b": e.get("has_phase_b"),
        "has_phase_c": e.get("has_phase_c"),
        "is_feeder": e.get("is_feeder"),
        "is_recloser": e.get("is_recloser"),
        "is_fuse": e.get("is_fuse"),
    }


def _derive_region_voltage(elem_by_name, xfmr_attr, src_attr) -> dict:
    """Stopgap: primary L-L (from source) on every non-transformer node.
    Replace with the voltage-region SQL for multi-voltage feeders."""
    src_ln = float(src_attr.get("nominal_voltage") or 0.0)
    src_ll = round(src_ln * sqrt(3.0), 2) if src_ln else None
    return {name: src_ll for name in elem_by_name if name not in xfmr_attr}
