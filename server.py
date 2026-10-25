"""漢字構造エクスプローラー HTTPサーバーモジュール.

Python 3.12 標準ライブラリ（http.server.ThreadingHTTPServer, sqlite3, json, urllib.parse 等）
のみを用いて構築された、高速かつスレッドセーフな漢字探索・構造解析Webサーバーです。
ids_parser, glyph_service, jp_metadata と連携し、10万字以上の漢字に対する
詳細メタデータ、インタラクティブ複合SVG、KanjiVG筆順木、構成要素検索機能を提供します。
すべてのAPIラベル、メッセージ、メタデータは100%日本語で出力されます。
"""

from __future__ import annotations

import argparse
import functools
import json
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
from typing import Any
import urllib.parse
import html
import io
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 連携モジュールの読み込み
import glyph_service
import ids_parser
import jp_metadata
import view_renderer

# ディレクトリパス定数
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "kanji_explorer.db"

# スレッドローカルストレージ（SQLite接続キャッシュ用）
_thread_local = threading.local()


def get_db_connection() -> sqlite3.Connection | None:
    """
    スレッドセーフなSQLite読み込み専用接続を取得します。
    データベースファイルが存在しない場合は None を返します。
    kanji_explorer.db が未解凍で kanji_explorer.db.gz が存在する場合は自動解凍します。
    """
    if not DB_PATH.is_file():
        gz_path = DATA_DIR / "kanji_explorer.db.gz"
        if gz_path.is_file():
            try:
                import gzip
                import shutil
                temp_path = DATA_DIR / "kanji_explorer.db.tmp"
                with gzip.open(gz_path, "rb") as f_in, open(temp_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                temp_path.replace(DB_PATH)
            except Exception:
                if not DB_PATH.is_file():
                    return None
        else:
            return None

    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        try:
            # 読み込み専用URI接続でオープン（ロック競合を防止）
            conn = sqlite3.connect(f"file:{DB_PATH.resolve()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            _thread_local.conn = conn
        except sqlite3.Error:
            return None
    return conn


def close_db_connection() -> None:
    """現在のスレッドのSQLite接続を閉じます。"""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _thread_local.conn = None


def resolve_query(query: str) -> tuple[str, str]:
    """
    検索クエリ文字列から (canonical_char, requested_char) を解決します。

    対応クエリ形式:
    1. '⺍' (U+2E8D): canonical '𭕄' に正規化しつつ requested_char に '⺍' を記録
    2. コードポイント表記 ('U+86CD', 'U+2D544', 'u2d544', '0x86cd')
    3. CHISE実体参照 ('&CDP-8BD9;', 'CDP-8BD9')
    4. 単一漢字 ('蛍', '𰃮', '𭕄')
    """
    q = query.strip()
    if not q:
        return "", ""

    # 1. ⺍ (U+2E8D) の正規化
    if q == "⺍":
        return "𭕄", "⺍"

    # 2. コードポイント表記 (U+86CD, U 86CD, 0x86cd 等)
    m_cp = re.match(r"^(?:[Uu][\+\s]|0[xX])([0-9a-fA-F]+)$", q)
    if not m_cp and re.match(r"^[0-9a-fA-F]{4,6}$", q) and not q.startswith("&"):
        m_cp = re.match(r"^([0-9a-fA-F]+)$", q)

    if m_cp:
        try:
            val = int(m_cp.group(1), 16)
            char = chr(val)
            norm_char = "𭕄" if char == "⺍" else char
            return norm_char, char
        except (ValueError, OverflowError):
            pass

    # 3. CHISE実体参照
    if q.startswith("&") and q.endswith(";"):
        return q, q
    if re.match(r"^(?:CDP|GT|MJ|M|C[1-7]|J90|CB|HZK|SW-JIGUGE)-[0-9A-Za-z]+'?$", q):
        entity = f"&{q};"
        return entity, q

    # 4. 複数文字入力の処理（IDC演算子で始まらない通常の複数文字文字列の場合は先頭1文字を採用）
    idc_operators = set("⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻⿼⿽⿾⿿")
    if len(q) > 1 and q[0] not in idc_operators:
        chars = [c for c in q if not c.isspace()]
        if len(chars) > 1:
            first_char = chars[0]
            norm_char = "𭕄" if first_char == "⺍" else first_char
            return norm_char, first_char

    # 5. 通常文字
    norm_char = "𭕄" if q == "⺍" else q
    return norm_char, q


def to_katakana(text: str) -> str:
    """ひらがな文字列をカタカナに変換します。"""
    return "".join(
        chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in text
    )


def to_hiragana(text: str) -> str:
    """カタカナ文字列をひらがなに変換します。"""
    return "".join(
        chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in text
    )


def split_csv_field(val: Any) -> list[str]:
    """カンマ区切りの文字列をリストに分割します。"""
    if not val or not isinstance(val, str):
        return []
    return [s.strip() for s in val.split(",") if s.strip()]


@functools.lru_cache(maxsize=10000)
def get_meta_summary(char: str) -> dict[str, Any]:
    """
    指定された文字の簡易メタデータを返します（木構造ノードの meta_summary 用）。
    """
    conn = get_db_connection()
    if conn is not None:
        try:
            cur = conn.execute(
                "SELECT codepoint, tier, stroke_count, ja_on, ja_kun, chise_ids FROM characters WHERE char = ?",
                (char,),
            )
            row = cur.fetchone()
            if row is not None:
                return {
                    "codepoint": row["codepoint"],
                    "tier": row["tier"],
                    "stroke_count": row["stroke_count"],
                    "ja_on": split_csv_field(row["ja_on"]),
                    "ja_kun": split_csv_field(row["ja_kun"]),
                    "chise_ids": row["chise_ids"] or ids_parser.get_character_ids(char),
                }
        except sqlite3.Error:
            pass

    # フォールバック
    block_info = jp_metadata.get_unicode_block_jp(char)
    chise_ids = ids_parser.get_character_ids(char)
    return {
        "codepoint": block_info["codepoint"],
        "tier": block_info["tier"],
        "stroke_count": None,
        "ja_on": [],
        "ja_kun": [],
        "chise_ids": chise_ids,
    }


def _build_equivalents_list(char: str) -> list[dict[str, str]]:
    """指定文字の同等字・部首リストを構築します。"""
    equiv_list = []
    for eq_c in ids_parser.EQUIV_GROUPS.get(char, []):
        if eq_c != char:
            cp = f"U+{ord(eq_c):04X}" if len(eq_c) == 1 else eq_c
            equiv_list.append({
                "char": eq_c,
                "codepoint": cp,
                "label": "同等字/部首",
            })
    return equiv_list


def get_fallback_character_meta(
    char: str, requested_char: str | None = None
) -> dict[str, Any]:
    """DB未収録時またはDB非接続時に、ids_parserとjp_metadataから完全なメタデータを生成します。"""
    norm_char = ids_parser.normalize_component(char)
    req_char = requested_char or char
    block_info = jp_metadata.get_unicode_block_jp(norm_char)

    return {
        "char": norm_char,
        "literal": norm_char,
        "requested_char": req_char,
        "codepoint": block_info["codepoint"],
        "block_name": block_info["block_name"],
        "tier": block_info["tier"],
        "sort_priority": block_info["sort_priority"],
        "stroke_count": None,
        "radical": "-",
        "radical_dict": None,
        "badges": [],
        "ja_on": [],
        "ja_kun": [],
        "on_readings": [],
        "kun_readings": [],
        "nanori": [],
        "grade": None,
        "jlpt": None,
        "freq": None,
        "daikanwa": None,
        "four_corner": None,
        "skip": None,
        "skip_code": None,
        "cangjie": None,
        "mojijoho": None,
        "moji_joho": None,
        "equivalents": _build_equivalents_list(norm_char),
    }


def row_to_meta(row: sqlite3.Row, requested_char: str) -> dict[str, Any]:
    """SQLiteの characters レコードから 100% 日本語のメタデータ辞書を構築します。"""
    char = row["char"]
    keys = row.keys()

    meta = get_fallback_character_meta(char, requested_char)

    rad_num = row["radical_num"] if "radical_num" in keys else (row["radical"] if "radical" in keys else None)
    if rad_num and rad_num in jp_metadata.KANGXI_RADICALS:
        rad_info = jp_metadata.KANGXI_RADICALS[rad_num]
        meta["radical_dict"] = {
            "num": rad_num,
            "char": rad_info["char"],
            "variants": rad_info["variants"],
            "name": rad_info["name"],
        }
        meta["radical"] = f"{rad_info['name']} [{rad_num}]"
    elif rad_num:
        meta["radical"] = f"第{rad_num}部首"

    grade = row["grade"] if "grade" in keys else None
    jlpt = row["jlpt"] if "jlpt" in keys else None
    freq = row["freq"] if "freq" in keys else None
    meta["grade"] = grade
    meta["jlpt"] = jlpt
    meta["freq"] = freq
    meta["badges"] = jp_metadata.format_grade_jp(grade, jlpt, freq)

    if "codepoint" in keys and row["codepoint"]:
        meta["codepoint"] = row["codepoint"]
    if "block_name" in keys and row["block_name"]:
        meta["block_name"] = row["block_name"]
    if "tier" in keys and row["tier"]:
        meta["tier"] = row["tier"]
    if "sort_priority" in keys and row["sort_priority"] is not None:
        meta["sort_priority"] = row["sort_priority"]

    if "stroke_count" in keys:
        meta["stroke_count"] = row["stroke_count"]

    ja_on = split_csv_field(row["ja_on"]) if "ja_on" in keys else []
    ja_kun = split_csv_field(row["ja_kun"]) if "ja_kun" in keys else []
    nanori = split_csv_field(row["nanori"]) if "nanori" in keys else []
    meta["ja_on"] = ja_on
    meta["ja_kun"] = ja_kun
    meta["on_readings"] = ja_on
    meta["kun_readings"] = ja_kun
    meta["nanori"] = nanori

    skip_val = row["skip_code"] if "skip_code" in keys else None
    meta["skip"] = skip_val
    meta["skip_code"] = skip_val

    moji_val = row["moji_joho"] if "moji_joho" in keys else None
    meta["mojijoho"] = moji_val
    meta["moji_joho"] = moji_val

    meta["daikanwa"] = row["daikanwa"] if "daikanwa" in keys else None
    meta["four_corner"] = row["four_corner"] if "four_corner" in keys else None
    meta["cangjie"] = row["cangjie"] if "cangjie" in keys else None

    return meta


def enrich_tree_with_meta(node: dict[str, Any]) -> None:
    """再帰木の全ノードに対して meta_summary を付与します。"""
    char = node.get("char")
    if char:
        node["meta_summary"] = get_meta_summary(char)
    for child in node.get("children", []):
        enrich_tree_with_meta(child)


def format_result_item(
    char: str,
    codepoint: str,
    tier: str,
    stroke_count: int | None,
    chise_ids: str | None,
    ja_on_list: list[str],
    ja_kun_list: list[str],
    grade: int | None = None,
    freq: int | None = None,
    is_direct: int = 1,
    via_char: str = "",
    min_depth: int = 1,
) -> dict[str, Any]:
    """検索結果および構成要素閉包の各アイテムをフロントエンド仕様に合致する統一形式で構築します。"""
    ids_str = chise_ids or ""
    readings = " / ".join(["・".join(ja_on_list), "・".join(ja_kun_list)]).strip(" /")
    via_clean = via_char or ""

    return {
        "char": char,
        "literal": char,
        "codepoint": codepoint,
        "tier": tier,
        "stroke_count": stroke_count,
        "chise_ids": chise_ids,
        "ids": ids_str,
        "ja_on": ja_on_list,
        "ja_kun": ja_kun_list,
        "readings": readings,
        "grade": grade,
        "freq": freq,
        "is_direct": is_direct,
        "via_char": via_clean,
        "via": via_clean,
        "min_depth": min_depth,
    }


def row_to_result_item(
    r: sqlite3.Row,
    is_direct: int = 1,
    via_char: str = "",
    min_depth: int = 1,
) -> dict[str, Any]:
    """SQLiteの検索結果Rowから統一された結果アイテムを生成します。"""
    keys = r.keys()
    d_val = r["is_direct"] if "is_direct" in keys and r["is_direct"] is not None else is_direct
    v_val = (r["via_char"] or "") if "via_char" in keys and r["via_char"] is not None else via_char
    m_val = r["min_depth"] if "min_depth" in keys and r["min_depth"] is not None else min_depth
    return format_result_item(
        char=r["char"],
        codepoint=r["codepoint"],
        tier=r["tier"],
        stroke_count=r["stroke_count"],
        chise_ids=r["chise_ids"],
        ja_on_list=split_csv_field(r["ja_on"]),
        ja_kun_list=split_csv_field(r["ja_kun"]),
        grade=r["grade"],
        freq=r["freq"],
        is_direct=d_val,
        via_char=v_val,
        min_depth=m_val,
    )


def _build_tier_and_stroke_filters(
    tier: str, min_strokes: int | None, max_strokes: int | None
) -> tuple[list[str], list[Any]]:
    """区分（tier/category）および画数フィルターのSQL条件節とパラメータを構築します。"""
    where_clauses: list[str] = []
    sql_params: list[Any] = []
    if tier == "joyo":
        where_clauses.append("c.grade IN (1, 2, 3, 4, 5, 6, 8, 9, 10)")
    elif tier == "bmp":
        where_clauses.append("c.sort_priority = 1")
    elif tier == "ext":
        where_clauses.append("c.sort_priority IN (2, 4)")
    elif tier == "gaiji":
        where_clauses.append("c.sort_priority = 5")

    if min_strokes is not None:
        where_clauses.append("c.stroke_count >= ?")
        sql_params.append(min_strokes)
    if max_strokes is not None:
        where_clauses.append("c.stroke_count <= ?")
        sql_params.append(max_strokes)
    return where_clauses, sql_params


@functools.lru_cache(maxsize=1)
def get_joyo_characters() -> list[str]:
    """常用漢字（grade <= 8）の全ソート済みリストをキャッシュ取得します。"""
    conn = get_db_connection()
    if conn is None:
        return []
    try:
        cur_all = conn.execute("SELECT char FROM characters WHERE grade <= 8 ORDER BY grade, sort_priority, rowid")
        return [r[0] for r in cur_all.fetchall() if r[0]]
    except sqlite3.Error:
        return []


def query_component_closure_db(
    conn: sqlite3.Connection, char: str
) -> dict[str, Any]:
    """
    component_closure テーブルから指定文字（および同等部首・文字）を含む
    直接（direct）および間接（transitive/indirect）漢字群を取得します。
    """
    equivs = [char] + [
        eq for eq in ids_parser.EQUIV_GROUPS.get(char, []) if eq != char
    ]
    placeholders = ", ".join(["?"] * len(equivs))

    # 1. 直接構成要素（is_direct = 1）の総数と一覧
    cur = conn.execute(
        f"SELECT COUNT(DISTINCT target_char) FROM component_closure WHERE component IN ({placeholders}) AND is_direct = 1",
        equivs,
    )
    direct_total = cur.fetchone()[0]

    cur = conn.execute(
        f"""
        SELECT DISTINCT
            c.char, c.codepoint, c.tier, c.stroke_count, c.chise_ids,
            c.ja_on, c.ja_kun, c.grade, c.freq,
            cc.target_priority
        FROM component_closure cc
        JOIN characters c ON cc.target_char = c.char
        WHERE cc.component IN ({placeholders}) AND cc.is_direct = 1
        ORDER BY
            COALESCE(c.freq, 999999) ASC,
            CASE WHEN c.grade IS NOT NULL THEN c.grade ELSE 999 END ASC,
            c.sort_priority ASC,
            CASE WHEN (c.ja_on IS NOT NULL AND c.ja_on != '') OR (c.ja_kun IS NOT NULL AND c.ja_kun != '') THEN 0 ELSE 1 END ASC,
            COALESCE(c.stroke_count, 999) ASC
        LIMIT 150
        """,
        equivs,
    )
    direct_rows = cur.fetchall()
    direct_list = [row_to_result_item(r, is_direct=1) for r in direct_rows]

    # 2. 間接構成要素（is_direct = 0）の総数と一覧
    cur = conn.execute(
        f"SELECT COUNT(DISTINCT target_char) FROM component_closure WHERE component IN ({placeholders}) AND is_direct = 0",
        equivs,
    )
    transitive_total = cur.fetchone()[0]

    cur = conn.execute(
        f"""
        SELECT
            c.char, c.codepoint, c.tier, c.stroke_count, c.chise_ids,
            c.ja_on, c.ja_kun, c.grade, c.freq,
            cc.via_char, MIN(cc.min_depth) AS min_depth,
            cc.target_priority
        FROM component_closure cc
        JOIN characters c ON cc.target_char = c.char
        WHERE cc.component IN ({placeholders}) AND cc.is_direct = 0
        GROUP BY c.char
        ORDER BY
            COALESCE(c.freq, 999999) ASC,
            CASE WHEN c.grade IS NOT NULL THEN c.grade ELSE 999 END ASC,
            c.sort_priority ASC,
            CASE WHEN (c.ja_on IS NOT NULL AND c.ja_on != '') OR (c.ja_kun IS NOT NULL AND c.ja_kun != '') THEN 0 ELSE 1 END ASC,
            min_depth ASC,
            COALESCE(c.stroke_count, 999) ASC
        LIMIT 150
        """,
        equivs,
    )
    trans_rows = cur.fetchall()
    trans_list = [row_to_result_item(r, is_direct=0) for r in trans_rows]

    return {
        "direct": direct_list,
        "direct_total": direct_total,
        "transitive": trans_list,
        "transitive_total": transitive_total,
        "indirect": trans_list,
        "indirect_total": transitive_total,
        "total": direct_total + transitive_total,
    }


def query_component_closure_fallback(char: str) -> dict[str, Any]:
    """DB非接続時のインメモリ走査フォールバック処理。"""
    ids_dict = ids_parser.get_ids_dict()
    equivs = set([char] + ids_parser.EQUIV_GROUPS.get(char, []))

    matches: list[dict[str, Any]] = []
    for target_char, ids_str in ids_dict.items():
        if any(eq in ids_str for eq in equivs):
            block_info = jp_metadata.get_unicode_block_jp(target_char)
            matches.append(
                format_result_item(
                    char=target_char,
                    codepoint=block_info["codepoint"],
                    tier=block_info["tier"],
                    stroke_count=None,
                    chise_ids=ids_str,
                    ja_on_list=[],
                    ja_kun_list=[],
                    grade=None,
                    freq=None,
                    is_direct=1,
                    via_char="",
                    min_depth=1,
                )
            )
            if len(matches) >= 150:
                break

    return {
        "direct": matches,
        "direct_total": len(matches),
        "transitive": [],
        "transitive_total": 0,
        "indirect": [],
        "indirect_total": 0,
        "total": len(matches),
    }


def query_words_db(
    conn: sqlite3.Connection,
    canonical_char: str,
    position: str = "all",
    tier: str = "all",
    keyword: str = "",
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    """
    指定された漢字を含む熟語・単語をSQLiteデータベースから頻度順に取得します。
    すべての出力は100%日本語で返却されます。
    """
    equiv_symbols = glyph_service.get_equivalent_symbols(canonical_char)
    symbols = list({canonical_char} | set(equiv_symbols))

    placeholders = ", ".join(["?"] * len(symbols))
    base_params: list[Any] = list(symbols)

    where_clauses = [f"wk.kanji IN ({placeholders})"]

    # 1. 出現位置フィルタ (head / middle / tail / single)
    if position in ("head", "middle", "tail", "single"):
        where_clauses.append("wk.position_type = ?")
        base_params.append(position)

    # 2. 頻度区分フィルタ
    if tier == "top":
        where_clauses.append("w.frequency_tier = '最頻出'")
    elif tier == "high":
        where_clauses.append("w.frequency_tier IN ('最頻出', '頻出')")
    elif tier == "general":
        where_clauses.append("w.frequency_tier IN ('最頻出', '頻出', '一般')")
    elif tier in ("最頻出", "頻出", "一般", "発展", "専門・稀少"):
        where_clauses.append("w.frequency_tier = ?")
        base_params.append(tier)

    # 3. 語句・意味キーワード検索フィルタ
    if keyword:
        kw_like = f"%{keyword}%"
        where_clauses.append("(w.lemma LIKE ? OR w.reading LIKE ? OR w.definition LIKE ?)")
        base_params.extend([kw_like, kw_like, kw_like])

    where_sql = " AND ".join(where_clauses)

    count_sql = f"""
    SELECT
        COUNT(DISTINCT w.word_id) AS total_count,
        COUNT(DISTINCT CASE WHEN w.frequency_tier = '最頻出' THEN w.word_id END) AS count_top,
        COUNT(DISTINCT CASE WHEN w.frequency_tier = '頻出' THEN w.word_id END) AS count_high,
        COUNT(DISTINCT CASE WHEN w.frequency_tier = '一般' THEN w.word_id END) AS count_mid,
        COUNT(DISTINCT CASE WHEN w.frequency_tier = '発展' THEN w.word_id END) AS count_adv,
        COUNT(DISTINCT CASE WHEN w.frequency_tier = '専門・稀少' THEN w.word_id END) AS count_rare,
        COUNT(DISTINCT CASE WHEN wk.position_type = 'head' THEN w.word_id END) AS count_head,
        COUNT(DISTINCT CASE WHEN wk.position_type = 'middle' THEN w.word_id END) AS count_middle,
        COUNT(DISTINCT CASE WHEN wk.position_type = 'tail' THEN w.word_id END) AS count_tail,
        COUNT(DISTINCT CASE WHEN wk.position_type = 'single' THEN w.word_id END) AS count_single
    FROM word_kanji wk
    JOIN words w ON wk.word_id = w.word_id
    WHERE {where_sql}
    """
    cur = conn.cursor()
    count_row = cur.execute(count_sql, base_params).fetchone()

    total_count = count_row["total_count"] if count_row else 0
    counts_summary = {
        "total": total_count,
        "top": count_row["count_top"] if count_row else 0,
        "high": count_row["count_high"] if count_row else 0,
        "mid": count_row["count_mid"] if count_row else 0,
        "adv": count_row["count_adv"] if count_row else 0,
        "rare": count_row["count_rare"] if count_row else 0,
        "head": count_row["count_head"] if count_row else 0,
        "middle": count_row["count_middle"] if count_row else 0,
        "tail": count_row["count_tail"] if count_row else 0,
        "single": count_row["count_single"] if count_row else 0,
    }

    query_sql = f"""
    SELECT
        w.word_id,
        w.lemma,
        w.reading,
        w.pos,
        w.definition,
        w.frequency_rank,
        w.frequency_tier,
        w.source,
        CASE MIN(CASE wk.position_type
            WHEN 'single' THEN 1
            WHEN 'head' THEN 2
            WHEN 'middle' THEN 3
            WHEN 'tail' THEN 4
            ELSE 5 END)
            WHEN 1 THEN 'single'
            WHEN 2 THEN 'head'
            WHEN 3 THEN 'middle'
            WHEN 4 THEN 'tail'
            ELSE 'middle' END AS position_type
    FROM word_kanji wk
    JOIN words w ON wk.word_id = w.word_id
    WHERE {where_sql}
    GROUP BY w.word_id
    ORDER BY
        (CASE WHEN w.frequency_rank IS NULL OR w.frequency_rank <= 0 THEN 99999999 ELSE w.frequency_rank END) ASC,
        length(w.lemma) ASC,
        w.word_id ASC
    LIMIT ? OFFSET ?
    """
    exec_params = list(base_params) + [limit, offset]
    rows = cur.execute(query_sql, exec_params).fetchall()

    results: list[dict[str, Any]] = []
    for r in rows:
        def_raw = r["definition"] or "[]"
        try:
            defs_list = json.loads(def_raw) if def_raw.startswith("[") else [def_raw]
        except (json.JSONDecodeError, ValueError):
            defs_list = [def_raw]

        formatted_def = " / ".join(defs_list[:3]) if defs_list else ""
        f_rank = r["frequency_rank"]
        display_rank = f"#{f_rank}" if f_rank and f_rank < 9999990 else "未詳"

        results.append({
            "word_id": r["word_id"],
            "lemma": r["lemma"],
            "reading": r["reading"] or "",
            "pos": r["pos"] or "名詞",
            "definitions": defs_list,
            "definition": formatted_def,
            "frequency_rank": f_rank if f_rank and f_rank < 9999990 else None,
            "frequency_display": display_rank,
            "frequency_tier": r["frequency_tier"] or "専門・稀少",
            "position_type": r["position_type"],
            "source": r["source"] or "辞書",
        })

    return {
        "kanji": canonical_char,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "summary": counts_summary,
        "results": results,
    }


def query_words_fallback(canonical_char: str) -> dict[str, Any]:
    """DB非接続時のインメモリ語彙検索フォールバック処理。"""
    return {
        "kanji": canonical_char,
        "total": 0,
        "limit": 60,
        "offset": 0,
        "summary": {
            "total": 0,
            "top": 0,
            "high": 0,
            "mid": 0,
            "adv": 0,
            "rare": 0,
            "head": 0,
            "middle": 0,
            "tail": 0,
            "single": 0,
        },
        "results": [],
    }


class KanjiExplorerHandler(BaseHTTPRequestHandler):
    """HTTPリクエストハンドラクラス。"""

    server_version = "KanjiExplorerServer/1.0"

    def _send_json_response(
        self, data: Any, status: int = 200, cache_age: int = 0
    ) -> None:
        """JSON形式のレスポンスを日本語エンコーディングで返却します。"""
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if cache_age > 0:
            self.send_header("Cache-Control", f"public, max-age={cache_age}")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        """エラーメッセージをJSON形式で返却します。"""
        self._send_json_response({"error": message}, status=status)

    def do_OPTIONS(self) -> None:
        """CORSプリフライトリクエストに対応します。"""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_HEAD(self) -> None:
        """HEADリクエストに対応します。"""
        self.do_GET()

    def do_GET(self) -> None:
        """GETリクエストのルーティングとハンドリング。"""
        raw_path = self.path
        try:
            raw_path = raw_path.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        parsed_url = urllib.parse.urlparse(raw_path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # 1. ルートエンドポイント GET /
        if path == "/":
            self.handle_root()
            return

        # 2. 静的ファイル GET /static/<path> または直下の静的アセット
        if path.startswith("/static/"):
            subpath = path[len("/static/") :]
            self.handle_static(subpath)
            return
        if path in ("/styles.css", "/app.js", "/index.html") or path.startswith("/fonts/"):
            self.handle_static(path.lstrip("/"))
            return

        # 3. 漢字詳細API GET /api/char または GET /api/character
        if path in ("/api/char", "/api/character"):
            self.handle_api_char(query_params)
            return

        # 4. 構成要素検索API GET /api/ids-find
        if path == "/api/ids-find":
            self.handle_api_ids_find(query_params)
            return

        # 5. グリフSVG取得API GET /api/glyph
        if path == "/api/glyph":
            self.handle_api_glyph(query_params)
            return

        # 6. 収録熟語・語彙検索API GET /api/words
        if path == "/api/words":
            self.handle_api_words(query_params)
            return

        # 7. コンポーネント並置プレビュー GET /view または GET /audit/view または GET /view/<char>
        if path in ("/view", "/audit/view", "/audit") or path.startswith("/view/") or path.startswith("/audit/"):
            char_arg = ""
            if path.startswith("/view/"):
                char_arg = urllib.parse.unquote(path[len("/view/") :])
            elif path.startswith("/audit/") and not path.startswith("/audit/view"):
                char_arg = urllib.parse.unquote(path[len("/audit/") :])
            self.handle_side_by_side_view(query_params, char_arg)
            return

        # 該当しないパス
        self._send_error_json("指定されたエンドポイントは存在しません。", status=404)

    def handle_root(self) -> None:
        """GET / -> static/index.html を配信（不在時は日本語案内HTML）。"""
        index_file = STATIC_DIR / "index.html"
        if index_file.is_file():
            try:
                content = index_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except OSError:
                pass

        # フォールバックHTML
        fallback_html = (
            "<!DOCTYPE html>\n"
            '<html lang="ja">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            "  <title>漢字構造エクスプローラー</title>\n"
            "</head>\n"
            "<body>\n"
            "  <h1>漢字構造エクスプローラー API サーバー</h1>\n"
            "  <p>サーバーは正常に稼働しています。以下のAPIエンドポイントをご利用いただけます:</p>\n"
            "  <ul>\n"
            '    <li><code>/api/character?c=蛍</code>: 漢字詳細および構成木・メタデータ取得</li>\n'
            '    <li><code>/api/ids-find?components=𭕄&amp;components=虫</code>: 構成要素による漢字検索</li>\n'
            '    <li><code>/api/glyph?c=蛍</code>: ベクターSVGグリフ配信</li>\n'
            "  </ul>\n"
            "</body>\n"
            "</html>"
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(fallback_html)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(fallback_html)

    def handle_static(self, subpath: str) -> None:
        """GET /static/<path> -> 静的ファイルを配信。"""
        unquoted = urllib.parse.unquote(subpath)
        file_path = (STATIC_DIR / unquoted).resolve()

        # パストラバーサル防止
        if not file_path.is_relative_to(STATIC_DIR.resolve()):
            self._send_error_json("不正なパスです。", status=403)
            return

        if not file_path.is_file():
            self._send_error_json("指定された静的ファイルが存在しません。", status=404)
            return

        # 拡張子ごとの正確なMIMEタイプ判別
        ext = file_path.suffix.lower()
        mime_map = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".ttf": "font/ttf",
            ".svg": "image/svg+xml",
            ".html": "text/html; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
        }
        content_type = mime_map.get(ext) or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

        try:
            file_size = file_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return
        except OSError:
            try:
                self._send_error_json("ファイルの読み込み中にエラーが発生しました。", status=500)
            except Exception:
                pass

    def handle_api_char(self, params: dict[str, list[str]]) -> None:
        """GET /api/char または /api/character を処理。q=<query> または c=<query> を受容。"""
        q = (params.get("q", [""])[0] or params.get("c", [""])[0]).strip()
        alt_ids = params.get("alt_ids", [""])[0].strip()

        if not q:
            self._send_error_json("検索対象の文字クエリ 'q' または 'c' を指定してください。", status=400)
            return

        canonical_char, requested_char = resolve_query(q)
        if not canonical_char:
            self._send_error_json(f"クエリ '{q}' を解決できませんでした。", status=400)
            return

        # 1. データベース検索
        conn = get_db_connection()
        db_row: sqlite3.Row | None = None
        if conn is not None:
            try:
                cur = conn.execute(
                    "SELECT * FROM characters WHERE char = ?", (canonical_char,)
                )
                db_row = cur.fetchone()
            except sqlite3.Error:
                db_row = None

        if db_row is not None:
            meta = row_to_meta(db_row, requested_char)
            db_chise_ids = db_row["chise_ids"] if "chise_ids" in db_row.keys() else None
            apparent_ids = db_row["apparent_ids"] if "apparent_ids" in db_row.keys() else None
            cjkvi_ids = db_row["cjkvi_ids"] if "cjkvi_ids" in db_row.keys() else None
        else:
            meta = get_fallback_character_meta(canonical_char, requested_char)
            db_chise_ids = ids_parser.get_character_ids(canonical_char)
            apparent_ids = None
            cjkvi_ids = None

        # 2. 構文木の構築 (primary_ids)
        if alt_ids:
            primary_ids = alt_ids
        else:
            if not db_chise_ids or db_chise_ids == canonical_char or re.search(r"[\u2460-\u2473]", db_chise_ids):
                primary_ids = ids_parser.get_character_ids(canonical_char) or ids_parser.COMPONENT_SUBDECOMPOSITIONS.get(canonical_char) or canonical_char
            else:
                primary_ids = db_chise_ids

        tree = ids_parser.decompose_character(
            primary_ids, max_depth=8, use_atomic=True, compute_bbox=True
        )
        tree["char"] = canonical_char

        # 全ノードへのメタデータ再帰付与
        enrich_tree_with_meta(tree)

        # 3. 構造バリエーション（alternatives）
        alternatives: list[dict[str, str]] = []
        chise_display_ids = db_chise_ids
        if (not chise_display_ids or chise_display_ids == canonical_char) and canonical_char in ids_parser.COMPONENT_SUBDECOMPOSITIONS:
            chise_display_ids = ids_parser.COMPONENT_SUBDECOMPOSITIONS[canonical_char]

        if chise_display_ids and not re.search(r"[\u2460-\u2473]", chise_display_ids):
            alternatives.append({
                "id": "chise",
                "label": "CHISE標準構造",
                "source": "CHISE標準構造",
                "ids": chise_display_ids,
            })
        if apparent_ids and apparent_ids != chise_display_ids and not re.search(r"[\u2460-\u2473]", apparent_ids):
            alternatives.append({
                "id": "apparent",
                "label": "視覚的構造 (@apparent)",
                "source": "視覚的構造 (@apparent)",
                "ids": apparent_ids,
            })
        if cjkvi_ids:
            for c_ids in cjkvi_ids.split(" | "):
                c_ids_clean = c_ids.strip()
                if (
                    c_ids_clean
                    and c_ids_clean != chise_display_ids
                    and not re.search(r"[\u2460-\u2473]", c_ids_clean)
                    and not any(a["ids"] == c_ids_clean for a in alternatives)
                ):
                    alternatives.append({
                        "id": "cjkvi",
                        "label": "CJKVI構造",
                        "source": "CJKVI構造",
                        "ids": c_ids_clean,
                    })
        if canonical_char in ids_parser.ATOMIC_SUBDECOMPOSITIONS and canonical_char not in ids_parser.COMPONENT_SUBDECOMPOSITIONS:
            alternatives.append({
                "id": "atomic",
                "label": "筆画・基礎要素分解",
                "source": "筆画・基礎要素分解",
                "ids": ids_parser.ATOMIC_SUBDECOMPOSITIONS[canonical_char],
            })

        # 4. 視覚情報（visual）
        kvg_res = glyph_service.extract_kanjivg_stroke_layers(canonical_char, tree)
        if kvg_res.get("has_kvg"):
            has_kanjivg = True
            kvg_data = kvg_res["kvg_tree"]
        else:
            kvg_service = glyph_service._get_default_kanjivg_service()
            kvg_data = kvg_service.parse_kanji(canonical_char, align_chise=True)
            has_kanjivg = kvg_data is not None

        interactive_svg = glyph_service.build_interactive_ids_svg(tree)
        visual = {
            "has_kanjivg": has_kanjivg,
            "kanjivg": kvg_data,
            "interactive_svg": interactive_svg,
            "all_strokes": kvg_res.get("all_strokes", []),
            "layer_strokes": kvg_res.get("layer_strokes", {}),
            "default_mode": "kvg" if has_kanjivg else "mincho",
        }

        # 5. 構成要素推移閉包（component_closure）
        closure_data: dict[str, Any]
        if conn is not None:
            try:
                # component_closure テーブルの存在確認
                tbl_check = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='component_closure'"
                ).fetchone()
                if tbl_check:
                    closure_data = query_component_closure_db(conn, canonical_char)
                else:
                    closure_data = query_component_closure_fallback(canonical_char)
            except sqlite3.Error:
                closure_data = query_component_closure_fallback(canonical_char)
        else:
            closure_data = query_component_closure_fallback(canonical_char)

        response_data = {
            "meta": meta,
            "tree": tree,
            "alternatives": alternatives,
            "visual": visual,
            "components_usage": closure_data,
        }

        self._send_json_response(response_data)

    def handle_api_ids_find(self, params: dict[str, list[str]]) -> None:
        """GET /api/ids-find を処理。構成要素や読みによる漢字検索。"""
        raw_list = params.get("components", []) + params.get("q", [])
        raw_query = " ".join(raw_list).strip()
        mode = (params.get("mode", [""])[0] or params.get("hierarchy", ["all"])[0]).lower()
        tier = (params.get("tier", [""])[0] or params.get("category", ["all"])[0]).lower()
        limit_str = params.get("limit", ["120"])[0]
        min_strokes_str = params.get("min_strokes", [""])[0]
        max_strokes_str = params.get("max_strokes", [""])[0]

        try:
            limit = min(max(int(limit_str), 1), 500)
        except ValueError:
            limit = 120

        min_strokes = int(min_strokes_str) if min_strokes_str.isdigit() else None
        max_strokes = int(max_strokes_str) if max_strokes_str.isdigit() else None

        # トークン分割（空白・カンマ区切り）
        raw_tokens: list[str] = []
        for item in raw_list:
            for t in re.split(r"[\s,]+", item):
                if t.strip():
                    raw_tokens.append(t.strip())

        # トークンの正規化と解決
        norm_components: list[str] = []
        is_all_kana = True
        for t in raw_tokens:
            norm_c, _ = resolve_query(t)
            norm_c = ids_parser.normalize_component(ids_parser.normalize_entity(norm_c))
            norm_components.append(norm_c)
            if not re.match(r"^[\u3040-\u309F\u30A0-\u30FF\u30FC]+$", t):
                is_all_kana = False

        conn = get_db_connection()

        # 読み検索（全トークンがひらがな・カタカナの場合）
        if raw_tokens and is_all_kana:
            reading_term = raw_tokens[0]
            term_hira = to_hiragana(reading_term)
            term_kata = to_katakana(reading_term)

            if conn is not None:
                where_clauses = [
                    "(c.ja_kun LIKE ? OR c.ja_kun LIKE ? OR c.ja_on LIKE ? OR c.ja_on LIKE ?)"
                ]
                sql_params: list[Any] = [
                    f"%{term_hira}%",
                    f"%{term_kata}%",
                    f"%{term_hira}%",
                    f"%{term_kata}%",
                ]

                # 区分（tier/category）及び画数フィルター
                f_clauses, f_params = _build_tier_and_stroke_filters(tier, min_strokes, max_strokes)
                where_clauses.extend(f_clauses)
                sql_params.extend(f_params)

                where_sql = " AND ".join(where_clauses)
                count_query = f"SELECT COUNT(*) FROM characters c WHERE {where_sql}"
                total = conn.execute(count_query, sql_params).fetchone()[0]

                query_sql = f"""
                    SELECT c.char, c.codepoint, c.tier, c.stroke_count, c.chise_ids,
                           c.ja_on, c.ja_kun, c.grade, c.freq
                    FROM characters c
                    WHERE {where_sql}
                    ORDER BY
                        COALESCE(c.freq, 999999) ASC,
                        CASE WHEN c.grade IS NOT NULL THEN c.grade ELSE 999 END ASC,
                        c.sort_priority ASC,
                        CASE WHEN (c.ja_on IS NOT NULL AND c.ja_on != '') OR (c.ja_kun IS NOT NULL AND c.ja_kun != '') THEN 0 ELSE 1 END ASC,
                        COALESCE(c.stroke_count, 999) ASC
                    LIMIT ?
                """
                sql_params.append(limit)
                rows = conn.execute(query_sql, sql_params).fetchall()
                results = [row_to_result_item(r, is_direct=1) for r in rows]

                self._send_json_response({
                    "query": raw_query,
                    "components": norm_components,
                    "search_type": "読み検索",
                    "total": total,
                    "direct_total": total,
                    "indirect_total": 0,
                    "results": results,
                })
                return

        # 構成要素検索
        if not norm_components:
            self._send_json_response({
                "query": raw_query,
                "components": [],
                "search_type": "構成要素検索",
                "total": 0,
                "direct_total": 0,
                "indirect_total": 0,
                "results": [],
            })
            return

        if conn is not None:
            try:
                tbl_check = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='component_closure'"
                ).fetchone()
                if tbl_check:
                    primary_comp = norm_components[0]
                    primary_equivs = [primary_comp] + [
                        eq
                        for eq in ids_parser.EQUIV_GROUPS.get(primary_comp, [])
                        if eq != primary_comp
                    ]
                    primary_ph = ", ".join(["?"] * len(primary_equivs))

                    base_where_clauses: list[str] = ["1=1"]
                    base_where_params: list[Any] = []

                    # 追加構成要素 (norm_components[1:])
                    for comp in norm_components[1:]:
                        equivs = [comp] + [
                            eq
                            for eq in ids_parser.EQUIV_GROUPS.get(comp, [])
                            if eq != comp
                        ]
                        ph = ", ".join(["?"] * len(equivs))
                        base_where_clauses.append(
                            f"c.char IN (SELECT target_char FROM component_closure WHERE component IN ({ph}))"
                        )
                        base_where_params.extend(equivs)

                    # 区分（tier/category）及び画数フィルター
                    f_clauses, f_params = _build_tier_and_stroke_filters(tier, min_strokes, max_strokes)
                    base_where_clauses.extend(f_clauses)
                    base_where_params.extend(f_params)

                    base_where_sql = " AND ".join(base_where_clauses)

                    # 直接・間接および基底総数の集計
                    count_sql = f"""
                    SELECT
                        COUNT(*) AS base_total,
                        COALESCE(SUM(CASE WHEN is_direct = 1 THEN 1 ELSE 0 END), 0) AS direct_total,
                        COALESCE(SUM(CASE WHEN is_direct = 0 THEN 1 ELSE 0 END), 0) AS indirect_total
                    FROM (
                        SELECT c.char, MAX(cc_main.is_direct) AS is_direct
                        FROM characters c
                        JOIN component_closure cc_main ON cc_main.target_char = c.char AND cc_main.component IN ({primary_ph})
                        WHERE {base_where_sql}
                        GROUP BY c.char
                    )
                    """
                    count_params = list(primary_equivs) + base_where_params
                    count_row = conn.execute(count_sql, count_params).fetchone()
                    base_total = count_row[0] if count_row else 0
                    direct_total = count_row[1] if count_row else 0
                    indirect_total = count_row[2] if count_row else 0

                    # 階層（mode/hierarchy）フィルターの適用
                    query_where_clauses = list(base_where_clauses)
                    query_where_params = list(base_where_params)

                    if mode == "direct":
                        query_where_clauses.append("cc_main.is_direct = 1")
                        total = direct_total
                    elif mode in ("indirect", "transitive"):
                        query_where_clauses.append("cc_main.is_direct = 0")
                        total = indirect_total
                    else:
                        total = base_total

                    query_where_sql = " AND ".join(query_where_clauses)

                    query_sql = f"""
                        SELECT
                            c.char, c.codepoint, c.tier, c.stroke_count, c.chise_ids,
                            c.ja_on, c.ja_kun, c.grade, c.freq,
                            MAX(cc_main.is_direct) AS is_direct,
                            cc_main.via_char,
                            MIN(cc_main.min_depth) AS min_depth,
                            MIN(cc_main.target_priority) AS target_priority
                        FROM characters c
                        JOIN component_closure cc_main ON cc_main.target_char = c.char AND cc_main.component IN ({primary_ph})
                        WHERE {query_where_sql}
                        GROUP BY c.char
                        ORDER BY
                            COALESCE(c.freq, 999999) ASC,
                            CASE WHEN c.grade IS NOT NULL THEN c.grade ELSE 999 END ASC,
                            c.sort_priority ASC,
                            CASE WHEN (c.ja_on IS NOT NULL AND c.ja_on != '') OR (c.ja_kun IS NOT NULL AND c.ja_kun != '') THEN 0 ELSE 1 END ASC,
                            min_depth ASC,
                            COALESCE(c.stroke_count, 999) ASC
                        LIMIT ?
                    """
                    exec_params = list(primary_equivs) + query_where_params + [limit]
                    rows = conn.execute(query_sql, exec_params).fetchall()
                    results = [row_to_result_item(r) for r in rows]

                    self._send_json_response({
                        "query": raw_query,
                        "components": norm_components,
                        "search_type": "構成要素検索",
                        "total": total,
                        "direct_total": direct_total,
                        "indirect_total": indirect_total,
                        "results": results,
                    })
                    return
            except sqlite3.Error:
                pass

        # DB非接続時のインメモリフォールバック構成要素検索
        ids_dict = ids_parser.get_ids_dict()
        comp_equiv_sets = [
            set([c] + ids_parser.EQUIV_GROUPS.get(c, [])) for c in norm_components
        ]

        matched_chars: list[dict[str, Any]] = []
        for target_char, ids_str in ids_dict.items():
            if all(any(eq in ids_str for eq in s) for s in comp_equiv_sets):
                block_info = jp_metadata.get_unicode_block_jp(target_char)
                matched_chars.append(
                    format_result_item(
                        char=target_char,
                        codepoint=block_info["codepoint"],
                        tier=block_info["tier"],
                        stroke_count=None,
                        chise_ids=ids_str,
                        ja_on_list=[],
                        ja_kun_list=[],
                        grade=None,
                        freq=None,
                        is_direct=1,
                        via_char="",
                        min_depth=1,
                    )
                )
                if len(matched_chars) >= limit:
                    break

        self._send_json_response({
            "query": raw_query,
            "components": norm_components,
            "search_type": "構成要素検索（インメモリ）",
            "total": len(matched_chars),
            "direct_total": len(matched_chars),
            "indirect_total": 0,
            "results": matched_chars,
        })

    def handle_api_glyph(self, params: dict[str, list[str]]) -> None:
        """GET /api/glyph?c=<token> -> 完全なSVGベクター画像を配信。"""
        token = (params.get("c", [""])[0] or params.get("q", [""])[0]).strip()
        if not token:
            self._send_error_json("文字パラメータ 'c' を指定してください。", status=400)
            return

        canonical_token, _ = resolve_query(token)
        target_token = canonical_token if canonical_token else token
        svg_content = glyph_service.get_glyph_svg(target_token)
        svg_bytes = svg_content.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(svg_bytes)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(svg_bytes)

    def handle_api_words(self, params: dict[str, list[str]]) -> None:
        """GET /api/words を処理。提示漢字を含む熟語・語彙の頻度順検索。"""
        raw_kanji = (
            params.get("kanji", [""])[0]
            or params.get("char", [""])[0]
            or params.get("c", [""])[0]
            or params.get("q", [""])[0]
        )
        raw_kanji = raw_kanji.strip()
        if not raw_kanji:
            self._send_error_json("kanji パラメータは必須です。", status=400)
            return

        canonical_char, _ = resolve_query(raw_kanji)
        if not canonical_char:
            self._send_error_json("指定された文字を解決できませんでした。", status=400)
            return

        position = params.get("position", ["all"])[0].lower()
        tier = params.get("tier", ["all"])[0].lower()
        keyword = (
            params.get("keyword", [""])[0]
            or params.get("query", [""])[0]
            or params.get("word", [""])[0]
        ).strip()
        limit_str = params.get("limit", ["60"])[0]
        offset_str = params.get("offset", ["0"])[0]

        try:
            limit = min(max(int(limit_str), 1), 200)
        except ValueError:
            limit = 60

        try:
            offset = max(int(offset_str), 0)
        except ValueError:
            offset = 0

        conn = get_db_connection()
        if conn is not None:
            try:
                tbl_check = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='words'"
                ).fetchone()
                if tbl_check:
                    words_data = query_words_db(
                        conn=conn,
                        canonical_char=canonical_char,
                        position=position,
                        tier=tier,
                        keyword=keyword,
                        limit=limit,
                        offset=offset,
                    )
                else:
                    words_data = query_words_fallback(canonical_char)
            except sqlite3.Error:
                words_data = query_words_fallback(canonical_char)
        else:
            words_data = query_words_fallback(canonical_char)

        self._send_json_response(words_data)

    def handle_side_by_side_view(self, params: dict[str, list[str]], char_arg: str = "") -> None:
        """GET /view?char=<kanji> -> 全構成要素の並置プレビューHTMLを配信。"""
        raw_char = char_arg or params.get("char", [""])[0] or params.get("c", [""])[0] or params.get("q", [""])[0] or "名"
        raw_char = raw_char.strip()
        canonical_char, requested_char = resolve_query(raw_char)
        if not canonical_char:
            canonical_char = "名"

        # 1. データベース検索 & 前後の常用漢字取得
        conn = get_db_connection()
        meta = None
        prev_char = ""
        next_char = ""
        joyo_index = None
        joyo_total = 0
        if conn is not None:
            try:
                cur = conn.execute("SELECT * FROM characters WHERE char = ?", (canonical_char,))
                row = cur.fetchone()
                if row is not None:
                    meta = row_to_meta(row, requested_char)

                joyo_list = get_joyo_characters()
                joyo_total = len(joyo_list)
                if canonical_char in joyo_list:
                    idx = joyo_list.index(canonical_char)
                    joyo_index = idx + 1
                    if idx > 0:
                        prev_char = joyo_list[idx - 1]
                    if idx + 1 < len(joyo_list):
                        next_char = joyo_list[idx + 1]
            except sqlite3.Error:
                pass

        if meta is None:
            meta = get_fallback_character_meta(canonical_char, requested_char)

        # 2. 外部レンダラーモジュールによるHTML合成
        full_html = view_renderer.render_side_by_side_html(
            canonical_char=canonical_char,
            meta=meta,
            params=params,
            prev_char=prev_char,
            next_char=next_char,
            joyo_index=joyo_index,
            joyo_total=joyo_total,
        )

        content_bytes = full_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content_bytes)


