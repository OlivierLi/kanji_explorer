"""Tests for scripts/apply_stroke_approvals.py and stroke shape approval tools."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.apply_stroke_approvals import (
    StrokeVariantsError,
    apply_decisions,
    main,
)
from scripts.audit.evaluate_brushwork_canvas import APP_JS_PATH, BASE_DIR
from scripts.build_stroke_approval import VARIANTS


def test_apply_decisions_flips_only_approved_flags() -> None:
    """(a) apply_decisions flips only the approved flags and leaves the rest of a small synthetic JS snippet byte-identical."""
    synthetic_js = (
        "// Leading comment\n"
        "const CONFIG = { debug: false };\n"
        "\n"
        "const STROKE_VARIANTS = {\n"
        "  anchoredEnds: false,\n"
        "  ellipticalCaps: false,\n"
        "  mitreCorners: false\n"
        "};\n"
        "\n"
        "function getVariantKey() {\n"
        "  return 'abc';\n"
        "}\n"
    )

    decisions = {
        "generated": "2026-11-06T12:00:00Z",
        "decisions": {
            "ellipticalCaps": {"decision": "ok", "comment": "looks much more natural"},
            "anchoredEnds": {"decision": "undecided"},
            "mitreCorners": {"decision": "no", "comment": "too sharp"},
        },
    }

    new_js, summary = apply_decisions(synthetic_js, decisions)

    expected_js = (
        "// Leading comment\n"
        "const CONFIG = { debug: false };\n"
        "\n"
        "const STROKE_VARIANTS = {\n"
        "  anchoredEnds: false,\n"
        "  ellipticalCaps: true,\n"
        "  mitreCorners: false\n"
        "};\n"
        "\n"
        "function getVariantKey() {\n"
        "  return 'abc';\n"
        "}\n"
    )

    assert new_js == expected_js
    assert summary["ellipticalCaps"] == (False, True)
    assert summary["anchoredEnds"] == (False, False)
    assert summary["mitreCorners"] == (False, False)


def test_apply_decisions_tweak_no_undecided_become_false() -> None:
    """(b) tweak/no/undecided => false."""
    synthetic_js = (
        "const STROKE_VARIANTS = {\n"
        "  flagTweak: true,\n"
        "  flagNo: true,\n"
        "  flagUndecided: true,\n"
        "  flagOk: false\n"
        "};\n"
    )

    decisions = {
        "decisions": {
            "flagTweak": {"decision": "tweak", "comment": "needs adjustment"},
            "flagNo": {"decision": "no"},
            "flagUndecided": {"decision": "undecided"},
            "flagOk": {"decision": "ok"},
        }
    }

    new_js, summary = apply_decisions(synthetic_js, decisions)

    expected_js = (
        "const STROKE_VARIANTS = {\n"
        "  flagTweak: false,\n"
        "  flagNo: false,\n"
        "  flagUndecided: false,\n"
        "  flagOk: true\n"
        "};\n"
    )

    assert new_js == expected_js
    assert summary["flagTweak"] == (True, False)
    assert summary["flagNo"] == (True, False)
    assert summary["flagUndecided"] == (True, False)
    assert summary["flagOk"] == (False, True)


def test_missing_stroke_variants_block_raises_and_exits_2(tmp_path: Path) -> None:
    """(c) missing block raises/exits with code 2."""
    bad_js = "const OTHER_SETTINGS = { foo: 1, bar: 2 };\n"

    # Pure function raises ValueError / StrokeVariantsError
    with pytest.raises((ValueError, StrokeVariantsError)):
        apply_decisions(bad_js, {"decisions": {"foo": {"decision": "ok"}}})

    # CLI exits with code 2
    bad_js_file = tmp_path / "bad_app.js"
    bad_js_file.write_text(bad_js, encoding="utf-8")
    dec_file = tmp_path / "decisions.json"
    dec_file.write_text(
        json.dumps({"decisions": {"foo": {"decision": "ok"}}}), encoding="utf-8"
    )

    with pytest.raises(SystemExit) as exc_info:
        main([str(dec_file), "--app-js", str(bad_js_file)])
    assert exc_info.value.code == 2


def test_real_app_js_all_undecided_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(d) running against the real static/app.js with an all-"undecided" decision file via --dry-run exits 0 and reports no changes."""
    real_js = APP_JS_PATH.read_text(encoding="utf-8")
    m = re.search(r"const\s+STROKE_VARIANTS\s*=\s*\{([^}]*)\};", real_js)
    assert m is not None, "STROKE_VARIANTS block missing in real static/app.js"
    block_body = m.group(1)

    real_flags = re.findall(
        r"^\s*([a-zA-Z0-9_$]+)\s*:\s*(?:true|false)", block_body, re.MULTILINE
    )
    assert len(real_flags) > 0

    # Mirror the current defaults: already-enabled flags are "ok", the rest "undecided" -> nothing should change
    enabled = {
        flag for flag in real_flags
        if re.search(rf"^\s*{flag}\s*:\s*true", block_body, re.MULTILINE)
    }

    dec_file = tmp_path / "all_undecided.json"
    dec_file.write_text(
        json.dumps({
            "generated": "2026-11-06T12:00:00Z",
            "decisions": {
                f: {"decision": "ok" if f in enabled else "undecided", "comment": ""} for f in real_flags
            },
        }),
        encoding="utf-8",
    )

    ret = main([str(dec_file), "--app-js", str(APP_JS_PATH), "--dry-run"])
    assert ret == 0

    # Real static/app.js should not be modified
    assert APP_JS_PATH.read_text(encoding="utf-8") == real_js

    captured = capsys.readouterr()
    assert "0 changed" in captured.out
    assert "no changes" in captured.out.lower()


