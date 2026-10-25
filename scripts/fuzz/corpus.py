"""
scripts/fuzz/corpus.py
コーパス層別化・文字リスト抽出・画数取得ユーティリティ。

fuzz.md 仕様:
- Tier 1: 常用漢字 (2136字) + 人名用漢字 (約863字)
- Tier 2: KanjiVG収録全字 (約6.7k字)
- Tier 3: リスクの高い構文シグネチャを持つ文字 (⿻, 深さ>=3, 複合包囲, 1インク島など)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import ids_parser
import glyph_service

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "kanji_explorer.db"

# 基本筆画・部首の画数フォールバック（辞書にない極小部品用）
PRIMITIVE_STROKES: dict[str, int] = {
    "一": 1, "丨": 1, "丿": 1, "丶": 1, "乙": 1, "亅": 1, "乚": 1, "乀": 1, "乁": 1,
    "二": 2, "十": 2, "人": 2, "入": 2, "八": 2, "几": 2, "凵": 2, "刀": 2, "力": 2,
    "勹": 2, "匕": 2, "匚": 2, "卜": 2, "卩": 2, "厂": 2, "厶": 2, "又": 2, "冖": 2,
    "冫": 2, "冂": 2, "亠": 2, "亻": 2, "𠂉": 2, "𭕄": 3, "⺍": 3, "⺌": 3, "丷": 2,
    "口": 3, "囗": 3, "土": 3, "士": 3, "夂": 3, "夕": 3, "大": 3, "女": 3, "子": 3,
    "寸": 3, "小": 3, "尢": 3, "尸": 3, "屮": 3, "山": 3, "川": 3, "工": 3, "己": 3,
    "巾": 3, "干": 3, "幺": 3, "广": 3, "廴": 3, "弋": 3, "弓": 3, "ヨ": 3, "彐": 3,
    "彡": 3, "彳": 3, "氵": 3, "犭": 3, "艹": 3, "辶": 3, "門": 8, "日": 4, "木": 4,
    # CJK部首補助・変形部首の画数
    "⺫": 5, "⺜": 4, "罒": 5, "网": 6, "⺼": 4, "⺾": 3, "⺡": 3, "⺦": 4, "⺧": 4, "⺨": 3,
    "⺩": 4, "⺪": 5, "⺭": 4, "⺮": 6, "⺯": 3, "⺰": 3, "⺱": 6, "⺲": 5, "⺳": 5, "⺶": 6,
    "⺷": 6, "⺸": 6, "⺹": 4, "⺺": 6, "⺻": 6, "⺽": 6, "⻀": 4, "⻁": 6, "⻂": 5, "⻃": 6,
    "⻄": 6, "⻅": 7, "⻆": 7, "⻇": 7, "⻈": 7, "⻉": 7, "⻊": 7, "⻋": 7, "⻌": 3, "⻍": 3,
    "⻎": 3, "⻏": 3, "⻐": 8, "⻑": 8, "⻒": 8, "⻓": 4, "⻔": 8, "⻕": 8, "⻖": 3, "⻗": 8,
    "⻘": 8, "⻙": 9, "⻚": 9, "⻛": 9, "⻜": 9, "⻝": 9, "⻞": 9, "⻟": 9, "⻠": 9, "⻡": 9,
    "⻢": 10, "⻣": 10, "⻤": 10, "⻥": 11, "⻦": 11, "⻧": 11, "⻨": 11, "⻩": 11, "⻪": 11,
}

_STROKE_CACHE: dict[str, int] | None = None


def load_stroke_counts() -> dict[str, int]:
    """DBから文字ごとの公式総画数をロードします。"""
    global _STROKE_CACHE
    if _STROKE_CACHE is not None:
        return _STROKE_CACHE

    counts = dict(PRIMITIVE_STROKES)
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            c.execute("SELECT char, stroke_count FROM characters WHERE stroke_count IS NOT NULL;")
            for ch, sc in c.fetchall():
                if ch and sc:
                    counts[ch] = int(sc)
            conn.close()
        except Exception:
            pass

    _STROKE_CACHE = counts
    return _STROKE_CACHE


def get_stroke_count(char: str, default: int = 1) -> int:
    """文字の画数を返します（未知の場合はdefault）。"""
    counts = load_stroke_counts()
    if char in counts:
        return counts[char]
    norm = ids_parser.normalize_component(char)
    if norm in counts:
        return counts[norm]
    norm_ent = ids_parser.normalize_entity(char)
    if norm_ent in counts:
        return counts[norm_ent]
    if hasattr(ids_parser, "EQUIV_GROUPS") and char in ids_parser.EQUIV_GROUPS:
        for eq in ids_parser.EQUIV_GROUPS[char]:
            if eq in counts:
                return counts[eq]
    return default


def estimate_node_strokes(node: dict[str, Any]) -> int:
    """ASTノードが持つ部品の合計画数を推定します。"""
    c_char = node.get("char") or node.get("raw_char") or ""
    if c_char:
        sc = get_stroke_count(c_char, default=0)
        if sc > 0:
            return sc

    children = node.get("children", [])
    if children:
        child_sum = sum(estimate_node_strokes(c) for c in children)
        if child_sum > 0:
            return child_sum

    return 1


def get_tier_1() -> list[str]:
    """Tier 1: 常用漢字 (2136字) + 人名用漢字 (~863字)."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT char FROM characters WHERE grade IS NOT NULL ORDER BY grade, sort_priority;")
    chars = [r[0] for r in c.fetchall() if r[0]]
    conn.close()
    return chars


