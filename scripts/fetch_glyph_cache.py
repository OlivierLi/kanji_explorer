#!/usr/bin/env python3
"""Fetch and cache GlyphWiki SVGs for unresolved CHISE/CJK entities.

This script scans characters in Kanji Explorer, walks their decomposition trees,
and identifies any reachable entity reference (&...;) that cannot be rendered
via Jigmo font Unicode mappings or structural sub-decompositions.
For each such entity, it fetches the corresponding vector SVG from GlyphWiki
and stores it in data/glyphwiki_cache/<slug>.svg so that glyph_service.py can
render it offline without fallback boxes.

Usage:
    python3 scripts/fetch_glyph_cache.py [--all] [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import glyph_service as G
import ids_parser as P

CACHE_DIR = ROOT_DIR / "data" / "glyphwiki_cache"
DB_PATH = ROOT_DIR / "data" / "kanji_explorer.db"
USER_AGENT = "KanjiExplorer-GlyphCache/1.0"


def get_candidate_slugs(entity: str) -> list[str]:
    """Return possible GlyphWiki slug names for a given entity reference."""
    slug = entity.strip("&;").lower()
    slugs = [slug]

    # Handle CDP variants: &CDP-i001-8BD9; -> cdp-8bd9
    m_cdp = re.match(r"^cdp-i\d+-(.+)$", slug)
    if m_cdp:
        slugs.append(f"cdp-{m_cdp.group(1)}")

    # Mojikyo: mj007273 -> jmj-007273
    if slug.startswith("mj") and len(slug) == 8 and slug[2:].isdigit():
        slugs.append(f"jmj-{slug[2:]}")

    # Daikanwa: m-00914 -> dkw-00914
    if slug.startswith("m-") and slug[2:].isdigit():
        slugs.append(f"dkw-{int(slug[2:]):05d}")

    return list(dict.fromkeys(slugs))


def collect_reachable_entities(
    scope: str = "joyo_basic",
) -> set[str]:
    """Find all entity references reachable via recursive decomposition."""
    if not DB_PATH.is_file():
        print(f"Database not found at {DB_PATH}, scanning CHISE files directly...")
        return _collect_entities_from_chise()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if scope == "all":
        cur.execute("SELECT char, apparent_ids, cjkvi_ids FROM characters")
    elif scope == "joyo":
        cur.execute(
            "SELECT char, apparent_ids, cjkvi_ids FROM characters WHERE grade IS NOT NULL"
        )
    else:  # joyo_basic
        cur.execute(
            "SELECT char, apparent_ids, cjkvi_ids FROM characters WHERE grade IS NOT NULL OR tier = '基本漢字'"
        )

    rows = cur.fetchall()
    conn.close()

    print(f"Scanning decomposition trees for {len(rows):,} characters ({scope})...")
    t0 = time.time()

    reachable_entities: set[str] = set()

    def _walk_tree(node: dict) -> None:
        if not isinstance(node, dict):
            return
        ch = node.get("char") or ""
        raw = node.get("raw_char") or ""
        for token in (ch, raw):
            if token.startswith("&") and token.endswith(";"):
                norm = P.normalize_entity(token)
                if norm.startswith("&"):
                    reachable_entities.add(norm)
        for child in node.get("children", []):
            _walk_tree(child)

    for ch, apparent_ids, cjkvi_ids in rows:
        try:
            tree = P.decompose_character(ch, max_depth=6, compute_bbox=False)
            _walk_tree(tree)
        except Exception:
            pass

        # Also collect entities from alternative representations (@apparent, cjkvi)
        for alt_str in (apparent_ids, cjkvi_ids):
            if alt_str:
                for tok in re.findall(r"&[A-Za-z0-9_+-]+;", alt_str):
                    norm = P.normalize_entity(tok)
                    if norm.startswith("&"):
                        reachable_entities.add(norm)
                    try:
                        sub_tree = P.decompose_character(
                            norm, max_depth=6, compute_bbox=False
                        )
                        _walk_tree(sub_tree)
                    except Exception:
                        pass

    print(
        f"  -> Found {len(reachable_entities):,} distinct reachable entities ({time.time() - t0:.2f}s)"
    )
    return reachable_entities


def _collect_entities_from_chise() -> set[str]:
    """Fallback: collect entity tokens directly from CHISE dataset files."""
    chise_dir = ROOT_DIR / "data" / "chise-ids"
    entities = set()
    for p in chise_dir.glob("IDS-*.txt"):
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                for ent in re.findall(r"&[A-Za-z0-9_+-]+;", line):
                    norm = P.normalize_entity(ent)
                    if norm.startswith("&"):
                        entities.add(norm)
    return entities


def fetch_svg_for_slug(slug: str) -> str | None:
    """Download an SVG document from GlyphWiki for the given slug."""
    url = f"https://glyphwiki.org/glyph/{slug}.svg"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8", errors="replace").strip()
                if "<svg" in body and "</svg>" in body:
                    return body
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
    except Exception:
        pass
    return None


def fetch_and_cache_entity(
    entity: str,
    cache_dir: Path,
    force: bool = False,
) -> tuple[str, bool, str]:
    """Fetch and cache the SVG for an entity."""
    slugs = get_candidate_slugs(entity)
    primary_slug = slugs[0]
    target_path = cache_dir / f"{primary_slug}.svg"

    if target_path.is_file() and not force:
        return entity, True, "cached"

    for slug in slugs:
        svg_content = fetch_svg_for_slug(slug)
        if svg_content:
            target_path.write_text(svg_content, encoding="utf-8")
            # If fetched via alias, also link or write alias
            if slug != primary_slug:
                alias_path = cache_dir / f"{slug}.svg"
                if not alias_path.exists():
                    alias_path.write_text(svg_content, encoding="utf-8")
            return entity, True, f"fetched ({slug})"

    return entity, False, "not found on GlyphWiki"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch GlyphWiki SVGs for unresolved entities."
    )
    parser.add_argument(
        "--all", action="store_true", help="Scan all characters in DB"
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download already cached SVGs"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List missing entities without downloading"
    )
    parser.add_argument(
        "--concurrency", type=int, default=8, help="Number of concurrent download threads"
    )
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    scope = "all" if args.all else "joyo_basic"
    entities = collect_reachable_entities(scope=scope)

    # Filter out entities that already resolve to Jigmo font glyphs, IDS dictionary, or component subdecompositions
    unresolved_entities: list[str] = []
    for ent in sorted(entities):
        norm = P.normalize_entity(ent)
        if not norm.startswith("&") and G.get_jigmo_path(norm):
            continue
        if norm in P.COMPONENT_SUBDECOMPOSITIONS or ent in P.COMPONENT_SUBDECOMPOSITIONS:
            continue
        if P.get_character_ids(norm) is not None:
            continue
        unresolved_entities.append(ent)

    print(
        f"Entities needing vector SVG glyphs: {len(unresolved_entities):,}"
    )

    already_cached = 0
    missing: list[str] = []
    for ent in unresolved_entities:
        slug = get_candidate_slugs(ent)[0]
        if (CACHE_DIR / f"{slug}.svg").is_file() and not args.force:
            already_cached += 1
        else:
            missing.append(ent)

    print(f"  Already cached: {already_cached}")
    print(f"  To download   : {len(missing)}")

    if args.dry_run or not missing:
        if args.dry_run:
            print("Dry run requested. Missing entities:")
            for e in missing[:30]:
                print(f"  {e}")
        return

    print(f"Downloading {len(missing)} SVGs from GlyphWiki (concurrency={args.concurrency})...")
    t0 = time.time()
    fetched_count = 0
    failed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {
            executor.submit(fetch_and_cache_entity, ent, CACHE_DIR, args.force): ent
            for ent in missing
        }
        for future in concurrent.futures.as_completed(futures):
            ent, ok, status = future.result()
            if ok:
                fetched_count += 1
            else:
                failed_count += 1

    print(
        f"Download complete in {time.time() - t0:.2f}s: "
        f"Fetched {fetched_count:,}, Failed {failed_count:,}"
    )
    total_cached = len(list(CACHE_DIR.glob("*.svg")))
    print(f"Total SVGs in cache: {total_cached:,}")


if __name__ == "__main__":
    main()
