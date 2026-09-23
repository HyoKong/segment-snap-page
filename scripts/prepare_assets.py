#!/usr/bin/env python3
"""Stage source-native, high-density scientific figures and the current paper.

The existing repository environment supplies matplotlib/NumPy. Each renderer runs
in its own process so the report and experiment packages do not shadow each other.
All exports finish successfully before any live website asset is replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "website" / "assets"
PYTHON = ROOT / ".venv/bin/python"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-only", action="store_true",
                        help="refresh the compiled PDF and its manifest record without replotting figures")
    args = parser.parse_args()
    if args.paper_only:
        manifest_path = ASSETS / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        paper = ROOT / "report/build/main.pdf"
        paper_hash = sha256(paper)
        shutil.copy2(paper, ASSETS / "paper.pdf")
        manifest["assets"]["paper.pdf"] = {
            "kind": "byte_for_byte_copy", "source": "report/build/main.pdf",
            "source_sha256": paper_hash, "output": "website/assets/paper.pdf",
            "output_sha256": sha256(ASSETS / "paper.pdf"),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print("Staged the current paper; all scientific figure exports are unchanged.")
        return
    if not PYTHON.is_file():
        raise FileNotFoundError(f"The existing plotting environment is required: {PYTHON}")
    ASSETS.mkdir(parents=True, exist_ok=True)
    paper = ROOT / "report" / "build" / "main.pdf"
    assets = {}
    preview = ROOT / "website/preview"
    preview.mkdir(exist_ok=True)
    # Repository-local staging allows each record to use portable repo-relative paths.
    with tempfile.TemporaryDirectory(prefix="asset-export-", dir=preview) as temp:
        directory = Path(temp)
        for script in ("render_illustrations.py", "render_qualitative.py"):
            records_path = directory / f"{Path(script).stem}.json"
            subprocess.run([str(PYTHON), str(Path(__file__).parent / script),
                            "--output-dir", str(directory), "--manifest", str(records_path)],
                           cwd=ROOT, check=True)
            assets.update(json.loads(records_path.read_text()))
        for name, record in assets.items():
            source = ROOT / record["output"]
            if sha256(source) != record["output_sha256"]:
                raise ValueError(f"Staged asset checksum mismatch: {name}")
        for name, record in assets.items():
            shutil.copy2(ROOT / record["output"], ASSETS / name)
            record["output"] = f"website/assets/{name}"
    shutil.copy2(paper, ASSETS / "paper.pdf")
    assets["paper.pdf"] = {
        "kind": "byte_for_byte_copy", "source": paper.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(paper), "output": "website/assets/paper.pdf",
        "output_sha256": sha256(ASSETS / "paper.pdf"),
    }

    manifest = {
        "schema_version": 2,
        "generated_by": "website/scripts/prepare_assets.py",
        "scientific_visualization_policy": (
            "No synthetic prediction imagery or bitmap upscaling. Illustrations and selected "
            "prediction panels are re-rendered from their original plotting data; "
            "geometry, specimen choices, labels and numerical claims are preserved."
        ),
        "interpretation": {
            "teaser_and_pipeline": "Illustrative report artwork explaining the method; not a gallery of model predictions.",
            "qualitative_panels": "Selected validation predictions from verified source galleries; individual examples are illustrative rather than AP estimates.",
            "matching": "Gallery labels describe the producer's visualization matching. They are not a replacement for the evaluation's IoU/AP matching protocol.",
            "counts": "Producer footer counts and source-gallery population totals are intentionally omitted from website panels and must not be used as AP evidence.",
        },
        "assets": assets,
    }
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"staged {len(assets)} assets in {ASSETS}")


if __name__ == "__main__":
    main()
