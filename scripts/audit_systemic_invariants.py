"""Read-only audit of stored graph paths and all graded print glyphs.

Run after the runtime database has been extracted: python3 scripts/audit_systemic_invariants.py
"""
import argparse
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import glyph_service
import ids_parser
from geometry import contains_polygon


PATH_CHECKS = {
    'missing_direct_edges': '''
        SELECT count(*) FROM component_edges e
        LEFT JOIN component_closure c ON c.target_char=e.parent_char AND c.component=e.child_char
        WHERE e.parent_char != e.child_char
          AND (c.component IS NULL OR c.is_direct != 1 OR c.min_depth != 1)
    ''',
    'invalid_indirect_via': '''
        SELECT count(*) FROM component_closure c WHERE c.is_direct=0 AND NOT EXISTS (
            SELECT 1 FROM component_edges e
            WHERE e.parent_char=c.target_char AND e.child_char=c.via_char
        )
    ''',
    'self_paths': 'SELECT count(*) FROM component_closure WHERE component=target_char',
    'invalid_depths': 'SELECT count(*) FROM component_closure WHERE min_depth NOT BETWEEN 1 AND 6 OR min_depth IS NULL',
    'shortest_path_violations': '''
        SELECT count(*) FROM component_closure c JOIN component_edges e
          ON c.component=e.parent_char AND e.source IN ('chise','atomic')
        WHERE c.min_depth < 6 AND e.child_char != c.target_char AND NOT EXISTS (
            SELECT 1 FROM component_closure n
            WHERE n.target_char=c.target_char AND n.component=e.child_char
              AND n.min_depth <= c.min_depth+1
        )
    ''',
}


def _has_semicolon_child(node: dict) -> bool:
    for child in node.get('children') or ():
        if child.get('char') == ';' or child.get('raw_char') == ';' or _has_semicolon_child(child):
            return True
    return False


def audit(database: Path) -> dict:
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.execute('BEGIN')
        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        path_checks = {name: conn.execute(sql).fetchone()[0] for name, sql in PATH_CHECKS.items()}
        paths = conn.execute('SELECT count(*) FROM component_closure').fetchone()[0]
        chars = conn.execute(
            'SELECT char, chise_ids FROM characters WHERE grade IS NOT NULL ORDER BY grade, char'
        ).fetchall()

    mutations, unstable, invalid_holes, missing_glyphs, corrupted_primary_ids = [], [], [], [], []
    holes_checked = 0
    for char, chise_ids in chars:
        primary_ids = chise_ids or ids_parser.get_character_ids(char) or char
        primary_tree = ids_parser.decompose_character(primary_ids, max_depth=6, compute_bbox=False)
        if _has_semicolon_child(primary_tree):
            corrupted_primary_ids.append(char)
        tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
        original = copy.deepcopy(tree)
        first = glyph_service.build_interactive_ids_svg(tree)
        second = glyph_service.build_interactive_ids_svg(tree)
        if tree != original:
            mutations.append(char)
        if first != second:
            unstable.append(char)
        if not first['base_path']:
            missing_glyphs.append(char)
        for island in glyph_service._extract_ink_islands(first['base_path'] or ''):
            if island['is_linear']:
                for hole in island['hole_polygons']:
                    holes_checked += 1
                    if not contains_polygon(island['polygon'], hole):
                        invalid_holes.append(char)

    result = {
        'database_integrity': integrity,
        'component_paths': paths,
        'path_violations': path_checks,
        'graded_characters_checked': len(chars),
        'linear_holes_checked': holes_checked,
        'mutated_trees': mutations,
        'unstable_print_renders': unstable,
        'invalid_hole_parents': invalid_holes,
        'missing_graded_glyphs': missing_glyphs,
        'corrupted_primary_ids': corrupted_primary_ids,
    }
    result['passed'] = (
        integrity == 'ok'
        and not any(path_checks.values())
        and not any([mutations, unstable, invalid_holes, missing_glyphs, corrupted_primary_ids])
    )
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT / 'data' / 'kanji_explorer.db')
    report = audit(parser.parse_args().database)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['passed'] else 1)
