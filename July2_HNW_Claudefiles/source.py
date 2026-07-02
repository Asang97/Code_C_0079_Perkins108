"""
elements/source.py — WindMil substation/source -> OpenDSS `Circuit` (the slack).

The source is the feeder head: it defines the slack bus and the reference
voltage that the voltage-region assignment propagates downstream. Each feeder
is rooted at one source.

Emits the circuit-defining statement (must be FIRST in the .dss):
  New Circuit.<name> bus1=<node> basekv=<kv_LL> phases=3 pu=<setpoint>

Optionally sets a source impedance from the zsm labels; if unavailable, an
ideal (stiff) source is used -- standard and acceptable for distribution
load-flow, recorded as an assumption.

Two silver sources:
  * TOPOLOGY  from `network_edges` (the source node; parent = ROOT).
  * ATTRIBUTES from `network_substations` (nominal voltage, pu setpoint).
Voltage is stored line-to-neutral (like transformers); basekv must be L-L.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt

from .base import WindMilElement

_SQRT3 = sqrt(3.0)

# reuse the same standard L-L nominals used by the transformer (ANSI C84.1)
from .transformer import _STD_KV_LL, _snap_ll


@dataclass
class Source(WindMilElement):
    nominal_raw: float = 0.0          # nominal_voltage (line-to-neutral, as stored)
    pu_setpoint: float = 1.0          # voltage_bus_ratio (per-unit slack setpoint)
    substation_number: object = None  # groups the 212 feeders under 49 substations
    # resolved
    basekv_ll: float = 0.0            # line-to-line base kV for the circuit
    dss_type: str = "Circuit"

    @classmethod
    def from_row(cls, edge: dict, attr: dict, snapshot: str):
        obj = cls(
            name=edge.get("target_node_id") or edge.get("element_name"),
            parent=edge.get("source_node_id"),   # 'ROOT' for a source
            snapshot=snapshot,
            valid_from=edge.get("VALID_FROM"),
            valid_to=edge.get("VALID_TO"),
            nominal_raw=float(attr.get("nominal_voltage") or 0.0),
            pu_setpoint=float(attr.get("voltage_bus_ratio") or 1.0),
            substation_number=attr.get("substation_number"),
        )
        # source phasing: read the real flags; a substation head is normally 3-phase.
        # fall back to 3-phase if the flags are absent (with a note).
        ha, hb, hc = attr.get("has_phase_a"), attr.get("has_phase_b"), attr.get("has_phase_c")
        if ha is None and hb is None and hc is None:
            obj.has_a = obj.has_b = obj.has_c = True
            obj.add_assumption("source phasing not provided; assumed 3-phase")
        else:
            obj.has_a, obj.has_b, obj.has_c = bool(ha), bool(hb), bool(hc)
            if not (obj.has_a and obj.has_b and obj.has_c):
                obj.add_flag(
                    f"source not fully 3-phase (A={obj.has_a} B={obj.has_b} C={obj.has_c})"
                )

        if obj.nominal_raw <= 0:
            obj.add_flag("source nominal_voltage missing/zero; basekv undetermined")
        if not (0.9 <= obj.pu_setpoint <= 1.1):
            obj.add_flag(
                f"source pu setpoint {obj.pu_setpoint} outside typical 0.9-1.1 range"
            )
        obj.add_assumption("ideal (stiff) source: no source impedance modeled "
                           "(zsm labels not resolved)")
        return obj

    def resolve(self, feeder=None) -> None:
        """Determine the line-to-line base kV. Stored nominal is L-N."""
        if self.nominal_raw <= 0:
            self.basekv_ll = 0.0
            return
        # nominal is L-N (e.g. 14.4); imply L-L and snap to standard nominal
        v_ll = self.nominal_raw * _SQRT3
        snapped, did, in_tol = _snap_ll(v_ll)
        if not in_tol:
            self.add_flag(
                f"source voltage {self.nominal_raw} (L-N) -> L-L {v_ll:.4f} "
                f"not near a standard nominal"
            )
        elif did:
            self.add_assumption(
                f"source voltage snapped: L-N {self.nominal_raw} -> L-L {snapped} kV"
            )
        self.basekv_ll = snapped

    def to_dss(self) -> str:
        # The Circuit statement roots the feeder. Must be emitted FIRST.
        return (
            f"New Circuit.{self.name} "
            f"bus1={self.name} "
            f"basekv={self.basekv_ll} "
            f"phases=3 "
            f"pu={self.pu_setpoint}"
        )
