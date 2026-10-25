"""Jigmoフォント、GlyphWiki、KanjiVG、およびCHISE IDSに基づく漢字グリフ抽出・合成サービス。

本モジュールは、Unicode未収録文字やKanjiVG未収録文字を含むあらゆる漢字に対して、
Jigmoフォントからの正確なベクターアウトライン抽出、CHISE IDS木に基づくインタラクティブ複合SVG生成、
およびKanjiVG階層構造とCHISE IDSツリーのスマート統合アライメントを提供します。
すべてのユーザー向けラベル・文字列は日本語で表現されます。
"""

from __future__ import annotations

import functools
import glob
import gzip
import html
from pathlib import Path
import re
import sqlite3
from typing import Any
import xml.etree.ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

import ids_parser

# パス定義
BASE_DIR = Path(__file__).resolve().parent
FONTS_DIR = BASE_DIR / "static" / "fonts"
DATA_DIR = BASE_DIR / "data"
KANJIVG_PATH = DATA_DIR / "kanjivg.xml.gz"
CHISE_DIR = DATA_DIR / "chise-ids"
GLYPHWIKI_CACHE_DIR = DATA_DIR / "glyphwiki_cache"

# KanjiVG XML名前空間
KVG_NS = "http://kanjivg.tagaini.net"

# KanjiVG位置属性（kvg:position）の日本語対訳辞書
POSITION_MAP: dict[str, str] = {
    "top": "上",
    "bottom": "下",
    "left": "左",
    "right": "右",
    "middle": "中",
    "kamae": "構え",
    "kamaec": "構え",
    "nyo": "繞",
    "nyoc": "繞",
    "tare": "垂れ",
    "tarec": "垂れ",
    "tsukuri": "旁",
    "hen": "偏",
    "kanmuri": "冠",
    "ashi": "脚",
}

# 部首変形および CJK 部首補助の標準部品等価マップ
RADICAL_FORM_MAP: dict[str, set[str]] = {
    "⺕": {"彐", "⺕", "ヨ"},
    "彐": {"⺕", "彐", "ヨ"},
    "冖": {"冖", "冂"},
    "冂": {"冂", "冖"},
    "⺌": {"⺌", "⺍", "𭕄", "小"},
    "⺍": {"⺍", "⺌", "𭕄", "小"},
    "𭕄": {"𭕄", "⺍", "⺌", "小"},
    "小": {"小", "⺌", "⺍", "𭕄"},
    "龸": {"龸", "𰃮"},
    "𰃮": {"𰃮", "龸"},
    "⺘": {"扌", "手"},
    "扌": {"⺘", "手"},
    "⺣": {"灬", "火"},
    "灬": {"⺣", "火"},
    "⺫": {"罒", "网", "目"},
    "⺜": {"日"},
    "⺼": {"月", "肉"},
    "⺾": {"艹", "艸"},
    "⺡": {"氵", "水"},
    "⺦": {"爿"},
    "⺧": {"牛"},
    "⺨": {"犭", "犬"},
    "⺩": {"王", "玉"},
    "⺪": {"疋"},
    "⺭": {"礻", "示"},
    "⺮": {"竹"},
    "⺯": {"糸"},
    "⺰": {"纟"},
    "⺱": {"网", "罒"},
    "⺲": {"罒", "网"},
    "⺳": {"罒", "网"},
    "⺶": {"羊"},
    "⺷": {"羊"},
    "⺸": {"羊"},
    "⺹": {"耂", "老"},
    "⺺": {"肉", "月"},
    "⺻": {"聿"},
    "⺽": {"臼"},
    "⻀": {"艸", "艹"},
    "⻁": {"虎"},
    "⻂": {"衣"},
    "⻃": {"西"},
    "⻄": {"西"},
    "⻅": {"見"},
    "⻆": {"角"},
    "⻇": {"言"},
    "⻈": {"谷"},
    "⻉": {"豆"},
    "⻊": {"足"},
    "⻋": {"車"},
    "⻌": {"辶", "辵"},
    "⻍": {"辶", "辵"},
    "⻎": {"辶", "辵"},
    "⻏": {"邑", "阝"},
    "⻐": {"金"},
    "⻑": {"長"},
    "⻒": {"門"},
    "⻓": {"長"},
    "⻔": {"門"},
    "⻕": {"雨"},
    "⻖": {"阜", "阝"},
    "⻗": {"青"},
    "⻘": {"青"},
    "⻙": {"韋"},
    "⻚": {"頁"},
    "⻛": {"風"},
    "⻜": {"飛"},
    "⻝": {"食"},
    "⻞": {"食"},
    "⻟": {"食"},
    "⻠": {"食"},
    "⻡": {"食"},
    "⻢": {"馬"},
    "⻣": {"骨"},
    "⻤": {"鬼"},
    "⻥": {"魚"},
    "⻦": {"鳥"},
    "⻧": {"鹵"},
    "⻨": {"鹿"},
    "⻩": {"麥", "麦"},
    "⻪": {"麻"},
}


def get_equivalent_symbols(elem: str) -> set[str]:
    """EQUIV_GROUPS および部首変形辞書を通じて同値な全部品記号の推移的集合を返します。"""
    res: set[str] = set()
    if not elem:
        return res
    queue = [elem]
    while queue:
        s = queue.pop()
        if s in res:
            continue
        res.add(s)
        norm = ids_parser.normalize_component(s)
        if norm and norm not in res:
            queue.append(norm)
        ent = ids_parser.normalize_entity(s)
        if ent and ent not in res:
            queue.append(ent)
        if s in RADICAL_FORM_MAP:
            for v in RADICAL_FORM_MAP[s]:
                if v not in res:
                    queue.append(v)
        if hasattr(ids_parser, "EQUIV_GROUPS") and s in ids_parser.EQUIV_GROUPS:
            for v in ids_parser.EQUIV_GROUPS[s]:
                if v not in res:
                    queue.append(v)
    return res


_get_equivalent_symbols = get_equivalent_symbols


def normalize_element_symbol(element: str | None) -> tuple[str | None, str | None]:
    """
    KanjiVGの構成要素記号を正規化します。
    ⺍ (U+2E8D: つ・小かんむり) は 𭕄 (U+2D544) に正規化し、raw_element に元の '⺍' を記録します。
    
    戻り値:
        (normalized_element, raw_element)
    """
    if element is None:
        return None, None
    if element == "⺍":
        return "𭕄", "⺍"
    return element, None


class _JigmoFontManager:
    """Jigmoフォント群（Jigmo.ttf, Jigmo2.ttf, Jigmo3.ttf）を遅延ロード管理するクラス。"""

    def __init__(self, fonts_dir: Path | None = None) -> None:
        self.fonts_dir = fonts_dir or FONTS_DIR
        self._fonts: list[TTFont] | None = None
        self._cmaps: list[dict[int, str]] | None = None

    def _ensure_loaded(self) -> None:
        if self._fonts is not None:
            return
        font_filenames = ["Jigmo.ttf", "Jigmo2.ttf", "Jigmo3.ttf"]
        loaded_fonts: list[TTFont] = []
        loaded_cmaps: list[dict[int, str]] = []
        for filename in font_filenames:
            font_path = self.fonts_dir / filename
            if not font_path.is_file():
                continue
            # lazy=True でメモリ効率よくオープン
            font = TTFont(str(font_path), lazy=True)
            loaded_fonts.append(font)
            loaded_cmaps.append(font.getBestCmap() or {})
        self._fonts = loaded_fonts
        self._cmaps = loaded_cmaps

    @functools.lru_cache(maxsize=16384)
    def get_path(self, char: str) -> str | None:
        """単一のUnicode文字のベクターアウトライン（SVG pathのd属性）を返します。"""
        if not char:
            return None
        self._ensure_loaded()
        if not self._fonts or not self._cmaps:
            return None

        # ⺍ の場合は 𭕄 (U+2D544) へのフォールバックも考慮
        candidates = [char]
        if char == "⺍":
            candidates.append("𭕄")
        elif char == "𭕄":
            candidates.append("⺍")

        for c in candidates:
            try:
                codepoint = ord(c)
            except TypeError:
                continue

            for font, cmap in zip(self._fonts, self._cmaps):
                if codepoint in cmap:
                    glyph_name = cmap[codepoint]
                    glyph_set = font.getGlyphSet()
                    pen = SVGPathPen(glyph_set)
                    glyph = glyph_set[glyph_name]
                    glyph.draw(pen)
                    commands = pen.getCommands()
                    if commands:
                        return commands

        return None


# シングルトンフォントマネージャ
_FONT_MANAGER = _JigmoFontManager()


def get_jigmo_path(char: str) -> str | None:
    """
    指定された単一Unicode文字（例: '蛍' U+86CD, '𭕄' U+2D544, '𰃮' U+300EE）のJigmoフォントアウトラインを取得します。

    Jigmo.ttf（Plane 0/1）、Jigmo2.ttf（Plane 2）、Jigmo3.ttf（Plane 3）のcmapテーブルを順次参照し、
    SVGPathPenにより描画したSVG <path d="..."/> の d 属性文字列を返します。
    文字が存在しない場合は None を返します。
    """
    return _FONT_MANAGER.get_path(char)


def _infer_char_from_children(node: dict[str, Any]) -> str:
    """子ノードの文字一覧からCHISE逆引き辞書を用いて親文字を推定します。"""
    children = node.get("children", [])
    if not children:
        return ""
    child_chars = []
    for c in children:
        ch = c.get("char") or c.get("raw_char") or ""
        norm_ch, _ = normalize_element_symbol(ch)
        child_chars.append(norm_ch or ch)
    if child_chars and all(child_chars):
        service = _get_default_kanjivg_service()
        rev_dict = service.get_reverse_chise_dictionary()
        found = rev_dict.get(tuple(child_chars))
        if found:
            return found
    return ""