class WSGIHandlerAdapter(KanjiExplorerHandler):
    """WSGI環境（PythonAnywhere, Gunicorn, uWSGI等）でKanjiExplorerHandlerを動作させるアダプター."""

    def __init__(self, environ: dict[str, Any]) -> None:
        self.environ = environ
        raw_path = environ.get("PATH_INFO", "")
        query = environ.get("QUERY_STRING", "")
        self.path = f"{raw_path}?{query}" if query else raw_path
        self.command = environ.get("REQUEST_METHOD", "GET")
        self.status_code = 200
        self.status_phrase = "OK"
        self.headers_out: list[tuple[str, str]] = []
        self.wfile = io.BytesIO()

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status_code = code
        try:
            self.status_phrase = message or HTTPStatus(code).phrase
        except ValueError:
            self.status_phrase = message or "OK"

    def send_header(self, keyword: str, value: Any) -> None:
        self.headers_out.append((str(keyword), str(value)))

    def end_headers(self) -> None:
        pass


def application(environ: dict[str, Any], start_response: Any) -> list[bytes]:
    """標準WSGIアプリケーションエントリーポイント（PythonAnywhere / WSGIサーバー互換）."""
    handler = WSGIHandlerAdapter(environ)
    if handler.command == "GET":
        handler.do_GET()
    elif handler.command == "HEAD":
        handler.do_HEAD()
    elif handler.command == "OPTIONS":
        handler.do_OPTIONS()
    else:
        handler._send_error_json("指定されたHTTPメソッドには対応していません。", status=405)

    status_str = f"{handler.status_code} {handler.status_phrase}"
    start_response(status_str, handler.headers_out)
    return [handler.wfile.getvalue()]


