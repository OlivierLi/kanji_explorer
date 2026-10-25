"""漢字探索データベース構築スクリプト (build_db.py).

CHISE IDS、CJKVI-IDS、KANJIDIC2、およびUnihanデータソースを統合し、
SQLiteデータベース (data/kanji_explorer.db) を構築します。
100%日本語のメタデータおよび構造辞書を提供し、英語の意味・定義（meaning, kDefinition）は一切保存しません。
"""

from __future__ import annotations

import glob
import gzip
import os
import re
import sqlite3
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from typing import Any

import ids_parser
import jp_metadata

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "kanji_explorer.db"
CHISE_DIR = DATA_DIR / "chise-ids"
CJKVI_PATH = DATA_DIR / "cjkvi-ids.txt"
KANJIDIC2_PATH = DATA_DIR / "kanjidic2.xml.gz"
UNIHAN_ZIP_PATH = DATA_DIR / "Unihan.zip"


# ==============================================================================
# 1. CHISE IDS 解析
# ==============================================================================

def parse_chise_ids() -> dict[str, dict[str, str]]:
    """CHISE IDS ファイル群（IDS-*.txt）を読み込み、文字ごとのIDSおよび外観IDSを抽出する.

    IDS-UCS-*.txt を最優先で読み込み、標準的なUnicode文字の分解表現を優先適用します。
    """
    print("【処理 1/6】CHISE IDS ファイル群の解析開始...")
    t0 = time.time()

    ucs_files = sorted(glob.glob(str(CHISE_DIR / "IDS-UCS-*.txt")))
    jis_files = sorted(glob.glob(str(CHISE_DIR / "IDS-JIS-*.txt")))
    other_files = [
        p for p in glob.glob(str(CHISE_DIR / "IDS-*.txt"))
        if p not in ucs_files and p not in jis_files
    ]
    file_order = ucs_files + jis_files + other_files

    chise_data: dict[str, dict[str, str]] = {}

    for path in file_order:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(";;") or not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue

                code_col = parts[0].strip()
                char_raw = parts[1].strip()
                char_token = ids_parser.normalize_entity(char_raw)
                if not char_token:
                    continue

                chise_ids = ""
                apparent_ids = ""

                for p in parts[2:]:
                    p = p.strip()
                    if p.startswith("@apparent="):
                        apparent_ids = p[len("@apparent="):].strip()
                    elif not chise_ids and p and p != "?":
                        chise_ids = p

                if char_token not in chise_data:
                    chise_data[char_token] = {
                        "code_col": code_col,
                        "chise_ids": chise_ids,
                        "apparent_ids": apparent_ids,
                    }
                else:
                    entry = chise_data[char_token]
                    if not entry["chise_ids"] and chise_ids:
                        entry["chise_ids"] = chise_ids
                    if not entry["apparent_ids"] and apparent_ids:
                        entry["apparent_ids"] = apparent_ids

    print(f"  -> CHISE IDS 読込完了: {len(chise_data):,} 件 ({time.time() - t0:.2f} 秒)")
    return chise_data


# ==============================================================================
# 2. CJKVI-IDS 解析
# ==============================================================================