def _parse_svg_path_points(d: str) -> list[tuple[float, float]]:
    """SVGパスのd属性文字列から制御点・端点の座標リストを抽出します。"""
    tokens = re.findall(r"([A-Za-z])|([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)", d)
    cur_x, cur_y = 0.0, 0.0
    pts: list[tuple[float, float]] = []
    cmd = ""
    i = 0
    while i < len(tokens):
        t_cmd, t_val = tokens[i]
        if t_cmd:
            cmd = t_cmd
            i += 1
            continue
        if cmd == "M":
            cur_x, cur_y = float(t_val), float(tokens[i + 1][1])
            pts.append((cur_x, cur_y))
            i += 2
            cmd = "L"
        elif cmd == "m":
            cur_x += float(t_val)
            cur_y += float(tokens[i + 1][1])
            pts.append((cur_x, cur_y))
            i += 2
            cmd = "l"
        elif cmd == "C":
            for _ in range(3):
                pts.append((float(tokens[i][1]), float(tokens[i + 1][1])))
                i += 2
            cur_x, cur_y = pts[-1]
        elif cmd == "c":
            p1 = (cur_x + float(tokens[i][1]), cur_y + float(tokens[i + 1][1]))
            p2 = (cur_x + float(tokens[i + 2][1]), cur_y + float(tokens[i + 3][1]))
            p3 = (cur_x + float(tokens[i + 4][1]), cur_y + float(tokens[i + 5][1]))
            pts.extend([p1, p2, p3])
            cur_x, cur_y = p3
            i += 6
        elif cmd == "S":
            pts.extend([
                (float(tokens[i][1]), float(tokens[i + 1][1])),
                (float(tokens[i + 2][1]), float(tokens[i + 3][1])),
            ])
            cur_x, cur_y = pts[-1]
            i += 4
        elif cmd == "s":
            pts.extend([
                (cur_x + float(tokens[i][1]), cur_y + float(tokens[i + 1][1])),
                (cur_x + float(tokens[i + 2][1]), cur_y + float(tokens[i + 3][1])),
            ])
            cur_x, cur_y = pts[-1]
            i += 4
        elif cmd == "Q":
            pts.extend([
                (float(tokens[i][1]), float(tokens[i + 1][1])),
                (float(tokens[i + 2][1]), float(tokens[i + 3][1])),
            ])
            cur_x, cur_y = pts[-1]
            i += 4
        elif cmd == "q":
            pts.extend([
                (cur_x + float(tokens[i][1]), cur_y + float(tokens[i + 1][1])),
                (cur_x + float(tokens[i + 2][1]), cur_y + float(tokens[i + 3][1])),
            ])
            cur_x, cur_y = pts[-1]
            i += 4
        elif cmd == "L":
            cur_x, cur_y = float(t_val), float(tokens[i + 1][1])
            pts.append((cur_x, cur_y))
            i += 2
        elif cmd == "l":
            cur_x += float(t_val)
            cur_y += float(tokens[i + 1][1])
            pts.append((cur_x, cur_y))
            i += 2
        elif cmd == "H":
            cur_x = float(t_val)
            pts.append((cur_x, cur_y))
            i += 1
        elif cmd == "h":
            cur_x += float(t_val)
            pts.append((cur_x, cur_y))
            i += 1
        elif cmd == "V":
            cur_y = float(t_val)
            pts.append((cur_x, cur_y))
            i += 1
        elif cmd == "v":
            cur_y += float(t_val)
            pts.append((cur_x, cur_y))
            i += 1
        else:
            i += 1
    return pts


def _extract_ink_islands(base_path: str) -> list[dict[str, Any]]:
    """
    Jigmo明朝体のアウトラインパス(d属性)から独立したインク連結成分(外側輪郭+内包する穴)を抽出します。
    """
    contours = re.findall(r"M[^Z]+Z", base_path)
    outers: list[dict[str, Any]] = []
    holes: list[dict[str, Any]] = []

    for idx, c in enumerate(contours):
        pts = [(p[0], 880.0 - p[1]) for p in _parse_svg_path_points(c)]
        if len(pts) < 3:
            continue
        n = len(pts)
        a = 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
        x1 = min(p[0] for p in pts)
        x2 = max(p[0] for p in pts)
        y1 = min(p[1] for p in pts)
        y2 = max(p[1] for p in pts)
        item = {
            "id": idx,
            "d": c,
            "a": a,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "area": (x2 - x1) * (y2 - y1),
        }
        if a >= 0:
            item["holes"] = []
            item["hole_boxes"] = []
            outers.append(item)
        else:
            holes.append(item)

    for h in holes:
        candidates = []
        for o in outers:
            if o["x1"] - 8 <= h["x1"] and h["x2"] <= o["x2"] + 8 and o["y1"] - 8 <= h["y1"] and h["y2"] <= o["y2"] + 8:
                candidates.append(o)
        hbox = [round(h["x1"] / 1024.0, 4), round(h["y1"] / 1024.0, 4), round(h["x2"] / 1024.0, 4), round(h["y2"] / 1024.0, 4)]
        if candidates:
            best = min(candidates, key=lambda c: c["area"])
            best["holes"].append(h["d"])
            best["hole_boxes"].append(hbox)
        else:
            if outers:
                outers[0]["holes"].append(h["d"])
                outers[0]["hole_boxes"].append(hbox)

    islands: list[dict[str, Any]] = []
    for i, o in enumerate(outers):
        x1 = o["x1"] / 1024.0
        y1 = o["y1"] / 1024.0
        x2 = o["x2"] / 1024.0
        y2 = o["y2"] / 1024.0
        d_full = o["d"] + "".join(o["holes"])
        islands.append({
            "id": i,
            "d": d_full,
            "x1": round(x1, 4),
            "y1": round(y1, 4),
            "x2": round(x2, 4),
            "y2": round(y2, 4),
            "cx": round((x1 + x2) / 2.0, 4),
            "cy": round((y1 + y2) / 2.0, 4),
            "w": round(x2 - x1, 4),
            "h": round(y2 - y1, 4),
            "hole_boxes": o["hole_boxes"],
        })
    return islands


def _expected_min_islands(node: dict[str, Any]) -> int:
    children = node.get("children", [])
    if children:
        return sum(_expected_min_islands(c) for c in children)
    ch = node.get("char") or node.get("raw_char") or ""
    if ch in ("⺍", "⺌", "𭕄", "彡", "巛", "川", "氵", "灬", "小"):
        return 3
    if ch in ("丷", "八", "冫", "二", "亠", "人", "入", "ソ"):
        return 2
    return 1


# 包囲演算子ごとの外枠が接する辺（L:左, R:右, T:上, B:下）
_ENCLOSURE_FRAME_SIDES: dict[str, str] = {
    "⿴": "LRTB",
    "⿵": "LRT",
    "⿶": "LRB",
    "⿷": "LTB",
    "⿸": "LT",
    "⿹": "RT",
    "⿺": "LB",
    "⿼": "TRB",
    "⿽": "RB",
}


def _span_overlap(a1: float, a2: float, b1: float, b2: float) -> float:
    """1次元区間 [a1, a2] と [b1, b2] の重なり長を返します。"""
    return max(0.0, min(a2, b2) - max(a1, b1))


def _find_linear_gaps(
    islands: list[dict[str, Any]],
    k1: str,
    k2: str,
    min_gap: float = 0.003,
) -> list[tuple[float, float, float]]:
    """
    islands の指定軸方向区間 [isl[k1], isl[k2]] から、
    島と島の間にある空隙ギャップ (gap_start, gap_end, gap_mid) のリストを返します。
    """
    if len(islands) < 2:
        return []
    intervals = sorted((isl[k1], isl[k2]) for isl in islands)
    merged: list[list[float]] = []
    for a1, a2 in intervals:
        if not merged or a1 > merged[-1][1]:
            merged.append([a1, a2])
        else:
            merged[-1][1] = max(merged[-1][1], a2)
    gaps: list[tuple[float, float, float]] = []
    for i in range(len(merged) - 1):
        g_start = merged[i][1]
        g_end = merged[i + 1][0]
        if g_end - g_start >= min_gap:
            gaps.append((g_start, g_end, (g_start + g_end) / 2.0))
    return gaps


def _assign_linear(
    children: list[dict[str, Any]],
    islands: list[dict[str, Any]],
    axis: str,
    extent: float,
    child_assignments: dict[int, list[dict[str, Any]]],
    shared_out: set[int],
) -> None:
    """
    左右（⿰⿲）・上下（⿱⿳）構造において、各インク島を子要素の理論領域との
    軸方向重なり率で分配します。複数の子要素へ深く跨る島は共有島としてクリップ対象にします。
    """
    k1, k2 = ("x1", "x2") if axis == "x" else ("y1", "y2")
    off, size = (0, 2) if axis == "x" else (1, 3)
    spans = [(c["bbox"][off], c["bbox"][off] + c["bbox"][size]) for c in children]

    # 隣接子要素間の境界がインク島を切断している場合、近傍（±0.15以内）の実測インク空隙ギャップへ境界をスナップ
    if len(children) >= 2 and len(islands) >= 2:
        gaps = _find_linear_gaps(islands, k1, k2, min_gap=0.003)
        if gaps:
            for k in range(len(children) - 1):
                b = spans[k][1]
                cuts_island = any(isl[k1] < b - 0.015 and isl[k2] > b + 0.015 for isl in islands)
                if cuts_island:
                    valid_gaps = [
                        g for g in gaps
                        if abs(g[2] - b) <= 0.15
                        and (g[2] - spans[k][0] >= extent * 0.12)
                        and (spans[k + 1][1] - g[2] >= extent * 0.12)
                    ]
                    if valid_gaps:
                        best_gap = min(valid_gaps, key=lambda g: abs(g[2] - b))
                        snap_pt = round(best_gap[2], 4)
                        spans[k] = (spans[k][0], snap_pt)
                        spans[k + 1] = (snap_pt, spans[k + 1][1])
                        children[k]["bbox"][size] = round(snap_pt - spans[k][0], 4)
                        children[k + 1]["bbox"][off] = snap_pt
                        children[k + 1]["bbox"][size] = round(spans[k + 1][1] - snap_pt, 4)
                        ids_parser.compute_bboxes(
                            children[k],
                            bbox=tuple(children[k]["bbox"]),
                            path=children[k].get("path", "0"),
                            role_label=children[k].get("role_label", ""),
                        )
                        ids_parser.compute_bboxes(
                            children[k + 1],
                            bbox=tuple(children[k + 1]["bbox"]),
                            path=children[k + 1].get("path", "0"),
                            role_label=children[k + 1].get("role_label", ""),
                        )

    spanning_islands: list[tuple[dict[str, Any], list[float], list[float], int]] = []
    for isl in islands:
        a1, a2 = isl[k1], isl[k2]
        length = max(1e-4, a2 - a1)
        ovs = [_span_overlap(a1, a2, s1, s2) for (s1, s2) in spans]
        fracs = [ov / length for ov in ovs]
        best = max(range(len(children)), key=lambda i: fracs[i])
        if fracs[best] >= 0.70 or max(ovs) <= 0.0:
            if max(ovs) <= 0.0:
                center = (a1 + a2) / 2.0
                best = min(
                    range(len(children)),
                    key=lambda i: 0.0 if spans[i][0] <= center <= spans[i][1]
                    else min(abs(center - spans[i][0]), abs(center - spans[i][1])),
                )
            child_assignments[best].append(isl)
        else:
            spanning_islands.append((isl, fracs, ovs, best))

    for isl, fracs, ovs, best in spanning_islands:
        targets = [i for i in range(len(children)) if fracs[i] >= 0.20 and ovs[i] >= extent * 0.06]
        # 各ターゲットの充足状況を確認: 既に自身で非跨ぎ島を持ち期待島数を満たしている要素には押し付けない
        unsatisfied = [
            i for i in targets
            if len(child_assignments[i]) < _expected_min_islands(children[i])
            or not child_assignments[i]
        ]
        if unsatisfied and len(unsatisfied) < len(targets):
            filtered = [i for i in targets if i in unsatisfied or fracs[i] >= 0.65]
            if filtered:
                targets = filtered

        if len(targets) >= 2:
            for i in targets:
                child_assignments[i].append(isl)
            shared_out.add(isl["id"])
        elif len(targets) == 1:
            child_assignments[targets[0]].append(isl)
        else:
            child_assignments[best].append(isl)

    # 期待島数に満たない子要素: その領域の大半を覆う他要素の島を共有して補完（当・光・尚の⺌中央画など）
    for c_idx, c in enumerate(children):
        need = _expected_min_islands(c)
        if len(child_assignments[c_idx]) >= need and child_assignments[c_idx]:
            continue
        s1, s2 = spans[c_idx]
        c_len = max(1e-4, s2 - s1)
        for isl in islands:
            if isl in child_assignments[c_idx]:
                continue
            ov = _span_overlap(isl[k1], isl[k2], s1, s2)
            covers = ov / c_len
            if covers >= 0.60 or (not child_assignments[c_idx] and ov >= extent * 0.04):
                child_assignments[c_idx].append(isl)
                shared_out.add(isl["id"])


