"""CI ratchet coverage tests for CHISE/CJK entities in Kanji Explorer.

Ensures no character decomposition tree leaves behind unresolved entities
(&...; placeholder boxes without SVG or structural decomposition).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

import glyph_service as G
import ids_parser as P

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "kanji_explorer.db"
ALLOWLIST_PATH = ROOT_DIR / "tests" / "entity_coverage_allowlist.txt"


def _load_allowlist() -> set[str]:
    """Load allowed unresolvable entities from allowlist file."""
    if not ALLOWLIST_PATH.is_file():
        return set()
    allowed = set()
    with open(ALLOWLIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                allowed.add(line)
    return allowed


def _is_entity_resolved(entity: str) -> bool:
    """Check if an entity is resolved via Unicode mapping, IDS decomposition, or vector SVG."""
    norm = P.normalize_entity(entity)
    if not norm.startswith("&"):
        return True

    # 1. Structural decomposition in IDS dictionary or component sub-decompositions
    if P.get_character_ids(entity) is not None or norm in P.COMPONENT_SUBDECOMPOSITIONS:
        return True

    # 2. Vector SVG rendering from font or local GlyphWiki cache
    svg = G.get_glyph_svg(entity)
    if svg and "<text>" not in svg and "<path" in svg and "<rect" not in svg:
        return True

    return False


def _collect_reachable_entities(
    char_rows: list[str] | list[tuple[str, ...]],
) -> set[str]:
    """Find all entity references reachable from the given characters across all IDS views."""
    reachable = set()
    ids_dict = P.get_ids_dict()

    def _walk(ch: str, seen: set[str], depth: int = 0) -> None:
        if depth > 10 or ch in seen:
            return
        seen.add(ch)
        ids_str = P.get_character_ids(ch, ids_dict=ids_dict)
        if not ids_str:
            return
        for tok in re.findall(r"&[^;]+;|.", ids_str):
            if tok.isspace():
                continue
            if tok.startswith("&") and tok.endswith(";"):
                norm = P.normalize_entity(tok)
                if norm.startswith("&"):
                    reachable.add(norm)
                _walk(norm, seen, depth + 1)
            elif tok not in P.IDC_INFO and tok != ch:
                _walk(tok, seen, depth + 1)

    for row in char_rows:
        if isinstance(row, (tuple, list)):
            ch = row[0]
            alt_sources = row[1:]
        else:
            ch = row
            alt_sources = ()

        _walk(ch, set())
        for alt_str in alt_sources:
            if alt_str:
                for tok in re.findall(r"&[A-Za-z0-9_+-]+;", alt_str):
                    norm = P.normalize_entity(tok)
                    if norm.startswith("&"):
                        reachable.add(norm)
                    _walk(norm, set())

    return reachable


class TestEntityCoverage:
    """Ratchet coverage test to eliminate raw placeholder boxes."""

    @pytest.fixture(scope="module")
    def db_conn(self):
        if not DB_PATH.is_file():
            pytest.skip("Database file data/kanji_explorer.db not available")
        conn = sqlite3.connect(DB_PATH)
        yield conn
        conn.close()

    def test_joyo_entity_coverage_zero_unresolved(self, db_conn):
        """All 2,999 Jōyō/graded kanji must have 0 unresolved entities across all IDS views."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT char, apparent_ids, cjkvi_ids FROM characters WHERE grade IS NOT NULL"
        )
        joyo_rows = cur.fetchall()
        assert len(joyo_rows) >= 2000

        reachable = _collect_reachable_entities(joyo_rows)
        unresolved = [e for e in sorted(reachable) if not _is_entity_resolved(e)]

        assert unresolved == [], (
            f"Found {len(unresolved)} unresolvable entities in Jōyō kanji: {unresolved}. "
            "Every Jōyō entity must either map to Unicode, have an IDS decomposition, "
            "or have a cached vector SVG in data/glyphwiki_cache/."
        )

    def test_basic_cjk_entity_coverage_ratchet(self, db_conn):
        """Basic CJK tier must only contain entities explicitly in the allowlist."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT char, apparent_ids, cjkvi_ids FROM characters WHERE tier = '基本漢字'"
        )
        basic_rows = cur.fetchall()
        assert len(basic_rows) >= 20000

        reachable = _collect_reachable_entities(basic_rows)
        unresolved = set(e for e in reachable if not _is_entity_resolved(e))
        allowlist = _load_allowlist()

        # 1. No new unresolvable entities outside allowlist
        new_unresolved = sorted(unresolved - allowlist)
        assert new_unresolved == [], (
            f"New unresolvable entities found in Basic CJK: {new_unresolved}. "
            "Resolve them via ids_parser.py, scripts/build_entity_map.py, or "
            "scripts/fetch_glyph_cache.py."
        )

        # 2. Ratchet check: allowlisted entities that are now resolved must be removed
        stale_allowlist = sorted(allowlist - unresolved)
        assert stale_allowlist == [], (
            f"Entities in tests/entity_coverage_allowlist.txt are now resolved: {stale_allowlist}. "
            "Please remove them from tests/entity_coverage_allowlist.txt to lock in coverage."
        )

    def test_ken_and_aj1_01904_full_resolution(self):
        """Verify the exact issue reported in solution.md (&AJ1-01904; & 牽)."""
        # Entity resolves to Unicode玄
        assert P.normalize_entity("&AJ1-01904;") == "玄"

        # Glyph renders vector path without placeholder rect
        svg = G.get_glyph_svg("&AJ1-01904;")
        assert "<rect" not in svg
        assert "<path" in svg

        # 牽 decomposes to 玄 and recursive components down to strokes
        tree = P.decompose_character("牽", max_depth=5)
        assert tree["char"] == "牽"
        assert tree["op"] == "⿱"

        # Find the CDP-89FE child node
        cdp_node = next(
            (c for c in tree.get("children", []) if c.get("char") == "&CDP-89FE;"), None
        )
        assert cdp_node is not None
        assert cdp_node["op"] == "⿻"

        # Verify child contains 玄 (resolved from &AJ1-01904;)
        gen_node = next(
            (c for c in cdp_node.get("children", []) if c.get("char") == "玄"), None
        )
        assert gen_node is not None
        assert gen_node.get("raw_char") == "&AJ1-01904;"
