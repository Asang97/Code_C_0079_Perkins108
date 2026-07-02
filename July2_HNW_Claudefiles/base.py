"""
elements/base.py — shared spine for every WindMil element.

Phases (construct→resolve→emit contract unchanged):
  PRIMARY (silver): boolean flags has_a/has_b/has_c drive bus()/nphases.
  FALLBACK SEAM (bronze): phase_code string, used only if flags are absent.

Connectivity (silver): source_node_id -> parent (bus1),
                       target_node_id -> name/element_name (bus2).
The loader normalizes silver's node columns to `parent`/`name`, so elements
see the same canonical fields regardless of source.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..phasing import (
    phase_suffix_from_flags, phase_count_from_flags,   # primary (silver)
    phase_suffix, phase_count,                          # fallback (bronze)
)


@dataclass
class WindMilElement:
    # --- identity (canonical; loader maps silver node cols into these) ---
    name: str                         # = target_node_id (silver) / element_name (bronze)
    parent: str                       # = source_node_id (silver) / parent_element_name (bronze)
    snapshot: str                     # discrete snapshot label

    # --- temporal validity (silver interval; should align with `snapshot`) ---
    valid_from: object = None         # VALID_FROM
    valid_to: object = None           # VALID_TO (None = open-ended / current)

    # --- phasing: silver booleans (primary) ---
    has_a: bool = False
    has_b: bool = False
    has_c: bool = False
    # --- phasing: bronze string (fallback seam; None on silver path) ---
    phase_code: object = None

    # --- resolved-later state ---
    base_kv: float | None = None
    feeder_root: str | None = None

    # --- provenance ---
    assumptions: list[str] = field(default_factory=list)
    flag: list[str] = field(default_factory=list)

    dss_type: str = "Element"

    # ---------- CONSTRUCT ----------
    @classmethod
    def from_row(cls, row: dict, snapshot: str):
        raise NotImplementedError

    # ---------- phasing helpers ----------
    def _phase_suffix(self) -> str:
        # primary: booleans
        suf = phase_suffix_from_flags(self.has_a, self.has_b, self.has_c)
        if suf:
            return suf
        # fallback: string code (bronze)
        suf = phase_suffix(self.phase_code)
        if suf:
            return suf
        # neither resolved -> flag, default 3-phase so it still builds
        self.add_flag(
            f"no phase info (flags all false, phase_code={self.phase_code!r}); "
            f"defaulted .1.2.3"
        )
        return ".1.2.3"

    def bus(self, node: str) -> str:
        return f"{node}{self._phase_suffix()}"

    @property
    def nphases(self) -> int:
        n = phase_count_from_flags(self.has_a, self.has_b, self.has_c)
        if n:
            return n
        n = phase_count(self.phase_code)
        return n if n else 3

    # ---------- RESOLVE ----------
    def resolve(self, feeder) -> None:
        return

    # ---------- EMIT ----------
    def to_dss(self) -> str:
        raise NotImplementedError

    # ---------- provenance helpers ----------
    def add_assumption(self, msg: str) -> None:
        self.assumptions.append(msg)

    def add_flag(self, msg: str) -> None:
        self.flag.append(msg)

    # ---------- shared constructor helper for silver rows ----------
    @staticmethod
    def _identity_from_silver(row: dict) -> dict:
        """Map silver edge columns -> canonical identity+phase+validity kwargs."""
        return dict(
            name=row.get("target_node_id") or row.get("element_name"),
            parent=row.get("source_node_id") or row.get("parent_element_name"),
            has_a=row.get("has_phase_a"),
            has_b=row.get("has_phase_b"),
            has_c=row.get("has_phase_c"),
            phase_code=row.get("phase_config_code"),  # present only on bronze fallback
            valid_from=row.get("VALID_FROM"),
            valid_to=row.get("VALID_TO"),
        )