def _assign_enclosure(
    op: str,
    children: list[dict[str, Any]],
    islands: list[dict[str, Any]],
    box: tuple[float, float, float, float, float, float],
    child_assignments: dict[int, list[dict[str, Any]]],
    shared_out: set[int],
) -> bool:
    """
    包囲・垂れ・繞構造（⿴⿵⿶⿷⿸⿹⿺⿼⿽）において、外枠の接する辺へ到達する島を外枠へ、
    内側に収まる島を内側要素へ分配します。内側要素がインク島を得られない場合（外枠と融合）は共有します。
    """
    px1, py1, px2, py2, pw, ph = box
    sides = _ENCLOSURE_FRAME_SIDES.get(op, "")
    c0_char = children[0].get("char") or children[0].get("raw_char") or ""
    c0_kids = children[0].get("children", [])
    # 𠔼（⿵冂一）など、外枠側に内部横画を含む場合
    c0_has_inner_bar = c0_char == "𠔼" or (
        len(c0_kids) == 2 and (c0_kids[1].get("char") or c0_kids[1].get("raw_char")) == "一"
    )

    def reaches(isl: dict[str, Any], side: str) -> bool:
        if side == "L":
            return isl["x1"] <= px1 + pw * 0.10
        if side == "R":
            return isl["x2"] >= px2 - pw * 0.10
        if side == "T":
            return isl["y1"] <= py1 + ph * 0.10
        if side == "B":
            if op == "⿺":
                return isl["y2"] >= py2 - ph * 0.10 and isl["x1"] <= px1 + pw * 0.20
            return isl["y2"] >= py2 - ph * 0.10
        return False

    outer: list[dict[str, Any]] = []
    inner: list[dict[str, Any]] = []
    for isl in islands:
        if any(reaches(isl, s) for s in sides):
            outer.append(isl)
        elif c0_has_inner_bar and op == "⿵" and isl["cy"] < py1 + ph * 0.32 and isl["h"] < ph * 0.15:
            outer.append(isl)
        else:
            inner.append(isl)

    if not outer:
        return False
    child_assignments[0] = list(outer)
    child_assignments[1] = list(inner)

    # 内側要素が外枠と融合している場合: 内側理論領域を大きく覆う外枠島を共有（近など）
    ibx, iby, ibw, ibh = children[1]["bbox"]
    i_area = max(1e-4, ibw * ibh)
    if not inner:
        for isl in outer:
            cover = (
                _span_overlap(isl["x1"], isl["x2"], ibx, ibx + ibw)
                * _span_overlap(isl["y1"], isl["y2"], iby, iby + ibh)
            ) / i_area
            if cover < 0.50:
                continue
            # 穴（中空）が内側領域の大半を占める純粋な外枠（国・団の囗など）は共有しない
            hole_cover = sum(
                _span_overlap(hb[0], hb[2], ibx, ibx + ibw) * _span_overlap(hb[1], hb[3], iby, iby + ibh)
                for hb in isl.get("hole_boxes", [])
            ) / i_area
            if hole_cover >= 0.45:
                continue
            child_assignments[1].append(isl)
            shared_out.add(isl["id"])
    if not child_assignments[1]:
        # 最終フォールバック: 全外枠島を共有し、内側要素は自身のクリップ矩形で切り抜く
        child_assignments[1] = list(outer)
        shared_out.update(i["id"] for i in outer)
    return True


