"""
io/loaders.py — hierarchical drill-down loaders (substation -> feeder -> tree).

Avoids the expensive `path LIKE '%feeder%'` self-join (which OOM'd) by:
  1. list_substations(as_of)                 -- cheap NODE_TYPE filter
  2. list_feeders(as_of, substation_id)       -- children of the substation
  3. feeder_elements via recursive tree walk  -- only this feeder's subtree
  4. attributes pulled by an EXPLICIT node list (no join)

Point-in-time via :as_of (VALID_FROM/VALID_TO). Catalog from MILSOFT_CATALOG.

Public API:
    list_as_of_dates()
    list_substations(as_of)                          -> [substation_id, ...]
    list_feeders(as_of, substation_id)               -> [feeder_id, ...]
    load_feeder_data(as_of, substation_id, feeder_id)-> dict for Feeder.build()

Defaults: substation -> 'Saint Johns' area default (caller may override);
feeder -> first in the list.
"""
from __future__ import annotations
from math import sqrt

from .connection import query
from . import queries as Q
from .meter_loads import build_all_consumer_attrs

DEFAULT_SUBSTATION = None   # set to your Saint Johns substation node id if desired


class FeederNotFound(Exception):
    pass


# ---------------------------------------------------------------- #
def list_as_of_dates() -> list:
    return [r["as_of"] for r in query(Q.LIST_SNAPSHOTS)]

list_snapshots = list_as_of_dates  # compat alias


def list_substations(as_of) -> list[str]:
    return [r["substation_id"] for r in query(Q.LIST_SUBSTATIONS, {"as_of": as_of})]


def list_feeders(as_of, substation_id: str | None = None) -> list[str]:
    """Feeders (reclosers) directly below a substation.
    Defaults the substation to the first available if not given."""
    if substation_id is None:
        subs = list_substations(as_of)
        if not subs:
            return []
        substation_id = DEFAULT_SUBSTATION or subs[0]
    rows = query(Q.LIST_FEEDERS, {"as_of": as_of, "substation_id": substation_id})
    return [r["feeder_id"] for r in rows]


# ---------------------------------------------------------------- #
def load_feeder_data(as_of, substation_id: str | None = None,
                     feeder_id: str | None = None,
                     period_hours: float | None = None) -> dict:
    # resolve defaults: substation -> first; feeder -> first under it
    if substation_id is None:
        subs = list_substations(as_of)
        if not subs:
            raise FeederNotFound(f"no substations at {as_of}")
        substation_id = DEFAULT_SUBSTATION or subs[0]
    if feeder_id is None:
        feeders = list_feeders(as_of, substation_id)
        if not feeders:
            raise FeederNotFound(f"no feeders under substation {substation_id}")
        feeder_id = feeders[0]

    # 1) the feeder's element set via the recursive tree walk
    elements = query(Q.FEEDER_ELEMENTS, {"as_of": as_of, "feeder_id": feeder_id})
    if not elements:
        raise FeederNotFound(f"no elements for feeder {feeder_id} at {as_of}")

    node_ids = sorted({e["element_name"] for e in elements if e.get("element_name")})

    # 2) attributes by EXPLICIT node list (no join). IN-list is expanded safely.
    lines_attr = {r["node_id"]: r for r in
                  _query_in(Q.FEEDER_LINES, as_of, node_ids)}
    xfmr_attr = {r["node_id"]: r for r in
                 _query_in(Q.FEEDER_TRANSFORMERS, as_of, node_ids)}

    # 3) source = the substation attributes
    src_rows = query(Q.FEEDER_SOURCE, {"as_of": as_of, "substation_id": substation_id})
    if not src_rows:
        raise FeederNotFound(f"no substation attributes for {substation_id}")
    src_attr = src_rows[0]

    # 4) meter loads (per-consumer), keyed by node
    meter_rows = query(Q.METER_LOADS, {"as_of": as_of})
    consumer_attrs = build_all_consumer_attrs(meter_rows, period_hours=period_hours)

    # shape rows for Feeder.build
    elem_by_name = {e["element_name"]: e for e in elements}
    line_rows, transformer_rows, consumer_rows = [], [], []
    for name, e in elem_by_name.items():
        edge = _edge_from_path_row(e)
        if name in xfmr_attr:
            transformer_rows.append({"edge": edge, "attr": dict(xfmr_attr[name])})
        elif name in lines_attr:
            line_rows.append({"edge": edge, "attr": dict(lines_attr[name])})
        elif name in consumer_attrs:
            consumer_rows.append({"edge": edge, "attr": consumer_attrs[name]})

    src_edge = {"target_node_id": substation_id, "source_node_id": "ROOT",
                "element_name": substation_id}
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
def _query_in(sql_with_nodes: str, as_of, node_ids: list[str]) -> list[dict]:
    """Run a query whose SQL has an IN (:nodes) placeholder, expanding the list
    into individual bound params (:n0, :n1, ...) to stay injection-safe.
    Chunks large lists to avoid parameter limits."""
    if not node_ids:
        return []
    out = []
    CHUNK = 500
    for i in range(0, len(node_ids), CHUNK):
        chunk = node_ids[i:i+CHUNK]
        markers = ", ".join(f":n{j}" for j in range(len(chunk)))
        sql = sql_with_nodes.replace("(:nodes)", f"({markers})")
        params = {"as_of": as_of}
        params.update({f"n{j}": v for j, v in enumerate(chunk)})
        out.extend(query(sql, params))
    return out


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
    src_ln = float(src_attr.get("nominal_voltage") or 0.0)
    src_ll = round(src_ln * sqrt(3.0), 2) if src_ln else None
    return {name: src_ll for name in elem_by_name if name not in xfmr_attr}
