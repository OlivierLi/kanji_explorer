"""漢字熟語・語彙辞書データベース構築スクリプト (scripts/build_words_db.py).

BCCWJコーパス（現代日本語書き言葉均衡コーパス 頻度順位）、
日本語版Wiktionary（Kaikki.org 日本語抽出データ）、および
NICT日本語WordNet辞書を統合し、完全オフラインで動作する
高品質・100%日本語の単語・熟語・語釈データベースを構築します。
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sqlite3
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "kanji_explorer.db"

BCCWJ_ZIP_PATH = DATA_DIR / "BCCWJ-LUW.zip"
WIKTIONARY_GZ_PATH = DATA_DIR / "ja-extract.jsonl.gz"
WORDNET_GZ_PATH = DATA_DIR / "wnjpn.db.gz"
WORDNET_DB_PATH = DATA_DIR / "wnjpn.db"

KANJI_RE = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF\U00020000-\U0002EBEF]")


def map_pos_title(raw_pos: str) -> str:
    """品詞ラベルを統一日本語品詞名に正規化する."""
    if not raw_pos:
        return "名詞"
    p = raw_pos.strip()
    if "固有名詞" in p:
        return "固有名詞"
    if "名詞" in p or p in ("noun", "n"):
        return "名詞"
    if "動詞" in p or p in ("verb", "v"):
        return "動詞"
    if "形容動詞" in p or "形状詞" in p:
        return "形容動詞"
    if "形容詞" in p or p in ("adj", "adjective", "a"):
        return "形容詞"
    if "副詞" in p or p in ("adv", "adverb", "r"):
        return "副詞"
    if "成句" in p or "ことわざ" in p or "慣用句" in p or "四字熟語" in p:
        return "成句"
    if "接頭" in p or p == "prefix":
        return "接頭辞"
    if "接尾" in p or p == "suffix":
        return "接尾辞"
    if "接続詞" in p or p == "conjunction":
        return "接続詞"
    if "感動詞" in p or p == "interjection":
        return "感動詞"
    if "連体詞" in p:
        return "連体詞"
    if "字義" in p or "意義" in p:
        return "字義"
    return "語彙"


def get_frequency_tier(rank: int | None) -> str:
    """BCCWJ頻度順位から日本語頻度区分を判定する."""
    if rank is None or rank <= 0 or rank >= 9999990:
        return "専門・稀少"
    if rank <= 5000:
        return "最頻出"
    if rank <= 20000:
        return "頻出"
    if rank <= 60000:
        return "一般"
    if rank <= 150000:
        return "発展"
    return "専門・稀少"


def load_bccwj_frequencies() -> dict[str, tuple[int, str]]:
    """BCCWJ-LUW (Long Unit Words) から単語頻度順位と読みを読み込む."""
    print("【処理 1/4】BCCWJ 語彙頻度辞書の解析中...")
    t0 = time.time()
    freq_map: dict[str, tuple[int, str]] = {}

    if not BCCWJ_ZIP_PATH.exists():
        print(f"  ※ {BCCWJ_ZIP_PATH} が存在しないため、BCCWJ頻度解析をスキップします。")
        return freq_map

    with zipfile.ZipFile(BCCWJ_ZIP_PATH) as z:
        for name in z.namelist():
            if not name.startswith("term_meta_bank"):
                continue
            with z.open(name) as f:
                data = json.load(f)
                for item in data:
                    if not isinstance(item, list) or len(item) < 3:
                        continue
                    w = item[0]
                    meta = item[2]
                    if not isinstance(meta, dict):
                        continue
                    rank = meta.get("frequency", 9999999)
                    reading = meta.get("reading", "")
                    if w not in freq_map or rank < freq_map[w][0]:
                        freq_map[w] = (rank, reading)

    print(f"  -> BCCWJ {len(freq_map):,} 語の頻度データを読み込みました ({time.time() - t0:.2f}秒)")
    return freq_map


def load_wordnet_definitions() -> dict[str, dict[str, Any]]:
    """NICT 日本語WordNet から語釈データを抽出する."""
    print("【処理 2/4】NICT 日本語WordNet の語釈データ解析中...")
    t0 = time.time()
    wn_words: dict[str, dict[str, Any]] = {}

    # db または db.gz の存在確認
    target_db = WORDNET_DB_PATH
    temp_unpacked = False

    if not target_db.exists() and WORDNET_GZ_PATH.exists():
        target_db = DATA_DIR / "temp_wnjpn.db"
        with gzip.open(WORDNET_GZ_PATH, "rb") as gz_in, open(target_db, "wb") as db_out:
            db_out.write(gz_in.read())
        temp_unpacked = True
    elif not target_db.exists() and Path("/tmp/wnjpn.db").exists():
        target_db = Path("/tmp/wnjpn.db")

    if not target_db.exists():
        print("  ※ WordNet データベースが見つからないためスキップします。")
        return wn_words

    pos_code_map = {"n": "名詞", "v": "動詞", "a": "形容詞", "r": "副詞"}

    conn = sqlite3.connect(target_db)
    cur = conn.cursor()
    query = """
    SELECT w.lemma, w.pos, sd.def
    FROM word w
    JOIN sense s ON w.wordid = s.wordid AND s.lang = 'jpn'
    JOIN synset_def sd ON s.synset = sd.synset AND sd.lang = 'jpn'
    WHERE w.lang = 'jpn'
    """
    for lemma, pos, defn in cur.execute(query):
        if not KANJI_RE.search(lemma):
            continue
        clean_def = defn.strip()
        if not clean_def:
            continue
        if lemma not in wn_words:
            wn_words[lemma] = {"pos": pos_code_map.get(pos, "名詞"), "defs": []}
        if clean_def not in wn_words[lemma]["defs"]:
            wn_words[lemma]["defs"].append(clean_def)

    conn.close()
    if temp_unpacked and target_db.exists():
        try:
            target_db.unlink()
        except OSError:
            pass

    print(f"  -> WordNet {len(wn_words):,} 語の漢字語釈を抽出しました ({time.time() - t0:.2f}秒)")
    return wn_words


def load_wiktionary_definitions() -> dict[str, dict[str, Any]]:
    """日本語版 Wiktionary (Kaikki) から見出し語、読み、品詞、語釈を抽出する."""
    print("【処理 3/4】日本語版 Wiktionary (Kaikki) の語釈データ解析中...")
    t0 = time.time()
    wiki_words: dict[str, dict[str, Any]] = {}

    if not WIKTIONARY_GZ_PATH.exists():
        print(f"  ※ {WIKTIONARY_GZ_PATH} が存在しないためスキップします。")
        return wiki_words

    with gzip.open(WIKTIONARY_GZ_PATH, "rt", encoding="utf-8") as f:
        for line in f:
            if '"lang_code": "ja"' not in line and '"lang_code": "mul"' not in line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            lang_code = d.get("lang_code")
            if lang_code not in ("ja", "mul"):
                continue

            w = d.get("word", "")
            if not w or not KANJI_RE.search(w):
                continue

            # 記号や不要なメタ文字列を除去
            if w.startswith("Template:") or w.startswith("カテゴリ:") or w.startswith("付録:"):
                continue

            raw_pos = d.get("pos_title") or d.get("pos") or "名詞"
            pos = map_pos_title(raw_pos)

            glosses: list[str] = []
            for s in d.get("senses", []):
                for g in s.get("glosses", []):
                    clean_g = g.strip()
                    if clean_g and not clean_g.endswith("参照"):
                        glosses.append(clean_g)

            reading = ""
            for form in d.get("forms", []):
                tags = form.get("tags", [])
                if "transliteration" in tags or "kana" in tags:
                    f_text = form.get("form", "")
                    if f_text and not KANJI_RE.search(f_text):
                        reading = f_text
                        break

            if w not in wiki_words:
                wiki_words[w] = {"pos": pos, "reading": reading, "defs": []}
            else:
                if not wiki_words[w]["reading"] and reading:
                    wiki_words[w]["reading"] = reading

            for g in glosses:
                if g not in wiki_words[w]["defs"]:
                    wiki_words[w]["defs"].append(g)

    print(f"  -> Wiktionary {len(wiki_words):,} 語の漢字語釈を抽出しました ({time.time() - t0:.2f}秒)")
    return wiki_words


def build_words_tables(db_path: Path = DB_PATH) -> None:
    """統合辞書データを構築し、kanji_explorer.db に格納する."""
    t_start = time.time()
    print("=" * 70)
    print("漢字熟語・語彙辞書データベース (words / word_kanji) 構築開始")
    print(f"ターゲットDB: {db_path}")
    print("=" * 70)

    freq_map = load_bccwj_frequencies()
    wn_words = load_wordnet_definitions()
    wiki_words = load_wiktionary_definitions()

    print("\n【処理 4/4】データの統合および SQLite へのインデックス登録中...")
    t_merge = time.time()

    all_lemmas = sorted(set(wiki_words.keys()) | set(wn_words.keys()))
    print(f"  総収録見出し語数: {len(all_lemmas):,} 語")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA synchronous = OFF;")
    cur.execute("PRAGMA journal_mode = WAL;")

    # テーブル初期化
    cur.execute("DROP TABLE IF EXISTS word_kanji;")
    cur.execute("DROP TABLE IF EXISTS words;")

    cur.execute("""
    CREATE TABLE words (
        word_id INTEGER PRIMARY KEY AUTOINCREMENT,
        lemma TEXT NOT NULL,
        reading TEXT,
        pos TEXT,
        definition TEXT,
        frequency_rank INTEGER,
        frequency_tier TEXT,
        source TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE word_kanji (
        kanji TEXT NOT NULL,
        word_id INTEGER NOT NULL,
        position_type TEXT NOT NULL,
        char_index INTEGER NOT NULL,
        PRIMARY KEY (kanji, word_id, char_index),
        FOREIGN KEY (word_id) REFERENCES words(word_id) ON DELETE CASCADE
    );
    """)

    words_rows: list[tuple[Any, ...]] = []
    word_kanji_rows: list[tuple[Any, ...]] = []

    word_id = 1
    for lemma in all_lemmas:
        w_entry = wiki_words.get(lemma)
        wn_entry = wn_words.get(lemma)

        # 品詞
        pos = (w_entry and w_entry.get("pos")) or (wn_entry and wn_entry.get("pos")) or "名詞"

        # 読み (BCCWJコーパス読みを最優先、次にWiktionary読み)
        reading = ""
        f_rank = 9999999
        if lemma in freq_map:
            f_rank, f_read = freq_map[lemma]
            reading = f_read

        if not reading and w_entry:
            reading = w_entry.get("reading", "")

        tier = get_frequency_tier(f_rank)

        # 語釈（Wiktionaryの自然な語釈を最優先、次にWordNetの概念定義）
        defs: list[str] = []
        if w_entry and w_entry.get("defs"):
            defs.extend(w_entry["defs"])
        if wn_entry and wn_entry.get("defs"):
            for d in wn_entry["defs"]:
                if d not in defs:
                    defs.append(d)

        # JSON形式および結合文字列の双方で活用できるように保存
        definition_json = json.dumps(defs[:5], ensure_ascii=False) if defs else "[]"
        source = "統合辞書" if (w_entry and wn_entry) else ("Wiktionary" if w_entry else "WordNet")

        words_rows.append((word_id, lemma, reading, pos, definition_json, f_rank, tier, source))

        # 漢字出現位置マッピング
        lemma_len = len(lemma)
        for idx, char in enumerate(lemma):
            if KANJI_RE.match(char):
                if lemma_len == 1:
                    pos_type = "single"
                elif idx == 0:
                    pos_type = "head"
                elif idx == lemma_len - 1:
                    pos_type = "tail"
                else:
                    pos_type = "middle"
                word_kanji_rows.append((char, word_id, pos_type, idx))

        word_id += 1

    print(f"  -> SQLite へ単語 {len(words_rows):,} 件、漢字マッピング {len(word_kanji_rows):,} 件を一括挿入中...")
    cur.executemany(
        "INSERT INTO words (word_id, lemma, reading, pos, definition, frequency_rank, frequency_tier, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        words_rows,
    )
    cur.executemany(
        "INSERT OR IGNORE INTO word_kanji (kanji, word_id, position_type, char_index) VALUES (?, ?, ?, ?);",
        word_kanji_rows,
    )

    print("  -> 高速検索インデックスを生成中...")
    cur.execute("CREATE INDEX idx_word_kanji_lookup ON word_kanji(kanji, word_id);")
    cur.execute("CREATE INDEX idx_word_kanji_pos ON word_kanji(kanji, position_type);")
    cur.execute("CREATE INDEX idx_words_freq ON words(frequency_rank);")
    cur.execute("CREATE INDEX idx_words_lemma ON words(lemma);")

    conn.commit()

    # 動作確認検証
    print("\n【検証】主要漢字（蛍、学、木）の語彙検索テスト:")
    for test_k in ("蛍", "学", "木"):
        cur.execute(
            """
            SELECT w.lemma, w.reading, w.frequency_rank, w.frequency_tier, w.definition
            FROM word_kanji wk
            JOIN words w ON wk.word_id = w.word_id
            WHERE wk.kanji = ?
            ORDER BY (CASE WHEN w.frequency_rank IS NULL OR w.frequency_rank = 0 THEN 99999999 ELSE w.frequency_rank END) ASC
            LIMIT 5;
            """,
            (test_k,),
        )
        test_rows = cur.fetchall()
        print(f"  ■ 漢字「{test_k}」の熟語上位 {len(test_rows)} 件:")
        for r in test_rows:
            d_list = json.loads(r[4])
            d_first = d_list[0] if d_list else "語釈なし"
            print(f"    ・{r[0]} ({r[1]}) 順位: #{r[2]} [{r[3]}] - {d_first[:40]}...")

    conn.close()
    print("=" * 70)
    print(f"語彙データベース構築完了（総所要時間: {time.time() - t_start:.2f}秒）")
    print("=" * 70)


if __name__ == "__main__":
    build_words_tables()
