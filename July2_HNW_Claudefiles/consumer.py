"""
elements/consumer.py — WindMil consumer -> OpenDSS `Load`(s).

Consumers are metered service points (usage points). Load values come from AMI
meter data (netsense_reading x readingdefinition), supplied by the query layer
-- this class does NOT query meters. It carries per-phase kW/kVAR for THREE
selectable scenarios and emits the chosen one.

DESIGN (mirrors the transformer's "carry all forms, decide at emit"):
  * three scenarios carried: "coincident" (feeder-peak), "max" (customer max
    demand), "average" (from kWh consumption). Emit picks one via `scenario`.
  * PER-PHASE values (kw_a/b/c, kvar_a/b/c per scenario) to match the unbalanced
    network. Emitted as SEPARATE single-phase Loads per energized phase --
    the OpenDSS-correct way to represent unbalanced load.
  * phasing from USAGE_POINT_PHASE (like the transformer).
  * constant-PQ model (model=1), the screening standard.

Serving voltage (kv) is the L-N secondary voltage of the upstream transformer,
supplied to the consumer (like a line's base_kv).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt

from .base import WindMilElement

_SQRT3 = sqrt(3.0)

SCENARIOS = ("coincident", "max", "average")
_PHASE_NODE = {"A": "1", "B": "2", "C": "3"}


def _empty_scenario_map() -> dict:
    return {s: {"A": 0.0, "B": 0.0, "C": 0.0} for s in SCENARIOS}


@dataclass
class Consumer(WindMilElement):
    # per-scenario, per-phase load  {scenario: {"A":kw, "B":kw, "C":kw}}
    kw: dict = field(default_factory=_empty_scenario_map)
    kvar: dict = field(default_factory=_empty_scenario_map)
    scenario: str = "coincident"        # which scenario to emit
    serving_kv_ln: float = 0.0          # L-N serving voltage (transformer secondary)
    usage_point_phase: str = ""
    load_model: int = 1                 # constant PQ
    dss_type: str = "Load"

    @classmethod
    def from_row(cls, edge: dict, attr: dict, snapshot: str, scenario: str = "coincident"):
        up_phase = (attr.get("USAGE_POINT_PHASE") or "").strip().upper()

        obj = cls(
            name=edge.get("target_node_id") or edge.get("element_name"),
            parent=edge.get("source_node_id"),
            snapshot=snapshot,
            valid_from=edge.get("VALID_FROM"),
            valid_to=edge.get("VALID_TO"),
            usage_point_phase=up_phase,
            scenario=scenario if scenario in SCENARIOS else "coincident",
            serving_kv_ln=float(attr.get("serving_kv_ln") or 0.0),
        )
        # phasing from usage point (drives which phases get a Load)
        obj.phase_code = up_phase
        obj.has_a = "A" in up_phase
        obj.has_b = "B" in up_phase
        obj.has_c = "C" in up_phase

        # load values: attr provides per-scenario per-phase kW/kVAR.
        # expected keys like  kw_coincident_a, kvar_max_b, ...
        got_any = False
        for s in SCENARIOS:
            for ph in "ABC":
                kw = attr.get(f"kw_{s}_{ph.lower()}")
                kvar = attr.get(f"kvar_{s}_{ph.lower()}")
                if kw is not None:
                    obj.kw[s][ph] = float(kw); got_any = True
                if kvar is not None:
                    obj.kvar[s][ph] = float(kvar)

        if not got_any:
            obj.add_flag("no meter load values supplied; consumer has zero load")
        if obj.serving_kv_ln <= 0:
            obj.add_flag("serving voltage (kv) not set; load kv undetermined")
        if not up_phase:
            obj.add_flag("USAGE_POINT_PHASE missing; consumer phasing undetermined")

        obj.add_assumption(f"load scenario = {obj.scenario}")
        obj.add_assumption("constant-PQ load model (model=1)")
        return obj

    def set_scenario(self, scenario: str) -> None:
        if scenario in SCENARIOS:
            self.scenario = scenario

    def _phases_with_load(self):
        """Yield (phase_letter, node_suffix, kw, kvar) for each energized phase
        that has nonzero load in the selected scenario."""
        s = self.scenario
        for ph in "ABC":
            if not getattr(self, f"has_{ph.lower()}"):
                continue
            kw = self.kw[s].get(ph, 0.0)
            kvar = self.kvar[s].get(ph, 0.0)
            if kw == 0.0 and kvar == 0.0:
                continue
            yield ph, _PHASE_NODE[ph], kw, kvar

    def to_dss(self) -> str:
        """Emit one single-phase Load per energized phase (unbalanced-correct)."""
        stmts = []
        for ph, node, kw, kvar in self._phases_with_load():
            stmts.append(
                f"New Load.{self.name}_{ph} "
                f"bus1={self.name}.{node} "
                f"phases=1 "
                f"kv={round(self.serving_kv_ln, 5)} "
                f"kw={kw} kvar={kvar} "
                f"model={self.load_model} conn=wye"
            )
        if not stmts:
            return f"! Load.{self.name}: no nonzero load in scenario '{self.scenario}'"
        return "\n".join(stmts)

    def total_kw(self, scenario: str | None = None) -> float:
        s = scenario or self.scenario
        return sum(self.kw[s].values())