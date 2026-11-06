#!/usr/bin/env python3
"""Apply review decisions from stroke_approval.html to STROKE_VARIANTS in static/app.js.

Approved ("ok") variants are switched on. For approved and "tweak" variants, exported slider values ("params") are
written into the variant's tuning block (STROKE_VARIANT_TUNING maps variant id -> `const X_TUNING = {...}`).

CLI:
    python3 scripts/apply_stroke_approvals.py decisions.json [--app-js static/app.js] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_APP_JS = BASE_DIR / "static" / "app.js"

STROKE_VARIANTS_BLOCK_RE = re.compile(
    r"(const\s+STROKE_VARIANTS\s*=\s*\{)([\s\S]*?)(\};)"
)
FLAG_LINE_RE = re.compile(
    r"^(\s*)([a-zA-Z0-9_$]+)(\s*:\s*)(true|false)([\s\S]*)$"
)


class StrokeVariantsError(ValueError):
    """Raised when STROKE_VARIANTS cannot be found or parsed."""


def _extract_decisions_map(decisions: dict[str, Any]) -> dict[str, str]:
    """Normalize decisions payload to a mapping of variant_id -> decision string."""
    raw = decisions.get("decisions", decisions) if isinstance(decisions, dict) else {}
    if not isinstance(raw, dict):
        return {}
    res: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            res[k] = str(v.get("decision", "undecided"))
        else:
            res[k] = str(v)
    return res


def apply_decisions(
    js_text: str, decisions: dict[str, Any]
) -> tuple[str, dict[str, tuple[bool, bool]]]:
    """Pure function applying decisions to the STROKE_VARIANTS block in JS text.

    Args:
        js_text: Full JavaScript source code containing `const STROKE_VARIANTS = { ... };`.
        decisions: Either full decisions JSON dict or inner decisions mapping.

    Returns:
        tuple of (new_js_text, {flag_name: (old_bool, new_bool)})

    Raises:
        StrokeVariantsError: If the block is missing, empty, or has no valid flag entries.
    """
    match = STROKE_VARIANTS_BLOCK_RE.search(js_text)
    if not match:
        raise StrokeVariantsError("STROKE_VARIANTS block not found in JS text")

    prefix = match.group(1)
    body = match.group(2)
    suffix = match.group(3)

    decision_map = _extract_decisions_map(decisions)

    lines = body.splitlines(keepends=True)
    new_lines: list[str] = []
    summary: dict[str, tuple[bool, bool]] = {}

    found_flags = 0
    for line in lines:
        flag_match = FLAG_LINE_RE.match(line)
        if flag_match:
            found_flags += 1
            indent = flag_match.group(1)
            flag_name = flag_match.group(2)
            colon_sep = flag_match.group(3)
            old_str = flag_match.group(4)
            trailing = flag_match.group(5)

            old_bool = (old_str == "true")
            if flag_name in decision_map:
                dec = decision_map[flag_name]
                new_bool = (dec == "ok")
            else:
                new_bool = old_bool

            summary[flag_name] = (old_bool, new_bool)
            new_str = "true" if new_bool else "false"
            new_lines.append(f"{indent}{flag_name}{colon_sep}{new_str}{trailing}")
        else:
            new_lines.append(line)

    if found_flags == 0:
        raise StrokeVariantsError("STROKE_VARIANTS block contains no recognized flag entries")

    # Warn about unknown ids in decisions
    unknown_ids = sorted(set(decision_map.keys()) - set(summary.keys()))
    for uid in unknown_ids:
        warnings.warn(f"Unknown variant id in decisions: '{uid}'", UserWarning)

    new_block = prefix + "".join(new_lines) + suffix
    new_js = js_text[:match.start()] + new_block + js_text[match.end():]
    return new_js, summary


TUNING_MAP_RE = re.compile(r"const\s+STROKE_VARIANT_TUNING\s*=\s*\{([^}]*)\};")
PARAMS_APPLY_DECISIONS = ("ok", "tweak")


def _tuning_block_names(js_text: str) -> dict[str, str]:
    """variant id -> tuning const name, parsed from STROKE_VARIANT_TUNING."""
    m = TUNING_MAP_RE.search(js_text)
    if not m:
        return {}
    return dict(re.findall(r"([A-Za-z0-9_$]+)\s*:\s*([A-Za-z0-9_$]+)", m.group(1)))


def _fmt_number(x: float) -> str:
    if float(x).is_integer() and abs(x) >= 10:
        return str(int(x))
    out = f"{float(x):.4f}".rstrip("0")
    return out + "0" if out.endswith(".") else out


def apply_params(
    js_text: str, decisions: dict[str, Any]
) -> tuple[str, dict[str, dict[str, tuple[float, float]]]]:
    """Write exported slider values into the tuning blocks of approved / tweak variants.

    Returns (new_js_text, {variant_id: {key: (old, new)}}) listing only values that changed.
    Unknown variants or keys are warned about and skipped.
    """
    raw = decisions.get("decisions", decisions) if isinstance(decisions, dict) else {}
    names = _tuning_block_names(js_text)
    changes: dict[str, dict[str, tuple[float, float]]] = {}
    for vid, entry in (raw or {}).items():
        if not isinstance(entry, dict) or not isinstance(entry.get("params"), dict):
            continue
        if entry.get("decision") not in PARAMS_APPLY_DECISIONS:
            continue
        const_name = names.get(vid)
        if not const_name:
            warnings.warn(f"No tuning block for variant '{vid}'; params ignored", UserWarning)
            continue
        block_re = re.compile(r"(const\s+" + re.escape(const_name) + r"\s*=\s*\{)([\s\S]*?)(\};)")
        m = block_re.search(js_text)
        if not m:
            warnings.warn(f"Tuning block {const_name} not found; params for '{vid}' ignored", UserWarning)
            continue
        body = m.group(2)
        for key, value in entry["params"].items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            line_re = re.compile(r"^(\s*" + re.escape(key) + r"\s*:\s*)(-?[0-9.]+(?:e-?[0-9]+)?)", re.MULTILINE)
            lm = line_re.search(body)
            if not lm:
                warnings.warn(f"Unknown param '{key}' for variant '{vid}'", UserWarning)
                continue
            old = float(lm.group(2))
            if abs(old - float(value)) < 1e-9:
                continue
            body = body[:lm.start(2)] + _fmt_number(value) + body[lm.end(2):]
            changes.setdefault(vid, {})[key] = (old, float(value))
        js_text = js_text[:m.start(2)] + body + js_text[m.end(2):]
    return js_text, changes


def format_params_table(changes: dict[str, dict[str, tuple[float, float]]]) -> str:
    if not changes:
        return "Params: no slider values changed."
    lines = ["Params:", f"{'Variant':<16} {'Param':<18} {'Old':>10} {'New':>10}", "-" * 57]
    for vid, kv in changes.items():
        for k, (old, new) in kv.items():
            lines.append(f"{vid:<16} {k:<18} {_fmt_number(old):>10} {_fmt_number(new):>10}")
    return "\n".join(lines)


def format_summary_table(summary: dict[str, tuple[bool, bool]]) -> str:
    """Format old -> new values summary table."""
    lines = [
        f"{'Variant':<20} {'Old':<8} {'New':<8} {'Changed':<8}",
        "-" * 48,
    ]
    changed_count = 0
    for flag, (old, new) in summary.items():
        chg_str = "YES" if old != new else "no"
        if old != new:
            changed_count += 1
        lines.append(f"{flag:<20} {str(old).lower():<8} {str(new).lower():<8} {chg_str:<8}")
    lines.append("-" * 48)
    lines.append(f"Summary: {changed_count} changed, {len(summary) - changed_count} unchanged.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply stroke approval decisions to STROKE_VARIANTS in static/app.js."
    )
    parser.add_argument("decisions", help="Path to decisions JSON file (from stroke_approval.html)")
    parser.add_argument(
        "--app-js",
        default="static/app.js",
        help="Path to static/app.js (default: static/app.js)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary table without writing changes",
    )

    args = parser.parse_args(argv)

    decisions_path = Path(args.decisions)
    if not decisions_path.is_file():
        sys.stderr.write(f"Error: decisions file not found: {decisions_path}\n")
        sys.exit(2)

    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            decisions_data = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error reading JSON from {decisions_path}: {e}\n")
        sys.exit(2)

    app_js_path = Path(args.app_js)
    if not app_js_path.is_file():
        # Fall back to DEFAULT_APP_JS if standard default was used from another working directory
        if args.app_js == "static/app.js" and DEFAULT_APP_JS.is_file():
            app_js_path = DEFAULT_APP_JS
        else:
            sys.stderr.write(f"Error: app.js file not found: {app_js_path}\n")
            sys.exit(2)

    try:
        js_text = app_js_path.read_text(encoding="utf-8")
        new_js, summary = apply_decisions(js_text, decisions_data)
        new_js, param_changes = apply_params(new_js, decisions_data)
    except StrokeVariantsError as e:
        sys.stderr.write(f"Error applying decisions: {e}\n")
        sys.exit(2)
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(2)

    print(format_summary_table(summary))
    print(format_params_table(param_changes))

    has_changes = any(old != new for old, new in summary.values()) or bool(param_changes)
    if has_changes:
        if args.dry_run:
            print(f"[dry-run] Changes detected for {app_js_path} (not written).")
        else:
            app_js_path.write_text(new_js, encoding="utf-8")
            print(f"Applied changes to {app_js_path}.")
    else:
        if args.dry_run:
            print("[dry-run] No changes to apply.")
        else:
            print(f"No changes to apply to {app_js_path}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
