"""
io/meter_loads.py — turn the structured meter table into per-phase consumer loads.

Takes the wide rows from METER_LOADS (one per consumer node) and produces the
per-scenario, per-phase kW/kVAR the Consumer element expects, using a V*I
(apparent-power) weighted split for multi-phase consumers.

Split logic:
  * single-phase consumer -> full total on its one phase (exact).
  * multi-phase -> split the total proportional to each phase's apparent power
    S_ph = V_ph * I_ph.  (Assumes uniform power factor across phases: kW and
    kVAR split by the same S-ratio -- flagged.)

Consistency check (per the design):
  compare  sum(V_ph * I_ph)  against  sqrt(kW^2 + kVAR^2)  (total apparent power).
  Agreement -> data consistent. Disagreement -> a phase shows no current though
  USAGE_POINT_PHASE claims it (likely mislabel, possibly unmeasured) -> FLAG,
  and weight only by the phases that actually show current.

Output per consumer: an attr dict ready for Consumer.from_row, i.e. keys like
  kw_coincident_a, kvar_max_b, ... plus usage_point_phase, meter, and any flags.
"""
from __future__ import annotations
from math import sqrt

# fraction tolerance for the apparent-power consistency check
_CONSISTENCY_TOL = 0.15
# a phase is "carrying current" if its share of total S exceeds this
_ACTIVE_PHASE_MIN_SHARE = 0.02


def _f(v):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _phase_apparent_power(row: dict) -> dict:
    """S_ph = V_ph * I_ph per phase (apparent power weights)."""
    return {
        "A": _f(row.get("v_a")) * _f(row.get("i_a")),
        "B": _f(row.get("v_b")) * _f(row.get("i_b")),
        "C": _f(row.get("v_c")) * _f(row.get("i_c")),
    }


def build_consumer_attr(row: dict, period_hours: float | None = None) -> dict:
    """Turn one wide meter row into a Consumer attr dict (all scenarios, per phase).

    period_hours: hours in the reading period, to convert kWh -> average kW.
    """
    flags = []
    phase_str = (row.get("usage_point_phase") or "").strip().upper()
    phases = [p for p in "ABC" if p in phase_str]
    if not phases:
        # unknown phasing — cannot place load; return minimal attr with a flag
        return {"usage_point_phase": phase_str, "meter": row.get("meter"),
                "_flags": ["USAGE_POINT_PHASE missing; cannot place load"]}

    # --- totals per scenario ---
    totals = {
        "coincident": (_f(row.get("kw_coincident")), _f(row.get("kvar_coincident"))),
        "max":        (_f(row.get("kw_max")),        _f(row.get("kvar_max"))),
    }
    # average scenario from kWh consumption (needs period hours)
    kwh = _f(row.get("kwh_consumption"))
    kvarh = _f(row.get("kvarh"))
    if kwh and period_hours:
        totals["average"] = (kwh / period_hours, (kvarh / period_hours) if kvarh else 0.0)
    else:
        totals["average"] = (0.0, 0.0)
        if kwh and not period_hours:
            flags.append("kWh present but period_hours not given; average scenario = 0")

    # --- per-phase weights from V*I ---
    s_ph = _phase_apparent_power(row)
    # restrict to the phases the consumer is supposed to be on
    s_on = {p: s_ph[p] for p in phases}
    s_sum = sum(s_on.values())

    # consistency check against the coincident demand's apparent power.
    # V*I is in VA; demand is in kVA -> convert V*I sum to kVA to compare.
    kw_c, kvar_c = totals["coincident"]
    s_demand = sqrt(kw_c**2 + kvar_c**2)             # kVA
    s_sum_kva = s_sum / 1000.0                        # VA -> kVA
    if s_sum_kva > 0 and s_demand > 0:
        rel = abs(s_sum_kva - s_demand) / s_demand
        if rel > _CONSISTENCY_TOL:
            flags.append(
                f"apparent-power mismatch: sum(V*I)={s_sum_kva:.1f} kVA vs "
                f"sqrt(kW^2+kVAR^2)={s_demand:.1f} kVA ({rel*100:.0f}% off) - "
                f"possible phase mislabel or unmeasured phase"
            )

    # identify phases actually carrying current (share of total S)
    active = phases
    if s_sum > 0:
        active = [p for p in phases if (s_on[p] / s_sum) >= _ACTIVE_PHASE_MIN_SHARE]
        missing = [p for p in phases if p not in active]
        if missing:
            flags.append(
                f"phase(s) {','.join(missing)} in USAGE_POINT_PHASE but show ~no "
                f"current; weighting by active phases {','.join(active)} "
                f"(likely mislabel)"
            )

    # --- compute the split weights ---
    if len(phases) == 1:
        weights = {phases[0]: 1.0}                     # single-phase: all on it
    elif s_sum > 0:
        # weight by apparent power over the ACTIVE phases
        act_sum = sum(s_on[p] for p in active) or 1.0
        weights = {p: (s_on[p] / act_sum if p in active else 0.0) for p in phases}
    else:
        # no V/I signal -> fall back to equal split, flagged
        weights = {p: 1.0 / len(phases) for p in phases}
        flags.append("no per-phase V*I available; equal split assumed")

    # --- build per-scenario, per-phase attr ---
    attr = {"usage_point_phase": phase_str, "meter": row.get("meter"),
            "serving_kv_ln": None}                     # filled by the Feeder
    for scen, (kw_tot, kvar_tot) in totals.items():
        for p in phases:
            w = weights.get(p, 0.0)
            attr[f"kw_{scen}_{p.lower()}"] = round(kw_tot * w, 4)
            attr[f"kvar_{scen}_{p.lower()}"] = round(kvar_tot * w, 4)

    if weights and len(phases) > 1:
        attr.setdefault("_assumptions", []).append(
            "per-phase load split by measured apparent power (V*I); "
            "uniform power factor across phases assumed"
        )
    if flags:
        attr["_flags"] = flags
    return attr


def build_all_consumer_attrs(rows: list[dict], period_hours: float | None = None) -> dict:
    """Map node_id -> consumer attr dict, for every metered consumer."""
    out = {}
    for row in rows:
        node = row.get("node_id")
        if node:
            out[node] = build_consumer_attr(row, period_hours=period_hours)
    return out
