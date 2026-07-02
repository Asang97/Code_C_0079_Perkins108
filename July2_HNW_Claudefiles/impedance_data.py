"""
libraries/impedance_data.py — standard per-unit-length sequence impedance,
bucketed by (line_type, voltage_class).

FIRST-PASS APPROXIMATION (coarsest tier):
  Impedance is estimated from line TYPE (overhead/underground) and VOLTAGE
  CLASS only -- NOT from the specific conductor. This means a 477 ACSR backbone
  and a #2 ACSR lateral in the same class get the SAME impedance. Voltage drop
  on small-conductor laterals is therefore UNDER-estimated. This is a
  screening-of-screening bootstrap; upgrade to conductor-keyed lookup later
  without changing the LineCodeLibrary interface.

Values are SEQUENCE impedance in OHMS PER MILE: (R1, X1, R0, X0).
OpenDSS multiplies these by the line's `length` (converted to miles).
The line supplies the length; this table supplies impedance/length.

Representative values below are typical distribution figures; tune freely.
Capacitance (C1/C0) is omitted first-pass (OpenDSS defaults), add later if
shunt charging matters.
"""
from __future__ import annotations

# Voltage-class buckets (line-to-line kV midpoints -> class label)
# A line's base_kv (from the voltage trace) is snapped to the nearest class.
VOLTAGE_CLASSES = {
    "secondary":   0.24,    # <1 kV service / secondary
    "primary_4":   4.16,
    "primary_15":  12.47,
    "primary_25":  24.90,
    "primary_35":  34.50,
}

def voltage_class(base_kv: float | None) -> str:
    """Snap a line-to-line base kV to the nearest standard class label."""
    if not base_kv or base_kv <= 0:
        return "primary_25"   # safe default class; flagged upstream if unknown
    nearest = min(VOLTAGE_CLASSES.items(), key=lambda kv: abs(kv[1] - base_kv))
    return nearest[0]


# (line_type, voltage_class) -> (R1, X1, R0, X0) ohms/mile
# Overhead: higher reactance (wider spacing). Underground: lower X, higher C.
_IMPEDANCE: dict[tuple[str, str], tuple[float, float, float, float]] = {
    # ---- overhead ----
    ("overhead", "secondary"):  (0.90, 0.30, 1.80, 1.20),
    ("overhead", "primary_4"):  (0.55, 0.45, 1.40, 1.60),
    ("overhead", "primary_15"): (0.40, 0.55, 1.10, 1.80),
    ("overhead", "primary_25"): (0.35, 0.60, 1.00, 2.00),
    ("overhead", "primary_35"): (0.30, 0.62, 0.95, 2.10),
    # ---- underground (cable: lower X, lower R0 via concentric neutral) ----
    ("underground", "secondary"):  (0.50, 0.10, 0.80, 0.30),
    ("underground", "primary_4"):  (0.45, 0.12, 0.70, 0.35),
    ("underground", "primary_15"): (0.40, 0.13, 0.65, 0.38),
    ("underground", "primary_25"): (0.38, 0.14, 0.62, 0.40),
    ("underground", "primary_35"): (0.36, 0.15, 0.60, 0.42),
}

# fallback when a (type, class) bucket isn't in the table
_FALLBACK = (0.40, 0.50, 1.00, 1.80)


def lookup(line_type: str | None, base_kv: float | None):
    """Return ((R1,X1,R0,X0) ohms/mi, vclass, was_fallback)."""
    lt = (line_type or "overhead").lower()
    if lt not in ("overhead", "underground"):
        lt = "overhead"
    vclass = voltage_class(base_kv)
    key = (lt, vclass)
    if key in _IMPEDANCE:
        return _IMPEDANCE[key], vclass, False
    return _FALLBACK, vclass, True


def bucket_name(line_type: str | None, base_kv: float | None) -> str:
    """Stable LineCode name for a (type, voltage-class) bucket, e.g. 'OH_PRIMARY_25'."""
    lt = (line_type or "overhead").lower()
    prefix = "UG" if lt == "underground" else "OH"
    return f"{prefix}_{voltage_class(base_kv).upper()}"