def run_internal_self_tests() -> bool:
    """
    サーバーの自己診断テストを実行します（--test フラグ用）。
    エフェメラルポートにThreadingHTTPServerを一時起動し、標準urllibで検証します。
    """
    import urllib.request

    print("=" * 60)
    print("【サーバー自己診断テスト開始】server.py")
    print("=" * 60)

    test_server = ThreadingHTTPServer(("127.0.0.1", 0), KanjiExplorerHandler)
    test_port = test_server.server_port
    server_thread = threading.Thread(target=test_server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{test_port}"
    all_passed = True

    try:
        # 1. GET /
        with urllib.request.urlopen(f"{base_url}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            print("✓ GET /: 正常（HTML配信成功）")

        # 2. GET /static/styles.css 及び /static/fonts/Jigmo.ttf
        with urllib.request.urlopen(f"{base_url}/static/styles.css") as resp:
            assert resp.status == 200
            assert "text/css" in resp.headers.get("Content-Type", "")
            assert "max-age=3600" in resp.headers.get("Cache-Control", "")
            css_data = resp.read()
            assert len(css_data) > 0
            print("✓ GET /static/styles.css: 正常（MIMEタイプ・キャッシュヘッダー合致）")

        with urllib.request.urlopen(f"{base_url}/static/fonts/Jigmo.ttf") as resp:
            assert resp.status == 200
            assert "font/ttf" in resp.headers.get("Content-Type", "")
            assert "max-age=3600" in resp.headers.get("Cache-Control", "")
            font_chunk = resp.read(8192)
            assert len(font_chunk) > 0
            print("✓ GET /static/fonts/Jigmo.ttf: 正常（MIMEタイプ・キャッシュヘッダー合致）")

        # 3. GET /api/glyph
        for glyph_c in ["蛍", "𰃮", "𭕄", "&CDP-8BD9;"]:
            url_enc = urllib.parse.quote(glyph_c)
            with urllib.request.urlopen(f"{base_url}/api/glyph?c={url_enc}") as resp:
                assert resp.status == 200
                assert "image/svg+xml" in resp.headers.get("Content-Type", "")
                data = resp.read().decode("utf-8")
                assert "<svg" in data and "</svg>" in data
                print(f"✓ GET /api/glyph?c={glyph_c}: 正常（SVG長={len(data)}）")

        # 4. GET /api/char?q=蛍
        with urllib.request.urlopen(f"{base_url}/api/char?q={urllib.parse.quote('蛍')}") as resp:
            assert resp.status == 200
            char_data = json.loads(resp.read().decode("utf-8"))
            meta = char_data.get("meta", {})
            tree = char_data.get("tree", {})
            visual = char_data.get("visual", {})

            assert meta.get("char") == "蛍"
            assert meta.get("literal") == "蛍"
            assert meta.get("codepoint") == "U+86CD"
            assert meta.get("on_readings") == ["ケイ"]
            assert meta.get("kun_readings") == ["ほたる"]
            assert "虫" in meta.get("radical", "")
            assert tree.get("char") == "蛍"
            assert "meta_summary" in tree
            assert visual.get("has_kanjivg") is True
            assert visual.get("interactive_svg", {}).get("base_path") is not None
            assert len(visual.get("interactive_svg", {}).get("component_layers", [])) >= 3
            print("✓ GET /api/char?q=蛍: 正常（メタデータ・木構造・KanjiVG・インタラクティブSVG合致）")

        # 5. GET /api/character?c=蛍 (新ルート /api/character & c= パラメータ検証)
        with urllib.request.urlopen(f"{base_url}/api/character?c={urllib.parse.quote('蛍')}") as resp:
            assert resp.status == 200
            char_data = json.loads(resp.read().decode("utf-8"))
            meta = char_data.get("meta", {})
            alts = char_data.get("alternatives", [])
            usage = char_data.get("components_usage", {})

            assert meta.get("literal") == "蛍"
            assert len(alts) >= 1
            assert "source" in alts[0] and "ids" in alts[0]
            assert "direct_total" in usage and "indirect_total" in usage and "total" in usage
            if usage.get("direct"):
                d0 = usage["direct"][0]
                assert "literal" in d0 and "ids" in d0 and "readings" in d0 and "via" in d0
            print("✓ GET /api/character?c=蛍: 正常（/api/character ルーティング・c=受容・拡張スキーマ合致）")

        # 6. GET /api/character?c=⺍ (U+2E8D 正規化 & c= パラメータ検証)
        with urllib.request.urlopen(f"{base_url}/api/character?c={urllib.parse.quote('⺍')}") as resp:
            assert resp.status == 200
            c_data = json.loads(resp.read().decode("utf-8"))
            meta = c_data.get("meta", {})
            assert meta.get("char") == "𭕄" and meta.get("literal") == "𭕄", f"期待値 '𭕄' ですが '{meta.get('char')}' でした。"
            assert meta.get("requested_char") == "⺍"
            print("✓ GET /api/character?c=⺍: 正常（'⺍' -> '𭕄' 正規化合致）")

        # 7. GET /api/char?q=U+300EE (コードポイント表記解決 & 拡張領域文字)
        with urllib.request.urlopen(f"{base_url}/api/char?q=U+300EE") as resp:
            assert resp.status == 200
            c_data = json.loads(resp.read().decode("utf-8"))
            meta = c_data.get("meta", {})
            assert meta.get("char") == "𰃮"
            assert c_data.get("visual", {}).get("interactive_svg", {}).get("base_path") is not None
            print("✓ GET /api/char?q=U+300EE: 正常（'𰃮' 拡張G文字解決＆インタラクティブSVG生成合致）")

        # 8. GET /api/ids-find?components=𭕄&components=虫&hierarchy=indirect&category=all (複数 components, hierarchy=indirect, category 検証)
        with urllib.request.urlopen(
            f"{base_url}/api/ids-find?components={urllib.parse.quote('𭕄')}&components={urllib.parse.quote('虫')}&hierarchy=indirect&category=all"
        ) as resp:
            assert resp.status == 200
            find_data = json.loads(resp.read().decode("utf-8"))
            assert "results" in find_data
            assert find_data.get("total") == 8
            assert find_data.get("direct_total") == 0
            assert find_data.get("indirect_total") == 8
            results = find_data["results"]
            assert len(results) == 8

            hotaru = next((r for r in results if r.get("literal") == "蛍"), None)
            assert hotaru is not None, "結果に '蛍' が含まれていません。"
            assert hotaru.get("is_direct") == 0
            assert hotaru.get("via") == "𰃮"
            assert hotaru.get("via_char") == "𰃮"
            assert hotaru.get("min_depth") == 2
            assert hotaru.get("readings") == "ケイ / ほたる"
            assert hotaru.get("ids") == "⿱𰃮虫"
            assert hotaru.get("codepoint") == "U+86CD"
            print("✓ GET /api/ids-find?components=𭕄&components=虫&hierarchy=indirect&category=all: 正常（複数components・indirect階層・蛍抽出・スキーマ合致）")

        # 9. GET /api/ids-find?components=𭕄&hierarchy=direct (直接構成要素フィルター検証)
        with urllib.request.urlopen(
            f"{base_url}/api/ids-find?components={urllib.parse.quote('𭕄')}&hierarchy=direct"
        ) as resp:
            assert resp.status == 200
            find_direct = json.loads(resp.read().decode("utf-8"))
            assert find_direct.get("direct_total") == 45
            assert find_direct.get("indirect_total") == 225
            assert find_direct.get("total") == 45
            assert len(find_direct.get("results", [])) > 0
            assert all(r.get("is_direct") == 1 for r in find_direct["results"])
            print("✓ GET /api/ids-find?components=𭕄&hierarchy=direct: 正常（direct_total=45, indirect_total=225, 全件is_direct=1）")

        # 10. GET /api/ids-find?q=ほたる (読み検索検証)
        with urllib.request.urlopen(
            f"{base_url}/api/ids-find?q={urllib.parse.quote('ほたる')}"
        ) as resp:
            assert resp.status == 200
            read_data = json.loads(resp.read().decode("utf-8"))
            assert "results" in read_data
            assert read_data.get("total") > 0
            assert read_data.get("direct_total") == read_data.get("total")
            r0 = read_data["results"][0]
            assert "literal" in r0 and "readings" in r0 and "ids" in r0 and "is_direct" in r0
            print(f"✓ GET /api/ids-find?q=ほたる: 正常（読み検索総数={read_data.get('total')}、スキーマ合致）")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"✗ テスト失敗: {e}")
        all_passed = False
    finally:
        test_server.shutdown()
        close_db_connection()

    print("=" * 60)
    if all_passed:
        print("【全テスト完了】すべてのHTTPハンドラー自己診断テストに100%合格しました。")
    else:
        print("【テスト失敗】一部のテストに不合格がありました。")
    print("=" * 60)
    return all_passed


def main() -> None:
    """メイン実行関数。"""
    parser = argparse.ArgumentParser(description="漢字構造エクスプローラー Webサーバー")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8888")),
        help="待受ポート番号（デフォルト: 8888 または 環境変数 PORT）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="バインドアドレス（デフォルト: 0.0.0.0）",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="内部自己診断テストを実行して終了します。",
    )

    args = parser.parse_args()

    if args.test:
        success = run_internal_self_tests()
        sys.exit(0 if success else 1)

    server = ThreadingHTTPServer((args.host, args.port), KanjiExplorerHandler)
    print("=" * 60)
    print(f"【サーバー起動】漢字構造エクスプローラーサーバーが起動しました。")
    print(f" - URL: http://{args.host}:{args.port}/")
    print(f" - データベース: {DB_PATH} ({'接続可能' if DB_PATH.is_file() else '未配備（インメモリフォールバックモード）'})")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n【サーバー停止】シャットダウンしています...")
    finally:
        server.server_close()
        close_db_connection()


if __name__ == "__main__":
    main()
