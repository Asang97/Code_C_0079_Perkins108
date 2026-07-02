"""
phasing.py — phase decoding for OpenDSS bus suffixes.

OpenDSS encodes phases as dotted node numbers on bus names:
    node.1.2.3  -> A,B,C    node.1 -> A    node.2 -> B    node.0 -> neutral

PRIMARY PATH (silver): boolean flags has_phase_a/b/c, taken directly.
    -> phase_suffix_from_flags(a, b, c)

FALLBACK SEAM (bronze): WindMil phase_config_code string ("ABC", "A", ...).
    -> phase_suffix(code)
    Kept available for when silver is absent; not used on the silver path.
"""
from __future__ import annotations

_LETTER_TO_INDEX = {"A": 1, "B": 2, "C": 3, "N": 0}


# ---------------------------------------------------------------------------
# PRIMARY: boolean flags (silver)
# ---------------------------------------------------------------------------
def _flag(v) -> bool:
    """Normalize a silver phase flag to bool (handles True/1/'true'/'t'/None)."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "t", "yes", "y")


def phase_suffix_from_flags(a, b, c, n=False) -> str:
    """OpenDSS dotted suffix from boolean phase flags, e.g. '.1.2.3'."""
    nodes = []
    if _flag(a): nodes.append(1)
    if _flag(b): nodes.append(2)
    if _flag(c): nodes.append(3)
    if _flag(n): nodes.append(0)
    return "".join(f".{i}" for i in nodes)


def phase_count_from_flags(a, b, c) -> int:
    """Number of phase conductors (A/B/C) present per the flags."""
    return sum(1 for x in (a, b, c) if _flag(x))


# ---------------------------------------------------------------------------
# FALLBACK SEAM: phase_config_code string (bronze) — kept, not used on silver
# ---------------------------------------------------------------------------
_PHASE_LETTERS_BY_CODE: dict = {}  # only if a code is ever integer/enum


def _letters_from_code(code) -> str:
    if code is None:
        return ""
    s = str(code).strip().upper()
    if s and all(ch in "ABCN" for ch in s):
        return s
    try:
        ival = int(float(s))
    except (ValueError, TypeError):
        return ""
    return _PHASE_LETTERS_BY_CODE.get(ival, "")


def phase_suffix(code) -> str:
    letters = _letters_from_code(code)
    ordered = [L for L in ("A", "B", "C", "N") if L in letters]
    return "".join(f".{_LETTER_TO_INDEX[L]}" for L in ordered)


def phase_count(code) -> int:
    letters = _letters_from_code(code)
    return sum(1 for L in letters if L in ("A", "B", "C"))
