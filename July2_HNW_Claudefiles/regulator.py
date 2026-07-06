"""
elements/regulator.py — WindMil regulator -> OpenDSS `Transformer` + `RegControl`.

A step voltage regulator holds downstream voltage near a target by changing taps.
OpenDSS models it as a TWO-WINDING TRANSFORMER (1:1 nominal, small impedance)
paired with a RegControl object that sets the target voltage and bandwidth.

Emits TWO statements:
    New Transformer.<name> phases=<n> windings=2 buses=[<in>, <out>]
        kvs=[<kv>, <kv>] kvas=[<kva>, <kva>] xhl=<x> %loadloss=<r>
    New RegControl.<name> transformer=<name> winding=2
        vreg=<target_120base> band=<band> ptratio=<pt>

Modeling choices (screening; flagged):
  * regulator kV = the region voltage at its location (in == out, it's a
    series regulator on one voltage level).
  * target 120 V-base vreg from the bus setpoint (default 122 ~ 1.017 pu) and a
    2 V bandwidth, typical utility defaults, unless the data provides them.
  * small series impedance (regulators are near-ideal series devices).
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt

from .base import WindMilElement

_SQRT3 = sqrt(3.0)

# typical regulator control defaults (120 V base, as OpenDSS RegControl uses)
_DEFAULT_VREG = 122.0     # ~1.017 pu target
_DEFAULT_BAND = 2.0       # volts
_DEFAULT_PTRATIO = None   # computed from kv if not supplied


@dataclass
class Regulator(WindMilElement):
    base_kv: float | None = None      # region L-L voltage at the regulator
    bank_kva: float = 5000.0          # nominal pass-through rating (large; near-ideal)
    vreg: float = _DEFAULT_VREG       # target voltage on 120 V base
    band: float = _DEFAULT_BAND
    dss_type: str = "Transformer"     # emitted as transformer + regcontrol

    @classmethod
    def from_row(cls, edge: dict, attr: dict, snapshot: str):
        attr = attr or {}
        obj = cls(
            name=edge.get("target_node_id") or edge.get("element_name"),
            parent=edge.get("source_node_id"),
            snapshot=snapshot,
            valid_from=edge.get("VALID_FROM"),
            valid_to=edge.get("VALID_TO"),
            has_a=edge.get("has_phase_a"),
            has_b=edge.get("has_phase_b"),
            has_c=edge.get("has_phase_c"),
        )
        # optional control settings from data
        if attr.get("vreg") is not None:
            obj.vreg = float(attr["vreg"])
        if attr.get("bandwidth") is not None:
            obj.band = float(attr["bandwidth"])
        if attr.get("rated_kva"):
            obj.bank_kva = float(attr["rated_kva"])

        obj.add_assumption(
            f"regulator modeled as tap-changing transformer + RegControl "
            f"(vreg={obj.vreg} V/120-base, band={obj.band} V)"
        )
        obj.add_assumption("regulator near-ideal series device (small impedance)")
        return obj

    def resolve(self, feeder=None) -> None:
        if not self.base_kv:
            self.add_flag("regulator base_kv unset; voltage undetermined")

    def _emit_kv(self) -> float:
        if self.base_kv and self.nphases == 1:
            return round(self.base_kv / _SQRT3, 5)
        return self.base_kv or 0.0

    def _pt_ratio(self) -> float:
        """Potential-transformer ratio: bus kv (in volts, per the winding
        convention) to the 120 V control base."""
        kv = self._emit_kv()
        return round((kv * 1000.0) / 120.0, 3) if kv else 1.0

    def to_dss(self) -> str:
        n = self.nphases
        bus_in = self.bus(self.parent)
        bus_out = self.bus(self.name)
        kv = self._emit_kv()
        # near-ideal series regulator: 1:1, small reactance, low loss
        xfmr = (
            f"New Transformer.{self.name} phases={n} windings=2 "
            f"buses=[{bus_in}, {bus_out}] "
            f"kvs=[{kv}, {kv}] kvas=[{self.bank_kva}, {self.bank_kva}] "
            f"conns=[wye, wye] xhl=0.1 %loadloss=0.01"
        )
        reg = (
            f"New RegControl.{self.name} transformer={self.name} winding=2 "
            f"vreg={self.vreg} band={self.band} ptratio={self._pt_ratio()}"
        )
        return xfmr + "\n" + reg