def _assign_ink_islands_to_tree(
    tree_node: dict[str, Any],
    islands: list[dict[str, Any]],
    shared_ids: set[int] | None = None,
    parent_op: str | None = None,
) -> None:
    """
    抽出されたインク島を漢字構成木の各階層ノードへ再帰的に最適分配・局所化します。
    """
    if shared_ids is None:
        shared_ids = set()

    tree_node["_islands"] = islands
    # インク島を持たないノードは全体グリフへフォールバックするため、必ずクリップ対象とする
    has_shared = (not islands) or bool(shared_ids and any(isl["id"] in shared_ids for isl in islands))
    tree_node["_has_shared_island"] = has_shared

    children = tree_node.get("children", [])

    # 共有島を持たない非ルートノードの場合、所属インク島の外接矩形へbboxを精密に引き締める
    if islands and not has_shared and tree_node.get("path", "0") != "0":
        ix1 = max(0.0, min(i["x1"] for i in islands) - 0.008)
        iy1 = max(0.0, min(i["y1"] for i in islands) - 0.008)
        ix2 = min(1.0, max(i["x2"] for i in islands) + 0.008)
        iy2 = min(1.0, max(i["y2"] for i in islands) + 0.008)
        theo = tree_node.get("bbox") or [0.0, 0.0, 1.0, 1.0]
        if parent_op in ("⿰", "⿲") or theo[0] > 0.0:
            ix1 = max(theo[0], ix1)
        if parent_op in ("⿰", "⿲") or (theo[0] + theo[2]) < 1.0:
            ix2 = min(theo[0] + theo[2], ix2)
        if ix2 <= ix1 + 0.02:
            ix1 = theo[0]
            ix2 = theo[0] + theo[2]
        if iy2 <= iy1 + 0.02:
            iy1 = theo[1]
            iy2 = theo[1] + theo[3]
        oversized = (
            not tree_node.get("is_flanking")
            and ((ix2 - ix1) > theo[2] + 0.30 or (iy2 - iy1) > theo[3] + 0.30)
        )
        if oversized:
            # 理論領域を大きく逸脱するインク島（隣接要素と融合）: 引き締めず理論領域でクリップ
            has_shared = True
            tree_node["_has_shared_island"] = True
        else:
            tree_node["bbox"] = [round(ix1, 4), round(iy1, 4), round(ix2 - ix1, 4), round(iy2 - iy1, 4)]
            if tree_node.get("is_flanking") or tree_node.get("role_label") == "中央・下":
                # 挟み込み構造は親側で配置済みのため、葉矩形のみ同期
                if not children:
                    tree_node["clip_rects"] = [tree_node["bbox"]]
            else:
                # clip_rects / hit_rects と子要素の理論領域を引き締め後のbboxへ再同期
                ids_parser.compute_bboxes(
                    tree_node,
                    bbox=tuple(tree_node["bbox"]),
                    path=tree_node.get("path", "0"),
                    role_label=tree_node.get("role_label", ""),
                )

    if not children or not islands:
        return

    px1 = min(i["x1"] for i in islands)
    py1 = min(i["y1"] for i in islands)
    px2 = max(i["x2"] for i in islands)
    py2 = max(i["y2"] for i in islands)
    pw = max(0.01, px2 - px1)
    ph = max(0.01, py2 - py1)

    op = tree_node.get("op", "")
    next_shared_ids = set(shared_ids)
    child_assignments: dict[int, list[dict[str, Any]]] = {idx: [] for idx in range(len(children))}

    if len(children) == 2 and children[0].get("is_flanking"):
        left_flank = [isl for isl in islands if isl["cx"] < px1 + pw * 0.36 and isl["w"] < pw * 0.52]
        right_flank = [isl for isl in islands if isl["cx"] > px1 + pw * 0.64 and isl["w"] < pw * 0.52]
        center_islands = [isl for isl in islands if isl not in left_flank and isl not in right_flank]
        if left_flank and right_flank and center_islands:
            child_assignments[0] = left_flank + right_flank
            child_assignments[1] = list(center_islands)
            # 中央要素の島が両脇へ深く食い込む場合（辯の言の口と右の辛など）は共有してクリップ
            for isl in center_islands:
                if isl["w"] > pw * 0.50 and (isl["x2"] > px1 + pw * 0.72 or isl["x1"] < px1 + pw * 0.28):
                    child_assignments[0].append(isl)
                    next_shared_ids.add(isl["id"])
        else:
            next_shared_ids |= {i["id"] for i in islands}
            child_assignments[0] = list(islands)
            child_assignments[1] = list(islands)

    elif op in ("⿱", "⿳"):
        handled = False
        if len(islands) == 1:
            pass
        elif len(children) == 2 and len(islands) > 4:
            # 冠の下部アーチ（蛍の𰃮の冖など）: 上部要素が冖系の冠である場合のみ
            c0 = children[0]
            c0_char = c0.get("char") or c0.get("raw_char") or ""
            c0_leaf_chars = {(k.get("char") or k.get("raw_char") or "") for k in c0.get("children", [])}
            is_crown = c0_char in ("𰃮", "冖", "宀", "罒", "⺫") or bool(c0_leaf_chars & {"冖", "宀"})
            if is_crown:
                mid_arches = [
                    isl for isl in islands
                    if isl["w"] > pw * 0.80 and isl["h"] < ph * 0.35
                    and py1 + ph * 0.22 <= isl["y1"] <= py1 + ph * 0.48
                ]
                if mid_arches:
                    arch_y1 = max(a["y1"] for a in mid_arches)
                    above = [isl for isl in islands if isl["y1"] <= arch_y1 + 0.03 and isl["h"] < ph * 0.72]
                    below = [isl for isl in islands if isl["y1"] > arch_y1 + 0.03 and isl["h"] < ph * 0.72]
                    spanning = [isl for isl in islands if isl["h"] >= ph * 0.72]
                    if above and below:
                        child_assignments[0] = above
                        child_assignments[1] = below
                        for s in spanning:
                            child_assignments[0].append(s)
                            child_assignments[1].append(s)
                            next_shared_ids.add(s["id"])
                        handled = True
        if not handled:
            if len(islands) == 1:
                for c_idx in range(len(children)):
                    child_assignments[c_idx] = list(islands)
                next_shared_ids.add(islands[0]["id"])
            else:
                _assign_linear(children, islands, "y", ph, child_assignments, next_shared_ids)

    elif op in ("⿰", "⿲"):
        if len(islands) == 1:
            for c_idx in range(len(children)):
                child_assignments[c_idx] = list(islands)
            next_shared_ids.add(islands[0]["id"])
        else:
            _assign_linear(children, islands, "x", pw, child_assignments, next_shared_ids)

    else:
        # 構え(包囲)構造や交差構造
        assigned = False
        if op in _ENCLOSURE_FRAME_SIDES and len(children) == 2 and len(islands) >= 2:
            assigned = _assign_enclosure(
                op, children, islands, (px1, py1, px2, py2, pw, ph), child_assignments, next_shared_ids
            )

        if not assigned and op == "⿻" and len(children) == 2 and len(islands) >= 2:
            # 交差構造（氷、𠂭など）: 単独の点・払いあるいは大きな骨格島と小さな点島を分離
            c0_char = children[0].get("char") or children[0].get("raw_char") or ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or ""
            if c1_char in ("丶", "丿") and c0_char not in ("丶", "丿"):
                c1_bx, c1_by, c1_bw, c1_bh = children[1]["bbox"]
                c1_cx, c1_cy = c1_bx + c1_bw / 2.0, c1_by + c1_bh / 2.0
                dot = min(islands, key=lambda isl: (isl["cx"] - c1_cx) ** 2 + (isl["cy"] - c1_cy) ** 2)
                child_assignments[1] = [dot]
                child_assignments[0] = [i for i in islands if i is not dot]
                assigned = True
            elif c0_char in ("丶", "丿") and c1_char not in ("丶", "丿"):
                c0_bx, c0_by, c0_bw, c0_bh = children[0]["bbox"]
                c0_cx, c0_cy = c0_bx + c0_bw / 2.0, c0_by + c0_bh / 2.0
                dot = min(islands, key=lambda isl: (isl["cx"] - c0_cx) ** 2 + (isl["cy"] - c0_cy) ** 2)
                child_assignments[0] = [dot]
                child_assignments[1] = [i for i in islands if i is not dot]
                assigned = True
            elif abs((children[0]["bbox"][1] + children[0]["bbox"][3] / 2.0) - (children[1]["bbox"][1] + children[1]["bbox"][3] / 2.0)) >= 0.20:
                _assign_linear(children, islands, "y", ph, child_assignments, next_shared_ids)
                assigned = True
            elif abs((children[0]["bbox"][0] + children[0]["bbox"][2] / 2.0) - (children[1]["bbox"][0] + children[1]["bbox"][2] / 2.0)) >= 0.20:
                _assign_linear(children, islands, "x", pw, child_assignments, next_shared_ids)
                assigned = True
            else:
                large_spanning = [
                    isl
                    for isl in islands
                    if (isl["w"] > pw * 0.60 and isl["h"] > ph * 0.60)
                    or max(isl["w"] / pw, isl["h"] / ph) > 0.72
                ]
                small_local = [isl for isl in islands if isl not in large_spanning]
                if large_spanning and small_local:
                    exp0 = _expected_min_islands(children[0])
                    exp1 = _expected_min_islands(children[1])
                    if c0_char in ("丶", "丿", "丷", "八", "冫") and c1_char not in ("丶", "丿", "丷", "八", "冫"):
                        child_assignments[0] = small_local
                        child_assignments[1] = large_spanning
                    elif exp0 > exp1 and len(small_local) >= exp0 and len(large_spanning) <= exp1:
                        child_assignments[0] = small_local
                        child_assignments[1] = large_spanning
                    else:
                        child_assignments[0] = large_spanning
                        child_assignments[1] = small_local
                    assigned = True

        if not assigned:
            next_shared_ids |= {i["id"] for i in islands}
            for c_idx in range(len(children)):
                child_assignments[c_idx] = list(islands)

    for c_idx, child in enumerate(children):
        _assign_ink_islands_to_tree(child, child_assignments[c_idx], next_shared_ids, parent_op=op)

    if (
        len(children) == 2
        and (children[0].get("char") in ("口", "囗") or children[0].get("raw_char") in ("口", "囗"))
        and (children[1].get("char") == "丨" or children[1].get("raw_char") == "丨")
    ):
        all_holes = [hb for isl in islands for hb in isl.get("hole_boxes", [])]
        if len(all_holes) >= 2:
            sorted_holes = sorted(all_holes, key=lambda b: b[0])
            hl, hr = None, None
            for k in range(len(sorted_holes) - 1):
                h1 = sorted_holes[k]
                h2 = sorted_holes[k + 1]
                if max(h1[1], h2[1]) < min(h1[3], h2[3]):
                    hl, hr = h1, h2
                    break
            if hl and hr:
                hx1 = hl[0]
                hx2 = hr[2]
                hy1 = min(hl[1], hr[1])
                hy2 = max(hl[3], hr[3])

                ox1 = round(max(0.0, hx1 - 0.085), 4)
                ox2 = round(min(1.0, hx2 + 0.085), 4)
                oy1 = round(max(0.0, hy1 - 0.055), 4)
                oy2 = round(min(1.0, hy2 + 0.058), 4)

                children[0]["bbox"] = [ox1, oy1, round(ox2 - ox1, 4), round(oy2 - oy1, 4)]
                children[0]["clip_rects"] = [
                    [ox1, oy1, round(ox2 - ox1, 4), round(hy1 - oy1 + 0.006, 4)],
                    [ox1, round(hy2 - 0.006, 4), round(ox2 - ox1, 4), round(oy2 - hy2 + 0.006, 4)],
                    [ox1, oy1, round(hx1 - ox1 + 0.006, 4), round(oy2 - oy1, 4)],
                    [round(hx2 - 0.006, 4), oy1, round(ox2 - hx2 + 0.006, 4), round(oy2 - oy1, 4)],
                ]

                vx1 = round(max(0.0, hl[2] - 0.015), 4)
                vx2 = round(min(1.0, hr[0] + 0.028), 4)
                if tree_node.get("path", "0") != "0" and (tree_node["bbox"][1] > 0.25 or oy1 > 0.30):
                    vy1 = round(max(max(0.0, oy1 - 0.10), min(tree_node["bbox"][1], min(i["y1"] for i in islands))), 4)
                else:
                    vy1 = round(min(tree_node["bbox"][1], min(i["y1"] for i in islands)), 4)
                vy2 = round(min(tree_node["bbox"][1] + tree_node["bbox"][3], oy2 + 0.08), 4)
                children[1]["bbox"] = [vx1, vy1, round(vx2 - vx1, 4), round(vy2 - vy1, 4)]
                children[1]["clip_rects"] = [children[1]["bbox"]]
                tree_node["bbox"] = [ox1, vy1, round(ox2 - ox1, 4), round(vy2 - vy1, 4)]

    if tree_node.get("is_flanking") and len(children) == 2:
        tree_node["clip_rects"] = [children[0]["bbox"], children[1]["bbox"]]
        tree_node["hit_rects"] = [children[0]["bbox"], children[1]["bbox"]]
    elif len(children) == 2 and tree_node.get("role_label") == "中央・下":
        tree_node["clip_rects"] = [children[0]["bbox"], children[1]["bbox"]]
        tree_node["hit_rects"] = [children[0]["bbox"], children[1]["bbox"]]
    elif children and tree_node.get("_has_shared_island") and tree_node.get("path", "0") != "0":
        if tree_node.get("hit_rects"):
            tree_node["clip_rects"] = list(tree_node["hit_rects"])
        elif not tree_node.get("clip_rects"):
            tree_node["clip_rects"] = [tree_node["bbox"]]


def build_interactive_ids_svg(tree_node: dict[str, Any]) -> dict[str, Any]:
    """
    KanjiVG未収録文字や拡張領域文字を含む任意の漢字構成木から、
    ホバーやドリルダウンが可能なインタラクティブ複合SVGデータ構造を生成します。
    """
    root_char = tree_node.get("char") or tree_node.get("raw_char") or _infer_char_from_children(tree_node)
    base_path = get_jigmo_path(root_char)
    if not base_path and root_char:
        norm_root = ids_parser.normalize_entity(root_char)
        if norm_root != root_char:
            base_path = get_jigmo_path(norm_root)

    if base_path:
        islands = _extract_ink_islands(base_path)
        _assign_ink_islands_to_tree(tree_node, islands, set())

    component_layers: list[dict[str, Any]] = []

    def traverse(node: dict[str, Any], depth: int, parent_path: str) -> None:
        children = node.get("children", [])
        for i, child in enumerate(children):
            c_char = child.get("char") or child.get("raw_char") or _infer_char_from_children(child)
            c_path = child.get("path") or f"{parent_path}.{i}"
            c_role = child.get("role_label", "")
            c_bbox = child.get("bbox", [0.0, 0.0, 1.0, 1.0])
            c_clip_rects = child.get("clip_rects") or [c_bbox]
            x, y, w, h = c_bbox

            child_islands = child.get("_islands") or []
            slice_path = "".join(isl["d"] for isl in child_islands) if child_islands else (base_path or "")
            if not child_islands or slice_path == (base_path or ""):
                needs_clip = True
            else:
                needs_clip = bool(child.get("_has_shared_island", False))
                if not needs_clip and child_islands and child.get("path", "0") != "0":
                    sw = max(i["x2"] for i in child_islands) - min(i["x1"] for i in child_islands)
                    sh = max(i["y2"] for i in child_islands) - min(i["y1"] for i in child_islands)
                    if sw > w + 0.30 or sh > h + 0.30:
                        needs_clip = True

            svg_p = get_jigmo_path(c_char)
            if not svg_p and c_char:
                norm_c = ids_parser.normalize_entity(c_char)
                if norm_c != c_char:
                    svg_p = get_jigmo_path(norm_c)

            # svg_transform 計算式:
            # translate({x*1024}, {y*1024 + h*880}) scale({w}, {-h})
            tx = round(x * 1024.0, 2)
            ty = round(y * 1024.0 + h * 880.0, 2)
            sx = round(w, 4)
            sy = round(-h, 4)
            svg_transform = f"translate({tx:g}, {ty:g}) scale({sx:g}, {sy:g})"

            component_layers.append({
                "path": c_path,
                "char": c_char,
                "depth": depth,
                "role_label": c_role,
                "bbox": c_bbox,
                "clip_rects": c_clip_rects,
                "hit_rects": child.get("hit_rects"),
                "svg_path": svg_p,
                "svg_transform": svg_transform,
                "slice_path": slice_path,
                "needs_clip": needs_clip,
            })
            traverse(child, depth + 1, c_path)

    root_path = tree_node.get("path", "0")
    traverse(tree_node, 1, root_path)

    return {
        "base_path": base_path,
        "component_layers": component_layers,
    }


