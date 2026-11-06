"""Visibility guard for stroke-shape variants under review (see scripts/audit/variant_visibility.py).

Encodes the round-1 / round-2 review feedback:
  * dryKasure "too strong on 国" (round-1 version: largest changed blob 663 display px, ink mass -3.1 %)
  * dryKasure tweak then rated "does nothing to the naked eye"
  * wetDryTrim "too subtle"
"""

from __future__ import annotations

import shutil

import pytest

from scripts.audit.evaluate_brushwork_canvas import APP_JS_PATH
from scripts.audit.variant_visibility import REVIEW_CHARS, evaluate, is_visible

pytestmark = pytest.mark.skipif(
    not any(shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")),
    reason="headless Chrome not available",
)

ROUND1_KUNI_BLOB = 663


@pytest.fixture(scope="module")
def results() -> dict:
    return evaluate(APP_JS_PATH.read_text(encoding="utf-8"), REVIEW_CHARS, ["dryKasure", "wetDryTrim"])


@pytest.mark.parametrize("variant", ["dryKasure", "wetDryTrim"])
def test_variant_is_noticeable_on_most_review_characters(results: dict, variant: str) -> None:
    per_char = results[variant]
    visible = [ch for ch, r in per_char.items() if is_visible(r)]
    assert len(visible) >= 9, f"{variant} only noticeable on {visible}: {per_char}"


def test_dry_kasure_on_kuni_is_restrained_but_present(results: dict) -> None:
    r = results["dryKasure"]["国"]
    assert is_visible(r), r
    assert r["blob_px"] <= ROUND1_KUNI_BLOB * 0.35, r
    assert r["mass_pct"] > -2.0, r
