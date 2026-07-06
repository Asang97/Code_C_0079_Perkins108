"""
elements/capacitor.py — WindMil capacitor -> OpenDSS `Capacitor`.

A shunt capacitor bank connected at a bus, injecting reactive power (kvar) to
support voltage / correct power factor. Unlike series elements (line, switch),
a capacitor connects to ONE bus (shunt to ground/neutral).

Emits:
    New Capacitor.<name> bus1=<node.phases> phases=<n> kv=<kv> kvar=<kvar>

Phasing from the edge has_phase_* (the bank sits on the line phases). kv is the
line-to-line (3ph) or line-to-neutral (1ph) voltage at the bus, same convention
as elsewhere. Total kvar is split across phases by OpenDSS automatically for a
balanced bank; per-phase kvar handled if the data provides it.

Capacitor CONTROL (switched vs fixed, voltage/time control) is not modeled --
the bank is treated as FIXED (always on), the standard screening assumption.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt

from .base import WindMilElement

_SQRT3 = sqrt(3.0)


@dataclass
class Capacitor(WindMilElement):
    kvar_a: float = 0.0
    kvar_b: float = 0.0
    kvar_c: float = 0.0
    kv_ll: float = 0.0                # bus voltage (line-to-line)
    base_kv: float | None = None      # set from region voltage (like a line)
    dss_type: str = "Capacitor"

    @classmethod
    def from_row(cls, edge: dict, attr: dict, snapshot: str):
        obj = cls(
            name=edge.get("target_node_id") or edge.get("element_name"),
            parent=edge.get("source_node_id"),
            snapshot=snapshot,
            valid_from=edge.get("VALID_FROM"),
            valid_to=edge.get("VALID_TO"),
            has_a=edge.get("has_phase_a"),
            has_b=edge.get("has_phase_b"),
            has_c=edge.get("has_phase_c"),
            kvar_a=float(attr.get("kvar_a") or attr.get("rated_kvar_a") or 0.0),
            kvar_b=float(attr.get("kvar_b") or attr.get("rated_kvar_b") or 0.0),
            kvar_c=float(attr.get("kvar_c") or attr.get("rated_kvar_c") or 0.0),
        )
        total = obj.kvar_a + obj.kvar_b + obj.kvar_c
        if total <= 0:
            obj.add_flag("capacitor kvar missing/zero")
        obj.add_assumption("capacitor modeled as FIXED (always on); control not modeled")
        return obj

    @property
    def total_kvar(self) -> float:
        return self.kvar_a + self.kvar_b + self.kvar_c

    def resolve(self, feeder=None) -> None:
        """kv for the capacitor: the L-L base voltage at its bus (from region)."""
        if self.base_kv:
            self.kv_ll = self.base_kv
        else:
            self.add_flag("capacitor base_kv unset; kv undetermined")

    def _emit_kv(self) -> float:
        """L-L for 3-phase, L-N for 1-phase (same convention as other elements)."""
        if self.kv_ll and self.nphases == 1:
            return round(self.kv_ll / _SQRT3, 5)
        return self.kv_ll

    def to_dss(self) -> str:
        n = self.nphases
        bus1 = self.bus(self.name)
        kv = self._emit_kv()
        return (
            f"New Capacitor.{self.name} "
            f"bus1={bus1} phases={n} "
            f"kv={kv} kvar={round(self.total_kvar, 3)}"
        )