def get_glyph_svg(token: str, recursive_tree: dict[str, Any] | None = None) -> str:
    """
    指定された文字または実体参照（token）の完全なSVG文書文字列を返します。
    """
    token_clean = token.strip()
    if not token_clean:
        return ""

    # 1. 単一文字または正規化エンティティがJigmoフォントで描画可能な場合
    path_d = get_jigmo_path(token_clean) or get_jigmo_path(ids_parser.normalize_entity(token_clean))
    if path_d:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">\n'
            f'  <path d="{path_d}" transform="translate(0, 880) scale(1, -1)" fill="#57606a"/>\n'
            f'</svg>'
        )

    # 3. ローカルGlyphWikiキャッシュの確認
    slug = token_clean.strip("&;").lower()
    cache_candidates = [
        GLYPHWIKI_CACHE_DIR / f"{slug}.svg",
    ]
    if slug.startswith("i-"):
        cache_candidates.append(GLYPHWIKI_CACHE_DIR / f"{slug[2:]}.svg")

    for cache_path in cache_candidates:
        if cache_path.is_file():
            try:
                content = cache_path.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except OSError:
                pass

    # 4. 合成複合ベクターSVGの生成試行（IDS木分解からトップレベル部品を抽出）
    tree = recursive_tree
    if tree is None:
        try:
            tree = ids_parser.decompose_character(
                token_clean, max_depth=3, use_atomic=True, compute_bbox=True
            )
        except Exception:
            tree = None

    if tree:
        interactive_svg = build_interactive_ids_svg(tree)
        layers = interactive_svg.get("component_layers", [])
        # 祖先（depth >= 1）がすでに svg_path を持つ層を除外し、最上位の svg_path 保持層を収集
        selected_layers: list[dict[str, Any]] = []
        svg_ancestor_paths: set[str] = set()
        sorted_layers = sorted(layers, key=lambda l: len(l["path"].split(".")))
        for layer in sorted_layers:
            l_path = layer.get("path", "")
            if not layer.get("svg_path"):
                continue
            has_ancestor = False
            for anc in svg_ancestor_paths:
                if l_path.startswith(anc + "."):
                    has_ancestor = True
                    break
            if not has_ancestor:
                selected_layers.append(layer)
                svg_ancestor_paths.add(l_path)

        if selected_layers:
            paths_xml = [
                f'  <path d="{l["svg_path"]}" transform="{l["svg_transform"]}" fill="#57606a"/>'
                for l in selected_layers
            ]
            paths_content = "\n".join(paths_xml)
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">\n'
                f"{paths_content}\n"
                f'</svg>'
            )

    # 5. 完全フォールバック（暗色テーマ調和・コンパクト角丸矩形）
    display_text = html.escape(token_clean)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">\n'
        f'  <rect width="1024" height="1024" rx="32" fill="rgba(128,128,128,0.12)" stroke="rgba(128,128,128,0.35)" stroke-width="8"/>\n'
        f'  <text x="512" y="512" font-family="sans-serif" font-size="140" font-weight="bold" '
        f'text-anchor="middle" dominant-baseline="central" fill="#8b949e">{display_text}</text>\n'
        f'</svg>'
    )


class KanjiVGService:
    """
    KanjiVG XMLデータのオンデマンド解析およびCHISE IDS木とのスマート整合を行うサービスクラス。
    """

    def __init__(
        self,
        kanjivg_path: str | Path | None = None,
        chise_dir: str | Path | None = None,
    ) -> None:
        self.kanjivg_path = Path(kanjivg_path or KANJIVG_PATH)
        self.chise_dir = Path(chise_dir or CHISE_DIR)
        self._kanji_index: dict[str, str] | None = None
        self._chise_dict: dict[str, str] | None = None
        self._reverse_chise: dict[tuple[str, ...], str] | None = None

    def get_chise_dictionary(self) -> dict[str, str]:
        """CHISE IDS辞書（文字または実体参照 -> IDS文字列）を取得します。"""
        if self._chise_dict is None:
            self._chise_dict = ids_parser.get_ids_dict()
        return self._chise_dict

    def get_reverse_chise_dictionary(self) -> dict[tuple[str, ...], str]:
        """CHISE IDSの構成要素タプル -> 合成文字の逆引き辞書を返します。"""
        if self._reverse_chise is not None:
            return self._reverse_chise

        chise_dict = self.get_chise_dictionary()
        rev_map: dict[tuple[str, ...], str] = {}
        def _char_priority(c: str) -> int:
            if len(c) == 1:
                cp = ord(c)
                if 0x4E00 <= cp <= 0x9FFF:  # CJK統合漢字
                    return 10
                if 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x323AF:  # 拡張領域 A-J
                    return 8
                return 6
            if not c.startswith("&") and not any(
                c.startswith(p)
                for p in ["J90", "C1", "C2", "C3", "CDP", "CB", "HZK", "M-"]
            ):
                return 4
            return 1

        for char, ids_str in chise_dict.items():
            if not ids_str or ids_str == char:
                continue
            raw_tree = ids_parser.parse_ids(ids_str)
            raw_children = raw_tree.get("children", [])
            if raw_children:
                c_chars = []
                for rc in raw_children:
                    ch = rc.get("char") or rc.get("raw_char") or ""
                    norm_ch, _ = normalize_element_symbol(ch)
                    c_chars.append(norm_ch or ch)
                if all(c_chars) and len(c_chars) >= 2:
                    tup = tuple(c_chars)
                    curr = rev_map.get(tup)
                    if curr is None or _char_priority(char) > _char_priority(curr):
                        rev_map[tup] = char
        self._reverse_chise = rev_map
        return self._reverse_chise

    def _ensure_kanjivg_loaded(self) -> None:
        """kanjivg.xml.gz を読み込み、16進コードポイントからXMLブロックへの索引を作成します。"""
        if self._kanji_index is not None:
            return

        index: dict[str, str] = {}
        if self.kanjivg_path.is_file():
            try:
                with gzip.open(self.kanjivg_path, "rt", encoding="utf-8") as f:
                    xml_text = f.read()

                # <kanji id="kvg:kanji_086cd">...</kanji> の抽出
                start_marker = "<kanji "
                end_marker = "</kanji>"
                pos = 0
                while True:
                    start_pos = xml_text.find(start_marker, pos)
                    if start_pos == -1:
                        break
                    end_pos = xml_text.find(end_marker, start_pos)
                    if end_pos == -1:
                        break
                    block = xml_text[start_pos : end_pos + len(end_marker)]
                    pos = end_pos + len(end_marker)

                    # id 属性から 16 進コードポイントを取得
                    id_idx = block.find('id="kvg:kanji_')
                    if id_idx != -1:
                        val_start = id_idx + len('id="kvg:kanji_')
                        val_end = block.find('"', val_start)
                        if val_end != -1:
                            hex_code = block[val_start:val_end].lower()
                            index[hex_code] = block
            except OSError:
                pass

        self._kanji_index = index

    def _normalize_codepoint_hex(self, char_or_hex: str) -> str:
        """文字または16進文字列を KanjiVG 形式の小文字16進数（例: '086cd'）に正規化します。"""
        token = char_or_hex.strip()
        if len(token) == 1:
            return f"{ord(token):05x}"
        if token.upper().startswith("U+"):
            try:
                return f"{int(token[2:], 16):05x}"
            except ValueError:
                return token.lower()
        try:
            return f"{int(token, 16):05x}"
        except ValueError:
            return token.lower()

    def get_kanji_xml(self, char_or_hex: str) -> str | None:
        """指定された文字または16進コードの <kanji> XML 文字列を取得します。"""
        self._ensure_kanjivg_loaded()
        if not self._kanji_index:
            return None
        hex_code = self._normalize_codepoint_hex(char_or_hex)
        return self._kanji_index.get(hex_code)

    def _get_chise_subcomponents(self, char_or_token: str) -> list[dict[str, str | None]]:
        """CHISE IDS辞書から直接の子コンポーネントとその役割（上、下、左、右等）を取得します。"""
        chise_dict = self.get_chise_dictionary()
        ids_str = chise_dict.get(char_or_token)
        if not ids_str or ids_str == char_or_token:
            return []

        raw_tree = ids_parser.parse_ids(ids_str)
        operator = raw_tree.get("op")
        raw_children = raw_tree.get("children", [])
        if not raw_children:
            return []

        roles = ids_parser.IDC_INFO.get(operator, {}).get("parts", [None] * len(raw_children))
        if len(roles) < len(raw_children):
            roles = list(roles) + [None] * (len(raw_children) - len(roles))

        results: list[dict[str, str | None]] = []
        for role, c in zip(roles, raw_children):
            c_char = c.get("char") or c.get("raw_char") or ""
            if c_char:
                norm_c, raw_c = normalize_element_symbol(c_char)
                results.append({
                    "char": norm_c or c_char,
                    "raw_char": raw_c or c_char,
                    "role": role,
                })
        return results

    def _align_with_chise(
        self,
        node: dict[str, Any],
        parent_element: str | None = None,
    ) -> None:
        """
        KanjiVGのグループ木を巡回し、kvg:element が欠落しているグループノードに対して
        親漢字のCHISE IDSツリーと位置・子構成要素を照合して要素文字を推定付与します。
        """
        # 現在のノードに element が存在しない場合、親のCHISE分解からマッチング
        if not node.get("element") and parent_element:
            pos = node.get("position")
            child_elems = [c.get("element") for c in node.get("children", []) if c.get("element")]
            child_raw_elems = [
                c.get("raw_element") or c.get("element")
                for c in node.get("children", [])
                if c.get("element")
            ]

            parent_candidates = self._get_chise_subcomponents(parent_element)
            matched_element: str | None = None

            for cand in parent_candidates:
                cand_char = cand["char"]
                cand_role = cand["role"]
                if not cand_char:
                    continue

                # 候補自身の子コンポーネントを取得
                cand_subs = self._get_chise_subcomponents(cand_char)
                cand_sub_chars = [s["char"] for s in cand_subs]
                cand_sub_raws = [s["raw_char"] for s in cand_subs]

                # 1. 子要素一覧の完全一致検証（正規化後またはraw形式）
                if cand_sub_chars and (
                    cand_sub_chars == child_elems
                    or cand_sub_raws == child_raw_elems
                    or cand_sub_chars == child_raw_elems
                ):
                    matched_element = cand_char
                    break

                # 2. 位置（例: '上', '下'）の一致と、子要素の包含検証
                if pos and cand_role == pos:
                    if not child_elems or not cand_sub_chars or set(child_elems).issubset(set(cand_sub_chars)):
                        matched_element = cand_char
                        break

            if matched_element:
                node["element"] = matched_element
                node["inferred_from_chise"] = True

        # 子ノードへの再帰処理
        current_elem = node.get("element") or parent_element
        for child in node.get("children", []):
            self._align_with_chise(child, current_elem)

    def parse_kanji(
        self,
        char_or_hex: str,
        align_chise: bool = True,
    ) -> dict[str, Any] | None:
        """
        指定された文字または16進コードのKanjiVG <g> および <path> 構造を解析し、
        正規化および日本語位置変換済みの構造化ディクショナリを返します。

        align_chise=True の場合、CHISE IDS情報に基づく推論補完を実施します。
        """
        xml_text = self.get_kanji_xml(char_or_hex)
        if not xml_text:
            return None

        # 単体パース時に未定義プレフィックスエラーを回避するため名前空間宣言を補完
        if "xmlns:kvg=" not in xml_text:
            xml_text = xml_text.replace("<kanji ", f'<kanji xmlns:kvg="{KVG_NS}" ', 1)

        try:
            kanji_elem = ET.fromstring(xml_text)
        except ET.ParseError:
            return None

        # kanji 要素直下のルート <g> を取得
        root_g = kanji_elem.find("g")
        if root_g is None:
            # 名前空間対応
            for child in kanji_elem:
                if child.tag.endswith("g"):
                    root_g = child
                    break
        if root_g is None:
            return None

        def parse_group(g: ET.Element) -> dict[str, Any]:
            gid = g.attrib.get("id", "")
            raw_elem = g.attrib.get(f"{{{KVG_NS}}}element") or g.attrib.get("kvg:element")
            orig = g.attrib.get(f"{{{KVG_NS}}}original") or g.attrib.get("kvg:original")
            pos = g.attrib.get(f"{{{KVG_NS}}}position") or g.attrib.get("kvg:position")

            element, raw_element = normalize_element_symbol(raw_elem)
            node: dict[str, Any] = {
                "id": gid,
                "element": element,
                "strokes": [],
                "children": [],
            }

            if raw_element:
                node["raw_element"] = raw_element
            if orig:
                node["original"] = orig
            if pos:
                node["position"] = POSITION_MAP.get(pos, pos)

            for child in g:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "path":
                    pid = child.attrib.get("id", "")
                    d = child.attrib.get("d", "")
                    ptype = (
                        child.attrib.get(f"{{{KVG_NS}}}type")
                        or child.attrib.get("kvg:type")
                        or ""
                    )
                    node["strokes"].append({"id": pid, "d": d, "type": ptype})
                elif tag == "g":
                    node["children"].append(parse_group(child))

            return node

        root_node = parse_group(root_g)

        if align_chise:
            self._align_with_chise(root_node, None)

        return root_node

    @staticmethod
    def get_group_by_id(root_node: dict[str, Any], target_id: str) -> dict[str, Any] | None:
        """解析済みグループ木から指定された id を持つノードを検索して返します。"""
        if root_node.get("id") == target_id:
            return root_node
        for child in root_node.get("children", []):
            found = KanjiVGService.get_group_by_id(child, target_id)
            if found is not None:
                return found
        return None

    @staticmethod
    def flatten_groups(root_node: dict[str, Any]) -> list[dict[str, Any]]:
        """解析済みグループ木に含まれるすべてのグループノードをリスト形式で返します。"""
        nodes = [root_node]
        for child in root_node.get("children", []):
            nodes.extend(KanjiVGService.flatten_groups(child))
        return nodes


