#!/usr/bin/env python3
"""Export the existing report drawings to self-contained, high-density SVGs.

Text, arrows and geometric annotations remain vectors. RGB scatter layers are
replotted from measured points at 900 DPI, not enlarged from the report PNGs.
No report artifact is rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "report/scripts"))

import matplotlib.pyplot as plt  # noqa: E402
import render_pipeline  # noqa: E402
import render_teaser  # noqa: E402

RASTER_DPI = 900


def source_record(path: Path) -> dict:
    return {"source": path.relative_to(ROOT).as_posix(),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def render_illustrations(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "text.color": render_pipeline.INK, "pdf.fonttype": 42,
                         "svg.fonttype": "path", "svg.hashsalt": "segment-snap-website"})
    # Verify source geometry, selected support and the displayed numerical claims.
    render_pipeline.verify()
    render_teaser.verify()
    common_inputs = [
        ROOT / "report/scripts/render_pipeline.py",
        ROOT / "report/scripts/coupling_evidence.py",
        ROOT / "report/scripts/check_evidence.py",
        ROOT / "report/data/current_results.csv",
        *sorted((ROOT / "report/data").glob("new_results_*.csv")),
        render_pipeline.DATA / "validation" / f"{render_pipeline.SCENE}.npy",
        render_pipeline.DATA / "instance_gt/validation" / f"{render_pipeline.SCENE}.txt",
    ]
    records = {}
    for name, draw, extra_inputs in [
        ("teaser", render_teaser.draw, [ROOT / "report/scripts/render_teaser.py",
                                       ROOT / "report/data/teaser_illustration.json"]),
        ("pipeline", render_pipeline.illustration,
         [ROOT / "report/data/pipeline_illustration.json",
          ROOT / "report/data/pipeline_cross_task_example.npz",
          ROOT / "report/data/pipeline_handle_motion_example.npz"]),
    ]:
        fig = draw(return_figure=True)
        target = output_dir / f"{name}.svg"
        try:
            fig.savefig(target, format="svg", dpi=RASTER_DPI, metadata={"Date": None})
            figure_size = list(fig.get_size_inches())
        finally:
            plt.close(fig)
        root = ET.parse(target).getroot()
        svg = "{http://www.w3.org/2000/svg}"
        records[target.name] = {
            "kind": "source_native_svg_export",
            **source_record(ROOT / f"report/figures/{name}_rgb.pdf"),
            "output": target.relative_to(ROOT).as_posix(),
            "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "view_box": [float(value) for value in root.attrib["viewBox"].split()],
            "figure_size_inches": figure_size,
            "vector_text_and_annotations": True,
            "raster_dpi": RASTER_DPI,
            "embedded_point_layers": len(root.findall(f".//{svg}image")),
            "inputs": [source_record(path) for path in [*common_inputs, *extra_inputs]],
            "exporter": source_record(Path(__file__).resolve()),
            "preservation": "The original figure function and measured RGB points are reused. "
                            "Only the export format and native scatter rendering density change; "
                            "geometry, labels, layout and reported gains are unchanged.",
        }
        print(f"Exported {target.name}: vector labels/arrows, {RASTER_DPI}-DPI point layers")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    records = render_illustrations(args.output_dir.resolve())
    args.manifest.write_text(json.dumps(records, indent=2) + "\n")
