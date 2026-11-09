#!/usr/bin/env python3
"""Quantify how visible each STROKE_VARIANTS flag is at the size the approval page displays it.

Every review character is rendered in headless Chrome with the baseline flags (all off, like
stroke_approval.html) and with baseline + one variant. Both renders are box-downsampled to the on-screen
card size (~264 px) and compared on ink darkness:

  visible_px   display pixels whose darkness changes by >= DELTA (default 0.10 of full scale)
  blob_px      largest 8-connected region of such pixels (scattered single-pixel noise is not "noticeable")
  emd_px       sliced earth mover's distance between the two normalised ink-mass distributions, in display px
  mass_pct     relative change of total ink mass

A variant counts as visibly noticeable on a character when blob_px >= MIN_BLOB (one coherent changed region)
or visible_px >= MIN_SPREAD (many small changes spread along the contour, e.g. a roughened edge). MIN_SPREAD is
calibrated on the round-1 review, where a variant changing <= 125 display px was rated "too subtle".

CLI:
    python3 scripts/audit/variant_visibility.py [--variants strongCefeng,ellipticalCaps] [--chars 永国] [--app-js PATH]
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.stats import wasserstein_distance

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.audit.evaluate_brushwork_canvas import APP_JS_PATH, extract_strokes_for_characters, find_chrome_binary  # noqa: E402

REVIEW_CHARS = ["永", "道", "心", "成", "水", "井", "力", "九", "長", "必", "国", "日"]
FULL = 792
DOWN = 3  # 792 / 3 = 264 px, the approximate width of one card canvas in stroke_approval.html
DELTA = 0.10
MIN_BLOB = 25
MIN_SPREAD = 250
N_PROJ = 48


def _render_all(app_js: str, chars: list[str], configs: dict[str, dict[str, bool]]) -> dict[str, dict[str, np.ndarray]]:
    strokes = extract_strokes_for_characters(chars)
    script = f"""
