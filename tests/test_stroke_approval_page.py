"""Smoke test for the generated stroke-shape approval page (scripts/build_stroke_approval.py)."""

from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

from scripts.audit.evaluate_brushwork_canvas import find_chrome_binary
from scripts.build_stroke_approval import VARIANTS, build_html

_DRIVER = """
<script>
window.__errs = [];
window.addEventListener('error', e => window.__errs.push(String(e.message)));
setTimeout(() => {
  try {
    document.querySelector('input[name="dec-ellipticalCaps"][value="ok"]').click();
    const ta = document.querySelector('#card-strongCefeng textarea');
    document.querySelector('input[name="dec-strongCefeng"][value="tweak"]').click();
    ta.value = 'less sharp';
    ta.dispatchEvent(new Event('input'));
    document.getElementById('renderCombined').click();
    window.__dkBefore = document.querySelector('#card-ellipticalCaps .view:nth-child(2) canvas').toDataURL();
    const slider = document.querySelector('#card-ellipticalCaps .tune-row input[type=range]');
    slider.value = slider.max;
    slider.dispatchEvent(new Event('input'));
    document.querySelector('#card-anchoredEnds .view').click();
  } catch (e) { window.__errs.push('driver: ' + e.message); }
  setTimeout(() => {
    const out = document.createElement('pre');
    out.id = 'res';
    out.textContent = JSON.stringify({
      errs: window.__errs,
      store: JSON.parse(localStorage.getItem('strokeApproval.v1')),
      modalOpen: document.getElementById('modal').classList.contains('open'),
      cards: document.querySelectorAll('#cards .card').length,
      canvases: document.querySelectorAll('#cards canvas').length,
      combined: document.querySelectorAll('#combPair canvas').length,
      stats: [...document.querySelectorAll('.stat')].map(s => s.textContent),
      sliders: Object.fromEntries([...document.querySelectorAll('#cards .card')].map(c => [c.id.slice(5), c.querySelectorAll('.tune-row input[type=range]').length])),
      dkChanged: window.__dkBefore !== document.querySelector('#card-ellipticalCaps .view:nth-child(2) canvas').toDataURL(),
      dkMod: (document.querySelector('#card-ellipticalCaps .tune-head .mod') || {}).textContent,
    });
    document.body.append(out);
  }, 8000);
}, 12000);
</script></body>
"""


def test_stroke_approval_page_renders_variants_and_records_decisions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "stroke_approval.html"
        build_html(page)
        page.write_text(page.read_text(encoding="utf-8").replace("</body>", _DRIVER), encoding="utf-8")
        proc = subprocess.run(
            [
                find_chrome_binary(),
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--virtual-time-budget=90000",
                "--dump-dom",
                f"file://{page}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

    m = re.search(r'<pre id="res">(.*?)</pre>', proc.stdout, re.DOTALL)
    assert m, f"driver output missing: {proc.stderr[:400]}"
    data = json.loads(html.unescape(m.group(1)))

    assert data["errs"] == []
    assert data["cards"] == len(VARIANTS)
    assert data["canvases"] >= 3 * len(VARIANTS)
    assert data["combined"] == 2
    assert data["modalOpen"] is True
    decisions = data["store"]["decisions"]
    assert decisions["ellipticalCaps"]["decision"] == "ok"
    assert decisions["strongCefeng"]["decision"] == "tweak"
    assert decisions["strongCefeng"]["comment"] == "less sharp"
    # every variant must actually change pixels for the default character (otherwise the review page shows nothing)
    assert len(data["stats"]) == len(VARIANTS)
    for line in data["stats"]:
        changed = int(line.split(" pixels")[0].replace(",", ""))
        assert changed > 0, line
    # sliders: one per declared param; moving one re-renders the variant and is persisted with the judgment
    for v in VARIANTS:
        assert data["sliders"][v["id"]] == len(v.get("params", [])), v["id"]
    assert data["dkChanged"] is True
    assert "1 slider changed" in data["dkMod"]
    first_key = next(v for v in VARIANTS if v["id"] == "ellipticalCaps")["params"][0]
    assert data["store"]["params"]["ellipticalCaps"] == {first_key["key"]: first_key["max"]}
