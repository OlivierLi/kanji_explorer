"""
tests/test_ink_physics_canvas_validation.py

Programmatic HTML Canvas mathematical validation for physically-based Xuan paper,
D2Q9 Lattice Boltzmann percolation, contact-line coffee-ring edge darkening,
colloidal glue/soot chromatic separation, skeletal bristle-track striations,
calligraphic dwell pooling, two-flux Kubelka-Munk optical layering (I1-I8),
and the Interactive Advanced Ink & Paper Settings Panel UI.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import view_renderer
from scripts.audit.evaluate_brushwork_canvas import (
    APP_JS_PATH,
    BASE_DIR,
    build_evaluation_html,
    evaluate_defects,
    evaluate_ink_physics_defects,
    extract_strokes_for_characters,
    find_chrome_binary,
    run_headless_evaluator,
)


def test_advanced_ink_settings_panel_in_index_and_view_html() -> None:
    """Verify the Advanced Ink & Paper Settings Panel is present in both / and /view."""
    index_html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
    styles_css = (BASE_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    expected_ids = [
        "btnInkSettingsToggle",
        "inkPhysicsSettingsPanel",
        "btnResetInkPhysics",
        "inkPresetRow",
    ]
    for elem_id in expected_ids:
        assert f'id="{elem_id}"' in index_html, f"Missing #{elem_id} in static/index.html"

    expected_presets = ["standard", "raw_xuan", "sized_feibai", "light_wash"]
    for preset in expected_presets:
        assert f'data-preset="{preset}"' in index_html, f"Missing preset {preset} in static/index.html"

    expected_params = [
        "paperGrainIntensity",
        "coffeeRingIntensity",
        "nijimiIntensity",
        "bristleStriationIntensity",
        "dwellPoolingIntensity",
        "kmTransmittanceContrast",
        "glueChromaticWarmth",
        "kasureAmount",
    ]
    for param in expected_params:
        assert f'data-param="{param}"' in index_html, f"Missing slider {param} in static/index.html"
        assert f'data-val-for="{param}"' in index_html, f"Missing value badge for {param} in static/index.html"

    assert ".ink-physics-panel" in styles_css
    assert ".ink-physics-slider" in styles_css

    # Check /view renderer output
    view_html = view_renderer.render_side_by_side_html(
        canonical_char="永",
        meta={"codepoint": "U+6C38", "stroke_count": 5},
        params={"mode": ["kvg"]},
    )
    for elem_id in expected_ids:
        assert f'id="{elem_id}"' in view_html, f"Missing #{elem_id} in /view HTML"
    for param in expected_params:
        assert f'data-param="{param}"' in view_html, f"Missing slider {param} in /view HTML"


def test_canvas_ink_physics_metrics_i1_to_i8_zero_defects() -> None:
    """Validate mathematical ink & paper metrics I1-I8 and brushwork metrics M1-M12 on canvas pixels."""
    chars = ["永", "水", "道", "心", "成", "井"]
    char_strokes = extract_strokes_for_characters(chars)
    app_js = APP_JS_PATH.read_text(encoding="utf-8")
    html = build_evaluation_html(char_strokes, app_js)
    results = run_headless_evaluator(html)

    total_strokes = 0
    crossing_strokes = 0
    for ch in chars:
        assert ch in results, f"Missing evaluation result for {ch}"
        cdata = results[ch]
        assert cdata["fullRenderSuccess"] is True
        assert cdata["fullInkPixels"] > 1000
        for s in cdata["strokes"]:
            total_strokes += 1
            if s.get("hasCrossing"):
                crossing_strokes += 1
            ink_defects = evaluate_ink_physics_defects(s)
            all_defects = evaluate_defects(s)
            failed_ink = [k for k, v in ink_defects.items() if v]
            failed_all = [k for k, v in all_defects.items() if v]
            assert not failed_ink, f"{ch} stroke #{s['strokeIndex']} failed ink metrics {failed_ink}: {s}"
            assert not failed_all, f"{ch} stroke #{s['strokeIndex']} failed brushwork/ink metrics {failed_all}: {s}"

    assert total_strokes >= 25
    assert crossing_strokes >= 4


def test_ink_physics_sliders_and_presets_monotonic_canvas_response() -> None:
    """Verify that tweaking advanced settings sliders & presets produces monotonic mathematical changes on canvas."""
    char_strokes = extract_strokes_for_characters(["永"])
    app_js = APP_JS_PATH.read_text(encoding="utf-8")

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<button type="button" id="btnInkSettingsToggle" aria-expanded="false"></button>
<div id="inkPhysicsSettingsPanel" hidden>
  <button type="button" id="btnResetInkPhysics"></button>
  <button type="button" class="btn-ink-preset active" data-preset="standard"></button>
  <button type="button" class="btn-ink-preset" data-preset="raw_xuan"></button>
  <button type="button" class="btn-ink-preset" data-preset="sized_feibai"></button>
  <button type="button" class="btn-ink-preset" data-preset="light_wash"></button>
  <input type="range" class="ink-physics-slider" data-param="paperGrainIntensity" value="1.35">
  <span class="ink-slider-val" data-val-for="paperGrainIntensity">1.35</span>
</div>
<canvas id="c" width="792" height="792"></canvas>
<script>{app_js}</script>
<script>
(function() {{
  initInkPhysicsSettingsPanel();
  const strokes = {json.dumps(char_strokes["永"])};
  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d", {{ willReadFrequently: true }});
  const W = 792, H = 792;
  const paper = getXuanPaperSubstrate(W, H);
  const s0 = strokes[1]; // multi-segment main stroke of 永

  function measureStrokeWithParams(overrides) {{
    resetInkPhysicsSettings();
    for (const [k, v] of Object.entries(overrides)) {{
      updateInkPhysicsParameter(k, v);
    }}
    ctx.clearRect(0, 0, W, H);
    const compiled = compileStrokePhysics({{
      d: s0.d, type: s0.type, component: s0.component, index: 2
    }}, 0, 0, W, strokes.length);
    renderFullCompiledStroke(ctx, compiled, {{ toneMode: "sumi", opacity: 1.0 }});
    const raw = ctx.getImageData(0, 0, W, H).data;

    let valleyD = 0, vCnt = 0, ridgeD = 0, rCnt = 0;
    let rimD = 0, rimCnt = 0, troughD = 0, trCnt = 0;
    let haloBleed = 0, haloTotal = 0;
    let thinW = 0, thinCnt = 0, thickW = 0, thickCnt = 0;

    for (let y = 8; y < H - 8; y++) {{
      const rowOff = y * W;
      for (let x = 8; x < W - 8; x++) {{
        const idx = rowOff + x;
        const pOff = idx * 4;
        const a = raw[pOff + 3];
        const minN1 = Math.min(raw[((y-1)*W+x)*4+3], raw[((y+1)*W+x)*4+3], raw[(rowOff+x-1)*4+3], raw[(rowOff+x+1)*4+3]);
        const maxN2 = Math.max(raw[((y-1)*W+x)*4+3], raw[((y+1)*W+x)*4+3], raw[(rowOff+x-1)*4+3], raw[(rowOff+x+1)*4+3],
                               raw[((y-2)*W+x)*4+3], raw[((y+2)*W+x)*4+3], raw[(rowOff+x-2)*4+3], raw[(rowOff+x+2)*4+3]);
        if (a < 30) {{
          if (maxN2 >= 80) {{
            haloTotal++;
            haloBleed += a;
          }}
          continue;
        }}
        if (a >= 110 && minN1 >= 80) {{
          const r = raw[pOff], g = raw[pOff+1], b = raw[pOff+2];
          const lum = 0.299 * r + 0.587 * g + 0.114 * b;
          const dark = (a / 255.0) * (255.0 - lum);
          const gZero = paper.zeroB5Grain[idx];
          if (gZero < -0.22) {{ valleyD += dark; vCnt++; }}
          else if (gZero > 0.22) {{ ridgeD += dark; rCnt++; }}

          const minN23 = Math.min(raw[((y-2)*W+x)*4+3], raw[((y+2)*W+x)*4+3], raw[(rowOff+x-2)*4+3], raw[(rowOff+x+2)*4+3],
                                  raw[((y-3)*W+x)*4+3], raw[((y+3)*W+x)*4+3], raw[(rowOff+x-3)*4+3], raw[(rowOff+x+3)*4+3]);
          const minN5 = Math.min(raw[((y-5)*W+x)*4+3], raw[((y+5)*W+x)*4+3], raw[(rowOff+x-5)*4+3], raw[(rowOff+x+5)*4+3]);
          if (minN23 < 60) {{ rimD += dark; rimCnt++; }}
          else if (minN23 >= 100 && minN5 < 80) {{ troughD += dark; trCnt++; }}

          if (a <= 188) {{ thinW += (r - b); thinCnt++; }}
          else if (a >= 202) {{ thickW += (r - b); thickCnt++; }}
        }}
      }}
    }}
    return {{
      valleyRidgeContrast: (valleyD / Math.max(1, vCnt)) - (ridgeD / Math.max(1, rCnt)),
      coffeeRingRimDelta: (rimD / Math.max(1, rimCnt)) - (troughD / Math.max(1, trCnt)),
      nijimiFringeRatio: haloBleed / Math.max(1, haloTotal),
      glueWarmthShift: (thinW / Math.max(1, thinCnt)) - (thickW / Math.max(1, thickCnt)),
    }};
  }}

  const lowGrain = measureStrokeWithParams({{ paperGrainIntensity: 0.25 }});
  const highGrain = measureStrokeWithParams({{ paperGrainIntensity: 1.95 }});

  const lowRing = measureStrokeWithParams({{ coffeeRingIntensity: 0.20 }});
  const highRing = measureStrokeWithParams({{ coffeeRingIntensity: 1.95 }});

  const lowNijimi = measureStrokeWithParams({{ nijimiIntensity: 0.15 }});
  const highNijimi = measureStrokeWithParams({{ nijimiIntensity: 1.95 }});

  const lowWarmth = measureStrokeWithParams({{ glueChromaticWarmth: 0.10 }});
  const highWarmth = measureStrokeWithParams({{ glueChromaticWarmth: 1.95 }});

  // Verify preset switching and toggle button
  const btnToggle = document.getElementById("btnInkSettingsToggle");
  const panel = document.getElementById("inkPhysicsSettingsPanel");
  btnToggle.click();
  const openedState = !panel.hidden && btnToggle.getAttribute("aria-expanded") === "true";
  applyInkPhysicsPreset("raw_xuan");
  const rawXuanNijimi = SLENDER_PHYSICS.nijimiIntensity;
  resetInkPhysicsSettings();
  const resetNijimi = SLENDER_PHYSICS.nijimiIntensity;

  const out = document.createElement("script");
  out.id = "test-out";
  out.type = "application/json";
  out.textContent = JSON.stringify({{
    lowGrain, highGrain,
    lowRing, highRing,
    lowNijimi, highNijimi,
    lowWarmth, highWarmth,
    openedState, rawXuanNijimi, resetNijimi
  }});
  document.body.appendChild(out);
}})();
</script>
</body>
</html>"""

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            [find_chrome_binary(), "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom", f"file://{tmp_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    m = re.search(r'<script id="test-out" type="application/json">(.*?)</script>', proc.stdout, re.DOTALL)
    assert m, f"Missing test-out JSON in stdout: {proc.stderr[:500]}"
    data = json.loads(m.group(1))

    assert data["openedState"] is True
    assert data["rawXuanNijimi"] > data["resetNijimi"]
    assert data["highGrain"]["valleyRidgeContrast"] > data["lowGrain"]["valleyRidgeContrast"] + 10.0
    assert data["highRing"]["coffeeRingRimDelta"] > data["lowRing"]["coffeeRingRimDelta"] + 8.0
    assert data["highNijimi"]["nijimiFringeRatio"] > data["lowNijimi"]["nijimiFringeRatio"] + 3.0
    assert data["highWarmth"]["glueWarmthShift"] > data["lowWarmth"]["glueWarmthShift"] + 2.5