def parse_cjkvi_ids() -> dict[str, str]:
    """cjkvi-ids.txt を解析し、文字ごとの代替IDS文字列（' | ' 結合）を抽出する."""
    print("【処理 2/6】CJKVI-IDS ファイルの解析開始...")
    t0 = time.time()

    cjkvi_data: dict[str, str] = {}
    if not CJKVI_PATH.exists():
        print("  ※ cjkvi-ids.txt が見つかりません。スキップします。")
        return cjkvi_data

    with open(CJKVI_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue

            char_raw = parts[1].strip()
            char_token = ids_parser.normalize_entity(char_raw)
            if not char_token:
                continue

            cjkvi_cols = [p.strip() for p in parts[2:] if p.strip()]
            if cjkvi_cols:
                cjkvi_str = " | ".join(cjkvi_cols)
                cjkvi_data[char_token] = cjkvi_str

    print(f"  -> CJKVI-IDS 読込完了: {len(cjkvi_data):,} 件 ({time.time() - t0:.2f} 秒)")
    return cjkvi_data


# ==============================================================================
# 3. KANJIDIC2 解析 (日本語メタデータのみ抽出、英語 meaning は完全除外)
# ==============================================================================

def parse_kanjidic2() -> dict[str, dict[str, Any]]:
    """kanjidic2.xml.gz をストリーミング解析し、日本語漢字メタデータを抽出する."""
    print("【処理 3/6】KANJIDIC2 (XML) の解析開始...")
    t0 = time.time()

    kanjidic_data: dict[str, dict[str, Any]] = {}
    if not KANJIDIC2_PATH.exists():
        print("  ※ kanjidic2.xml.gz が見つかりません。スキップします。")
        return kanjidic_data

    with gzip.open(KANJIDIC2_PATH, "rb") as f:
        context = ET.iterparse(f, events=("end",))
        for _, elem in context:
            if elem.tag == "character":
                ch = elem.findtext("literal")
                if ch:
                    # 画数 (最初の stroke_count)
                    sc_elem = elem.find(".//misc/stroke_count")
                    stroke_count = int(sc_elem.text) if sc_elem is not None and sc_elem.text else None

                    # 康熙部首番号 (rad_type="classical")
                    rad_elem = elem.find('.//radical/rad_value[@rad_type="classical"]')
                    radical_num = int(rad_elem.text) if rad_elem is not None and rad_elem.text else None

                    # 学年・頻度・JLPT
                    gr_elem = elem.find(".//misc/grade")
                    grade = int(gr_elem.text) if gr_elem is not None and gr_elem.text else None

                    fq_elem = elem.find(".//misc/freq")
                    freq = int(fq_elem.text) if fq_elem is not None and fq_elem.text else None

                    jl_elem = elem.find(".//misc/jlpt")
                    jlpt = int(jl_elem.text) if jl_elem is not None and jl_elem.text else None

                    # 音読み・訓読み・名乗り
                    ja_on = [r.text.strip() for r in elem.findall('.//reading[@r_type="ja_on"]') if r.text]
                    ja_kun = [r.text.strip() for r in elem.findall('.//reading[@r_type="ja_kun"]') if r.text]
                    nanori = [n.text.strip() for n in elem.findall(".//nanori") if n.text]

                    # 大漢和番号 (dr_type="moro")
                    moro = elem.find('.//dic_ref[@dr_type="moro"]')
                    daikanwa = moro.text.strip() if moro is not None and moro.text else None

                    # 四角号碼 (qc_type="four_corner")
                    fc_list = [q.text.strip() for q in elem.findall('.//q_code[@qc_type="four_corner"]') if q.text]
                    four_corner = ", ".join(fc_list) if fc_list else None

                    # SKIPコード (qc_type="skip")
                    sk = elem.find('.//q_code[@qc_type="skip"]')
                    skip_code = sk.text.strip() if sk is not None and sk.text else None

                    kanjidic_data[ch] = {
                        "stroke_count": stroke_count,
                        "radical_num": radical_num,
                        "grade": grade,
                        "freq": freq,
                        "jlpt": jlpt,
                        "ja_on": ", ".join(ja_on) if ja_on else None,
                        "ja_kun": ", ".join(ja_kun) if ja_kun else None,
                        "nanori": ", ".join(nanori) if nanori else None,
                        "daikanwa": daikanwa,
                        "four_corner": four_corner,
                        "skip_code": skip_code,
                    }
                elem.clear()

    print(f"  -> KANJIDIC2 読込完了: {len(kanjidic_data):,} 件 ({time.time() - t0:.2f} 秒)")
    return kanjidic_data


# ==============================================================================
# 4. Unihan 解析 (ZIPストリーミング、日本語読み・画数・部首・コード類のフォールバック)
# ==============================================================================

def parse_unihan() -> dict[str, dict[str, Any]]:
    """Unihan.zip を解析し、Unicode漢字の補助メタデータを抽出する."""
    print("【処理 4/6】Unihan (ZIP) の解析開始...")
    t0 = time.time()

    unihan_data: dict[str, dict[str, Any]] = {}
    if not UNIHAN_ZIP_PATH.exists():
        print("  ※ Unihan.zip が見つかりません。スキップします。")
        return unihan_data

    def get_char_dict(cp_str: str) -> dict[str, Any] | None:
        try:
            cp = int(cp_str.replace("U+", ""), 16)
            ch = chr(cp)
        except (ValueError, OverflowError):
            return None
        if ch not in unihan_data:
            unihan_data[ch] = {}
        return unihan_data[ch]

    with zipfile.ZipFile(UNIHAN_ZIP_PATH) as z:
        # 1. 読み仮名 (Unihan_Readings.txt)
        if "Unihan_Readings.txt" in z.namelist():
            with z.open("Unihan_Readings.txt") as f:
                for line in f:
                    line_str = line.decode("utf-8").strip()
                    if not line_str or line_str.startswith("#"):
                        continue
                    parts = line_str.split("\t")
                    if len(parts) >= 3:
                        cp_str, prop, val = parts[0], parts[1], parts[2]
                        entry = get_char_dict(cp_str)
                        if entry is None:
                            continue
                        if prop in ("kJapaneseOn", "kJapaneseKun", "kJapanese"):
                            entry[prop] = val

        # 2. 画数・部首 (Unihan_IRGSources.txt / Unihan_RadicalStrokeCounts.txt)
        for rs_file in ("Unihan_IRGSources.txt", "Unihan_RadicalStrokeCounts.txt"):
            if rs_file in z.namelist():
                with z.open(rs_file) as f:
                    for line in f:
                        line_str = line.decode("utf-8").strip()
                        if not line_str or line_str.startswith("#"):
                            continue
                        parts = line_str.split("\t")
                        if len(parts) >= 3:
                            cp_str, prop, val = parts[0], parts[1], parts[2]
                            entry = get_char_dict(cp_str)
                            if entry is None:
                                continue
                            if prop == "kTotalStrokes" and "stroke_count" not in entry:
                                m = re.search(r"\d+", val)
                                if m:
                                    entry["stroke_count"] = int(m.group(0))
                            elif prop == "kRSUnicode" and "radical_num" not in entry:
                                m = re.match(r"(\d+)", val)
                                if m:
                                    entry["radical_num"] = int(m.group(1))

        # 3. 倉頡・四角号碼・文字情報基盤 (Unihan_DictionaryLikeData.txt)
        if "Unihan_DictionaryLikeData.txt" in z.namelist():
            with z.open("Unihan_DictionaryLikeData.txt") as f:
                for line in f:
                    line_str = line.decode("utf-8").strip()
                    if not line_str or line_str.startswith("#"):
                        continue
                    parts = line_str.split("\t")
                    if len(parts) >= 3:
                        cp_str, prop, val = parts[0], parts[1], parts[2]
                        entry = get_char_dict(cp_str)
                        if entry is None:
                            continue
                        if prop == "kCangjie":
                            entry["cangjie"] = val
                        elif prop == "kFourCornerCode":
                            entry["four_corner"] = val
                        elif prop == "kMojiJoho":
                            entry["moji_joho"] = val

    print(f"  -> Unihan 読込完了: {len(unihan_data):,} 件 ({time.time() - t0:.2f} 秒)")
    return unihan_data


# ==============================================================================
# 5. データベーステーブル構築およびインデックス生成
# ==============================================================================

def build_database() -> None:
    """全データソースをマージして SQLite データベース kanji_explorer.db を構築する."""
    start_time = time.time()
    print("=" * 70)
    print("漢字探索データベース (kanji_explorer.db) の構築開始")
    print("=" * 70)

    # 1. 各ソースの解析
    chise_data = parse_chise_ids()
    cjkvi_data = parse_cjkvi_ids()
    kanjidic_data = parse_kanjidic2()
    unihan_data = parse_unihan()

    print("\n【処理 5/6】文字マスター辞書の統合と空間要素グラフの解析...")
    t0 = time.time()

    # 全ユニーク文字の収集
    all_chars: set[str] = set()
    all_chars.update(chise_data.keys())
    all_chars.update(cjkvi_data.keys())
    all_chars.update(kanjidic_data.keys())
    all_chars.update(unihan_data.keys())

    # 必須文字および基本構成文字の確実な登録
    required_special_chars = [
        "𭕄", "⺍", "𰃮", "蛍", "学", "栄", "覚", "労", "営", "単", "巣", "脳", "獣"
    ]
    all_chars.update(required_special_chars)
    all_chars.update(ids_parser.ATOMIC_SUBDECOMPOSITIONS.keys())

    # 筆画文字の収集
    for v in ids_parser.ATOMIC_SUBDECOMPOSITIONS.values():
        toks = ids_parser.tokenize_ids(v, normalize=False)
        for t in toks:
            norm_t = ids_parser.normalize_component(ids_parser.normalize_entity(t))
            if norm_t and norm_t not in ids_parser.IDC_INFO:
                all_chars.add(norm_t)

    print(f"  統合対象文字数: {len(all_chars):,} 字")

    # 文字レコードの作成
    characters_rows: list[tuple] = []
    parent_to_primary_children: dict[str, list[str]] = {}
    parent_to_alt_children: dict[str, list[str]] = {}
    component_edges_set: set[tuple[str, str, str]] = set()
    edge_pairs_seen: set[tuple[str, str]] = set()

    for ch in all_chars:
        # Unicode ブロック情報の取得
        meta = jp_metadata.get_unicode_block_jp(ch)
        codepoint = meta["codepoint"]
        block_name = meta["block_name"]
        tier = meta["tier"]
        sort_priority = meta["sort_priority"]

        # IDS 情報
        chise_entry = chise_data.get(ch, {})
        chise_ids = chise_entry.get("chise_ids")
        apparent_ids = chise_entry.get("apparent_ids")
        cjkvi_ids = cjkvi_data.get(ch)

        # KANJIDIC2 メタデータ
        k_entry = kanjidic_data.get(ch, {})
        stroke_count = k_entry.get("stroke_count")
        radical_num = k_entry.get("radical_num")
        grade = k_entry.get("grade")
        freq = k_entry.get("freq")
        jlpt = k_entry.get("jlpt")
        ja_on = k_entry.get("ja_on")
        ja_kun = k_entry.get("ja_kun")
        nanori = k_entry.get("nanori")
        daikanwa = k_entry.get("daikanwa")
        four_corner = k_entry.get("four_corner")
        skip_code = k_entry.get("skip_code")

        # Unihan によるフォールバック
        u_entry = unihan_data.get(ch, {})
        if stroke_count is None and "stroke_count" in u_entry:
            stroke_count = u_entry["stroke_count"]
        if radical_num is None and "radical_num" in u_entry:
            radical_num = u_entry["radical_num"]
        if four_corner is None and "four_corner" in u_entry:
            four_corner = u_entry["four_corner"]

        # 読み仮名のフォールバック (KANJIDIC2 にない場合)
        if not ja_on and not ja_kun:
            on_list: list[str] = []
            kun_list: list[str] = []
            if "kJapaneseOn" in u_entry:
                on_list.extend(u_entry["kJapaneseOn"].split())
            if "kJapaneseKun" in u_entry:
                kun_list.extend(u_entry["kJapaneseKun"].split())
            if not on_list and not kun_list and "kJapanese" in u_entry:
                for token in u_entry["kJapanese"].split():
                    # カタカナを含む場合は音読み、ひらがなを含む場合は訓読み
                    if re.search(r"[\u30A0-\u30FF]", token):
                        on_list.append(token)
                    elif re.search(r"[\u3040-\u309F]", token):
                        kun_list.append(token)
            if on_list:
                ja_on = ", ".join(on_list)
            if kun_list:
                ja_kun = ", ".join(kun_list)

        cangjie = u_entry.get("cangjie")
        moji_joho = u_entry.get("moji_joho")

        characters_rows.append((
            ch,
            codepoint,
            block_name,
            tier,
            sort_priority,
            chise_ids,
            apparent_ids,
            cjkvi_ids,
            stroke_count,
            radical_num,
            grade,
            freq,
            jlpt,
            ja_on,
            ja_kun,
            nanori,
            daikanwa,
            four_corner,
            skip_code,
            cangjie,
            moji_joho,
        ))

        # 構成要素エッジの抽出
        # 1. CHISE IDS 由来
        primary_ch_list: list[str] = []
        if chise_ids and chise_ids != ch:
            toks = ids_parser.tokenize_ids(chise_ids, normalize=False)
            for t in toks:
                norm_c = ids_parser.normalize_component(ids_parser.normalize_entity(t))
                if norm_c and norm_c not in ids_parser.IDC_INFO and norm_c not in ("?", "？", "") and norm_c != ch:
                    if norm_c not in primary_ch_list:
                        primary_ch_list.append(norm_c)
                    pair = (ch, norm_c)
                    if pair not in edge_pairs_seen:
                        edge_pairs_seen.add(pair)
                        component_edges_set.add((ch, norm_c, "chise"))

        # 2. CHISE で原子要素の場合の組み込み筆画分解フォールバック
        if not primary_ch_list and ch in ids_parser.ATOMIC_SUBDECOMPOSITIONS:
            atomic_ids = ids_parser.ATOMIC_SUBDECOMPOSITIONS[ch]
            toks = ids_parser.tokenize_ids(atomic_ids, normalize=False)
            for t in toks:
                norm_c = ids_parser.normalize_component(ids_parser.normalize_entity(t))
                if norm_c and norm_c not in ids_parser.IDC_INFO and norm_c not in ("?", "？", "") and norm_c != ch:
                    if norm_c not in primary_ch_list:
                        primary_ch_list.append(norm_c)
                    pair = (ch, norm_c)
                    if pair not in edge_pairs_seen:
                        edge_pairs_seen.add(pair)
                        component_edges_set.add((ch, norm_c, "atomic"))

        if primary_ch_list:
            parent_to_primary_children[ch] = primary_ch_list

        # 3. 外観IDS (apparent) 由来
        alt_list: list[str] = []
        if apparent_ids:
            toks = ids_parser.tokenize_ids(apparent_ids, normalize=False)
            for t in toks:
                norm_c = ids_parser.normalize_component(ids_parser.normalize_entity(t))
                if norm_c and norm_c not in ids_parser.IDC_INFO and norm_c not in ("?", "？", "") and norm_c != ch:
                    if norm_c not in primary_ch_list and norm_c not in alt_list:
                        alt_list.append(norm_c)
                    pair = (ch, norm_c)
                    if pair not in edge_pairs_seen:
                        edge_pairs_seen.add(pair)
                        component_edges_set.add((ch, norm_c, "apparent"))

        # 4. CJKVI-IDS 由来
        if cjkvi_ids:
            toks = ids_parser.tokenize_ids(cjkvi_ids, normalize=False)
            for t in toks:
                norm_c = ids_parser.normalize_component(ids_parser.normalize_entity(t))
                if norm_c and norm_c not in ids_parser.IDC_INFO and norm_c not in ("?", "？", "", "|") and norm_c != ch:
                    if norm_c not in primary_ch_list and norm_c not in alt_list:
                        alt_list.append(norm_c)
                    pair = (ch, norm_c)
                    if pair not in edge_pairs_seen:
                        edge_pairs_seen.add(pair)
                        component_edges_set.add((ch, norm_c, "cjkvi"))

        if alt_list:
            parent_to_alt_children[ch] = alt_list

    print(f"  -> 文字・直接エッジ解析完了: エッジ数 {len(component_edges_set):,} 本 ({time.time() - t0:.2f} 秒)")

    # --------------------------------------------------------------------------
    # 6. 高速推移閉包インデックス (component_closure) の算出 (BFS)
    # --------------------------------------------------------------------------
    print("\n【処理 6/6】推移的部品逆引き閉包インデックス (component_closure) の高速算出...")
    t0_closure = time.time()

    # 文字の属性ルックアップ用マップ
    char_meta_map: dict[str, tuple[int, int | None, int | None]] = {
        row[0]: (row[4], row[8], row[11]) for row in characters_rows
    }

    closure_rows: list[tuple] = []

    for target_char in all_chars:
        target_priority, target_strokes, target_freq = char_meta_map.get(
            target_char, (5, None, None)
        )

        # target_char の子要素探索 (BFS)
        closure: dict[str, tuple[int, int, str]] = {}
        queue = deque()

        # 1. プライマリ（CHISE優先）の子要素を探索
        primary_children = parent_to_primary_children.get(target_char, [])
        for c in primary_children:
            if c == target_char:
                continue
            closure[c] = (1, 1, "")
            queue.append((c, 1, c))

        while queue:
            curr, depth, top_child = queue.popleft()
            if depth >= 6:
                continue
            for nxt in parent_to_primary_children.get(curr, []):
                if nxt == target_char:
                    continue
                if nxt not in closure:
                    closure[nxt] = (depth + 1, 0, top_child)
                    queue.append((nxt, depth + 1, top_child))

        # 2. 代替（apparent / cjkvi）の子要素で未到達のものを追加探索
        alt_children = parent_to_alt_children.get(target_char, [])
        for alt_c in alt_children:
            if alt_c == target_char:
                continue
            if alt_c not in closure:
                closure[alt_c] = (1, 1, "")
                queue.append((alt_c, 1, alt_c))

        while queue:
            curr, depth, top_child = queue.popleft()
            if depth >= 6:
                continue
            for nxt in parent_to_primary_children.get(curr, []):
                if nxt == target_char:
                    continue
                if nxt not in closure:
                    closure[nxt] = (depth + 1, 0, top_child)
                    queue.append((nxt, depth + 1, top_child))

        for comp, (min_depth, is_direct, via_char) in closure.items():
            closure_rows.append((
                comp,
                target_char,
                min_depth,
                is_direct,
                via_char,
                target_priority,
                target_strokes,
                target_freq,
            ))

    print(f"  -> 閉包インデックス生成完了: {len(closure_rows):,} 件 ({time.time() - t0_closure:.2f} 秒)")

    # --------------------------------------------------------------------------
    # 7. SQLite への書き込みとインデックス構築
    # --------------------------------------------------------------------------
    print("\n【データベース出力】SQLite データベースへのトランザクション書込...")
    t0_db = time.time()

    if DB_PATH.exists():
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")

    # テーブル作成
    cur.execute("""
    CREATE TABLE characters (
        char TEXT PRIMARY KEY,
        codepoint TEXT,
        block_name TEXT,
        tier TEXT,
        sort_priority INTEGER,
        chise_ids TEXT,
        apparent_ids TEXT,
        cjkvi_ids TEXT,
        stroke_count INTEGER,
        radical_num INTEGER,
        grade INTEGER,
        freq INTEGER,
        jlpt INTEGER,
        ja_on TEXT,
        ja_kun TEXT,
        nanori TEXT,
        daikanwa TEXT,
        four_corner TEXT,
        skip_code TEXT,
        cangjie TEXT,
        moji_joho TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE component_edges (
        parent_char TEXT,
        child_char TEXT,
        source TEXT,
        PRIMARY KEY (parent_char, child_char)
    );
    """)

    cur.execute("""
    CREATE TABLE component_closure (
        component TEXT,
        target_char TEXT,
        min_depth INTEGER,
        is_direct INTEGER,
        via_char TEXT,
        target_priority INTEGER,
        target_strokes INTEGER,
        target_freq INTEGER,
        PRIMARY KEY (component, target_char)
    );
    """)

    # レコードの一括挿入
    cur.executemany("""
    INSERT INTO characters VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
    );
    """, characters_rows)

    cur.executemany("""
    INSERT OR IGNORE INTO component_edges VALUES (?, ?, ?);
    """, list(component_edges_set))

    cur.executemany("""
    INSERT OR REPLACE INTO component_closure VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?
    );
    """, closure_rows)

    conn.commit()

    # 高速検索インデックスの生成
    print("  インデックス作成中...")
    cur.execute("CREATE INDEX idx_closure_comp ON component_closure(component, is_direct, target_priority, target_strokes);")
    cur.execute("CREATE INDEX idx_closure_target ON component_closure(target_char);")
    cur.execute("CREATE INDEX idx_chars_codepoint ON characters(codepoint);")
    cur.execute("CREATE INDEX idx_chars_readings ON characters(ja_on, ja_kun);")
    cur.execute("CREATE INDEX idx_edges_child ON component_edges(child_char);")
    conn.commit()

    print(f"  -> SQLite 書込およびインデックス作成完了 ({time.time() - t0_db:.2f} 秒)")

    # --------------------------------------------------------------------------
    # 7.5 熟語・語彙辞書データベースの統合 (words / word_kanji)
    # --------------------------------------------------------------------------
    try:
        from scripts.build_words_db import build_words_tables
        build_words_tables(DB_PATH)
    except Exception as e:
        print(f"  ※ 語彙辞書の構築中にエラーが発生しました: {e}")

    # --------------------------------------------------------------------------
    # 8. 検証テストの実行
    # --------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("データベース検証テスト")
    print("=" * 70)

    # 1. 総文字数の検証 (> 100,000)
    cur.execute("SELECT COUNT(*) FROM characters;")
    total_chars = cur.fetchone()[0]
    print(f"\n1. 総文字数: {total_chars:,} 字")
    assert total_chars > 100000, f"文字数が 100,000 件未満です: {total_chars}"
    print("  -> 合格: 100,000件以上の文字が正常に格納されています。")

    # 2. 蛍、𰃮、𭕄 の検証
    print("\n2. 主要文字（蛍, 𰃮, 𭕄）の登録情報:")
    for ch in ("蛍", "𰃮", "𭕄"):
        cur.execute("SELECT char, codepoint, block_name, chise_ids, cjkvi_ids, stroke_count, ja_on, ja_kun FROM characters WHERE char = ?;", (ch,))
        row = cur.fetchone()
        assert row is not None, f"文字 {ch} が characters に見つかりません"
        print(f"  【{row[0]}】コード:{row[1]} | ブロック:{row[2]} | CHISE:{row[3]} | CJKVI:{row[4]} | 画数:{row[5]} | 音:{row[6]} | 訓:{row[7]}")
    print("  -> 合格: 蛍、𰃮、𭕄 のメタデータが正しく取得できています。")

    # 3. component_closure における component = '𭕄' の検証
    print("\n3. 構成要素「𭕄」の逆引き検索（component_closure）の検証:")
    cur.execute("""
    SELECT target_char, is_direct, via_char, min_depth
    FROM component_closure
    WHERE component = '𭕄' AND target_char IN ('𰃮', '単', '巣', '脳', '獣', '蛍', '学', '栄', '覚', '労', '営')
    ORDER BY is_direct DESC, target_char ASC;
    """)
    closure_results = cur.fetchall()
    results_dict = {r[0]: (r[1], r[2], r[3]) for r in closure_results}

    # 直接構成要素の検証
    direct_expected = ["𰃮", "単", "巣", "脳", "獣"]
    print("  直接含む文字（is_direct=1）:")
    for ch in direct_expected:
        assert ch in results_dict, f"直接結果に {ch} が含まれていません"
        is_direct, via, depth = results_dict[ch]
        assert is_direct == 1, f"{ch} の is_direct が 1 ではありません ({is_direct})"
        print(f"    {ch}: is_direct={is_direct}, via_char='{via}', min_depth={depth}")

    # 間接構成要素（𰃮経由）の検証
    indirect_expected = ["蛍", "学", "栄", "覚", "労", "営"]
    print("  間接的に含む文字（via_char='𰃮', is_direct=0）:")
    for ch in indirect_expected:
        assert ch in results_dict, f"間接結果に {ch} が含まれていません"
        is_direct, via, depth = results_dict[ch]
        assert via == "𰃮", f"{ch} の via_char が '𰃮' ではありません ('{via}')"
        assert is_direct == 0, f"{ch} の is_direct が 0 ではありません ({is_direct})"
        print(f"    {ch}: is_direct={is_direct}, via_char='{via}', min_depth={depth}")

    print("  -> 合格: 「𭕄」を含む漢字の直接・間接検索インデックスが期待通り動作しています。")

    # 4. 熟語・語彙テーブル（words, word_kanji）の検証
    print("\n4. 熟語・語彙テーブルの登録検証:")
    cur.execute("SELECT COUNT(*) FROM words;")
    total_words = cur.fetchone()[0]
    print(f"  総熟語数: {total_words:,} 語")
    assert total_words > 100000, f"熟語数が 100,000 件未満です: {total_words}"

    cur.execute("""
    SELECT w.lemma, w.reading, w.frequency_rank, w.frequency_tier
    FROM word_kanji wk
    JOIN words w ON wk.word_id = w.word_id
    WHERE wk.kanji = '蛍'
    ORDER BY (CASE WHEN w.frequency_rank IS NULL OR w.frequency_rank = 0 THEN 99999999 ELSE w.frequency_rank END) ASC
    LIMIT 3;
    """)
    word_sample = cur.fetchall()
    assert len(word_sample) >= 3, "「蛍」を含む熟語が3件未満です"
    print("  「蛍」を含む熟語上位サンプル:", [f"{r[0]} ({r[1]}) #{r[2]} [{r[3]}]" for r in word_sample])
    print("  -> 合格: 熟語・語彙データが正常に登録され、頻度順検索が動作しています。")

    conn.close()
    print("\n" + "=" * 70)
    print(f"データベースの構築と全検証が正常に完了しました（総所要時間: {time.time() - start_time:.2f} 秒）")
    print("=" * 70)


if __name__ == "__main__":
    build_database()
