#!/usr/bin/env python3
"""Package the runtime files of Kanji Explorer for upload to PythonAnywhere.

Usage: python scripts/package_for_pythonanywhere.py TARGET_DIR [--big-threshold-mb 20]

Nothing is modified in place; outputs are written to TARGET_DIR:

* ``app.zip``  - all small runtime files (code, static, small data). Expand it
  once in the app directory (``unzip app.zip``), then delete it.
* Loose large files (>= threshold, e.g. the DB .gz and the big fonts), each
  < 100 MB. Upload them as-is (no decompression needed) and move them to the
  path listed in ``INSTALL.txt``.

Disk-peak notes (PythonAnywhere quota): the server auto-extracts
``data/kanji_explorer.db.gz`` -> ``data/kanji_explorer.db`` (~250 MB) on first
start, so delete the .gz afterwards. Only the small app.zip is ever expanded.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 100 * 1024 * 1024

# Runtime-only manifest (relative to project root).
CODE_FILES = [
    "server.py", "wsgi.py", "glyph_service.py", "ids_parser.py",
    "jp_metadata.py", "view_renderer.py",
]
RUNTIME_DIRS = ["static", "data/chise-ids"]
RUNTIME_DATA = [
    "data/kanji_explorer.db.gz", "data/kanjivg.xml.gz",
    "data/cjkvi-ids.txt", "data/EquivalentUnifiedIdeograph.txt",
]
SKIP_NAMES = {"__pycache__", ".DS_Store"}


def collect() -> list[Path]:
    files: list[Path] = []
    for rel in CODE_FILES + RUNTIME_DATA:
        p = ROOT / rel
        if not p.is_file():
            sys.exit(f"Missing required file: {rel}")
        files.append(p)
    for rel in RUNTIME_DIRS:
        d = ROOT / rel
        if not d.is_dir():
            sys.exit(f"Missing required directory: {rel}")
        files += [p for p in sorted(d.rglob("*"))
                  if p.is_file() and not (SKIP_NAMES & set(p.parts))
                  and p.suffix != ".pyc"]
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", type=Path, help="Output directory (created if needed)")
    ap.add_argument("--big-threshold-mb", type=float, default=20)
    args = ap.parse_args()

    threshold = int(args.big_threshold_mb * 1024 * 1024)
    target: Path = args.target.resolve()
    if ROOT == target or ROOT in target.parents:
        sys.exit("Target must be outside the project directory.")
    target.mkdir(parents=True, exist_ok=True)

    files = collect()
    big = [p for p in files if p.stat().st_size >= threshold]
    small = [p for p in files if p not in big]

    names = [p.name for p in big]
    if len(set(names)) != len(names):
        sys.exit("Large files have clashing basenames: " + ", ".join(names))
    for p in big:
        if p.stat().st_size >= LIMIT:
            sys.exit(f"{p} is >= 100MB; cannot upload as a single file.")

    zip_path = target / "app.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in small:
            z.write(p, p.relative_to(ROOT).as_posix())
    if zip_path.stat().st_size >= LIMIT:
        sys.exit("app.zip exceeds 100MB; lower --big-threshold-mb.")

    app = ROOT.name
    lines = ["Upload everything in this folder next to (not inside) the app dir, then:",
             f"  rm -rf {app}",
             f"  mkdir {app}",
             f"  cd {app}",
             "  unzip ../app.zip && rm ../app.zip"]
    for p in big:
        shutil.copyfile(p, target / p.name)
        lines.append(f"  mv ../{p.name} {p.relative_to(ROOT).as_posix()}")
    lines += ["Reload the web app; the first request extracts the DB (~250MB).",
              "Afterwards: rm data/kanji_explorer.db.gz to reclaim ~86MB.",
              "",
              "OPTIONAL - update only the code (re-upload just app.zip, keep the large files):",
              f"  cd {app}",
              "  unzip -o ../app.zip && rm ../app.zip",
              "  (overwrites files from the zip; the DB and big fonts are untouched.",
              "   Files deleted from the project are not removed; rm them by hand.)",
              "Then reload the web app."]
    (target / "INSTALL.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"app.zip: {zip_path.stat().st_size / 1e6:.1f} MB ({len(small)} files)")
    for p in big:
        print(f"{p.name}: {p.stat().st_size / 1e6:.1f} MB")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
