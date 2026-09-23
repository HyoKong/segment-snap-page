# Segment–Snap project website

Source for the research project page at the author-supplied canonical URL:
[hyokong.github.io/segment-snap-page](https://hyokong.github.io/segment-snap-page/).
These files are maintained and verified locally; editing them does not deploy the site.

## Preview

Open [index.html](index.html) directly in a browser, or serve the folder from the repository root:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory website
```

Visit **http://localhost:8765/**. This server is local to the machine running it. The page also works under the nested `/segment-snap-page/` project path.

The page presents the unified interaction-understanding task, three predictors, training-free motion decoding, both coupling directions, controlled validation gains, final challenge results, and selected qualitative successes and failures. The current report PDF, a technical-report citation, and the author-supplied [GitHub repository](https://github.com/HyoKong/Segment-Snap) and [Hugging Face checkpoint page](https://huggingface.co/imsuperkong/Segment-Snap) are included. An arXiv or publication link has not been supplied and is intentionally omitted.

The revised layout is Apple-inspired, not an Apple clone: white and pale-gray surfaces, charcoal typography, a slim translucent header, restrained blue actions, and larger unframed figures. There are no Apple assets or downloaded proprietary fonts. The original first-review sources are preserved in `preview/design-v1.zip`.

The latest revision keeps “Geometric and Semantic Coupling” on one rendered line at desktop/tablet widths (768px and above), with readable wrapping on phones. The qualitative section now introduces the question behind each category and supplies panel-specific legends, controlled-comparison explanations, and takeaways. The preceding two-line-title version is preserved in `preview/design-v2.zip`.

Figure-quality update: the teaser and pipeline now use self-contained SVGs with vector text/arrows
and native 900-DPI RGB point layers. All six qualitative panels are replotted from saved predictions
at least 2400px wide, rather than enlarging the low-resolution scatter layers inside the original
PDFs. The page and enlarged views use the same high-quality masters. The approved layout and
scientific examples are unchanged; earlier image exports are archived in `preview/resolution-before.zip`.

In **See the difference → Hinge placement**, select **Centroid** or **Handle-guided** to compare the two complete predictions. Arrow keys and Home/End also switch the selected view. A source-renderer audit found that the paired panels use different projection frames, so a spatial wipe would imply false pixel registration. The website deliberately uses a whole-image switch and explains the distinction; see `EVIDENCE.md`. Example tabs, full-size figure dialogs, optional section entrances, and citation copying remain keyboard accessible. Motion preferences are respected, including changes while the page is open.

## Editing

| File | Purpose |
| --- | --- |
| `index.html` | Scientific copy, result values, figure captions, authors, links |
| `styles.css` | White/charcoal visual system, typography, mobile and print styles |
| `app.js` | Whole-image before/after selector, example tabs, figure enlargement, restrained entrances, citation copying |
| `assets/` | Paper figures, selected qualitative panels, PDF, favicon |
| `EVIDENCE.md` | Internal provenance and interpretation notes; not website content |
| `assets/manifest.json` | Internal source/output hashes and exact PDF panel selections |
| `scripts/render_illustrations.py` | Reuse report drawing functions for vector / 900-DPI SVG exports |
| `scripts/render_qualitative.py` | Replot selected saved predictions at native high resolution |
| `scripts/prepare_readme_assets.py` | Generate local README resource buttons and copy the verified vector teaser |
| `assets/icons/` | Shared GitHub, Hugging Face, project, and paper icons with source/license notes |
| `../DESIGN.md` | Design decisions and implementation constraints |

All required page assets are local, with relative URLs; resource buttons link to the supplied external destinations. There is no build system, framework, package install, analytics, external font, or third-party JavaScript. The full scientific content remains available without JavaScript; the comparison becomes two complete labelled images and all gallery categories remain visible.

## Refresh and verify

After rebuilding the paper or updating its figures, refresh the staged assets:

```sh
python3 website/scripts/prepare_assets.py
python3 website/scripts/check_site.py
node --check website/app.js
node --experimental-websocket website/scripts/test_browser.mjs
```

For a text-only paper update, avoid replotting unchanged scientific figures:

```sh
python3 website/scripts/prepare_assets.py --paper-only
```

After changing a shared icon or the teaser, refresh the public repository's README assets:

```sh
python3 website/scripts/prepare_readme_assets.py
```

Both surfaces use local SVG icons; the README buttons embed their icons instead of depending
on a remote badge service. The README teaser is identical to `assets/teaser.svg`.
The canonical project URL is present in website metadata, citations, the paper, and the README's
Project page button. Buttons avoid self-links: the website shows Paper / Code / Hugging Face;
the README shows Project page / Hugging Face. Website icons are decorative and paired with
visible link labels.

Asset preparation uses the repository's existing `.venv/bin/python` plotting environment and Poppler.
It needs the saved local prediction artifacts and point clouds, but no GPU, inference run or new
dependency. Allow several minutes for reading the prediction files and redrawing the galleries.
Source rectangles, prediction geometry and labels are unchanged; reproduction checks compare with
the original galleries. Quantitative markers are checked against the report's evidence ledger.
The script reports stale sources or mismatches instead of accepting substitute illustrations.

Browser checks use the installed Chrome and Node 20 native WebSocket support, with no npm dependencies. They test nested-path and direct-file previews, exact resource destinations, image/PDF loading, 320–1440 px layouts, all gallery categories at narrow widths, before/after keyboard and selected states, figure-dialog focus, citation copying and its fallback, reduced motion, and no-JavaScript behavior. High-density checks cover 2× desktop and 3× mobile displays, the actual pixel capacity of each result panel, and SVG/PNG dialog sources. Screenshots and the machine-readable verdict are generated in `preview/` (git-ignored).

Verified September 21, 2026: 78 browser checks passed, including canonical URLs, resource icons without self-links, button alignment, local README asset rendering, 2× desktop / 3× mobile pixel capacity, high-resolution dialogs, actual title line counts at 768/820/1024/1440px and visible legends in every gallery category. The first-place callout is visible above the title without scrolling at 320/390/820/1440px, meets 4.5:1 text contrast, and remains visible without JavaScript. It links to the official leaderboard and the dated result details; test scores remain separate from validation gains. Both original prediction galleries were reproduced with exact RGB equality before high-resolution export. Desktop, tablet, mobile, pipeline, quantitative-results, per-category, and README asset previews are saved in `preview/`. The README preview uses GitHub-like image sizing; it does not test GitHub's production renderer. This is local review, not a deployed site.

## Deployment files

After the design is approved, the deployable content is only:

```text
index.html
styles.css
app.js
.nojekyll
assets/*.png
assets/teaser.svg
assets/pipeline.svg
assets/paper.pdf
assets/favicon.svg
assets/icons/
```

Do not publish the whole experiment repository. The internal evidence manifest, preparation/test
scripts, preview screenshots, and review notes are not needed for hosting. Keep the icon
source/license notice with `assets/icons/`. Canonical metadata already points to
`https://hyokong.github.io/segment-snap-page/`; no deployment command is run by these tools.

The supplied project URL returned HTTP 404 in the September 21 check. This is an external hosting
status, not a reason to rewrite the author's URL or to block local preview. The code and
checkpoint links likewise use the exact author-supplied destinations; this edit makes no new
claim about their remote availability.

Validation gains and the September 6, 2026 test-leaderboard snapshot are deliberately separate. Part-only and full-context label corrections are alternatives from the same handle union, not additive gains. The website's qualitative examples illustrate behavior, not the population frequency or per-example AP.
