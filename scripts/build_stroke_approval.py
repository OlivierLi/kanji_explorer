#!/usr/bin/env python3
"""Build ``stroke_approval.html``: a self-contained review page for the opt-in stroke-shape variants.

The page inlines ``static/app.js`` and the KanjiVG strokes of a few review characters, renders every variant next to the
baseline on <canvas>, and lets the reviewer approve / reject / request tweaks per variant. Decisions are stored in
localStorage and can be exported as JSON, which ``scripts/apply_stroke_approvals.py`` turns into new defaults.

Usage:  python3 scripts/build_stroke_approval.py  [--out stroke_approval.html]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.audit.evaluate_brushwork_canvas import APP_JS_PATH, extract_strokes_for_characters  # noqa: E402

REVIEW_CHARS = ["永", "道", "心", "成", "水", "井", "力", "九", "長", "必", "国", "日"]

VARIANTS = [
    {
        "id": "ellipticalCaps",
        "title": "Elliptical start / end caps",
        "jp": "楕円断面の起筆・収筆",
        "summary": "Pressed starts and tome (stop) ends become half-ellipses whose depth follows the simulated tuft flattening, instead of a nearly flat chop.",
        "why": "Chu & Tai 2002 Sec. 4.1.2 / 2004 model the tuft footprint as two half-ellipses; Xu et al. 2004 Eq. 18 elongates the ellipse with sideways drag. The current caps use fixed shallow fractions of the width and never read the ellipticity the model already computes.",
        "affects": "Every stroke with a blunt start or end (horizontals, verticals, dots, 横折 ends). Sharp-tipped strokes (撇 / 捺 tails, 鉤) are unchanged.",
        "risk": "Ends look rounder / softer. May feel less crisp for a 瘦金體 (slender gold) style that prefers squared ends.",
        "look_for": "Left and right ends of horizontals, the top of verticals, dots.",
    },
    {
        "id": "mitreCorners",
        "title": "Mitred outer corners",
        "jp": "折れ角の外側を鋭角に（マイター）",
        "summary": "At sharp turns (横折, 竖折, zigzags) the outer edge becomes a crisp mitre vertex instead of a round join, and the corner bulge scales with the turn angle.",
        "why": "Hsu & Lee 1994 Sec. 4.1 and Fig. 5 describe mitre / bevel / round joints for strongly bent strokes. Currently the outer shoulder is a constant boost followed by Laplacian + Chaikin smoothing, which always yields a round join.",
        "affects": "Strokes with a detected corner of at least ~30 degrees: 口 / 国 boxes, 横折, 竖折, 横折钩 bodies, zigzag 折.",
        "risk": "Bevel fallback is used when the spike would exceed 2.6 half-widths. Very acute turns are left alone (撇折). Corners can look hard or mechanical for a brush-like feel.",
        "look_for": "Top-right corner of 口 / 日 / 国 boxes; the 折 corners in 道 and 永.",
    },
    {
        "id": "strongCefeng",
        "title": "Stronger oblique-brush (側鋒) posture",
        "jp": "側鋒の効果を強める",
        "summary": "When the brush is slanted (側鋒) the tuft clearly shifts toward one stroke edge and the tone becomes asymmetric (tip side darker, belly side lighter); exposed-tip (露鋒) starts keep that shift from the first millimetre.",
        "why": "Xie et al. 2013 Sec. 4.1: in the oblique style the tip touches one side of the boundary and the belly is tangent to the other; Chu & Tai 2002 Sec. 2 describes slanted strokes the same way. Today the spine moves only ~5% of the width, so upright and oblique strokes look the same.",
        "affects": "All strokes whose entry direction differs from the nib angle (mostly 撇, 点, 横 with a slanted attack).",
        "risk": "Shifts where the contour sits relative to the KanjiVG centreline (a few px) and raises tonal contrast across the width. Strength is a model choice rather than a measured value.",
        "look_for": "Tonal asymmetry across 撇 and 点, slight lateral offset of slanted 横.",
    },
    {
        "id": "dryKasure",
        "title": "Dry-brush splits driven by wetness (飛白)",
        "jp": "渇筆（かすれ）を墨量シミュレーションに連動",
        "summary": "Hairline gaps appear wherever the simulated tuft has run low on ink, on any long stroke (not only long 撇); in very dry tails the gaps stay open to the tip so it forks into a few prongs.",
        "why": "Chu & Tai 2004 'Dry brush': ink deposits only where the dry map peaks, with a threshold set by brush wetness and pressure; Chu & Tai 2002 Sec. 3: a drying tuft splits, giving the flying-white effect; Xu et al. 2004 Sec. 5.5 splits the tuft when stress exceeds a threshold. Today kasure is hard-gated to 撇 over 45 units and ignores the wetness the model computes.",
        "affects": "Long strokes (about 60+ units) get faint feibai near the end; short strokes stay solid. Strength follows the existing 'kasure amount' slider.",
        "risk": "Adds visible texture to strokes that were clean. Depletion is a model heuristic, so which strokes dry out is a tuning decision.",
        "look_for": "Tails of 撇 / 捺, ends of long 横 and 竖.",
    },
    {
        "id": "anchoredEnds",
        "title": "Stroke-end forms keep absolute size",
        "jp": "払い・捺の長さを絶対長に固定",
        "summary": "The 捺 wave-foot and the 撇 taper keep a fixed physical length (capped) instead of stretching with the whole stroke, so a long stroke no longer gets an extremely long thin tail.",
        "why": "Hsu & Lee 1994 Sec. 4.1: stroke-end features such as serifs should be anchored so they keep their proportions while the body stretches with the path. Currently fractions of total length are used (foot from u=0.72, taper from u=0.43).",
        "affects": "Long 捺 (over ~32 units) and long free 撇 (over ~42 units). Short strokes are identical.",
        "risk": "Long sweeps become fatter for longer and then taper more abruptly, which changes the elegant long taper typical of slender-gold style.",
        "look_for": "The long 捺 in 道 / 永 / 長, the long 撇 in 井 / 力.",
    },
    {
        "id": "wetDryTrim",
        "title": "Paper-fibre wet/dry edge trimming",
        "jp": "紙繊維による滲み境界のトリミング",
        "summary": "The silhouette is trimmed where the low-passed wet mask minus a paper-fibre roughness term falls below zero, so the edge follows the fibres instead of the ideal contour. Colour and darkness are untouched.",
        "why": "Chu & Tai 2005 (MoXi) Sec. 6.1 / Eq. 11 trims the output where phi = rho_tau + r_scale (r + r_bias) < 0, with r a blurred random-spot texture, for natural, slightly rough boundaries.",
        "affects": "Every stroke edge. Effect is subtle; use the swipe compare to see it.",
        "risk": "Slightly ragged silhouettes. Interacts with the nijimi halo thresholds used by the audit metrics, which would be rechecked.",
        "look_for": "Edges at 2-3x zoom in the swipe compare.",
    },
]


def build_html(out_path: Path) -> None:
    strokes = extract_strokes_for_characters(REVIEW_CHARS)
    data = {
        "chars": REVIEW_CHARS,
        "strokes": {ch: strokes[ch] for ch in REVIEW_CHARS if ch in strokes},
        "variants": VARIANTS,
    }
    template = (BASE_DIR / "scripts" / "stroke_approval_template.html").read_text(encoding="utf-8")
    app_js = APP_JS_PATH.read_text(encoding="utf-8")
    if "</script" in app_js:
        raise SystemExit("static/app.js contains '</script'; cannot inline it safely")
    html = template.replace("/*__APP_JS__*/", app_js).replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size // 1024} KiB), {len(VARIANTS)} variants, {len(data['strokes'])} characters")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(BASE_DIR / "stroke_approval.html"))
    args = parser.parse_args()
    build_html(Path(args.out))


if __name__ == "__main__":
    main()
