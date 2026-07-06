"""
elements/transformer.py — WindMil step transformer -> OpenDSS `Transformer`.

Two-winding only (tertiary confirmed dead for this dataset).

Two silver sources:
  * TOPOLOGY  from a `network_edges` row -> HV bus (source_node_id),
              LV bus (target_node_id == element_name).
  * ATTRIBUTES from `network_transformers` (rated voltages, per-phase kVA) and
    silver.network_transformers (has_phase_a/b/c, kVA, voltages).

PHASING — from network_transformers.has_phase_a/b/c (device phasing):
  * TRANSFORMER_PHASE = the LINE phasing at the node (e.g. 'ABC'). Context only.
  * USAGE_POINT_PHASE = the phases the transformer actually CONNECTS to
                        (e.g. 'A', 'AB', 'ABC'). THIS drives the device model.
  The transformer's nphases, bus suffix, and kv form all come from
  USAGE_POINT_PHASE. TRANSFORMER_PHASE is kept for a subset-validation check.

OpenDSS `kv` convention depends on the CONNECTION, which the usage-point phase
COUNT reveals (data stored line-to-neutral):
  * 1 phase  (e.g. 'A')  -> line-to-NEUTRAL connection  -> kv = L-N value
  * 2 phases (e.g. 'AB') -> line-to-LINE connection      -> kv = L-L value
  * 3 phases ('ABC')     -> three-phase wye              -> kv = L-L value
So a single-phase transformer connected across A-B ('AB') uses L-L kv and bus
suffix '.1.2' — NOT L-N. Both kv forms are stored; the connection picks one.

Substituted (flagged): impedance by kVA (no %Z), connection wye-wye
(winding_code decode pending), voltage snapped to nearest nominal.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt

from .base import WindMilElement
from ..phasing import phase_suffix, phase_count   # string-based (letter) decoders


_SQRT3 = sqrt(3.0)

# Standard nominal LINE-TO-LINE system voltages (kV) per ANSI C84.1, Table 1.
# Low + medium voltage distribution classes. (L-N values like 0.12/0.277/7.2
# are NOT here — they are derived as L-L/√3 when needed.)
_STD_KV_LL = [
    0.208, 0.240, 0.480, 0.600,                 # low voltage
    2.40, 4.16, 4.80, 6.90, 8.32,               # medium voltage
    12.00, 12.47, 13.20, 13.80,
    20.78, 22.86, 23.00, 24.94, 34.50,
]
_SNAP_TOL = 0.10


def _snap_ll(v_ll: float):
    """Snap a line-to-line kV to nearest standard nominal. -> (kv, snapped, in_tol)."""
    if not v_ll or v_ll <= 0:
        return v_ll, False, False
    nearest = min(_STD_KV_LL, key=lambda s: abs(s - v_ll))
    in_tol = abs(nearest - v_ll) / nearest <= _SNAP_TOL
    return (nearest if in_tol else v_ll), (nearest != v_ll), in_tol


def std_impedance(kva: float):
    """Typical (%R, %X) for a distribution transformer of this kVA (screening)."""
    if kva <= 0:    return 1.0, 2.0
    if kva < 50:    return 1.4, 1.6
    if kva < 167:   return 1.1, 1.8
    if kva < 500:   return 1.0, 2.3
    return 0.8, 5.5


@dataclass
class Transformer(WindMilElement):
    # attributes (from network_transformers)
    hv_raw: float = 0.0          # rated_voltage_srcside
    lv_raw: float = 0.0          # rated_voltage_loadside
    kva_a: float = 0.0
    kva_b: float = 0.0
    kva_c: float = 0.0
    # phasing (from semantic.grid_location)
    transformer_phase: str = ""  # LINE phasing at node (context/validation)
    usage_point_phase: str = ""  # phases the device CONNECTS to (drives model)
    # resolved: BOTH forms per winding
    hv_kv_ln: float = 0.0
    hv_kv_ll: float = 0.0
    lv_kv_ln: float = 0.0
    lv_kv_ll: float = 0.0
    kva: float = 0.0             # bank rating (sum of present phases)
    dss_type: str = "Transformer"

    @classmethod
    def from_row(cls, edge: dict, attr: dict, snapshot: str):
        kva_a = float(attr.get("capacity_kva_a") or 0.0)
        kva_b = float(attr.get("capacity_kva_b") or 0.0)
        kva_c = float(attr.get("capacity_kva_c") or 0.0)

        # PHASING now comes from network_transformers.has_phase_a/b/c (booleans).
        # (Optional legacy string TRANSFORMER_PHASE/USAGE_POINT_PHASE still honored
        #  if present, e.g. synthetic tests.)
        def _flag(v):
            if v is None:
                return None
            return str(v).strip().lower() in ("1", "true", "t", "yes", "y")

        ha = _flag(attr.get("has_phase_a"))
        hb = _flag(attr.get("has_phase_b"))
        hc = _flag(attr.get("has_phase_c"))
        up_str = (attr.get("USAGE_POINT_PHASE") or "").strip().upper()
        tx_str = (attr.get("TRANSFORMER_PHASE") or "").strip().upper()

        # resolve device phasing: prefer booleans; else the string; else kVA presence
        if ha is not None or hb is not None or hc is not None:
            has_a, has_b, has_c = bool(ha), bool(hb), bool(hc)
        elif up_str:
            has_a, has_b, has_c = ("A" in up_str), ("B" in up_str), ("C" in up_str)
        else:
            has_a, has_b, has_c = (kva_a > 0), (kva_b > 0), (kva_c > 0)

        up_phase = "".join(p for p, h in zip("ABC", (has_a, has_b, has_c)) if h)

        obj = cls(
            name=edge.get("target_node_id") or edge.get("element_name"),
            parent=edge.get("source_node_id"),
            snapshot=snapshot,
            valid_from=edge.get("VALID_FROM"),
            valid_to=edge.get("VALID_TO"),
            hv_raw=float(attr.get("rated_voltage_srcside") or 0.0),
            lv_raw=float(attr.get("rated_voltage_loadside") or 0.0),
            kva_a=kva_a, kva_b=kva_b, kva_c=kva_c,
            transformer_phase=tx_str,
            usage_point_phase=up_phase,
        )
        obj.kva = kva_a + kva_b + kva_c

        # DEVICE phasing drives nphases, bus suffix, and the kv-form decision.
        obj.phase_code = up_phase
        obj.has_a, obj.has_b, obj.has_c = has_a, has_b, has_c

        # validation: device phases should match where the kVA is
        kva_phases = "".join(p for p, k in zip("ABC", (kva_a, kva_b, kva_c)) if k > 0)
        if up_phase and kva_phases and set(up_phase) != set(kva_phases):
            obj.add_flag(
                f"phasing '{up_phase}' != kVA-present phases '{kva_phases}'"
            )
        if not up_phase:
            obj.add_flag("transformer phasing undetermined (no has_phase_*, string, or kVA)")

        obj.add_assumption("transformer impedance standard-substituted by kVA (no %Z in data)")
        obj.add_assumption("winding connection assumed wye-wye (winding_code decode pending)")
        return obj

    def resolve(self, feeder=None) -> None:
        """Snap each winding's voltage to a standard nominal and store BOTH
        line-to-neutral and line-to-line forms. The OpenDSS-specific choice
        (which form to pass) is deferred to to_dss()."""
        self.hv_kv_ll, self.hv_kv_ln = self._winding_kv(self.hv_raw, side="HV")
        self.lv_kv_ll, self.lv_kv_ln = self._winding_kv(self.lv_raw, side="LV")

    def _winding_kv(self, v_raw: float, side: str):
        """Resolve a winding's stored L-N value to (kv_ll, kv_ln), both snapped
        and consistent (ll = ln*√3). Stored data is line-to-neutral."""
        if v_raw <= 0:
            self.add_flag(f"{side} voltage missing/zero")
            return 0.0, 0.0
        # data is L-N; the implied system L-L is v_raw*√3. Snap on the L-L.
        v_ll = v_raw * _SQRT3
        snapped_ll, did, in_tol = _snap_ll(v_ll)
        if not in_tol:
            self.add_flag(
                f"{side} voltage {v_raw} (L-N) -> implied L-L {v_ll:.4f} "
                f"not near a standard nominal"
            )
        elif did:
            self.add_assumption(
                f"{side} voltage snapped: L-N {v_raw} -> L-L {snapped_ll} kV"
            )
        kv_ll = snapped_ll
        kv_ln = round(snapped_ll / _SQRT3, 5)
        return kv_ll, kv_ln

    def _connection_is_line_to_line(self) -> bool:
        """True if the transformer's connection uses line-to-line voltage.
        Driven by USAGE_POINT_PHASE count:
          1 phase  -> line-to-NEUTRAL  (False)
          2 phases -> line-to-LINE     (True)  e.g. 'AB' across A-B
          3 phases -> three-phase wye, L-L kv (True)
        """
        n = self.nphases
        return n >= 2

    def _emit_kv(self, kv_ln: float, kv_ll: float) -> float:
        """Pick the kv form the OpenDSS connection expects.
        L-N for a 1-phase (line-to-neutral) winding; L-L for 2-phase
        (line-to-line) and 3-phase wye windings."""
        return kv_ll if self._connection_is_line_to_line() else kv_ln

    def secondary_kv(self) -> float:
        """LV (load-side) voltage the region SQL propagates downstream.
        Returned as LINE-TO-LINE (the system voltage of the downstream region)."""
        return self.lv_kv_ll

    def _primary_conn(self) -> str:
        """Primary winding connection.
        Per OpenDSS official single-phase modeling docs, a transformer connected
        across TWO phases (line-to-line, e.g. USAGE_POINT='AB') uses conn=delta
        on the primary (bus .1.2, L-L kv). 1-phase (L-N) and 3-phase use wye
        here (3-phase wye/delta refinement would come from winding_code).
        """
        return "delta" if self.nphases == 2 else "wye"

    def to_dss(self) -> str:
        pct_r, pct_x = std_impedance(self.kva)
        # OpenDSS `phases`: a 2-phase line-to-line transformer is a single-phase
        # device across two nodes -> phases=1 but bus suffix '.1.2'.
        up_n = self.nphases
        dss_phases = 1 if up_n <= 2 else 3
        bus_hv = self.bus(self.parent)   # suffix from usage_point_phase via phase_code
        bus_lv = self.bus(self.name)
        hv = self._emit_kv(self.hv_kv_ln, self.hv_kv_ll)
        lv = self._emit_kv(self.lv_kv_ln, self.lv_kv_ll)
        primary_conn = self._primary_conn()
        return (
            f"New Transformer.{self.name} phases={dss_phases} windings=2 "
            f"buses=[{bus_hv}, {bus_lv}] "
            f"kvs=[{hv}, {lv}] "
            f"kvas=[{self.kva}, {self.kva}] "
            f"conns=[{primary_conn}, wye] "
            f"xhl={pct_x} %loadloss={pct_r}"
        )