@functools.lru_cache(maxsize=1)
def _get_default_kanjivg_service() -> KanjiVGService:
    """内部利用のデフォルトKanjiVGServiceシングルトンを返します。"""
    return KanjiVGService()


# 基本筆画・部首の標準画数定義（辞書未収録・極小部品用フォールバック）
PRIMITIVE_STROKES: dict[str, int] = {
    "一": 1, "丨": 1, "丿": 1, "丶": 1, "乙": 1, "亅": 1, "乚": 1, "乀": 1, "乁": 1, "㇇": 1,
    "二": 2, "十": 2, "人": 2, "入": 2, "八": 2, "几": 2, "凵": 2, "刀": 2, "力": 2,
    "勹": 2, "匕": 2, "匚": 2, "卜": 2, "卩": 2, "厂": 2, "厶": 2, "又": 2, "冖": 2,
    "冫": 2, "冂": 2, "亠": 2, "亻": 2, "𠂉": 2, "𠂊": 2, "𭕄": 3, "⺍": 3, "⺌": 3, "丷": 2,
    "口": 3, "囗": 3, "土": 3, "士": 3, "夂": 3, "夕": 3, "大": 3, "女": 3, "子": 3,
    "寸": 3, "小": 3, "尢": 3, "尸": 3, "屮": 3, "山": 3, "川": 3, "工": 3, "己": 3,
    "巾": 3, "干": 3, "幺": 3, "广": 3, "廴": 3, "弋": 3, "弓": 3, "ヨ": 3, "彐": 3,
    "彡": 3, "彳": 3, "亍": 3, "丁": 2, "氵": 3, "犭": 3, "艹": 3, "辶": 3, "門": 8, "日": 4, "木": 4,
    "王": 4, "玉": 4, "金": 8, "𰡮": 6, "&CDP-8DF2;": 6, "首": 9, "自": 6, "䒑": 3, "圭": 6,
    "禾": 4, "未": 4, "末": 4, "儿": 2,
}

_STROKE_COUNT_CACHE: dict[str, int] | None = None


def _get_stroke_count(char: str) -> int | None:
    """文字の標準画数を返します（キャッシュ・DB照合対応）。"""
    global _STROKE_COUNT_CACHE
    if not char:
        return None
    if char in PRIMITIVE_STROKES:
        return PRIMITIVE_STROKES[char]
    if _STROKE_COUNT_CACHE is None:
        _STROKE_COUNT_CACHE = {}
        db_path = DATA_DIR / "kanji_explorer.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                c = conn.cursor()
                c.execute("SELECT char, stroke_count FROM characters WHERE stroke_count IS NOT NULL")
                for ch, sc in c.fetchall():
                    if ch and sc:
                        _STROKE_COUNT_CACHE[ch] = int(sc)
                conn.close()
            except Exception:
                pass
    if char in _STROKE_COUNT_CACHE:
        return _STROKE_COUNT_CACHE[char]
    norm = ids_parser.normalize_component(char)
    if norm in _STROKE_COUNT_CACHE:
        return _STROKE_COUNT_CACHE[norm]
    norm_ent = ids_parser.normalize_entity(char)
    if norm_ent in _STROKE_COUNT_CACHE:
        return _STROKE_COUNT_CACHE[norm_ent]
    return None


def _estimate_node_strokes(node: dict[str, Any]) -> int:
    """構文木ノードの期待画数を再帰的に推定します。"""
    children = node.get("children", [])
    if children:
        c_strokes = [_estimate_node_strokes(c) for c in children]
        return sum(c_strokes)
    ch = node.get("char") or node.get("raw_char") or ""
    direct = _get_stroke_count(ch)
    if direct is not None:
        return direct
    return 1


def _allocate_strokes_recursive(
    lp: str,
    ast_node: dict[str, Any] | None,
    p_strokes: list[str],
    layer_strokes: dict[str, list[str]],
) -> None:
    """親レイヤー確定筆画を子ノードへ汎用再帰配分します（インターレース構造例外対応）。"""
    if not ast_node or not p_strokes:
        return
    ch_nodes = ast_node.get("children", [])
    if not ch_nodes:
        return

    lc = ast_node.get("char") or ast_node.get("raw_char") or ""

    # 特殊な交差・包含構造の筆順インターレース対応
    # 1. 日 (4画) -> 囗 (3画: s0, s1, s3) + 一 (1画: s2)
    if lc == "日" and len(p_strokes) == 4 and len(ch_nodes) == 2:
        p0 = f"{lp}.0" if lp != "0" else "0.0"
        p1 = f"{lp}.1" if lp != "0" else "0.1"
        if not layer_strokes.get(p0):
            layer_strokes[p0] = [p_strokes[0], p_strokes[1], p_strokes[3]]
        if not layer_strokes.get(p1):
            layer_strokes[p1] = [p_strokes[2]]
        _allocate_strokes_recursive(p0, ch_nodes[0], layer_strokes[p0], layer_strokes)
        _allocate_strokes_recursive(p1, ch_nodes[1], layer_strokes[p1], layer_strokes)
        return

    # 2. 𰡮 (6画) または ⿻王丷 (6画) -> 王 (4画: s0, s1, s2, s5) + 丷 (2画: s3, s4)
    if (
        (lc in ("𰡮", "&CDP-8DF2;", "⿻王丷") or (
            ast_node.get("op") == "⿻"
            and len(ch_nodes) == 2
            and ch_nodes[0].get("char") in ("王", "玉")
        ))
        and len(p_strokes) == 6
        and len(ch_nodes) == 2
    ):
        p0 = f"{lp}.0" if lp != "0" else "0.0"
        p1 = f"{lp}.1" if lp != "0" else "0.1"
        if not layer_strokes.get(p0):
            layer_strokes[p0] = [p_strokes[0], p_strokes[1], p_strokes[2], p_strokes[5]]
        if not layer_strokes.get(p1):
            layer_strokes[p1] = [p_strokes[3], p_strokes[4]]
        _allocate_strokes_recursive(p0, ch_nodes[0], layer_strokes[p0], layer_strokes)
        _allocate_strokes_recursive(p1, ch_nodes[1], layer_strokes[p1], layer_strokes)
        return

    expected_counts = [_estimate_node_strokes(c) for c in ch_nodes]
    total_expected = sum(expected_counts)

    node_op = ast_node.get("op")
    is_sequential = node_op in ("⿱", "⿰", "⿳", "⿲") or node_op is None or lc in PRIMITIVE_STROKES

    if is_sequential and total_expected == len(p_strokes):
        offset = 0
        for i, (c_node, count) in enumerate(zip(ch_nodes, expected_counts)):
            child_p = f"{lp}.{i}" if lp != "0" else f"0.{i}"
            c_slice = p_strokes[offset : offset + count]
            offset += count
            if not layer_strokes.get(child_p):
                layer_strokes[child_p] = c_slice
            _allocate_strokes_recursive(child_p, c_node, layer_strokes[child_p], layer_strokes)
    else:
        for i, c_node in enumerate(ch_nodes):
            child_p = f"{lp}.{i}" if lp != "0" else f"0.{i}"
            if layer_strokes.get(child_p):
                _allocate_strokes_recursive(child_p, c_node, layer_strokes[child_p], layer_strokes)


