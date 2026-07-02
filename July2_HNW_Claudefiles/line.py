"""
elements/line.py — unified line section (overhead + underground) -> OpenDSS `Line`.

Two silver sources (per the agreed rule):
  * TOPOLOGY  comes from a `network_edges` row  -> bus1 (source_node_id),
              bus2 (target_node_id == element_name).
  * ATTRIBUTES come from a `network_lines` row  -> line_type, per-phase
              conductors, neutral, lengths, coordinates.

Overhead vs underground is the SAME class, branched on `line_type`:
  * overhead   -> bare conductors; impedance keyed on phase conductors.
  * underground-> cable assembly (Triplex/URD/etc); impedance is intrinsic to
                  the cable type. (The LineCodeLibrary decides the actual
                  impedance; here we only carry the facts and reference a
                  linecode name.)

Phasing for lines is derived from CONDUCTOR PRESENCE, not from has_phase_*:
  a phase exists on the section iff it has a conductor. (network_lines
  has_phase_* is null; the conductor columns are the physical truth.)
  The edge's has_phase_* booleans, if present, are used only as a CROSS-CHECK.

Emits:
  New Line.<name> bus1=<src>.<ph> bus2=<self>.<ph>
      phases=<n> linecode=<code> length=<len> units=ft
"""
from __future__ import annotations
from dataclasses import dataclass

from .base import WindMilElement
from ..phasing import _flag
from ..libraries.linecode import linecode_name_for


