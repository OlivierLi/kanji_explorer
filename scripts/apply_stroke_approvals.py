#!/usr/bin/env python3
"""Apply review decisions from stroke_approval.html to STROKE_VARIANTS in static/app.js.

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
    except StrokeVariantsError as e:
        sys.stderr.write(f"Error applying decisions: {e}\n")
        sys.exit(2)
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(2)

    print(format_summary_table(summary))

    has_changes = any(old != new for old, new in summary.values())
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
