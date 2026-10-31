# データソース一覧 (Data Sources)

本プロジェクト「漢字構造・部品探索システム (Kanji Explorer)」で使用されている各種データソース、文字メタデータ、筆画情報、字形ベクター、および熟語辞書コーパスの一覧と出典情報です。

---

## 1. 概要一覧表 (Overview)

| データソース名 | 用途・収録内容 | 形式・ファイル | プロジェクト / 提供元 | ライセンス |
| :--- | :--- | :--- | :--- | :--- |
| **KanjiVG** | 筆順・運筆ベクターSVG、筆画タイプ（㇐, ㇑等）、部品所属 | `data/kanjivg.xml.gz` | [KanjiVG Project](https://kanjivg.tagaini.net/) (Ulrich Apel) | CC BY-SA 3.0 |
| **Jigmo フォント** | 印刷書体（明朝体）TrueTypeベクター輪郭線抽出 | `static/fonts/Jigmo*.ttf` | [Jigmo (GlyphWiki)](https://glyphwiki.org/) | CC0 1.0 (Public Domain) |
| **GlyphWiki** | 外字・異体字・古字・歴史的字形デザイン | オンライン / Jigmo経由 | [GlyphWiki](https://glyphwiki.org/) | CC0 / 自由利用 |
| **日本語版 Wiktionary** | 見出し語、日本語語釈、品詞分類、読み仮名 | `data/ja-extract.jsonl.gz` | [Wiktionary](https://ja.wiktionary.org/) / [Kaikki.org](https://kaikki.org/) | CC BY-SA 3.0 / 4.0 |
| **NICT 日本語 WordNet** | 日本語概念定義・語義・同義語情報 | `data/wnjpn.db.gz` | [情報通信研究機構 (NICT)](https://bond-lab.github.io/wnja/) | WordNet License (Permissive) |
| **BCCWJ コーパス** | 現代日本語書き言葉均衡コーパス 語彙頻度順位・区分 | `data/BCCWJ-LUW.zip` | [国立国語研究所 (NINJAL)](https://clrd.ninjal.ac.jp/bccwj/) | NINJAL 規約利用 |
| **KANJIDIC2** | 漢字メタデータ（画数、部首、学年、音訓、JLPT等） | `data/kanjidic2.xml.gz` | [EDRDG](https://www.edrdg.org/wiki/index.php/KANJIDIC_Project) (Jim Breen) | CC BY-SA 4.0 |
| **Unicode Unihan** | 拡張漢字画数、部首、倉頡、四角号碼、文字情報基盤 | `data/Unihan.zip` | [Unicode Consortium](https://www.unicode.org/charts/unihan.html) | Unicode Terms of Use |
| **CHISE IDS** | 漢字構成記述文字列（IDS）、見かけ構造（@apparent） | `data/chise-ids/` | [CHISE Project](https://www.chise.org/) (京都大学) | GPL / CC BY-SA |
| **CJKVI-IDS** | CJKVI 代替構造分解記述データ | `data/cjkvi-ids.txt` | [CJKVI Database Project](https://github.com/cjkvi/cjkvi-ids) | GPL / オープンデータ |
| **Unicode UCD** | 康熙部首・部首補助と統合漢字の等価対応表 | `data/EquivalentUnifiedIdeograph.txt` | [Unicode Consortium](https://www.unicode.org/Public/UCD/latest/ucd/) | Unicode Terms of Use |

---

## 2. 筆画・運筆・グリフベクター情報 (Stroke & Glyph Vector Information)

### KanjiVG (Kanji Vector Graphics)
- **提供元**: [KanjiVG Project](https://kanjivg.tagaini.net/)（代表: Ulrich Apel 氏）
- **利用ファイル**: `data/kanjivg.xml.gz`
- **用途・役割**:
  - 全画ごとの手書き筆順データ、ベクターパス（SVG `d` 属性）、筆画タイプ属性（`kvg:type`: 永字八法・CJK Strokes に基づく `㇐`, `㇑`, `㇒`, `㇏`, `㇕`, `㇚` 等）の提供。
  - 筆画がどの部品要素（`kvg:element`）および空間位置（`kvg:position`: `left`, `right`, `top`, `bottom` 等）に属するかの階層構造定義。
  - [`glyph_service.py`](glyph_service.py) において、KanjiVG の筆画ストロークを CHISE IDS 構文木と照合・整列し、筆画単位のインタラクティブハイライトおよび墨絵書道キャンバス描画（`calligraphy-sumi-canvas`）に使用されます。
- **ライセンス**: Creative Commons Attribution-Share Alike 3.0 (CC BY-SA 3.0)

### Jigmo フォント (Jigmo Fonts)
- **提供元**: [Jigmo フォント配布所](https://glyphwiki.org/)（GlyphWiki 由来）
- **利用ファイル**:
  - `static/fonts/Jigmo.ttf`（BMP: 基本多言語面、拡張A）
  - `static/fonts/Jigmo2.ttf`（SIP: 第2基本多言語面、拡張B〜F）
  - `static/fonts/Jigmo3.ttf`（TIP: 第3基本多言語面、拡張G〜J）
- **用途・役割**:
  - Unicode 基本漢字から最新の拡張 J 面、および IVD（異体字セレクタ）を含む 145,973 字の明朝体（印刷書体）アウトラインを保持。
  - [`glyph_service.py`](glyph_service.py) 内の `TTFont` 抽出エンジンにより、フォントファイルから二次ベジェ曲線の輪郭線座標（1024×1024 EMスクエア）を直接展開。
  - 連結インクアイランド（`_extract_ink_islands`）および白抜き穴（`hole_boxes`）の解析を通じて、正確なベクター部品分解スライスを生成します。
- **ライセンス**: CC0 1.0 Universal (Public Domain Dedication)

### GlyphWiki (グリフウィキ)
- **提供元**: [GlyphWiki](https://glyphwiki.org/)（管理・運営: かみち 氏 / コミュニティ）
- **用途・役割**:
  - JIS規格外文字、敦煌文献漢字、大漢和辞典収録文字、CDP外字などのグリフ定義（KAGE記述）の元データ。Jigmoフォントの生成基盤となっています。

---

## 3. 語彙・熟語・国語辞典情報 (Vocabulary & Dictionaries)

### 日本語版 Wiktionary (via Kaikki.org)
- **提供元**: [Wiktionary 日本語版](https://ja.wiktionary.org/) / [Kaikki.org](https://kaikki.org/) (Tatu Ylonen 氏)
- **利用ファイル**: `data/ja-extract.jsonl.gz`
- **用途・役割**:
  - 10万語以上の現代語・熟語・固有名詞・専門用語・慣用句の見出し語、標準的な日本語語釈、読み仮名、品詞情報（名詞、動詞、形容詞など）を提供。
  - [`scripts/build_words_db.py`](scripts/build_words_db.py) により、漢字熟語辞書テーブル（`words`, `word_kanji`）の基礎語釈として統合されています。
- **ライセンス**: Creative Commons Attribution-ShareAlike License (CC BY-SA 3.0 / 4.0)

### NICT 日本語 WordNet (Japanese WordNet)
- **提供元**: [国立研究開発法人 情報通信研究機構 (NICT)](https://bond-lab.github.io/wnja/)
- **利用ファイル**: `data/wnjpn.db.gz`
- **用途・役割**:
  - 概念分類（シノセット）および精緻な語義定義・概念説明テキストを提供。
  - Wiktionary に語釈が未収録の語や概念的説明を補完するフォールバック語釈として活用されています。
- **ライセンス**: NICT WordNet License（学術・商用を問わず改変・再配布可能なパーミッシブライセンス）

### 現代日本語書き言葉均衡コーパス (BCCWJ - Balanced Corpus of Contemporary Written Japanese)
- **提供元**: [大学共同利用機関法人 人間文化研究機構 国立国語研究所 (NINJAL)](https://clrd.ninjal.ac.jp/bccwj/)
- **利用ファイル**: `data/BCCWJ-LUW.zip`（長単位語頻度データ / LUW: Long Unit Words）
- **用途・役割**:
  - 雑誌、書籍、新聞、白書、Webなど約1億語の書き言葉コーパスに基づく単語出現頻度順位（`frequency_rank`）および高信頼な読み仮名を提供。
  - アプリケーション内の単語ソート（最頻出語順）、および頻度区分バッジ（最頻出: 1〜5,000位、頻出: 5,001〜20,000位、一般: 20,001〜60,000位、発展: 60,001〜150,000位、専門・稀少: 150,001位〜）の判定に使用されます。
- **ライセンス**: 国立国語研究所 BCCWJ データ利用規約

---

## 4. 漢字メタデータ・属性情報 (Character Metadata & Attributes)

### KANJIDIC2
- **提供元**: [The Electronic Dictionary Research and Development Group (EDRDG)](https://www.edrdg.org/)（Jim Breen 氏 / EDRDG）
- **利用ファイル**: `data/kanjidic2.xml.gz`
- **用途・役割**:
  - 常用漢字・人名用漢字を含む 13,108 字の詳細な漢字属性を提供。
  - 総画数（`stroke_count`）、康熙部首番号（`radical_num`）、小学校配当学年（`grade`）、新聞頻度順位（`freq`）、日本語能力試験レベル（`jlpt`）、音読み（`ja_on`）・訓読み（`ja_kun`）・名乗り（`nanori`）、大漢和辞典番号（`daikanwa`）、四角号碼（`four_corner`）、SKIPコード（`skip_code`）の取得源。
- **ライセンス**: Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)

### Unicode Unihan Database
- **提供元**: [Unicode Consortium](https://www.unicode.org/)
- **利用ファイル**: `data/Unihan.zip`
- **用途・役割**:
  - KANJIDIC2 に収録されていない Unicode 拡張漢字（CJK Unified Ideographs Extension A〜J 等）のメタデータを補完。
  - 総画数（`kTotalStrokes`）、部首余画（`kRSUnicode`）、倉頡コード（`kCangjie`）、四角号碼（`kFourCornerCode`）、文字情報基盤ID（`kMojiJoho`）、日本語音訓（`kJapaneseOn`, `kJapaneseKun`）の抽出。
- **ライセンス**: Unicode Character Database Terms of Use

### Unicode 康熙部首等価表 (EquivalentUnifiedIdeograph.txt)
- **提供元**: [Unicode Consortium (UCD)](https://www.unicode.org/Public/UCD/latest/ucd/)
- **利用ファイル**: `data/EquivalentUnifiedIdeograph.txt`
- **用途・役割**:
  - Unicode 康熙部首ブロック（U+2F00..U+2FD5）および部首補助ブロック（U+2E80..U+2EFF）の文字と、CJK統合漢字（U+4E00..U+9FFF）の等価対応（例: `⾦` U+2F96 ⇄ `金` U+91D1、`⺡` U+2EA1 ⇄ `氵` U+6C35 ⇄ `水` U+6C34）を正規化・相互マッピングするために使用。
- **ライセンス**: Unicode Character Database Terms of Use

---

## 5. 漢字構成要素・分解構文情報 (Ideographic Structure & Decomposition)

### CHISE IDS (Character Information Service Environment)
- **提供元**: [CHISE プロジェクト](https://www.chise.org/)（京都大学 人文科学研究所 / 代表: Christian Wittern 教授、守岡知彦 博士）
- **利用ディレクトリ**: `data/chise-ids/`（`IDS-UCS-*.txt`, `IDS-JIS-*.txt`, `IDS-CDP.txt`, `IDS-Daikanwa-*.txt` 等）
- **用途・役割**:
  - 全16種類の Unicode 漢字構成記述文字（IDC: `⿰`, `⿱`, `⿲`, `⿳`, `⿴`, `⿵`, `⿶`, `⿷`, `⿸`, `⿹`, `⿺`, `⿻`, `⿼`, `⿽`, `⿾`, `⿿`）を用いた 10万文字以上の再帰的構文木分解の基本データ。
  - 各文字の標準構造（CHISE標準IDS）および視覚的レイアウト構造（`@apparent`）の提供。
  - [`ids_parser.py`](ids_parser.py) によりトークナイズ・構文解析され、下位部品探索木および包含漢字閉包テーブル（`component_closure`）の構築に用いられます。
- **ライセンス**: GNU General Public License (GPL) / Creative Commons Attribution-ShareAlike

### CJKVI-IDS
- **提供元**: [CJKVI Database Project](https://github.com/cjkvi/cjkvi-ids)
- **利用ファイル**: `data/cjkvi-ids.txt`
- **用途・役割**:
  - CHISE IDS とは異なる別系統の構造分解記述データを提供。
  - アプリケーションの中央カラムにおける「構造バリエーション切替（CJKVI構造）」として選択・表示可能。
- **ライセンス**: GPL / Open Data

---

## 6. 派生データベーステーブルと設計 (Derived Database Architecture)

上記ソースを統合し、[`build_db.py`](build_db.py) および [`scripts/build_words_db.py`](scripts/build_words_db.py) によって以下のオフライン SQLite データベース（`data/kanji_explorer.db` / `data/kanji_explorer.db.gz`）が生成されています。

```
                    [CHISE IDS] [CJKVI-IDS] [KANJIDIC2] [Unihan]
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   build_db.py       │
                         └──────────┬──────────┘
                                    ▼
               ┌─────────────────────────────────────────┐
               │         kanji_explorer.db               │
               ├──────────────────┬──────────────────────┤
               │ characters       │ 漢字基本メタデータ   │
               │ component_edges  │ 直接構成部品エッジ   │
               │ component_closure│ 推移閉包・逆引き探索 │
               └──────────────────┴──────────────────────┘
                                    ▲
                         ┌──────────┴──────────┐
                         │ build_words_db.py   │
                         └──────────▲──────────┘
                                    │
                    [BCCWJ] [Wiktionary] [WordNet]
                                    ▼
               ┌─────────────────────────────────────────┐
               │ words            │ 語彙・見出し語・語釈 │
               │ word_kanji       │ 単語・漢字所属マップ │
               └─────────────────────────────────────────┘
```

1. **`characters` テーブル (約 102,900 字)**:
   - 全漢字・構成部品の一意なコードポイント、ブロック名、画数、部首番号、学校配当学年、新聞頻度、音訓読み、大漢和番号、四角号碼、CHISE/CJKVI構造記述式を統合。
2. **`component_closure` テーブル (約 1,080,000 件)**:
   - CHISE IDS を再帰的に走査して構築した推移閉包（Transitive Closure）。
   - ある部品（例: `𭕄`）が、どの漢字（「学」「単」「覚」「労」「営」「桜」等）に直接（`is_direct=1`）または間接（`is_direct=0`）に含まれるかを高速インデックス検索可能。
3. **`words` テーブル (約 149,000 語)**:
   - BCCWJ の頻度順位、Wiktionary および WordNet の日本語語釈、品詞を保持。
4. **`word_kanji` テーブル (約 310,000 件)**:
   - 単語見出し内の漢字とその出現位置（語頭: `head`, 語中: `middle`, 語尾: `tail`, 単独: `single`）をマッピング。
   - `component_closure` と結合することで、**「部首・構成要素（例: 𭕄、缶）を含む漢字が使われている熟語（例: 学校、鬱病）」**を頻度順かつ瞬時に探索可能。
