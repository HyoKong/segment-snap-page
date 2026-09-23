#!/usr/bin/env python3
"""Native high-resolution exports for the website qualitative panels.

This module deliberately redraws the committed Matplotlib figure producers from the
released prediction artefacts.  It never scales, composites, or crops a rasterized
website/PDF image.  The rectangle coordinates are the verified PDF-space rectangles
used by :mod:`prepare_assets`; they exclude gallery-only header/footer text while
leaving every plotted point, line, colour, label, and camera untouched.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import os
import pickle
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[2]
POINTS_PER_INCH = 72.0
TARGET_WIDTH = 2400

# These are PDF coordinates (origin at the upper-left) and are intentionally shared
# with prepare_assets.py.  The page sizes are the original producer PDFs' MediaBox.
HINGE_PAGE = (1071.16, 415.25)
HANDLES_PAGE = (1199.71, 261.782)
PANELS = {
    "motion-before.png": ("hinge", (6.7, 74.0, 155.1, 150.5)),
    "motion-after.png": ("hinge", (6.7, 224.5, 155.1, 150.5)),
    "failure-axis.png": ("hinge", (502.7, 224.5, 155.1, 150.5)),
    "handle-recovered.png": ("handles", (394.9, 73.1, 131.2, 100.9)),
    "failure-handle.png": ("handles", (673.4, 73.1, 131.2, 100.9)),
    "handle-context.png": ("handles", (812.7, 73.1, 131.2, 100.9)),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_HASHES: dict[Path, str] = {}


def _source(path: Path) -> dict[str, str]:
    path = path.resolve()
    if path not in _HASHES:
        _HASHES[path] = _sha256(path)
    return {"source": path.relative_to(ROOT).as_posix(), "source_sha256": _HASHES[path]}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import producer {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_producer(module, argv: list[str]) -> object:
    """Run a producer in-process so its final live Figure remains available."""
    old_cwd = Path.cwd()
    try:
        os.chdir(ROOT)
        with patch.object(sys, "argv", [str(module.__file__), *argv]):
            rc = module.main()
        if rc not in (None, 0):
            raise RuntimeError(f"{module.__file__} returned {rc}")
        figures = [plt.figure(n) for n in plt.get_fignums()]
        if len(figures) != 1:
            raise RuntimeError(f"expected one live figure from {module.__file__}, found {len(figures)}")
        return figures[0]
    finally:
        os.chdir(old_cwd)


def _save_panel(native_pdf: Path, page, crop, output: Path) -> dict[str, object]:
    """Direct-render a verified PDF rectangle from a freshly redrawn native PDF."""
    page_width, _page_height = page
    page_render_width = int(np.ceil(page_width * TARGET_WIDTH / crop[2]))
    scale = page_render_width / page_width
    x, y, width, height = crop
    left, top, right, bottom = (round(value * scale) for value in (x, y, x + width, y + height))
    # This is a PDF renderer crop, not a crop/resample of a bitmap.  The temporary PDF
    # was just emitted from the live Matplotlib artists at 1400 DPI, so rasterized
    # point layers retain substantially more source detail than the historical 190-DPI PNG.
    subprocess.run([
        "pdftoppm", "-f", "1", "-l", "1", "-png", "-scale-to-x", str(page_render_width),
        "-scale-to-y", "-1", "-x", str(left), "-y", str(top), "-W", str(right - left),
        "-H", str(bottom - top), "-singlefile", str(native_pdf), str(output.with_suffix("")),
    ], check=True)
    with Image.open(output) as image:
        pixels = list(image.size)
    if pixels[0] < TARGET_WIDTH:
        raise RuntimeError(f"{output.name} is {pixels[0]} px wide, below {TARGET_WIDTH} px")
    return {"pixels": pixels, "page_render_width_px": page_render_width}


def _producer_reproduction(rendered_png: Path, source_png: Path) -> dict[str, object]:
    """Fail closed unless the whole regenerated historical raster is the same figure."""
    with Image.open(rendered_png).convert("RGB") as actual, Image.open(source_png).convert("RGB") as expected:
        same_dimensions = actual.size == expected.size
        if not same_dimensions:
            raise RuntimeError(f"native producer changed source dimensions: {actual.size} != {expected.size}")
        delta = ImageChops.difference(actual, expected)
        values = np.asarray(delta, dtype=np.uint8)
    mean = float(values.mean())
    maximum = int(values.max())
    # Same Matplotlib version and the same saved-PNG backend should reproduce exactly.
    # A nonzero value is evidence that an input, selection, font/backend, or producer changed;
    # exporting a different specimen would be worse than withholding an asset.
    if mean != 0.0 or maximum != 0:
        raise RuntimeError(
            f"native producer does not reproduce {source_png.name}: mean RGB delta={mean:.4f}, max={maximum}"
        )
    return {
        "reference": source_png.relative_to(ROOT).as_posix(),
        "reference_sha256": _source(source_png)["source_sha256"],
        "rendered_producer_png": rendered_png.name,
        "pixels": list(actual.size),
        "mean_absolute_rgb_difference": mean,
        "max_rgb_difference": maximum,
        "selection_confirmed": True,
        "gate": "exact whole-gallery RGB equality at the original 190 DPI",
    }


def _render_group(fig, group: str, page, source_pdf: Path, source_png: Path, output_dir: Path,
                  inputs: list[Path], provenance: dict[str, object], reproduction: dict[str, object]) -> dict[str, dict[str, object]]:
    native_pdf = output_dir / f".native-{group}.pdf"
    fig.savefig(native_pdf, format="pdf", dpi=1400, bbox_inches="tight")
    records = {}
    for name, (panel_group, crop) in PANELS.items():
        if panel_group != group:
            continue
        target = output_dir / name
        details = _save_panel(native_pdf, page, crop, target)
        records[name] = {
            "kind": "source_native_prediction_render",
            **_source(source_pdf),
            "output": target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else str(target),
            "output_sha256": _sha256(target),
            "pixels": details["pixels"],
            "preservation": "Exact verified PDF-space panel rectangle; native Matplotlib redraw from released predictions. No bitmap upscaling, image editing, inference, camera alignment, or specimen substitution.",
            "crop_bounds_pdf_points": {"x": crop[0], "y": crop[1], "width": crop[2], "height": crop[3]},
            "exporter": _source(ROOT / "website/scripts/render_qualitative.py"),
            "renderer": {"name": "matplotlib_pdf_then_poppler_rectangle", "native_scatter_dpi": 1400,
                         "page_render_width_px": details["page_render_width_px"], "target_min_width_px": TARGET_WIDTH},
            "inputs": [_source(path) for path in inputs],
            "plot_provenance": provenance,
            "reproduction": reproduction,
        }
    native_pdf.unlink()
    return records


def _coordinate_inputs(fig, dataset: Path) -> list[Path]:
    """Hash coordinate arrays for every selected scene named in the live plot titles."""
    prefixes = set()
    for axis in fig.axes:
        # Both producers place provenance titles at the left; get_title() only returns
        # the centre title and would silently miss every selected scene.
        match = re.search(r"\b([0-9a-f]{6})\s+·", axis.get_title(loc="left"))
        if match:
            prefixes.add(match.group(1))
    paths = []
    for prefix in sorted(prefixes):
        matches = sorted((dataset / "validation").glob(prefix + "*/coord.npy"))
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one selected coordinate input for {prefix}, found {matches}")
        paths.append(matches[0])
    if not paths:
        raise RuntimeError("producer figure exposed no selected scene identifiers")
    return paths


def render_panels(output_dir: Path) -> dict[str, dict[str, object]]:
    """Render all six website panels to *output_dir* and return their manifest records."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    hinge_producer = ROOT / "experiments/fig_hinge_gallery.py"
    handle_producer = ROOT / "experiments/fig_complementarity.py"
    specimens = ROOT / "runs/a1_cache/specimens.json"
    t1 = ROOT / "runs/release_repro/t1_validation_preds.pkl"
    dense = ROOT / "runs/a1_cache/seedrow_released/single/t2_validation_preds.pkl"
    union_compact = ROOT / "runs/a1_cache/t2_union_preds_compact.npz"
    hinge_pdf = ROOT / "report/figures/qualitative_hinge_source.pdf"
    hinge_png = ROOT / "report/figures/qualitative_hinge_source.png"
    handles_pdf = ROOT / "report/figures/qualitative_handles_source.pdf"
    handles_png = ROOT / "report/figures/qualitative_handles_source.png"
    required = [hinge_producer, handle_producer, specimens, t1, dense, union_compact,
                hinge_pdf, hinge_png, handles_pdf, handles_png]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("required native-render input missing: " + ", ".join(missing))

    records: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory(prefix="website-native-qualitative-") as temp_name:
        temporary = Path(temp_name)
        print("rendering hinge gallery from released predictions", flush=True)
        hinge_module = _load_module("website_native_hinge_gallery", hinge_producer)
        hinge_fig = _run_producer(hinge_module, ["--specimens", str(specimens), "--preds", str(t1),
                                                   "--out", str(temporary / "hinge.pdf")])
        hinge_reproduction = _producer_reproduction(temporary / "hinge.png", hinge_png)
        print("hinge whole-gallery reproduction passed; exporting panels", flush=True)
        records.update(_render_group(
            hinge_fig, "hinge", HINGE_PAGE, hinge_pdf, hinge_png, output_dir,
            [hinge_producer, specimens, t1, *_coordinate_inputs(hinge_fig, ROOT / "data/pointcept_mov")],
            {"producer": "experiments/fig_hinge_gallery.py", "selection": "runs/a1_cache/specimens.json",
             "source_gallery": "report/figures/qualitative_hinge_source.pdf",
             "camera_caveat": "The paired projection frames are producer-defined; they are not re-aligned by this exporter."},
            hinge_reproduction,
        ))
        plt.close(hinge_fig)
        del hinge_fig, hinge_module
        gc.collect()

        print("decoding compact union and rendering handle gallery", flush=True)
        union_decoder = ROOT / "experiments/t2_union_compact.py"
        union_module = _load_module("website_native_t2_union_compact", union_decoder)
        union = union_module.unpack(union_compact)
        union_pickle = temporary / "union.pkl"
        with union_pickle.open("wb") as handle:
            pickle.dump(union, handle, protocol=pickle.HIGHEST_PROTOCOL)
        del union
        gc.collect()
        handle_module = _load_module("website_native_complementarity", handle_producer)
        handle_fig = _run_producer(handle_module, ["--dense", str(dense), "--union", str(union_pickle),
                                                     "--t1", str(t1), "--out", str(temporary / "handles.pdf")])
        handles_reproduction = _producer_reproduction(temporary / "handles.png", handles_png)
        print("handle whole-gallery reproduction passed; exporting panels", flush=True)
        records.update(_render_group(
            handle_fig, "handles", HANDLES_PAGE, handles_pdf, handles_png, output_dir,
            [handle_producer, union_decoder, dense, union_compact, t1,
             *_coordinate_inputs(handle_fig, ROOT / "data/pointcept_lite")],
            {"producer": "experiments/fig_complementarity.py", "selection": "producer-defined deterministic named quantiles",
             "source_gallery": "report/figures/qualitative_handles_source.pdf",
             "union_decode": "experiments/t2_union_compact.py unpacked losslessly into a temporary pickle for the unchanged producer."},
            handles_reproduction,
        ))
        plt.close(handle_fig)
        del handle_fig, handle_module, union_module
        gc.collect()
    for record in records.values():
        record["runtime_seconds"] = round(time.monotonic() - started, 2)
    if set(records) != set(PANELS):
        raise RuntimeError("native export did not produce every required panel")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    records = render_panels(args.output_dir)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(records, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