def test_build_stroke_approval_variants_equal_app_js_stroke_variants() -> None:
    """(e) scripts/build_stroke_approval.py can be imported and its VARIANTS ids exactly equal the keys of the STROKE_VARIANTS block parsed from static/app.js."""
    app_js = APP_JS_PATH.read_text(encoding="utf-8")
    m = re.search(r"const\s+STROKE_VARIANTS\s*=\s*\{([^}]*)\};", app_js)
    assert m is not None, "STROKE_VARIANTS block not found in static/app.js"
    block_body = m.group(1)

    app_js_flags = re.findall(
        r"^\s*([a-zA-Z0-9_$]+)\s*:\s*(?:true|false)", block_body, re.MULTILINE
    )
    variant_ids = [v["id"] for v in VARIANTS]

    assert set(variant_ids) == set(app_js_flags)
    assert len(variant_ids) == len(app_js_flags)


def test_unknown_ids_in_json_ignored_with_warning() -> None:
    """Unknown ids in the JSON must be ignored with a warning."""
    synthetic_js = "const STROKE_VARIANTS = {\n  anchoredEnds: false\n};\n"
    decisions = {
        "decisions": {
            "anchoredEnds": {"decision": "ok"},
            "nonExistentVariant": {"decision": "ok"},
        }
    }
    with pytest.warns(UserWarning, match="Unknown variant id.*nonExistentVariant"):
        new_js, summary = apply_decisions(synthetic_js, decisions)

    assert "anchoredEnds: true" in new_js
    assert "nonExistentVariant" not in new_js
    assert "nonExistentVariant" not in summary


def test_cli_writes_file_when_not_dry_run(tmp_path: Path) -> None:
    """CLI without --dry-run writes updated file to disk."""
    app_js_file = tmp_path / "app.js"
    app_js_file.write_text("const STROKE_VARIANTS = {\n  anchoredEnds: false\n};\n", encoding="utf-8")
    dec_file = tmp_path / "dec.json"
    dec_file.write_text(json.dumps({"decisions": {"anchoredEnds": {"decision": "ok"}}}), encoding="utf-8")

    ret = main([str(dec_file), "--app-js", str(app_js_file)])
    assert ret == 0
    assert "anchoredEnds: true" in app_js_file.read_text(encoding="utf-8")
