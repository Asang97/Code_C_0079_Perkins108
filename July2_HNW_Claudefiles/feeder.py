"""
feeder.py — the Feeder orchestrator.

Assembles ONE feeder (rooted at its substation slack) into a complete,
ordered OpenDSS .dss. Pure assembly: it takes ALREADY-LOADED data (plain
dicts/lists) and produces text. It holds NO database connection and runs NO
SQL -- a separate query layer feeds it. This keeps the Feeder testable with
synthetic data and database-agnostic.

Responsibilities (the construct -> resolve -> register -> emit pipeline):
  1. construct the source (slack) + all elements from their rows
  2. set each line's base_kv from the region-voltage map
  3. resolve every element (voltage snapping, kv forms, etc.)
  4. register linecodes into the shared library
  5. emit in the REQUIRED OpenDSS order:
       circuit(slack) -> linecodes -> transformers -> lines -> loads
       -> voltagebases -> (solve is left to the caller)
  6. roll up assumptions/flags across all elements

Input shape (per element): a dict pair {"edge": {...}, "attr": {...}} using the
same keys the element from_row methods already expect. The region-voltage map
is {node_name: base_kv_LL}.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .elements.source import Source
from .elements.line import Line
from .elements.transformer import Transformer
from .libraries.linecode import LineCodeLibrary


@dataclass
class Feeder:
    name: str                         # feeder identifier (e.g. the head recloser)
    snapshot: str
    source: Source | None = None
    lines: list[Line] = field(default_factory=list)
    transformers: list[Transformer] = field(default_factory=list)
    # (loads, capacitors, ... added as those elements are built)
    linecodes: LineCodeLibrary = field(default_factory=LineCodeLibrary)
    resolved: bool = False

    # ---------------------------------------------------------------- #
    # CONSTRUCT — build elements from loaded rows
    # ---------------------------------------------------------------- #
    @classmethod
    def build(
        cls,
        name: str,
        snapshot: str,
        source_rows: dict,                 # {"edge":..., "attr":...}
        line_rows: list[dict],             # [{"edge":..., "attr":...}, ...]
        transformer_rows: list[dict],
        region_voltage: dict[str, float],  # {node_name: base_kv_LL}
    ) -> "Feeder":
        f = cls(name=name, snapshot=snapshot)

        # source (the slack)
        f.source = Source.from_row(source_rows["edge"], source_rows["attr"], snapshot)

        # lines — set base_kv from the region map (by the line's node name)
        for r in line_rows:
            ln = Line.from_row(r["edge"], r["attr"], snapshot)
            ln.base_kv = region_voltage.get(ln.name)
            if ln.base_kv is None:
                ln.add_flag("no region voltage found; base_kv unset")
            f.lines.append(ln)

        # transformers
        for r in transformer_rows:
            f.transformers.append(
                Transformer.from_row(r["edge"], r["attr"], snapshot)
            )
        return f

    # ---------------------------------------------------------------- #
    # RESOLVE — element-level resolution + linecode registration
    # ---------------------------------------------------------------- #
    def resolve(self) -> None:
        if self.source:
            self.source.resolve(self)
        for ln in self.lines:
            ln.resolve(self)
        for xf in self.transformers:
            xf.resolve(self)
        # register linecodes AFTER base_kv is known (lines carry it from build)
        for ln in self.lines:
            self.linecodes.register(ln)
        self.resolved = True

    # ---------------------------------------------------------------- #
    # EMIT — the complete ordered .dss
    # ---------------------------------------------------------------- #
    def to_dss(self) -> str:
        if not self.resolved:
            self.resolve()

        parts: list[str] = []
        parts.append(f"! ===== Feeder {self.name}  (snapshot {self.snapshot}) =====")

        # 1) circuit / slack — MUST be first
        if self.source:
            parts.append("! --- source (slack) ---")
            parts.append(self.source.to_dss())

        # 2) linecodes — before any line references them
        if len(self.linecodes):
            parts.append(self.linecodes.to_dss())

        # 3) transformers
        if self.transformers:
            parts.append("! --- transformers ---")
            parts.extend(xf.to_dss() for xf in self.transformers)

        # 4) lines
        if self.lines:
            parts.append("! --- lines ---")
            parts.extend(ln.to_dss() for ln in self.lines)

        # 5) (loads go here once built)

        # 6) voltage bases + calc
        vbases = self._voltage_bases()
        parts.append("! --- solve setup ---")
        parts.append(f"Set voltagebases={vbases}")
        parts.append("CalcVoltageBases")
        # NOTE: 'Solve' intentionally omitted — the caller decides when to solve.

        return "\n".join(parts)

    def _voltage_bases(self) -> str:
        """Distinct L-L base voltages present in the feeder, for OpenDSS."""
        levels = set()
        if self.source and self.source.basekv_ll:
            levels.add(round(self.source.basekv_ll, 3))
        for xf in self.transformers:
            if xf.hv_kv_ll:
                levels.add(round(xf.hv_kv_ll, 3))
            if xf.lv_kv_ll:
                levels.add(round(xf.lv_kv_ll, 3))
        for ln in self.lines:
            if ln.base_kv:
                levels.add(round(ln.base_kv, 3))
        return "[" + ", ".join(str(v) for v in sorted(levels, reverse=True)) + "]"

    # ---------------------------------------------------------------- #
    # PROVENANCE — roll up assumptions/flags across all elements
    # ---------------------------------------------------------------- #
    def report(self) -> dict:
        assumptions, flags = [], []
        elems = ([self.source] if self.source else []) + self.lines + self.transformers
        for e in elems:
            for a in e.assumptions:
                assumptions.append(f"[{e.dss_type} {e.name}] {a}")
            for fl in e.flag:
                flags.append(f"[{e.dss_type} {e.name}] {fl}")
        # library-level provenance
        for a in self.linecodes.assumptions:
            assumptions.append(f"[LineCode] {a}")
        for fl in self.linecodes.flags:
            flags.append(f"[LineCode] {fl}")
        return {
            "feeder": self.name,
            "snapshot": self.snapshot,
            "n_lines": len(self.lines),
            "n_transformers": len(self.transformers),
            "n_linecodes": len(self.linecodes),
            "assumptions": assumptions,
            "flags": flags,
        }