def get_tier_2() -> list[str]:
    """Tier 2: KanjiVG収録全字 (~6.7k字)."""
    service = glyph_service._get_default_kanjivg_service()
    service._ensure_kanjivg_loaded()
    index = service._kanji_index or {}
    chars: list[str] = []
    for h in sorted(index.keys()):
        try:
            cp = int(h, 16)
            chars.append(chr(cp))
        except (ValueError, OverflowError):
            pass
    return chars


def has_risky_signature(char: str) -> bool:
    """文字がリスクの高い構文構造（⿻、深さ>=3、複合包囲、単一島など）を持つか判定。"""
    ids_str = ids_parser.get_character_ids(char)
    if not ids_str:
        return False

    # 1. ⿻ (重畳演算子)
    if "⿻" in ids_str:
        return True

    # 2. 構文木展開による検査
    try:
        tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=False)
    except Exception:
        return True

    has_deep = False
    has_complex_enclosure = False
    has_hardcoded_special = False

    enclosure_ops = {"⿴", "⿵", "⿶", "⿷", "⿸", "⿹", "⿺", "⿼", "⿽"}
    special_chars = {"𠃌", "虫", "中", "口", "囗", "門", "走", "𭕄", "⺍", "⺌"}

    def walk(n: dict[str, Any], depth: int):
        nonlocal has_deep, has_complex_enclosure, has_hardcoded_special
        if depth >= 3:
            has_deep = True
        op = n.get("op")
        children = n.get("children", [])
        if op in enclosure_ops:
            for child in children:
                if child.get("op") or child.get("children"):
                    has_complex_enclosure = True
        c_char = n.get("char") or n.get("raw_char") or ""
        if c_char in special_chars and depth > 1:
            has_hardcoded_special = True
        for ch in children:
            walk(ch, depth + 1)

    walk(tree, 0)
    if has_deep or has_complex_enclosure or has_hardcoded_special:
        return True

    return False


def get_tier_3(limit: int | None = None) -> list[str]:
    """Tier 3: リスクの高いシグネチャを持つ文字."""
    t1 = set(get_tier_1())
    t2 = set(get_tier_2())
    base_chars = sorted(t1 | t2)
    risky: list[str] = []
    for ch in base_chars:
        if has_risky_signature(ch):
            risky.append(ch)
            if limit and len(risky) >= limit:
                break
    return risky


def get_corpus(tier: int = 1, limit: int | None = None) -> list[str]:
    """指定されたTierのコーパス文字リストを取得します。"""
    if tier == 1:
        chars = get_tier_1()
    elif tier == 2:
        chars = get_tier_2()
    elif tier == 3:
        chars = get_tier_3(limit=limit)
    else:
        chars = get_tier_1()

    if limit and tier != 3:
        chars = chars[:limit]
    return chars


def get_node_signature(node: dict[str, Any], depth: int = 0) -> str:
    """不具合をグルーピング・重複排除するためのシグネチャ文字列を生成。"""
    op = node.get("op") or "leaf"
    children = node.get("children", [])
    c0 = children[0].get("char", "") if len(children) > 0 else ""
    c1 = children[1].get("char", "") if len(children) > 1 else ""
    role = node.get("role_label", "")
    char = node.get("char", "")
    return f"{op}:{c0}+{c1}@d{depth}:{role}:{char}"
