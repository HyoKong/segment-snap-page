# Website asset evidence

`assets/manifest.json` is the machine-readable provenance record for every image and the
downloadable PDF staged by `scripts/prepare_assets.py`. It records source, renderer and input
SHA-256 hashes, crop bounds, output hashes/dimensions, and the intended interpretation.

The teaser and pipeline are source-native SVG exports of the current report drawing functions.
Typography, arrows and geometry remain vectors; measured RGB scatter layers are re-rendered at
900 DPI. The exporters call the original drawing functions through a return-figure option, so
they do not rewrite report figures or their evidence manifests. The two figures remain method
illustrations, not prediction galleries. `paper.pdf` is a byte-for-byte copy of the current report build.

The six qualitative PNGs are native Matplotlib re-renders of the same selected predictions,
at least 2400px wide. The original PDFs contained 100-DPI scatter layers: rendering those PDFs
at a higher resolution would only magnify existing pixels. Instead, `scripts/render_qualitative.py`
runs the unchanged gallery producers on saved prediction artifacts and exports their live plot
artists at the new resolution. The verified PDF-space rectangles still exclude producer title
bands, scene/specimen identifiers and gallery footers. Predictions, colors, geometry, camera
conventions and in-panel labels are preserved; there is no image upscaling or neural inference.
These remain selected validation examples, not per-example AP evidence.

Reproduction gate: before high-resolution export, both full gallery producers reproduce their
original 190-DPI PNGs with exact RGB equality (mean and maximum difference both zero). This also
checks the dense artifact and losslessly unpacked union used by the handle renderer. The new
exports use fresh 1400-DPI scatter layers inside temporary PDFs, then native Poppler rendering
of the unchanged panel rectangles. Hinge panels are 2400×2329px; handle panels are 2400×1846px.
The original report galleries and all saved predictions remain unchanged.

The source gallery's visualization matching and labels are class-agnostic illustrations. They do
not replace the benchmark evaluator's IoU/AP matching protocol. Its footer counts are deliberately
not presented on the site because they are producer-specific populations and must not be interpreted
as AP evidence.

## Selected panels

| Website asset | Source panel | Meaning |
| --- | --- | --- |
| `motion-before.png` | Hinge gallery, first column / centroid row | Same specimen and predicted part as the paired after panel; 0.42 m line error, FAIL. |
| `motion-after.png` | Hinge gallery, first column / handle-guided row | Same specimen and predicted part, separately computed projection frame; 0.05 m line error, PASS. |
| `handle-recovered.png` | Handle gallery, third column | Selected median-size child-only recovered handle. |
| `handle-context.png` | Handle gallery, sixth column | Selected matched child relabelled by its containing movable part. |
| `failure-axis.png` | Hinge gallery, fourth column / handle-guided row | Selected nonvertical-hinge failure. |
| `failure-handle.png` | Handle gallery, fifth column | Selected overextended dense-handle prediction. |

Run `python3 website/scripts/prepare_assets.py` after a verified report rebuild to refresh the staged
assets and manifest. It uses the existing `.venv` plotting environment and saved local data, without
network access or model inference. The fixed hinge specimen list and the handle producer's original
deterministic selection rule are preserved. Reproduction checks guard against silently changing
the illustrated specimens. Exports are staged before replacing the live assets. Previous website
bitmaps are retained in the ignored `preview/resolution-before.zip` review archive.

## Reader-facing legends

The source crops omit the gallery-wide legend, so the website supplies a separate key beside
each example. In the recovery and overextended-mask panels, black is the annotated handle.
In the context-correction panel, black is the **predicted child handle**, and green is the
predicted containing part (`experiments/fig_complementarity.py:159-180`). Do not reuse a
single “black = ground truth” legend across the handle gallery. In hinge panels, green is the
predicted part, black is the annotated hinge line, and the colored dot/segment show the
predicted origin and its perpendicular error. PASS means origin error below 0.25 m, not
that every condition of a full detection is correct (`experiments/fig_hinge_gallery.py:75-115`).

## Comparison alignment audit — September 21, 2026

The hinge pair is not pixel-registered. In `experiments/fig_hinge_gallery.py:80`, `panel()` chooses
the origin for each arm, then passes it to `frame()` at line 82. `frame()` flips the viewing normal
using that origin as the `toward` point (lines 55–60). This can reverse the projected direction
between rows even though the specimen and predicted part are identical. A whole-image selector
is therefore used on the website; there is no spatial wipe or interpolated prediction.

The gallery's source docstring/report describe a shared view, but that is not guaranteed by the
current renderer. Before introducing a registered slider or reusing the shared-camera claim,
compute one projection frame per specimen and reuse it across both rows. The prediction-gallery
renderers and report artwork were not modified as part of the website revisions; only the
illustration functions gained an optional return-figure export hook.