@dataclass
class Line(WindMilElement):
    # --- attribute fields (from network_lines) ---
    line_type: str | None = None          # 'overhead' | 'underground'
    cond_a: str | None = None
    cond_b: str | None = None
    cond_c: str | None = None
    neutral: str | None = None
    length_ft: float = 0.0
    neutral_length_ft: float = 0.0
    lat: float | None = None
    lon: float | None = None

    dss_type: str = "Line"

    # ------------------------------------------------------------------ #
    # CONSTRUCT — topology from `edge`, attributes from `attr`
    # ------------------------------------------------------------------ #
    @classmethod
    def from_row(cls, edge: dict, attr: dict, snapshot: str):
        cond_a = attr.get("conductor_eqdb_label_a")
        cond_b = attr.get("conductor_eqdb_label_b")
        cond_c = attr.get("conductor_eqdb_label_c")
        neutral = attr.get("conductor_eqdb_label_neutral")

        phase_len = attr.get("impedance_length_ft")
        neut_len = attr.get("neutral_impedance_length_ft")
        phase_len = float(phase_len) if phase_len not in (None, "") else None
        neut_len = float(neut_len) if neut_len not in (None, "") else None

        obj = cls(
            # identity + connectivity FROM THE EDGE
            name=edge.get("target_node_id") or edge.get("element_name"),
            parent=edge.get("source_node_id"),
            snapshot=snapshot,
            # temporal validity FROM THE EDGE (topology/temporal authority)
            valid_from=edge.get("VALID_FROM"),
            valid_to=edge.get("VALID_TO"),
            # phasing booleans derived from CONDUCTOR PRESENCE (below)
            line_type=(attr.get("line_type") or "").strip().lower() or None,
            cond_a=cond_a, cond_b=cond_b, cond_c=cond_c, neutral=neutral,
            neutral_length_ft=(neut_len or 0.0),
            lat=attr.get("latitude"), lon=attr.get("longitude"),
        )

        # ---- cross-check edge vs attr validity (both should align) ----
        a_from, a_to = attr.get("VALID_FROM"), attr.get("VALID_TO")
        if (a_from is not None or a_to is not None) and (
            a_from != obj.valid_from or a_to != obj.valid_to
        ):
            obj.add_flag(
                f"validity mismatch: edge [{obj.valid_from}..{obj.valid_to}] "
                f"vs lines [{a_from}..{a_to}]"
            )

        # ---- phasing from conductor presence ----
        obj.has_a = cond_a is not None
        obj.has_b = cond_b is not None
        obj.has_c = cond_c is not None
        if not (obj.has_a or obj.has_b or obj.has_c):
            obj.add_flag("no conductor on any phase; line has no phasing or impedance")

        # ---- cross-check against edge booleans, if the edge carried them ----
        cls._cross_check_phases(obj, edge)

        # ---- section length (precedence: phase, then neutral) ----
        if phase_len and phase_len > 0:
            obj.length_ft = phase_len
        elif neut_len and neut_len > 0:
            obj.length_ft = neut_len
            obj.add_flag("impedance_length_ft missing; fell back to neutral length")
        else:
            obj.length_ft = 0.0
            obj.add_flag("no usable length (phase and neutral both missing/zero)")
        if neut_len and phase_len and abs(phase_len - neut_len) > 1.0:
            obj.add_flag(
                f"phase length {phase_len} != neutral length {neut_len}; "
                f"neutral modeled implicitly (zero-seq), separate length not applied"
            )

        # ---- conductor / impedance provenance, branched on line_type ----
        present = [c for c in (cond_a, cond_b, cond_c) if c]
        distinct = list(dict.fromkeys(present))
        kind = obj.line_type or "unknown"
        if len(distinct) == 1:
            obj.add_assumption(
                f"{kind} line: impedance standard-substituted from '{distinct[0]}' "
                f"(uniform across present phases; no utility eqdb)"
            )
        elif len(distinct) > 1:
            obj.add_flag(
                f"{kind} line: mixed conductors across phases {distinct}; "
                f"LineCodeLibrary will decide symmetric-approx vs matrix"
            )
        if obj.line_type == "underground" and neutral:
            obj.add_assumption(
                f"underground cable neutral '{neutral}': concentric/return modeled "
                f"implicitly via cable linecode (not a separate conductor)"
            )
        elif neutral:
            obj.add_assumption(
                f"neutral conductor '{neutral}' modeled implicitly via standard "
                f"zero-sequence (not a separate conductor)"
            )
        return obj

    @staticmethod
    def _cross_check_phases(obj: "Line", edge: dict) -> None:
        """If the edge row carries has_phase_*, flag any disagreement with the
        conductor-derived phasing. Edge booleans are NOT authoritative for lines."""
        ea, eb, ec = edge.get("has_phase_a"), edge.get("has_phase_b"), edge.get("has_phase_c")
        if ea is None and eb is None and ec is None:
            return  # edge didn't carry booleans; nothing to check
        for ph, edge_val, cond_val in (
            ("A", ea, obj.has_a), ("B", eb, obj.has_b), ("C", ec, obj.has_c)
        ):
            if edge_val is None:
                continue
            if _flag(edge_val) != bool(cond_val):
                obj.add_flag(
                    f"phase {ph} mismatch: edge says {bool(_flag(edge_val))}, "
                    f"conductor presence says {bool(cond_val)} (used conductor)"
                )

    # ------------------------------------------------------------------ #
    # impedance reference
    # ------------------------------------------------------------------ #
    def conductor_key(self) -> tuple:
        """Per-phase conductor tuple — retained for the future conductor-keyed
        impedance upgrade; not used by the first-pass bucket library."""
        return (self.cond_a, self.cond_b, self.cond_c)

    def linecode_name(self) -> str:
        """First-pass: linecode is the (line_type, voltage-class) bucket.
        Requires base_kv to be set (by the voltage trace) before emit."""
        from ..libraries.impedance_data import bucket_name
        return bucket_name(self.line_type, self.base_kv)

    # ------------------------------------------------------------------ #
    # EMIT
    # ------------------------------------------------------------------ #
    def to_dss(self) -> str:
        bus1 = self.bus(self.parent)
        bus2 = self.bus(self.name)
        return (
            f"New Line.{self.name} "
            f"bus1={bus1} bus2={bus2} "
            f"phases={self.nphases} "
            f"linecode={self.linecode_name()} "
            f"length={self.length_ft} units=ft"
        )