(function() {{
  const STROKES = {json.dumps({c: strokes[c] for c in chars if c in strokes}, ensure_ascii=False)};
  const CONFIGS = {json.dumps(configs)};
  const FULL = {FULL}, DOWN = {DOWN}, W = FULL / DOWN;
  const out = {{}};
  try {{
    for (const ch of Object.keys(STROKES)) {{
      out[ch] = {{}};
      for (const [name, flags] of Object.entries(CONFIGS)) {{
        for (const k of Object.keys(STROKE_VARIANTS)) STROKE_VARIANTS[k] = !!flags[k];
        const canvas = document.createElement("canvas");
        canvas.width = FULL; canvas.height = FULL;
        const ctx = canvas.getContext("2d", {{ willReadFrequently: true }});
        ctx.fillStyle = "#f4efe3"; ctx.fillRect(0, 0, FULL, FULL);
        const ss = STROKES[ch];
        ss.forEach((s, i) => {{
          const c = compileStrokePhysics({{ d: s.d, type: s.type || "", component: s.component || "", index: i + 1 }}, 0, 0, FULL, ss.length);
          if (c) renderFullCompiledStroke(ctx, c, {{ toneMode: "sumi", opacity: 1.0 }});
        }});
        const px = ctx.getImageData(0, 0, FULL, FULL).data;
        const paperLum = 0.299 * 0xf4 + 0.587 * 0xef + 0.114 * 0xe3;
        const small = new Uint8Array(W * W);
        for (let y = 0; y < W; y++) for (let x = 0; x < W; x++) {{
          let acc = 0;
          for (let dy = 0; dy < DOWN; dy++) for (let dx = 0; dx < DOWN; dx++) {{
            const i = ((y * DOWN + dy) * FULL + (x * DOWN + dx)) * 4;
            acc += Math.max(0, paperLum - (0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]));
          }}
          small[y * W + x] = Math.min(255, Math.round(acc / (DOWN * DOWN) * 255 / paperLum));
        }}
        let bin = "";
        for (let i = 0; i < small.length; i++) bin += String.fromCharCode(small[i]);
        out[ch][name] = btoa(bin);
      }}
    }}
    const o = document.createElement("script"); o.id = "vis-out"; o.type = "application/json";
    o.textContent = JSON.stringify(out); document.body.appendChild(o);
  }} catch (e) {{
    const o = document.createElement("script"); o.id = "vis-err"; o.type = "application/json";
    o.textContent = JSON.stringify(String(e && e.stack || e)); document.body.appendChild(o);
  }}
}})();
"""
    html = f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><script>{app_js}</script><script>{script}</script></body></html>'
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        path = f.name
    proc = subprocess.run(
        [find_chrome_binary(), "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=120000", "--dump-dom", f"file://{path}"],
        capture_output=True, text=True, check=False, timeout=600,
    )
    Path(path).unlink(missing_ok=True)
    err = re.search(r'<script id="vis-err" type="application/json">(.*?)</script>', proc.stdout, re.DOTALL)
    if err:
        raise RuntimeError(json.loads(err.group(1)))
    m = re.search(r'<script id="vis-out" type="application/json">(.*?)</script>', proc.stdout, re.DOTALL)
    if not m:
        raise RuntimeError("no output from headless Chrome: " + proc.stderr[-800:])
    w = FULL // DOWN
    raw = json.loads(m.group(1))
    return {
        ch: {name: np.frombuffer(base64.b64decode(b64), dtype=np.uint8).reshape(w, w).astype(np.float64) / 255.0 for name, b64 in cfgs.items()}
        for ch, cfgs in raw.items()
    }


def sliced_emd(a: np.ndarray, b: np.ndarray, n_proj: int = N_PROJ) -> float:
    """Sliced Wasserstein-1 distance (px) between two non-negative images treated as mass distributions."""
    if a.sum() <= 0 or b.sum() <= 0:
        return 0.0
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    coords = np.stack([xs.ravel(), ys.ravel()], axis=1).astype(np.float64)
    wa, wb = a.ravel(), b.ravel()
    total = 0.0
    for k in range(n_proj):
        th = np.pi * k / n_proj
        proj = coords @ np.array([np.cos(th), np.sin(th)])
        total += wasserstein_distance(proj, proj, wa, wb)
    return total / n_proj


def compare(base: np.ndarray, alt: np.ndarray) -> dict[str, float]:
    diff = np.abs(alt - base)
    vis = diff >= DELTA
    labels, n = ndimage.label(vis, structure=np.ones((3, 3)))
    blob = int(np.bincount(labels.ravel())[1:].max()) if n else 0
    mass_b = base.sum()
    return {
        "visible_px": int(vis.sum()),
        "blob_px": blob,
        "emd_px": round(sliced_emd(base, alt), 3),
        "mass_pct": round(100.0 * (alt.sum() - mass_b) / max(mass_b, 1e-9), 2),
        "max_delta": round(float(diff.max()), 3),
    }


def evaluate(app_js: str, chars: list[str], variants: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    configs = {"baseline": {}}
    for v in variants:
        configs[v] = {v: True}
    renders = _render_all(app_js, chars, configs)
    return {v: {ch: compare(renders[ch]["baseline"], renders[ch][v]) for ch in renders} for v in variants}


def is_visible(r: dict[str, float]) -> bool:
    return r["blob_px"] >= MIN_BLOB or r["visible_px"] >= MIN_SPREAD


def print_report(results: dict[str, dict[str, dict[str, float]]]) -> None:
    for v, per_char in results.items():
        print(f"\n== {v} ==  (visible = blob >= {MIN_BLOB} or changed >= {MIN_SPREAD} display px at 1/{DOWN} scale, delta >= {DELTA})")
        print(f"{'char':<5}{'visible_px':>11}{'blob_px':>9}{'emd_px':>9}{'mass_%':>9}{'max_d':>8}  verdict")
        n_vis = 0
        for ch, r in per_char.items():
            ok = is_visible(r)
            n_vis += ok
            print(f"{ch:<5}{r['visible_px']:>11}{r['blob_px']:>9}{r['emd_px']:>9.3f}{r['mass_pct']:>9.2f}{r['max_delta']:>8.3f}  {'VISIBLE' if ok else '-'}")
        print(f"-> noticeable on {n_vis}/{len(per_char)} characters")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variants", default="", help="comma-separated variant ids (default: all STROKE_VARIANTS keys)")
    ap.add_argument("--chars", default="".join(REVIEW_CHARS))
    ap.add_argument("--app-js", default=str(APP_JS_PATH))
    ap.add_argument("--json", help="also write results to this JSON file")
    args = ap.parse_args(argv)
    app_js = Path(args.app_js).read_text(encoding="utf-8")
    if args.variants:
        variants = [v for v in args.variants.split(",") if v]
    else:
        block = re.search(r"const\s+STROKE_VARIANTS\s*=\s*\{([^}]*)\};", app_js)
        variants = re.findall(r"^\s*([A-Za-z0-9_$]+)\s*:", block.group(1), re.MULTILINE) if block else []
    results = evaluate(app_js, list(args.chars), variants)
    print_report(results)
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
