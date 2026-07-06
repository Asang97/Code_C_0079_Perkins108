"""
io/dss_output.py — write feeder .dss files to disk.

One file per feeder under output/dss/ (feeder-by-feeder modeling). The Solve
command is omitted -- the caller decides when/how to solve. This is the clean
"generate the .dss" entry point the query layer / FastAPI / a batch driver call.
"""
from __future__ import annotations
import os

DEFAULT_OUT_DIR = "output/dss"


def _safe_name(name: str) -> str:
    """Filesystem-safe filename from a feeder name."""
    keep = "-_."
    return "".join(c if (c.isalnum() or c in keep) else "_" for c in str(name))


def write_feeder_dss(feeder, out_dir: str = DEFAULT_OUT_DIR) -> str:
    """Write one feeder's .dss to out_dir/<feeder>.dss. Returns the path.

    Solve is intentionally omitted (feeder.to_dss() ends at CalcVoltageBases);
    the caller runs Solve when ready.
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{_safe_name(feeder.name)}.dss")
    with open(path, "w") as f:
        f.write(feeder.to_dss())
        f.write("\n")
    return path


def write_many(feeders, out_dir: str = DEFAULT_OUT_DIR) -> list[str]:
    """Write several feeders; returns the list of paths written."""
    return [write_feeder_dss(f, out_dir=out_dir) for f in feeders]