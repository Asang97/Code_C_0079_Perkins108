"""
elements/switch.py — WindMil switches / protective devices -> OpenDSS.

Covers edge_types: electric_switch and overcurrent_device
(reclosers, fuses, sectionalizers -- including the feeder-head reclosers).

In a steady-state load-flow, a CLOSED switch/recloser/fuse is electrically a
zero-impedance connection. OpenDSS models this as a Line with switch=yes (a
short, effectively-zero-impedance link that OpenDSS treats as a switch). An
OPEN device breaks the circuit (the downstream subtree is de-energized).

So this element emits:
    New Line.<name> bus1=<parent> bus2=<self> phases=<n> switch=yes  [enabled=no if open]

The device's protective FUNCTION (trip curves, coordination) is irrelevant to
steady-state power flow, so only its OPEN/CLOSED state matters here.

Phasing comes from the edge has_phase_* booleans (the device sits on the line
phases, unlike a transformer/consumer whose phasing is device-specific).
"""
from __future__ import annotations
from dataclasses import dataclass

from .base import WindMilElement

# device kinds we represent as switches
SWITCH_KINDS = ("electric_switch", "recloser", "fuse", "sectionalizer",
                "overcurrent_device")


@dataclass
class Switch(WindMilElement):
    kind: str = "electric_switch"     # electric_switch / recloser / fuse / ...
    is_closed: bool = True            # base-case state (closed = passthrough)
    dss_type: str = "Line"            # emitted as a switched Line

    @classmethod
    def from_row(cls, edge: dict, attr: dict | None, snapshot: str):
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
        # kind: prefer an explicit attr, else infer from edge_type / flags
        etype = (edge.get("edge_type") or "").strip().lower()
        if edge.get("is_recloser") or "rclsr" in (obj.name or "").lower():
            obj.kind = "recloser"
        elif edge.get("is_fuse"):
            obj.kind = "fuse"
        elif etype == "overcurrent_device":
            obj.kind = "overcurrent_device"
        else:
            obj.kind = "electric_switch"

        # state: default closed. WindMil status is often null -> assume closed
        # (radial base case). An explicit open/closed status overrides.
        status = attr.get("status")
        if status is not None:
            obj.is_closed = str(status).strip().lower() in ("closed", "c", "1", "true")
        else:
            obj.add_assumption("switch status not provided; assumed CLOSED (radial base case)")

        if edge.get("is_feeder"):
            obj.add_assumption("feeder-head recloser (connects feeder to substation slack)")
        return obj

    def to_dss(self) -> str:
        n = self.nphases
        bus1 = self.bus(self.parent)
        bus2 = self.bus(self.name)
        stmt = (
            f"New Line.{self.name} "
            f"bus1={bus1} bus2={bus2} "
            f"phases={n} switch=yes"
        )
        if not self.is_closed:
            # open device: emit but disable so the downstream subtree de-energizes
            stmt += " enabled=no"
        return stmt