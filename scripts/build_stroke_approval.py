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
        "params": [
            {"key": "exitDepth", "label": "End-cap roundness", "min": 0.15, "max": 0.8, "step": 0.01},
            {"key": "entryDepth", "label": "Start-cap roundness", "min": 0.1, "max": 0.7, "step": 0.01},
            {"key": "ellipticityGain", "label": "Extra roundness when the tuft is flattened", "min": 0.0, "max": 0.8, "step": 0.02},
        ],
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
        "params": [
            {"key": "shiftGain", "label": "Tuft shift toward one edge", "min": 0.0, "max": 0.6, "step": 0.01},
            {"key": "shiftCap", "label": "Maximum shift (fraction of width)", "min": 0.05, "max": 0.6, "step": 0.01},
            {"key": "toneGain", "label": "Tip-side vs. belly-side tone contrast", "min": 1.0, "max": 5.0, "step": 0.1},
            {"key": "entryFloor", "label": "Shift already present at an exposed-tip start", "min": 0.0, "max": 1.0, "step": 0.05},
        ],
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
        "params": [
            {"key": "naFootLen", "label": "捺 foot taper length (KanjiVG units)", "min": 3, "max": 20, "step": 0.5},
            {"key": "sweepLen", "label": "撇 taper length (KanjiVG units)", "min": 8, "max": 45, "step": 1},
        ],
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