def extract_kanjivg_stroke_layers(char: str, tree: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    指定漢字のKanjiVG筆画データ（全ベクターストローク）を抽出し、
    IDS構文木の各ノード・階層（path）とスマート対応付けした情報を返します。
    """
    if tree is None:
        tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)

    svc = _get_default_kanjivg_service()
    if not svc:
        return {"has_kvg": False, "all_strokes": [], "layer_strokes": {}, "kvg_tree": None}
    xml_text = svc.get_kanji_xml(char)
    if not xml_text:
        return {"has_kvg": False, "all_strokes": [], "layer_strokes": {}, "kvg_tree": None}

    wrapped = f'<kanjivg xmlns:kvg="{KVG_NS}">{xml_text}</kanjivg>'
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        return {"has_kvg": False, "all_strokes": [], "layer_strokes": {}, "kvg_tree": None}

    strokes_map: dict[str, dict[str, Any]] = {}
    all_strokes: list[dict[str, Any]] = []
    for p in root.iter():
        if p.tag.endswith("path"):
            sid = p.attrib.get("id", "")
            sd = p.attrib.get("d", "")
            if sid and sd:
                pts = _parse_svg_path_points(sd)
                if pts:
                    xs = [pt[0] / 109.0 for pt in pts]
                    ys = [pt[1] / 109.0 for pt in pts]
                    bx, by, bw, bh = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
                    cx, cy = bx + bw / 2.0, by + bh / 2.0
                else:
                    bx, by, bw, bh, cx, cy = 0.0, 0.0, 0.0, 0.0, 0.5, 0.5
                s_obj = {
                    "id": sid,
                    "d": sd,
                    "bbox": [round(bx, 4), round(by, 4), round(bw, 4), round(bh, 4)],
                    "center": (round(cx, 4), round(cy, 4)),
                }
                strokes_map[sid] = s_obj
                all_strokes.append(s_obj)

    def parse_group(g: ET.Element, parent: dict[str, Any] | None = None) -> dict[str, Any]:
        elem = g.attrib.get(f"{{{KVG_NS}}}element") or g.attrib.get("kvg:element") or ""
        pos = g.attrib.get(f"{{{KVG_NS}}}position") or g.attrib.get("kvg:position") or ""
        part = g.attrib.get(f"{{{KVG_NS}}}part") or g.attrib.get("kvg:part") or ""
        gid = g.attrib.get("id", "")
        direct = [c.attrib.get("id", "") for c in g if c.tag.endswith("path") and c.attrib.get("id")]
        norm_elem, raw_elem = normalize_element_symbol(elem)
        node: dict[str, Any] = {
            "id": gid,
            "element": norm_elem or elem,
            "raw_element": raw_elem or elem,
            "position": POSITION_MAP.get(pos, pos),
            "part": part,
            "direct": direct,
            "children": [],
            "strokes": [
                {"id": sid, "d": strokes_map[sid]["d"]}
                for sid in direct
                if sid in strokes_map
            ],
            "parent": parent,
            "path": "",
        }
        children = [parse_group(c, parent=node) for c in g if c.tag.endswith("g")]
        node["children"] = children
        all_s = list(direct)
        for c in children:
            all_s.extend(c["all_s"])
        all_s.sort(key=lambda sid: int(re.search(r"-s(\d+)", sid).group(1)) if re.search(r"-s(\d+)", sid) else 0)
        node["all_s"] = all_s

        pts_all = []
        for sid in all_s:
            s_data = strokes_map.get(sid)
            if s_data:
                b = s_data["bbox"]
                pts_all.append((b[0], b[1]))
                pts_all.append((b[0] + b[2], b[1] + b[3]))
        if pts_all:
            xs = [p[0] for p in pts_all]
            ys = [p[1] for p in pts_all]
            gbx, gby, gbw, gbh = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        else:
            gbx, gby, gbw, gbh = 0.0, 0.0, 0.0, 0.0

        node["bbox"] = [round(gbx, 4), round(gby, 4), round(gbw, 4), round(gbh, 4)]
        node["center"] = (round(gbx + gbw / 2, 4), round(gby + gbh / 2, 4))
        return node

    top_g = None
    for c in root.iter():
        if c.tag.endswith("g") and c.attrib.get("id"):
            top_g = c
            break

    if top_g is None:
        return {"has_kvg": False, "all_strokes": [], "layer_strokes": {}, "kvg_tree": None}

    root_parsed = parse_group(top_g)
    root_parsed["path"] = "0"

    all_groups: list[dict[str, Any]] = []
    def flatten_g(g: dict[str, Any]) -> None:
        all_groups.append(g)
        for ch in g["children"]:
            flatten_g(ch)
    flatten_g(root_parsed)

    interactive_svg = build_interactive_ids_svg(tree)
    layers = [l for l in interactive_svg.get("component_layers", []) if l.get("path") and l.get("path") != "0"]

    def _find_ast_node_by_path(node: dict[str, Any] | None, target_path: str) -> dict[str, Any] | None:
        if not node:
            return None
        if node.get("path") == target_path:
            return node
        for ch in node.get("children", []):
            res = _find_ast_node_by_path(ch, target_path)
            if res:
                return res
        return None

    # レイヤー処理順序：浅い階層優先、同階層では複合ノード（子要素を持つもの）を優先、面積大優先
    def layer_sort_key(l: dict[str, Any]) -> tuple[int, int, float, str]:
        lp = l.get("path", "")
        depth = len(lp.split("."))
        ast_node = _find_ast_node_by_path(tree, lp)
        is_composite = 1 if (ast_node and ast_node.get("children")) else 2
        bbox = l.get("bbox", [0.0, 0.0, 0.0, 0.0])
        area = bbox[2] * bbox[3] if len(bbox) >= 4 else 0.0
        return (depth, is_composite, -area, lp)

    layers.sort(key=layer_sort_key)

    matched_group_ids: set[str] = set()
    layer_to_group: dict[str, dict[str, Any]] = {"0": root_parsed}
    layer_strokes: dict[str, list[str]] = {"0": [s["id"] for s in all_strokes]}

    def has_desc_violation(node: dict[str, Any], target_lp: str) -> bool:
        for ch in node.get("children", []):
            if ch.get("path") and ch["path"] != "0":
                if not (ch["path"].startswith(target_lp + ".") or ch["path"] == target_lp):
                    return True
            if has_desc_violation(ch, target_lp):
                return True
        return False

    def _is_descendant_of(node: dict[str, Any], ancestor_id: str) -> bool:
        curr = node
        while curr:
            if curr.get("id") == ancestor_id:
                return True
            curr = curr.get("parent")
        return False

    def _check_hierarchy_invariants(g: dict[str, Any], lp: str, matched_ancestor_g: dict[str, Any] | None) -> bool:
        # Invariant 1 (AST親グループ制約): AST上の既マッチ祖先ノードがある場合、gはそのKanjiVG子孫でなければならない
        if matched_ancestor_g is not None and not _is_descendant_of(g, matched_ancestor_g["id"]):
            return False

        # Invariant 2 (KanjiVG親グループ制約): gのKanjiVG祖先が既にパスを持つ場合、lpはそのパスの接頭辞でなければならない
        curr = g.get("parent")
        while curr:
            if curr.get("path") and curr["path"] != "0":
                if not (lp.startswith(curr["path"] + ".") or lp == curr["path"]):
                    return False
            curr = curr.get("parent")

        # Invariant 3 (KanjiVG子グループ制約): gのKanjiVG子孫が既にパスを持つ場合、そのパスはlpの配下でなければならない
        if has_desc_violation(g, lp):
            return False

        return True

    # 1. 記号等価性 + 階層無矛盾性 + 重心距離最小化による一意マッチング
    for l in layers:
        lp = l.get("path", "")
        lc = l.get("char") or l.get("raw_char") or ""
        if not lc:
            continue
        equivs = _get_equivalent_symbols(lc)
        if lc in ("大", "犬"): equivs.update(("大", "犬"))
        if lc in ("⺜", "日"): equivs.update(("⺜", "日"))
        if lc in ("⺫", "罒", "网"): equivs.update(("⺫", "罒", "网"))

        l_bbox = l.get("bbox", [0.0, 0.0, 1.0, 1.0])
        l_cx = l_bbox[0] + l_bbox[2] / 2
        l_cy = l_bbox[1] + l_bbox[3] / 2

        parts = lp.split(".")
        matched_ancestor_g = None
        for k in range(len(parts) - 1, 0, -1):
            ancestor_p = ".".join(parts[:k])
            if ancestor_p in layer_to_group:
                matched_ancestor_g = layer_to_group[ancestor_p]
                break

        candidates = []
        for g in all_groups:
            if g["id"] in matched_group_ids:
                continue
            if not g["element"]:
                continue
            if not (g["element"] in equivs or bool(_get_equivalent_symbols(g["element"]) & equivs)):
                continue

            if not _check_hierarchy_invariants(g, lp, matched_ancestor_g):
                continue

            candidates.append(g)

        if candidates:
            def dist_fn(g: dict[str, Any]) -> float:
                gcx, gcy = g["center"]
                return (gcx - l_cx) ** 2 + (gcy - l_cy) ** 2
            best_g = min(candidates, key=dist_fn)
            matched_group_ids.add(best_g["id"])
            best_g["path"] = lp
            layer_to_group[lp] = best_g
            matched_strokes = list(best_g["all_s"])

            # kvg:part (囗、門、行 等) の複数パーツ結合
            if best_g.get("part"):
                elem_val = best_g["element"]
                for other_g in all_groups:
                    if other_g["id"] not in matched_group_ids and other_g["element"] == elem_val and other_g.get("part"):
                        if matched_ancestor_g is not None and not _is_descendant_of(other_g, matched_ancestor_g["id"]):
                            continue
                        matched_group_ids.add(other_g["id"])
                        matched_strokes.extend(other_g["all_s"])

            layer_strokes[lp] = list(dict.fromkeys(matched_strokes))

    # 1.3 構成要素のストローク事前分解（親要素確定ストロークの汎用再帰配分）
    all_target_layers = [{"path": "0", "char": char, "raw_char": char, "bbox": [0.0, 0.0, 1.0, 1.0]}] + layers
    for l in all_target_layers:
        lp = l.get("path", "")
        p_strokes = layer_strokes.get(lp, [])
        if not p_strokes:
            continue
        ast_node = _find_ast_node_by_path(tree, lp)
        if not ast_node or not ast_node.get("children"):
            continue
        _allocate_strokes_recursive(lp, ast_node, p_strokes, layer_strokes)

    # 1.5 無名グループ（elem="" または None）の空間幾何マッチング
    for l in layers:
        lp = l.get("path", "")
        if layer_strokes.get(lp):
            continue
        l_bbox = l.get("bbox", [0.0, 0.0, 1.0, 1.0])
        l_cx = l_bbox[0] + l_bbox[2] / 2
        l_cy = l_bbox[1] + l_bbox[3] / 2
        parts = lp.split(".")
        matched_ancestor_g = None
        for k in range(len(parts) - 1, 0, -1):
            ancestor_p = ".".join(parts[:k])
            if ancestor_p in layer_to_group:
                matched_ancestor_g = layer_to_group[ancestor_p]
                break

        unnamed_candidates = []
        for g in all_groups:
            if g["id"] in matched_group_ids:
                continue
            if g["element"]:
                continue
            if not _check_hierarchy_invariants(g, lp, matched_ancestor_g):
                continue

            gcx, gcy = g["center"]
            bx, by, bw, bh = l_bbox
            if (bx - 0.08) <= gcx <= (bx + bw + 0.08) and (by - 0.08) <= gcy <= (by + bh + 0.08):
                unnamed_candidates.append(g)

        if unnamed_candidates:
            def dist_fn(g: dict[str, Any]) -> float:
                gcx, gcy = g["center"]
                return (gcx - l_cx) ** 2 + (gcy - l_cy) ** 2
            best_g = min(unnamed_candidates, key=dist_fn)
            matched_group_ids.add(best_g["id"])
            best_g["path"] = lp
            layer_to_group[lp] = best_g
            layer_strokes[lp] = list(best_g["all_s"])

    # 2. 複合親ノードへの子筆画ボトムアップ伝播
    for l in reversed(layers):
        lp = l.get("path", "")
        if not layer_strokes.get(lp):
            ch_s = []
            for cl in layers:
                cp = cl.get("path", "")
                if cp.startswith(lp + ".") and len(cp.split(".")) == len(lp.split(".")) + 1:
                    ch_s.extend(layer_strokes.get(cp, []))
            if ch_s:
                layer_strokes[lp] = list(dict.fromkeys(ch_s))

    # 3. 単筆画末端ノードの順序ベース配分（未割り当て筆画の重複排除）
    for l in layers:
        lp = l.get("path", "")
        if not layer_strokes.get(lp):
            parts = lp.split(".")
            parent_p = ".".join(parts[:-1])
            parent_s = layer_strokes.get(parent_p, [])
            siblings = [sib for sib in layers if sib.get("path", "").startswith(parent_p + ".") and len(sib.get("path", "").split(".")) == len(parts)]
            if siblings and parent_s:
                used_by_sibs = set()
                for sib in siblings:
                    used_by_sibs.update(layer_strokes.get(sib.get("path", ""), []))
                remaining = [sid for sid in parent_s if sid not in used_by_sibs]
                unassigned_sibs = [sib for sib in siblings if not layer_strokes.get(sib.get("path", ""))]
                if len(unassigned_sibs) == len(remaining) and len(remaining) <= 4:
                    idx = unassigned_sibs.index(l)
                    layer_strokes[lp] = [remaining[idx]]

    # 4. 包含矩形空間フォールバック（最も近い祖先スコープに限定し、兄弟間筆画重複を排除）
    for l in layers:
        lp = l.get("path", "")
        if not layer_strokes.get(lp):
            parts = lp.split(".")
            parent_s: list[str] = []
            parent_p = ""
            for k in range(len(parts) - 1, 0, -1):
                anc_p = ".".join(parts[:k])
                if anc_p in layer_strokes and layer_strokes[anc_p]:
                    parent_s = layer_strokes[anc_p]
                    parent_p = anc_p
                    break
            if not parent_s:
                parent_s = layer_strokes.get("0", [])
                parent_p = "0"

            bx, by, bw, bh = l.get("bbox", [0.0, 0.0, 1.0, 1.0])
            contained = []
            for sid in parent_s:
                s_obj = strokes_map.get(sid)
                if s_obj:
                    scx, scy = s_obj["center"]
                    if (bx - 0.06) <= scx <= (bx + bw + 0.06) and (by - 0.06) <= scy <= (by + bh + 0.06):
                        contained.append(sid)

            if contained:
                # 既に兄弟ノードに割り当て済みの筆画を除外
                sibling_assigned = set()
                for sib_p, sib_s in layer_strokes.items():
                    if sib_p != lp and sib_p.startswith(parent_p + "."):
                        sibling_assigned.update(sib_s)
                unassigned_contained = [sid for sid in contained if sid not in sibling_assigned]
                if unassigned_contained:
                    layer_strokes[lp] = unassigned_contained
                elif not sibling_assigned:
                    layer_strokes[lp] = contained

    # クリーンアップ: JSONシリアライズ不可な循環参照 'parent' を削除
    def remove_parent_refs(g: dict[str, Any]) -> None:
        g.pop("parent", None)
        for ch in g.get("children", []):
            remove_parent_refs(ch)
    remove_parent_refs(root_parsed)

    return {
        "has_kvg": True,
        "all_strokes": all_strokes,
        "layer_strokes": layer_strokes,
        "kvg_tree": root_parsed,
    }


def main() -> None:
    print("=" * 60)
    print("【自己診断テスト開始】glyph_service.py")
    print("=" * 60)

    # 1. Jigmoフォントからのベクターパス抽出テスト（蛍、𰃮、𭕄）
    test_chars = ["蛍", "𰃮", "𭕄"]
    for char in test_chars:
        codepoint = ord(char)
        path = get_jigmo_path(char)
        assert path is not None and len(path) > 0, f"エラー: '{char}' のJigmoパス取得に失敗しました。"
        print(f"✓ Jigmoパス取得成功: '{char}' (U+{codepoint:04X}) パス長={len(path)}")

    # 2. 完全なSVG生成テスト（get_glyph_svg）
    for char in test_chars:
        svg = get_glyph_svg(char)
        assert "<svg" in svg and "</svg>" in svg, f"エラー: '{char}' のSVG生成に失敗しました。"
        assert 'viewBox="0 0 1024 1024"' in svg, f"エラー: '{char}' のviewBoxが不正です。"
        print(f"✓ 完全SVG生成成功: '{char}' SVG長={len(svg)}")

    # 実体参照ベクターSVG生成およびフォールバックSVG生成テスト
    entity_token = "&CDP-8BD9;"
    entity_svg = get_glyph_svg(entity_token)
    assert "<svg" in entity_svg and "<path" in entity_svg, f"エラー: '{entity_token}' のベクターSVG生成に失敗しました。"
    print(f"✓ 実体参照ベクターSVG生成成功: '{entity_token}'")

    unresolved_token = "&UNKNOWN-TEST;"
    fallback_svg = get_glyph_svg(unresolved_token)
    assert "<svg" in fallback_svg and ("&amp;UNKNOWN-TEST;" in fallback_svg or unresolved_token in fallback_svg)
    print(f"✓ 未登録実体参照フォールバックSVG生成成功: '{unresolved_token}'")

    # 3. インタラクティブ複合SVG生成テスト（build_interactive_ids_svg）
    for test_c in test_chars:
        c_tree = ids_parser.decompose_character(test_c, max_depth=2, compute_bbox=True)
        c_interactive = build_interactive_ids_svg(c_tree)
        assert c_interactive.get("base_path") is not None, f"エラー: '{test_c}' の base_path が取得できません。"
        print(f"✓ インタラクティブ複合SVG生成成功: '{test_c}' レイヤー数={len(c_interactive['component_layers'])}")
        for layer in c_interactive["component_layers"]:
            print(f"   - 階層={layer['depth']} 役割={layer['role_label']} 文字='{layer['char']}' 変形={layer['svg_transform']}")

    # 4. KanjiVG解析 & CHISE木アライメント検証（蛍 U+86CD）
    service = KanjiVGService()
    hotaru_kvg = service.parse_kanji("蛍", align_chise=True)
    assert hotaru_kvg is not None, "エラー: '蛍' のKanjiVG解析に失敗しました。"

    expected_nodes: dict[str, tuple[str, str | None]] = {
        "kvg:086cd-g1": ("𰃮", None),
        "kvg:086cd-g2": ("𭕄", "⺍"),
        "kvg:086cd-g3": ("冖", None),
        "kvg:086cd-g4": ("虫", None),
        "kvg:086cd-g5": ("中", None),
        "kvg:086cd-g6": ("口", None),
        "kvg:086cd-g7": ("丨", None),
    }

    print("\n【KanjiVG & CHISE アライメント詳細検証】")
    for gid, (exp_element, exp_raw) in expected_nodes.items():
        node = KanjiVGService.get_group_by_id(hotaru_kvg, gid)
        assert node is not None, f"エラー: グループ '{gid}' が見つかりません。"
        actual_element = node.get("element")
        actual_raw = node.get("raw_element")
        assert (
            actual_element == exp_element
        ), f"エラー: '{gid}' の element は '{exp_element}' であるべきですが '{actual_element}' でした。"
        assert (
            actual_raw == exp_raw
        ), f"エラー: '{gid}' の raw_element は '{exp_raw}' であるべきですが '{actual_raw}' でした。"
        inferred = node.get("inferred_from_chise", False)
        print(
            f"✓ 検証合致: id={gid} element='{actual_element}' "
            f"raw_element={actual_raw} position='{node.get('position')}' (CHISE推論={inferred})"
        )

    print("\n" + "=" * 60)
    print("【全テスト完了】すべての要件検証に100%合格しました。")
    print("=" * 60)


if __name__ == "__main__":
    main()
