#!/usr/bin/env python3
"""Validate the static site's links, evidence and asset provenance without a browser."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
PROJECT_URL = "https://hyokong.github.io/segment-snap-page/"
PAPER_URL = "https://arxiv.org/abs/2609.25247"
HANYANG_URL = "https://hyokong.github.io/"
LEADERBOARD_URL = "https://art3d-challenge.mooo.com/web/challenges/challenge-page/1/leaderboard/"
sys.path.insert(0, str(ROOT / "report/scripts"))
from check_evidence import read_evidence_rows  # noqa: E402


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None]
    children: list = field(default_factory=list)

    def text(self):
        return " ".join(child.text() if isinstance(child, Element) else child
                        for child in self.children)


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Element("root", {})
        self.stack = [self.root]
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        self.elements.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if len(self.stack) > 1 and self.stack[-1].tag == tag:
            self.stack.pop()
        elif tag not in self.VOID:
            raise ValueError(f"Unbalanced HTML end tag: {tag}")

    def handle_data(self, data):
        self.stack[-1].children.append(data)


@lru_cache(maxsize=None)
def digest(path):
    # Several panels share the same multi-GB prediction file. Verify it once per
    # invocation and stream the bytes rather than duplicating it in memory.
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def png_dimensions(path):
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Not a PNG with an IHDR header: {path}")
    return list(struct.unpack(">II", header[16:24]))


def descendants(node):
    result = []
    for child in node.children:
        if isinstance(child, Element):
            result.append(child)
            result.extend(descendants(child))
    return result


def main():
    html = (SITE / "index.html").read_text()
    document = Document(html)
    errors = []
    expect = lambda condition, message: errors.append(message) if not condition else None
    ids = [node.attrs["id"] for node in document.elements if "id" in node.attrs]
    expect(len(ids) == len(set(ids)), "HTML IDs must be unique")
    expect(len(document.stack) == 1, "HTML contains unclosed elements")
    headings = [node for node in document.elements if node.tag == "h1"]
    expect(len(headings) == 1, "Need exactly one h1")
    expected_title = "Geometric and Semantic Coupling for Interaction Understanding in 3D Scenes"
    expect(" ".join(headings[0].text().split()) == expected_title, "Paper title differs from report")
    title_main = [node for node in document.elements
                  if "title-main" in (node.attrs.get("class") or "").split()]
    title_subtitle = [node for node in document.elements
                      if "title-subtitle" in (node.attrs.get("class") or "").split()]
    expect(len(title_main) == 1 and " ".join(title_main[0].text().split()) == "Geometric and Semantic Coupling",
           "Main title must contain exactly 'Geometric and Semantic Coupling'")
    expect(len(title_subtitle) == 1 and " ".join(title_subtitle[0].text().split()) == "for Interaction Understanding in 3D Scenes",
           "Title subtitle must contain the remaining paper title")
    if title_main:
        expect(not any(node.tag == "br" for node in descendants(title_main[0])),
               "Main title must not use a forced line break")
    expect('lang="en"' in html, "Document language missing")

    links = 0
    for node in document.elements:
        for attribute in ("href", "src"):
            target = node.attrs.get(attribute)
            if not target:
                continue
            parsed = urlsplit(target)
            if parsed.scheme:
                expect(parsed.scheme in ("https", "mailto"), f"Unexpected link scheme: {target}")
                if node.tag == "script" or (node.tag == "link" and node.attrs.get("rel") == "stylesheet"):
                    errors.append(f"Site should not depend on a remote script/style: {target}")
                continue
            links += 1
            expect(not parsed.path.startswith("/"), f"Root-absolute URL breaks project subpaths: {target}")
            if parsed.path:
                resource = (SITE / unquote(parsed.path)).resolve()
                expect(resource.is_relative_to(SITE) and resource.is_file(), f"Missing/unsafe local resource: {target}")
            elif parsed.fragment:
                expect(parsed.fragment in ids, f"Anchor target missing: {target}")
        if node.tag == "a" and node.attrs.get("target") == "_blank":
            expect("noopener" in (node.attrs.get("rel") or ""), "New-window link lacks noopener")
        if node.tag == "img" and node.attrs.get("src"):
            decorative = ("resource-icon" in (node.attrs.get("class") or "").split()
                          and node.attrs.get("aria-hidden") == "true")
            if decorative:
                expect(node.attrs.get("alt") == "", "Decorative resource icons need empty alternative text")
            else:
                expect(bool(node.attrs.get("alt")), f"Scientific image lacks descriptive alt: {node.attrs.get('src')}")
            expect("width" in node.attrs and "height" in node.attrs, "Image lacks reserved dimensions")
        if node.tag == "button":
            expect(node.attrs.get("type") == "button", "Button type should be explicit")

    reference, updates = read_evidence_rows(ROOT / "report")
    records = {row["id"]: row for row in reference + updates}
    measurements = [node for node in document.elements if "data-evidence" in node.attrs]
    for node in measurements:
        name = node.attrs["data-evidence"]
        expect(name in records, f"Missing numerical evidence: {name}")
        if name in records:
            expect(Decimal(node.text().strip()) == Decimal(records[name]["paper_token"]),
                   f"Displayed result differs from manuscript: {name}")
    required_measurements = {
        "f3_handles_drop", "sep8_child_reference_union_step", "handle_parts_only_delta",
        "mov_centroid_joint", "mov_handle_joint", "handle_dense", "handle_union",
        "handle_parts_only", "handle_vote", "handle_full_vote_delta",
        "sep8_child_seed_b_union_step", "sep20_child_union_ci_low",
        "sep20_child_union_ci_high", "sep8_child_seed_a_vote_step",
        "sep8_child_reference_vote_step", "final_mov", "final_handle",
    }
    expect(required_measurements <= {node.attrs["data-evidence"] for node in measurements},
           "A core result or uncertainty marker is missing")
    visible = document.root.text()
    for text in ("Hanyang Kong", "Xingyi Yang", "National University of Singapore",
                 "The Hong Kong Polytechnic University", "September 6, 2026",
                 "42 public validation scenes", "195 training scenes"):
        expect(text in visible, f"Required author/protocol detail missing: {text}")
    expect(not re.search(r"\b(?:track\s*[12]|T[12]|two tasks)\b|part--handle|King Kong", visible, re.I),
           "Avoid separate-task framing or removed logo branding")
    expect("alternative corrections of the same union" in visible, "Part-only/full labels must not be additive")
    expect("never feed back" in html or "No final-handle feedback" in html, "One-pass boundary missing")

    award_links = [node for node in document.elements
                   if node.tag == "a" and "award-link" in (node.attrs.get("class") or "").split()]
    expect(len(award_links) == 1, "Show one prominent hero award, not duplicate badges")
    if award_links:
        award = award_links[0]
        expect(document.elements.index(award) < document.elements.index(headings[0]),
               "First-place recognition must appear above the paper title")
        expect(award.attrs.get("href") == LEADERBOARD_URL,
               "Hero recognition must link to the official leaderboard")
        expect("1st place" in award.text() and "Articulate3D Challenge" in award.text(),
               "Hero recognition must explicitly name the rank and challenge")
        expect(award.attrs.get("aria-describedby") == "award-scope",
               "Hero recognition must expose its evaluation scope")
    award_scope = next((node for node in document.elements if node.attrs.get("id") == "award-scope"), None)
    expect(award_scope is not None and "both evaluated outputs" in award_scope.text()
           and any(node.tag == "a" and node.attrs.get("href") == "#challenge"
                   for node in descendants(award_scope)),
           "Recognition needs its two-output scope and an in-page results link")

    authors = next(node for node in document.elements
                   if "authors" in (node.attrs.get("class") or "").split())
    hanyang_links = [node for node in descendants(authors)
                    if node.tag == "a" and node.text().strip().startswith("Hanyang Kong")]
    expect(len(hanyang_links) == 1 and hanyang_links[0].attrs.get("href") == HANYANG_URL,
           "Hanyang Kong's author name must link to his personal website, not email")

    external_hrefs = {node.attrs.get("href") for node in document.elements if node.tag == "a"}
    expect("https://github.com/HyoKong/Segment-Snap" in external_hrefs,
           "Missing or incorrect public code link")
    expect("https://huggingface.co/imsuperkong/Segment-Snap" in external_hrefs,
           "Missing or incorrect public checkpoint link")
    expect(PROJECT_URL not in external_hrefs, "The project page should not link to itself as a resource")
    canonical = [node for node in document.elements
                 if node.tag == "link" and node.attrs.get("rel") == "canonical"]
    expect(len(canonical) == 1 and canonical[0].attrs.get("href") == PROJECT_URL,
           "Canonical metadata must use the exact author-supplied project URL")
    expect(any(node.tag == "meta" and node.attrs.get("property") == "og:url"
               and node.attrs.get("content") == PROJECT_URL for node in document.elements),
           "Open Graph URL must match the canonical URL")
    citation = next(node for node in document.elements if node.attrs.get("id") == "bibtex")
    citation_file = (SITE / "assets/citation.bib").read_text().strip()
    expect(citation.text().strip() == citation_file, "Displayed and downloadable BibTeX must be identical")
    expect(citation_file.startswith("@article{kong2026segmentsnap,"), "Keep the stable citation key and use an article entry")
    citation_fields = {
        "title": expected_title, "author": "Kong, Hanyang and Yang, Xingyi", "year": "2026",
        "journal": "arXiv preprint arXiv:2609.25247", "url": PAPER_URL,
    }
    for field, value in citation_fields.items():
        match = re.search(rf"\b{field}\s*=\s*\{{([^}}]*)\}}", citation_file)
        expect(match is not None and " ".join(match.group(1).split()) == value,
               f"Citation differs from verified arXiv metadata: {field}")
    expect(any(node.tag == "a" and node.attrs.get("href") == "assets/citation.bib"
               and "download" in node.attrs for node in document.elements),
           "Provide a downloadable BibTeX file")
    navigation_paper = next(node for node in document.elements
                            if "nav-paper" in (node.attrs.get("class") or "").split())
    expect(navigation_paper.attrs.get("href") == PAPER_URL, "Navigation Paper button must open arXiv")
    expect(not any((href or "").startswith("assets/paper.pdf") for href in external_hrefs),
           "Public paper links must use arXiv, not the offline review PDF")
    resource_urls = {
        "paper": PAPER_URL,
        "code": "https://github.com/HyoKong/Segment-Snap",
        "huggingface": "https://huggingface.co/imsuperkong/Segment-Snap",
    }
    for group in ("hero-actions", "resource-links"):
        container = next(node for node in document.elements
                         if group in (node.attrs.get("class") or "").split())
        buttons = [node for node in descendants(container) if node.tag == "a"]
        expect(len(buttons) == 3 and {node.attrs.get("data-resource") for node in buttons} == set(resource_urls),
               f"{group} needs Paper, Code, and Hugging Face, without a project self-link")
        for button in buttons:
            name = button.attrs.get("data-resource")
            expect(button.attrs.get("href") == resource_urls.get(name), f"Wrong {group} destination: {name}")
            icons = [node for node in descendants(button) if node.tag == "img"]
            expect(len(icons) == 1 and icons[0].attrs.get("src") == f"assets/icons/{name}.svg"
                   and icons[0].attrs.get("alt") == "" and icons[0].attrs.get("aria-hidden") == "true",
                   f"{group} must pair {name}'s local icon with visible text")
            expect(len(button.text().strip()) >= 4, f"Resource link lacks a visible label: {name}")

    readme = (ROOT / "opensource/README.md").read_text()
    expect(f"[Hanyang Kong]({HANYANG_URL})" in readme
           and "[Hanyang Kong](mailto:" not in readme,
           "The README must link Hanyang Kong's name to his personal website")
    readme_document = Document(readme)
    readme_buttons = [node for node in readme_document.elements if node.tag == "a"
                      and any(child.tag == "img" and "button-" in (child.attrs.get("src") or "")
                              for child in descendants(node))]
    readme_resource_urls = {"paper": PAPER_URL, "project": PROJECT_URL, "huggingface": resource_urls["huggingface"]}
    expect(len(readme_buttons) == 3, "README needs paper, project, and checkpoint buttons without a code self-link")
    for name, url in readme_resource_urls.items():
        expect(any(node.attrs.get("href") == url
                   and any(child.tag == "img" and child.attrs.get("src") == f"docs/assets/button-{name}.svg"
                           and bool(child.attrs.get("alt")) for child in descendants(node))
                   for node in readme_buttons), f"README resource/icon mismatch: {name}")
    expect(not any(node.attrs.get("href") == resource_urls["code"] for node in readme_buttons),
           "README must not include a GitHub code button pointing to itself")
    readme_citation = re.search(r"```bibtex\s*\n(.*?)\n```", readme, re.S)
    expect(readme_citation is not None and readme_citation.group(1).strip() == citation_file,
           "Website and README citations must match")
    expect((ROOT / "opensource/CITATION.bib").read_text().strip() == citation_file,
           "Repository CITATION.bib must match the downloadable website citation")
    expect("[CITATION.bib](CITATION.bib)" in readme, "README must link its reusable BibTeX file")
    expect(readme.index('src="docs/assets/teaser.svg"') < readme.index("## The idea"),
           "README teaser must appear near the top, before method details")
    expect(digest(ROOT / "opensource/docs/assets/teaser.svg") == digest(SITE / "assets/teaser.svg"),
           "README must reuse the verified high-resolution teaser without re-encoding")
    for path in list((SITE / "assets/icons").glob("*.svg")) + list((ROOT / "opensource/docs/assets").glob("button-*.svg")):
        icon_svg = path.read_text()
        ET.fromstring(icon_svg)
        expect(not re.search(r"(?:href\s*=\s*['\"](?:https?:)?//|<script\b|<foreignObject\b)", icon_svg, re.I),
               f"Resource artwork must be self-contained and script-free: {path.name}")
    expect("Local review edition" not in visible, "Remove the obsolete placeholder footer label")

    comparisons = [node for node in document.elements
                   if "comparison" in (node.attrs.get("class") or "").split()
                   and "data-comparison" in node.attrs]
    expect(len(comparisons) == 1, "Need one explicit hinge before/after comparison")
    if comparisons:
        comparison = comparisons[0]
        images = [node for node in descendants(comparison) if node.tag == "img"]
        expect(len(images) == 2, "Comparison must retain the two original hinge images")
        expect({node.attrs.get("src") for node in images} == {"assets/motion-before.png", "assets/motion-after.png"},
               "Comparison must use the original before/after hinge assets")
        controls = [node for node in descendants(comparison) if "data-compare-controls" in node.attrs]
        expect(len(controls) == 1 and "hidden" in controls[0].attrs,
               "Comparison controls must be hidden before progressive enhancement")
        endpoint_buttons = [node for node in descendants(comparison)
                            if node.tag == "button" and node.attrs.get("data-compare-set") in {"before", "after"}]
        expect({node.attrs.get("data-compare-set") for node in endpoint_buttons} == {"before", "after"},
               "Comparison needs exact centroid-origin and handle-guided buttons")
        figures = [node for node in descendants(comparison)
                   if node.tag == "figure" and node.attrs.get("data-compare-view") in {"before", "after"}]
        expect({node.attrs.get("data-compare-view") for node in figures} == {"before", "after"},
               "Comparison needs complete before and after figure states")
        expect(all("hidden" not in figure.attrs for figure in figures),
               "Both comparison images must remain visible without JavaScript")
        statuses = [node for node in descendants(comparison) if "data-compare-status" in node.attrs]
        expect(len(statuses) == 1 and statuses[0].attrs.get("aria-live") == "polite",
               "Comparison needs a polite live status")
        expect(not any("data-compare-range" in node.attrs for node in descendants(comparison)),
               "Comparison must not spatially wipe mismatched projection frames")

    gallery_contract = {
        "gallery-motion": ["motion-legend"],
        "gallery-handles": ["recovery-legend", "context-legend"],
        "gallery-limits": ["axis-legend", "extent-legend"],
    }
    panel_by_id = {node.attrs.get("id"): node for node in document.elements if node.tag == "section"}
    for panel_id, legend_ids in gallery_contract.items():
        panel = panel_by_id.get(panel_id)
        expect(panel is not None, f"Missing qualitative panel: {panel_id}")
        if panel:
            panel_nodes = descendants(panel)
            intros = [node for node in panel_nodes
                      if "gallery-intro" in (node.attrs.get("class") or "").split()]
            expect(len(intros) == 1, f"{panel_id} needs one gallery-intro")
            if intros:
                intro_nodes = descendants(intros[0])
                intro_heading = [node for node in intro_nodes if node.tag == "h3"]
                intro_paragraphs = [node for node in intro_nodes if node.tag == "p"]
                expect(len(intro_heading) >= 1 and len(" ".join(intro_heading[0].text().split())) >= 8,
                       f"{panel_id} intro needs a meaningful heading")
                expect(any(len(" ".join(node.text().split())) >= 40 for node in intro_paragraphs),
                       f"{panel_id} intro needs a substantive explanatory paragraph")
            panel_legend_ids = {node.attrs.get("id") for node in panel_nodes}
            expect(set(legend_ids) <= panel_legend_ids,
                   f"{panel_id} is missing its named figure legend")

    legend_text = {node.attrs.get("id"): " ".join(node.text().split()).lower()
                   for node in document.elements if node.attrs.get("id") in {
                       "motion-legend", "recovery-legend", "context-legend", "axis-legend", "extent-legend"}}
    for legend_id in ("motion-legend", "recovery-legend", "context-legend", "axis-legend", "extent-legend"):
        expect(len(legend_text.get(legend_id, "")) >= 20, f"{legend_id} needs an explanatory label")
    for legend_id in ("recovery-legend", "extent-legend"):
        text = legend_text.get(legend_id, "")
        expect(all(term in text for term in ("black", "annotat", "handle")),
               f"{legend_id} must identify black marks as annotated handles")
    context_text = legend_text.get("context-legend", "")
    expect(all(term in context_text for term in ("black", "predict", "handle")) and
           ("child" in context_text or "joint branch" in context_text),
           "context-legend must identify black marks as predicted child handles")
    expect("ground truth" not in context_text and "annotated" not in context_text,
           "context-legend must not misidentify predicted child handles as annotations")

    manifest = json.loads((SITE / "assets/manifest.json").read_text())
    expected_scientific_assets = {
        "teaser.svg", "pipeline.svg", "paper.pdf",
        "motion-before.png", "motion-after.png", "failure-axis.png",
        "handle-recovered.png", "handle-context.png", "failure-handle.png",
    }
    expect(set(manifest["assets"]) == expected_scientific_assets,
           "Manifest must contain exactly the nine scientific website assets")
    for name, record in manifest["assets"].items():
        expect(digest(ROOT / record["source"]) == record["source_sha256"], f"Changed figure/PDF source: {name}")
        expect(digest(ROOT / record["output"]) == record["output_sha256"], f"Changed staged figure/PDF: {name}")
        if record["kind"] == "byte_for_byte_copy":
            expect(record["source_sha256"] == record["output_sha256"], f"Nonidentical direct copy: {name}")

    image_nodes = [node for node in document.elements if node.tag == "img" and node.attrs.get("src")]
    images_by_source = {}
    for image in image_nodes:
        images_by_source.setdefault(image.attrs["src"], []).append(image)

    for name, expected_size in {"teaser.svg": [1968, 696], "pipeline.svg": [2016, 864]}.items():
        record = manifest["assets"].get(name, {})
        source = f"assets/{name}"
        image = images_by_source.get(source, [])
        expect(record.get("kind") == "source_native_svg_export", f"{name} must be a source-native SVG export")
        expect(record.get("vector_text_and_annotations") is True and record.get("raster_dpi") == 900,
               f"{name} must document vector text/annotations and 900-DPI point layers")
        expect(isinstance(record.get("view_box"), list) and len(record["view_box"]) == 4 and
               all(isinstance(value, (int, float)) for value in record["view_box"]),
               f"{name} needs a numeric SVG view box")
        expect(isinstance(record.get("embedded_point_layers"), int) and record["embedded_point_layers"] > 0,
               f"{name} needs documented embedded RGB point layers")
        expect(len(image) == 1 and [int(image[0].attrs["width"]), int(image[0].attrs["height"])] == expected_size,
               f"HTML must reserve the source-native {name} dimensions")
        if record.get("view_box") and len(image) == 1:
            view_box = record["view_box"]
            expect(abs((view_box[2] / view_box[3]) - (expected_size[0] / expected_size[1])) < 1e-6,
                   f"{name} view box and HTML dimensions must share an aspect ratio")
        svg_path = ROOT / record.get("output", "")
        if svg_path.is_file():
            svg = svg_path.read_text(encoding="utf-8")
            expect("<svg" in svg and "<path" in svg, f"{name} must contain native vector paths")
            expect(not re.search(r"(?:xlink:)?href\s*=\s*['\"](?:https?:)?//", svg, re.I),
                   f"{name} must not load external SVG resources")
            layers = ET.fromstring(svg).findall(".//{http://www.w3.org/2000/svg}image")
            expect(len(layers) == record.get("embedded_point_layers"),
                   f"{name} must record its actual number of point layers")
            for layer in layers:
                payload = layer.attrib.get("{http://www.w3.org/1999/xlink}href", "")
                expect(payload.startswith("data:image/png;base64,"),
                       f"{name} point layers must be embedded PNGs")
                if payload.startswith("data:image/png;base64,"):
                    png = base64.b64decode(payload.split(",", 1)[1])
                    pixels = struct.unpack(">II", png[16:24])
                    # SVG plot units are points. Check the real embedded image
                    # resolution, not just the exporter's declared DPI.
                    actual_dpi = pixels[0] * 72 / float(layer.attrib["width"])
                    expect(abs(actual_dpi - 900) < 1,
                           f"{name} contains a point layer below the native 900-DPI contract")

    qualitative_assets = {
        "motion-before.png", "motion-after.png", "failure-axis.png",
        "handle-recovered.png", "handle-context.png", "failure-handle.png",
    }
    for name in qualitative_assets:
        record = manifest["assets"].get(name, {})
        output = ROOT / record.get("output", "")
        source = f"assets/{name}"
        image = images_by_source.get(source, [])
        expect(record.get("kind") == "source_native_prediction_render",
               f"{name} must be a source-native high-resolution prediction render")
        reproduction = record.get("reproduction", {})
        expect(reproduction.get("selection_confirmed") is True and
               reproduction.get("mean_absolute_rgb_difference") == 0 and
               reproduction.get("max_rgb_difference") == 0,
               f"{name} must pass exact original-gallery reproduction before export")
        reference = ROOT / reproduction.get("reference", "")
        expect(reference.is_file() and digest(reference) == reproduction.get("reference_sha256"),
               f"{name} reproduction reference must match the original gallery")
        expect(record.get("renderer", {}).get("native_scatter_dpi", 0) >= 1400,
               f"{name} must be replotted natively, not magnified from the old PDF")
        if output.is_file():
            pixels = png_dimensions(output)
            expect(pixels[0] >= 2400, f"{name} must be at least 2400 pixels wide")
            expect(record.get("pixels") == pixels, f"{name} manifest dimensions must match its PNG")
            expect(len(image) == 1 and [int(image[0].attrs["width"]), int(image[0].attrs["height"])] == pixels,
                   f"HTML dimensions must match the native PNG dimensions for {name}")

    for name, record in manifest["assets"].items():
        if name == "paper.pdf":
            continue
        inputs = record.get("inputs")
        exporter = record.get("exporter")
        expect(isinstance(inputs, list) and len(inputs) > 0, f"{name} needs hashed source inputs")
        expect(isinstance(exporter, dict), f"{name} needs hashed renderer/exporter provenance")
        for reference in (inputs or []) + ([exporter] if isinstance(exporter, dict) else []):
            source = ROOT / reference.get("source", "")
            expected_hash = reference.get("source_sha256")
            expect(source.is_file() and isinstance(expected_hash, str) and digest(source) == expected_hash,
                   f"{name} provenance hash must match local {reference.get('source', '<missing>')}")
    expect(digest(SITE / "assets/paper.pdf") == digest(ROOT / "report/build/main.pdf"), "Staged paper is stale")

    board = json.loads((ROOT / "report/data/leaderboard_public_20260906T090000Z.json").read_text())
    for track in board["tracks"].values():
        ranked = track["api_response"]["results"]
        expect(ranked[0]["submission__participant_team__team_name"] == "TnG", "Challenge first-place claim differs from snapshot")
    if errors:
        raise SystemExit("Website checks failed:\n- " + "\n- ".join(errors))
    print(f"PASS: {links} local URLs, {len(measurements)} source-linked measurements, 9 verified scientific assets, authorship and unified-task framing.")
    print("Scope: source/evidence checks; browser layout and interactions are checked separately.")


if __name__ == "__main__":
    main()
