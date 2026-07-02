"""
libraries/linecode.py — shared LineCode naming + (later) the dedup registry
and impedance definitions.

For now this provides ONLY the name-derivation helper, so elements can
reference a linecode by name and the (future) library will define it under
the same name — single source of truth, no drift.

The conductor KEY is the per-phase tuple (cond_a, cond_b, cond_c):
  - uniform line  -> all equal -> name from the single conductor
  - mixed line    -> distinct  -> a composite name (asymmetric/matrix linecode)
  - missing       -> 'UNKNOWN'
"""
from __future__ import annotations


def _sanitize(label: str) -> str:
    return (label or "UNKNOWN").replace(" ", "_").replace("/", "-").replace("#", "N")


def linecode_name_for(conductor_key: tuple) -> str:
    """Derive a stable LineCode name from a per-phase conductor tuple.

    conductor_key = (cond_a, cond_b, cond_c), any may be None.
    """
    present = [c for c in conductor_key if c]
    distinct = list(dict.fromkeys(present))
    if not distinct:
        return "UNKNOWN"
    if len(distinct) == 1:
        return _sanitize(distinct[0])
    # mixed -> composite name encoding the per-phase set (asymmetric line)
    return "MIX__" + "__".join(_sanitize(c) for c in distinct)


# ===================================================================== #
# LineCodeLibrary — collect used (type, voltage) buckets, emit LineCodes
# ===================================================================== #
from . import impedance_data as _imp


class LineCodeLibrary:
    """Collects the distinct linecode buckets actually used by lines and emits
    one `New LineCode...` per bucket. First-pass: buckets are (line_type,
    voltage_class); impedance is per-mile sequence values from impedance_data.

    Usage (AFTER the voltage trace has set base_kv on lines):
        lib = LineCodeLibrary()
        for ln in feeder.lines:
            lib.register(ln)          # records the bucket this line needs
        header = lib.to_dss()         # emit LineCodes BEFORE the lines
    """

    def __init__(self):
        # bucket_name -> (nphases, (R1,X1,R0,X0), vclass, was_fallback)
        self._codes: dict = {}
        self.assumptions: list[str] = []
        self.flags: list[str] = []

    def register(self, line) -> str:
        """Register the bucket a line needs; return the linecode name to reference.
        `line` must have .line_type, .base_kv, .nphases."""
        name = _imp.bucket_name(line.line_type, line.base_kv)
        if name not in self._codes:
            zseq, vclass, fallback = _imp.lookup(line.line_type, line.base_kv)
            # nphases for the linecode: use 3 (symmetric sequence works for 1/2/3-ph
            # lines referencing it; OpenDSS applies sequence Z regardless of phases).
            self._codes[name] = (3, zseq, vclass, fallback)
            self.assumptions.append(
                f"LineCode {name}: impedance estimated by ({line.line_type}, "
                f"{vclass}) bucket [per-mile seq], NOT by conductor; small-lateral "
                f"voltage drop under-estimated"
            )
            if fallback:
                self.flags.append(
                    f"LineCode {name}: no bucket match; used generic fallback impedance"
                )
        return name

    def to_dss(self) -> str:
        """Emit all registered LineCodes. Place this BEFORE any New Line."""
        lines = ["! --- LineCodes (per-mile sequence impedance; (type,voltage) buckets) ---"]
        for name, (nph, (r1, x1, r0, x0), vclass, _) in sorted(self._codes.items()):
            lines.append(
                f"New LineCode.{name} nphases={nph} "
                f"R1={r1} X1={x1} R0={r0} X0={x0} units=mi"
            )
        return "\n".join(lines)

    def __len__(self):
        return len(self._codes)
