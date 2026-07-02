"""
elements/overhead_line.py — overhead line section -> OpenDSS `Line`.

Emits:
  New Line.<name> bus1=<parent>.<ph> bus2=<self>.<ph>
      phases=<n> linecode=<code> length=<len> units=ft

The element is a faithful DATA CARRIER. It holds the per-phase conductors
(cond_a/b/c), the neutral conductor, and the lengths. It does NOT decide the
impedance representation (symmetric vs asymmetric/matrix) — that is the
LineCodeLibrary's job, which reads the per-phase conductors via
`conductor_key()` and emits the appropriate LineCode. The element only needs
the linecode NAME to reference, derived from the same key (shared helper, so
reference and definition can't drift).

Lengths:
  impedance_length_ft         -> operative `length=` (phase run).
  neutral_impedance_length_ft -> stored, not used in sequence-impedance emit;
                                 flagged when it differs materially.
  Precedence: prefer phase length; fall back to neutral length if phase missing.
"""
from __future__ import annotations
from dataclasses import dataclass

from .base import WindMilElement
from ..libraries.linecode import linecode_name_for   # shared name derivation


@dataclass
class OverheadLine(WindMilElement):
    # per-phase + neutral conductors (the truth; library decides impedance)
    cond_a: str | None = None
    cond_b: str | None = None
    cond_c: str | None = None
    neutral: str | None = None
    # lengths
    length_ft: float = 0.0
    neutral_length_ft: float = 0.0
    dss_type: str = "Line"

    @classmethod
    def from_row(cls, row: dict, snapshot: str):
        cond_a = row.get("conductor_eqdb_label_a")
        cond_b = row.get("conductor_eqdb_label_b")
        cond_c = row.get("conductor_eqdb_label_c")
        neutral = row.get("conductor_eqdb_label_neutral")

        phase_len = row.get("impedance_length_ft")
        neut_len = row.get("neutral_impedance_length_ft")
        phase_len = float(phase_len) if phase_len not in (None, "") else None
        neut_len = float(neut_len) if neut_len not in (None, "") else None

        obj = cls(
            snapshot=snapshot,
            **cls._identity_from_silver(row),     # name, parent, has_a/b/c, phase_code
            cond_a=cond_a, cond_b=cond_b, cond_c=cond_c, neutral=neutral,
            neutral_length_ft=(neut_len or 0.0),
        )

        # ---- section length (precedence: phase, then neutral) ----
        if phase_len and phase_len > 0:
            obj.length_ft = phase_len
        elif neut_len and neut_len > 0:
            obj.length_ft = neut_len
            obj.flag("impedance_length_ft missing; fell back to neutral length")
        else:
            obj.length_ft = 0.0
            obj.flag("no usable length (phase and neutral both missing/zero)")

        if neut_len and phase_len and abs(phase_len - neut_len) > 1.0:
            obj.flag(
                f"phase length {phase_len} != neutral length {neut_len}; "
                f"neutral modeled implicitly (zero-seq), separate length not applied"
            )

        # ---- conductor provenance (selection deferred to LineCodeLibrary) ----
        present = [c for c in (cond_a, cond_b, cond_c) if c]
        distinct = list(dict.fromkeys(present))
        if len(distinct) == 0:
            obj.flag("no conductor label on any phase; line has no impedance reference")
        elif len(distinct) == 1:
            obj.assume(
                f"impedance standard-substituted from conductor '{distinct[0]}' "
                f"(uniform across present phases; no utility eqdb)"
            )
        else:
            obj.flag(
                f"mixed conductors across phases {distinct}; "
                f"LineCodeLibrary will decide symmetric-approx vs matrix"
            )
        if neutral:
            obj.assume(
                f"neutral conductor '{neutral}' modeled implicitly via standard "
                f"zero-sequence (not a separate conductor)"
            )
        return obj

    def conductor_key(self) -> tuple:
        """Per-phase conductor tuple the LineCodeLibrary keys on.
        Uniform lines collapse to one distinct value; mixed keep all three."""
        return (self.cond_a, self.cond_b, self.cond_c)

    def linecode_name(self) -> str:
        """Name to reference; derived from the per-phase key via shared helper."""
        return linecode_name_for(self.conductor_key())

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
