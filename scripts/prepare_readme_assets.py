#!/usr/bin/env python3
"""Export self-contained README buttons and copy the verified vector teaser.

This uses the same local icons as the website. No badge service, plotting run,
network request, or additional package is needed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "website/assets"
OUTPUT = ROOT / "opensource/docs/assets"
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def button(name: str, label: str, width: int, primary: bool = False) -> str:
    background = "#0066cc" if primary else "#f5f5f7"
    foreground = "#ffffff" if primary else "#1d1d1f"
    root = ET.Element(f"{{{SVG}}}svg", {
        "width": str(width), "height": "40", "viewBox": f"0 0 {width} 40",
        "role": "img", "aria-label": label,
    })
    ET.SubElement(root, f"{{{SVG}}}title").text = label
    ET.SubElement(root, f"{{{SVG}}}rect", {
        "x": "0.5", "y": "0.5", "width": str(width - 1), "height": "39",
        "rx": "19.5", "fill": background,
        "stroke": background if primary else "#dedee3",
    })
    icon = ET.fromstring((ASSETS / "icons" / f"{name}.svg").read_text())
    icon.attrib.update({"x": "18", "y": "10", "width": "20", "height": "20"})
    if primary:
        for node in icon.iter():
            for attribute in ("fill", "stroke"):
                if node.get(attribute) == "#1d1d1f":
                    node.set(attribute, foreground)
    root.append(icon)
    ET.SubElement(root, f"{{{SVG}}}text", {
        "x": "47", "y": "20", "dominant-baseline": "central",
        "fill": foreground, "font-family": "Arial, Helvetica, sans-serif",
        "font-size": "13", "font-weight": "500",
    }).text = label
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def main() -> None:
    teaser = ASSETS / "teaser.svg"
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    expected = manifest["assets"]["teaser.svg"]["output_sha256"]
    if hashlib.sha256(teaser.read_bytes()).hexdigest() != expected:
        raise ValueError("Teaser does not match the website's verified asset manifest")
    buttons = {
        "project": button("project", "Project page", 152, primary=True),
        "huggingface": button("huggingface", "Hugging Face", 166),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, markup in buttons.items():
        (OUTPUT / f"button-{name}.svg").write_text(markup)
    shutil.copy2(teaser, OUTPUT / "teaser.svg")
    shutil.copy2(ASSETS / "icons/LICENSE.txt", OUTPUT / "LICENSE.txt")
    print("Staged two self-contained resource buttons and the unchanged vector teaser.")


if __name__ == "__main__":
    main()
