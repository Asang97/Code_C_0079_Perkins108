"""
elements/step_transformer.py — WindMil step transformer -> OpenDSS `Transformer`.

Two-winding only (tertiary confirmed dead for this dataset).
Emits:
  New Transformer.<name> phases=<n> windings=2
      buses=[<parent>.<ph>, <self>.<ph>]
      kvs=[<hv>, <lv>] kvas=[<kva>, <kva>]
      conns=[<hv_conn>, <lv_conn>] xhl=<pct_x> %r=<pct_r>

Voltages from rated_voltage_srcside / loadside, snapped to nearest standard
nominal (the dataset stores actual/computed, not nominal). Impedance is
standard-substituted by kVA (no %Z in data). Both recorded as assumptions.
"""
from __future__ import annotations
from dataclasses import dataclass

from .base import WindMilElement

# Standard nominal voltages (kV) to snap to. Extend as needed.
_STD_KV = [0.12, 0.208, 0.24, 0.277, 0.48, 2.4, 4.16, 7.2, 12.47, 14.4, 24.9, 34.5]
_SNAP_TOL = 0.10  # within 10% snaps; else flagged


def snap_kv(v: float):
    """Return (snapped_kv, was_snapped, within_tol)."""
    if not v or v <= 0:
        return v, False, False
    nearest = min(_STD_KV, key=lambda s: abs(s - v))
    within = abs(nearest - v) / nearest <= _SNAP_TOL
    return (nearest if within else v), (nearest != v), within


# Standard transformer impedance by kVA (rough, screening-grade).
def std_impedance(kva: float):
    """Return (%R, %X) typical for a distribution transformer of this size."""
    if kva <= 0:
        return 1.0, 2.0
    if kva < 50:
        return 1.4, 1.6
    if kva < 167:
        return 1.1, 1.8
    if kva < 500:
        return 1.0, 2.3
    return 0.8, 5.5


@dataclass
class StepTransformer(WindMilElement):
    hv_kv_raw: float = 0.0
    lv_kv_raw: float = 0.0
    kva: float = 0.0
    dss_type: str = "Transformer"

    # resolved
    hv_kv: float = 0.0
    lv_kv: float = 0.0

    @classmethod
    def from_row(cls, row: dict, snapshot: str):
        # per-phase kVA: sum populated phases for the bank rating
        kva = sum(float(row.get(f"capacity_kva_{p}") or 0.0) for p in ("a", "b", "c"))
        obj = cls(
            name=row["element_name"],
            parent=row["parent_element_name"],
            snapshot=snapshot,
            phase_code=row.get("phase_config_code"),
            hv_kv_raw=float(row.get("rated_voltage_srcside") or 0.0),
            lv_kv_raw=float(row.get("reate_voltage_loadside") or 0.0),  # note: source typo
            kva=kva,
        )
        obj.assume("transformer impedance standard-substituted by kVA (no %Z in data)")
        obj.assume("winding connection assumed wye-wye (winding_code not decoded)")
        return obj

    def resolve(self, feeder) -> None:
        # snap voltages to standard nominal; flag non-decodable
        self.hv_kv, hv_snapped, hv_ok = snap_kv(self.hv_kv_raw)
        self.lv_kv, lv_snapped, lv_ok = snap_kv(self.lv_kv_raw)
        if hv_snapped:
            self.assume(f"HV voltage snapped {self.hv_kv_raw}->{self.hv_kv} kV")
        if lv_snapped:
            self.assume(f"LV voltage snapped {self.lv_kv_raw}->{self.lv_kv} kV")
        if not hv_ok:
            self.flag(f"HV voltage {self.hv_kv_raw} not near a standard nominal")
        if not lv_ok:
            self.flag(f"LV voltage {self.lv_kv_raw} not near a standard nominal")

    def to_dss(self) -> str:
        pct_r, pct_x = std_impedance(self.kva)
        n = self.nphases
        bus_hv = self.bus(self.parent)
        bus_lv = self.bus(self.name)
        return (
            f"New Transformer.{self.name} phases={n} windings=2 "
            f"buses=[{bus_hv}, {bus_lv}] "
            f"kvs=[{self.hv_kv}, {self.lv_kv}] "
            f"kvas=[{self.kva}, {self.kva}] "
            f"conns=[wye, wye] "
            f"xhl={pct_x} %r={pct_r}"
        )
