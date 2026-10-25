"""漢字構造記述文字列（IDS: Ideographic Description Sequences）構文解析モジュール.

標準ライブラリのみで構成され、CHISE IDSおよびUnicode IDSの構文木（AST）解析、
文字・エンティティの正規化、2次元空間バウンディングボックス算出、
および構成要素の再帰的木展開を提供します。
すべてのラベル・演算子説明・メタデータ文字列は日本語です。
"""

from __future__ import annotations

import glob
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

# ==============================================================================
# 1. IDC 演算子および日本語メタデータ (IDC_INFO)
# ==============================================================================

IDC_INFO: dict[str, dict[str, Any]] = {
    # 2項演算子 (アリティ 2)
    "⿰": {"arity": 2, "name": "左右構造", "short": "左右", "parts": ["左", "右"]},
    "⿱": {"arity": 2, "name": "上下構造", "short": "上下", "parts": ["上", "下"]},
    "⿴": {
        "arity": 2,
        "name": "全包囲構造（国構え等）",
        "short": "全包囲",
        "parts": ["外囲", "内側"],
    },
    "⿵": {
        "arity": 2,
        "name": "上三方包囲（同構え等）",
        "short": "上包囲",
        "parts": ["上囲", "内側"],
    },
    "⿶": {
        "arity": 2,
        "name": "下三方包囲（凶構え等）",
        "short": "下包囲",
        "parts": ["下囲", "内側"],
    },
    "⿷": {
        "arity": 2,
        "name": "左三方包囲（区構え等）",
        "short": "左包囲",
        "parts": ["左囲", "内側"],
    },
    "⿸": {
        "arity": 2,
        "name": "左上包囲（垂れ）",
        "short": "左上包囲",
        "parts": ["垂れ", "内側"],
    },
    "⿹": {
        "arity": 2,
        "name": "右上包囲（包み構え）",
        "short": "右上包囲",
        "parts": ["包み", "内側"],
    },
    "⿺": {
        "arity": 2,
        "name": "左下包囲（繞・にょう）",
        "short": "左下包囲",
        "parts": ["繞", "内側"],
    },
    "⿻": {
        "arity": 2,
        "name": "重ね・交差構造",
        "short": "重ね",
        "parts": ["要素1", "要素2"],
    },
    "⿼": {"arity": 2, "name": "右三方包囲", "short": "右包囲", "parts": ["右囲", "内側"]},
    "⿽": {"arity": 2, "name": "右下包囲", "short": "右下包囲", "parts": ["右下囲", "内側"]},
    # 3項演算子 (アリティ 3)
    "⿲": {"arity": 3, "name": "左中右構造", "short": "左中右", "parts": ["左", "中", "右"]},
    "⿳": {"arity": 3, "name": "上中下構造", "short": "上中下", "parts": ["上", "中", "下"]},
    # 1項演算子 (アリティ 1)
    "⿾": {"arity": 1, "name": "左右反転（鏡像）", "short": "反転", "parts": ["元字"]},
    "⿿": {"arity": 1, "name": "上下反転（回転）", "short": "回転", "parts": ["元字"]},
}

# ==============================================================================
# 2. 組み込み構成要素および筆画分解定義 (COMPONENT_SUBDECOMPOSITIONS, STROKE_SUBDECOMPOSITIONS)
# ==============================================================================

# 単一Unicode文字に対応するCHISE実体参照の対応マップ
CHISE_ENTITY_UNICODE_MAP: dict[str, str] = {
    "&CDP-8958;": "⺼",
    "&GT-K00059;": "八",
    "&CDP-8B43;": "阝",
    "&CDP-8B7C;": "艮",
    "&GT-K01085;": "𠫓",
    "&CDP-89AE;": "冫",
    "&CDP-8964;": "𫠣",
    "&CDP-8CBB;": "𪜋",
    "&CDP-8968;": "𠂤",
    "&JX2-7461;": "䍃",
    "&CDP-89D5;": "𠂊",
    "&CDP-8BD9;": "甲",
    "&CDP-8BC0;": "冂",
    "&CDP-8BEA;": "刂",
    "&CDP-895F;": "匕",
    "&CDP-895C;": "纟",
    "&CDP-8DD8;": "𠂊",
    "&CDP-88C8;": "甘",
    "&CDP-8AC0;": "㸒",
    "&CDP-8BD0;": "𠦂",
    "&CDP-8665;": "⺌",
    "&CDP-8DEF;": "尣",
    "&CDP-8BF8;": "𠦝",
    "&HD-TK-01032130;": "𥃻",
    "&MJ013489;": "曷",
    "&GT-00154;": "𠂈",
    "&GT-K01770;": "𤰔",
    "&CDP-8BE9;": "𡗗",
    "&CDP-897D;": "丰",
    "&CDP-89B6;": "丣",
    "&CDP-8D41;": "𠂎",
    "&JSP-457C;": "歰",
    "&CDP-8845;": "𡊮",
    "&CDP-8965;": "隹",
    "&CDP-8DE4;": "㇀",
    "&CDP-8974;": "丁",
    "&CDP-8C78;": "コ",
    "&CDP-89C8;": "𠃍",
    "&CDP-89D7;": "卅",
    "&CDP-88B6;": "丩",
    "&CDP-865E;": "月",
    "&GT-K00207;": "夂",
}

# 部品レベルの下位分解（漢字の構成要素として意味のある中間部品およびCHISE複合エンティティ）
COMPONENT_SUBDECOMPOSITIONS: dict[str, str] = {
    "虫": "⿱中𠃌",
    "中": "⿻口丨",
    "亼": "⿱𠆢一",
    "土": "⿱十一",
    "王": "⿱一土",
    "玉": "⿻王丶",
    "氷": "⿻水丶",
    "日": "⿴囗一",
    "目": "⿴囗二",
    "田": "⿴囗十",
    "木": "⿻十丷",
    "大": "⿻一人",
    "子": "⿻了一",
    "䒑": "⿱丷一",
    "亠": "⿱丶一",
    "&CDP-88F1;": "⿸𠂇丨",   # 在・存の左上
    "𠂇": "⿱一丿",
    "&CDP-8CA9;": "⿱左月",
    "&CDP-89AB;": "⿰丿丨",
    "&CDP-8BAE;": "⿱亠丷",
    "&CDP-8CAC;": "⿱丿彐",
    "&CDP-8B64;": "⿱𦥑冖",
    "&CDP-8CC6;": "⿰𠄌⿺乀丿",
    "&CDP-89BD;": "⿻日电",
    "&CDP-8CC8;": "⿱丿囗",
    "&CDP-8D50;": "⿰臣⿱𠂉罒",
    "&CDP-8C69;": "⿰𠂎刀",
    "&CDP-8BA8;": "⿳𦥑一八",
    "&CDP-8DAE;": "⿱㽞一",
    "&CDP-8CAF;": "⿱𠂊目",
    "&CDP-88FD;": "夂",
    "&CDP-8D76;": "⿴北口",
    "&CDP-8DBF;": "⿹𠃌灬",
    "&CDP-8D56;": "⿸广⿻コ⿰丨丨",
    "&CDP-8BB0;": "⿱从龰",
    "&CDP-8BB8;": "⿱爫冖",
    "&CDP-8BBE;": "⿳𠂉卌一",
    "&CDP-8D60;": "⿳艹罒冖",
    "&CDP-8CC9;": "⿰臣⿱𠂉丶",
    "&CDP-8C4F;": "⿰⺼又",
    "&CDP-8A65;": "⿻土丷",
    "&CDP-8BFE;": "⿻⺕亅",
    "&CDP-8CDE;": "⿻⺕⿰丨丨",
    "&CDP-8BC7;": "⿱ユ矢",
    "&GT-K06360;": "⿳⺊⺕龰",
    "&CDP-89A6;": "⿱丿丿",
    "&CDP-8DBB;": "⿱口冊",
    "&CDP-8CA3;": "⿱吅𠀎",
    "&CDP-8A6D;": "⿻口龶",
    "&CDP-8BF5;": "⿰丿丨",
    "&CDP-8CB3;": "⿵戌小",
    "&CDP-8D46;": "⿵冂𰀉",
    "&CDP-8BEC;": "⿱立冖",
    "&CDP-8CE7;": "⿱一丰",
    "&CDP-89C6;": "⿲丿二丨",
    "&CDP-8B63;": "⿴囗⿱丷一",
    "&CDP-8DBC;": "⿰氵刅",
    "&CDP-8C6A;": "⿱士示",
    "&CDP-8CB8;": "⿶弋一",
    "&CDP-8BA1;": "⿱勹又",
    "&CDP-8DB4;": "⿱臼土",
    "&CDP-8D55;": "⿱𠂉氏",
    "&CDP-8BE8;": "⿻日乚",
    "&CDP-8D65;": "⿹勹屮",
    "&CDP-8DE9;": "⿻十从",
    "&CDP-8DB3;": "⿱𠂉巾",
    "&CDP-89ED;": "⿻二巾",
    "&CDP-8A64;": "⿻丷十",
    "&GT-36324;": "⿵冂八",
    "&CDP-89E2;": "冖",
    "&GT-K02033;": "⿻了冫",
    "&CDP-89EC;": "⿻牛冂",
    "&CDP-8BC5;": "⿱一止",
    "&CDP-89BE;": "⿻白丿",
    "&CDP-8CBD;": "⿸丿𠄌",
    "&CDP-8962;": "⿺乚⺀",
    "&CDP-89B3;": "⿻ユ丨",
    "&CDP-89F5;": "⿺𠃑口",
    "&GT-K00822;": "⿱⺀乂",
    "&CDP-89F3;": "⿴夂丶",
    "&GT-K06261;": "⿵冂米",
    "&CDP-89E5;": "⿻十⺕",
    "&CDP-89C5;": "⿱串中",
    "&CDP-85A7;": "⿻又丷",
    "&CDP-8DE2;": "⿻⺕人",
    "&CDP-8AF0;": "⿻丿七",
    "&GT-36228;": "⿱爫缶",
    "&CDP-8C66;": "⿱𠂉氏",
    "&GT-K09590;": "⿱日出",
    "&CDP-8D61;": "⿻一曲",
    "&CDP-89AD;": "⿻大口",
    "&CDP-8DA8;": "⿻廿木",
    "&CDP-88F0;": "⿴𠂊⺀",
    "&GT-K03616;": "⿱𠂊旧",
    "&CDP-8A43;": "⿻二乚",
    "&CDP-89FD;": "⿻二儿",
    "&CDP-8BA5;": "⿴且一",
    "&GT-K04958;": "⿱口𧘇",
    "&GT-K07616;": "⿴囗米",
    "&GT-K01352;": "⿱一夫",
    "&GT-K00877;": "⿱⺊冖",
    "&CDP-88D2;": "⿻人冫",
    "&CDP-85A1;": "⿻二𠈌",
    "&CDP-89EF;": "⿻口一",
    "&GT-K02380;": "⿱𠂊口",
    "&GT-K07262;": "⿱⿻十吅冖",
    "&CDP-89FA;": "⿻刀二",
    "&GT-K01888;": "⿱口䒑",
    "&GT-K03318;": "⿱𠂊旧",
    "&GT-K03457;": "⿱䒑夫",
    "龍": "⿰𦚏&CDP-89B0;",
    "&CDP-89B0;": "⿱⿱一𠃑⿻乚三",
    "敢": "⿰⿱一耳攵",
}

# 筆画レベルの下位分解（これ以上意味を持たない単一筆画への展開）
STROKE_SUBDECOMPOSITIONS: dict[str, str] = {
    "𭕄": "⿲丶丶丿",  # 3画: 点・点・払
    "⺍": "⿲丶丶丿",
    "冖": "⿰丶乛",
    "口": "⿵冂一",
    "儿": "⿰丿乚",
    "八": "⿰丿乀",
    "丷": "⿰丶丿",
    "𠆢": "⿰丿乀",
    "十": "⿻一丨",
    "人": "⿰丿乀",
    "女": "⿻𡿨丿",
}

# 後方互換性および網羅的検索のための統合辞書
ATOMIC_SUBDECOMPOSITIONS: dict[str, str] = {
    **COMPONENT_SUBDECOMPOSITIONS,
    **STROKE_SUBDECOMPOSITIONS,
}


# ==============================================================================
# 3. 部首等価性および正規化マップ (CANONICAL_COMPONENT_MAP, EQUIV_GROUPS)
# ==============================================================================

CANONICAL_COMPONENT_MAP: dict[str, str] = {}
EQUIV_GROUPS: dict[str, list[str]] = {}


def load_equivalent_unified_ideographs(file_path: Path | str | None = None) -> None:
    """EquivalentUnifiedIdeograph.txt を読み込み、部首等価辞書とグループを構築する.

    - ⺍ (U+2E8D) は「小」ではなく「𭕄」(U+2D544) に明示的に対応付けます。
    - 康熙部首 (0x2F00..0x2FD5) は字形が統合漢字と同一なため canonical_map に登録します。
    - CJK部首補助 (0x2E80..0x2EFF) は視覚的部首字形（例: ⺼, ⻖ 等）を保持するため canonical_map を上書きせず、
      双方向等価グループ (EQUIV_GROUPS) のみに関連付けます。
    - 代表的な部首変形リンク（氵-水, 扌-手, ⺼-月, ⻖-阝 等）を明示的に等価グループに追加します。
    """
    global CANONICAL_COMPONENT_MAP, EQUIV_GROUPS

    if file_path is None:
        file_path = (
            Path(__file__).resolve().parent / "data" / "EquivalentUnifiedIdeograph.txt"
        )
    else:
        file_path = Path(file_path)

    canonical_map: dict[str, str] = {}
    adj: dict[str, set[str]] = defaultdict(set)

    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "#" in line:
                    line = line.split("#", 1)[0].strip()
                if ";" not in line:
                    continue
                src_part, target_part = [p.strip() for p in line.split(";", 1)]
                target_cp = int(target_part, 16)
                target_char = chr(target_cp)

                if ".." in src_part:
                    start_hex, end_hex = src_part.split("..", 1)
                    start_cp = int(start_hex, 16)
                    end_cp = int(end_hex, 16)
                    cps = range(start_cp, end_cp + 1)
                else:
                    cps = [int(src_part, 16)]

                for cp in cps:
                    if cp == 0x2E8D:
                        # ⺍ は「小」ではなく「𭕄」にマップするため除外
                        continue
                    src_char = chr(cp)
                    adj[src_char].add(target_char)
                    adj[target_char].add(src_char)

                    # 康熙部首 (0x2F00..0x2FD5) は字形が同一のため canonical_map に登録
                    # CJK部首補助 (0x2E80..0x2EFF) は視覚的字形を保持するため canonical_map には登録しない
                    if 0x2F00 <= cp <= 0x2FD5:
                        canonical_map[src_char] = target_char

    # ⺍ (U+2E8D) -> 𭕄 (U+2D544) の統合
    canonical_map["⺍"] = "𭕄"
    adj["⺍"].add("𭕄")
    adj["𭕄"].add("⺍")

    # 代表的な部首変形リンクの明示的追加
    extra_variant_links = [
        ("氵", "水"),
        ("扌", "手"),
        ("忄", "心"),
        ("亻", "人"),
        ("艹", "艸"),
        ("辶", "辵"),
        ("⻌", "辶"),
        ("⺼", "月"),
        ("⻖", "阝"),
        ("⻏", "阝"),
        ("礻", "示"),
        ("訁", "言"),
        ("釒", "金"),
        ("飠", "食"),
        ("糹", "糸"),
        ("犭", "犬"),
        ("⺍", "𭕄"),
        ("⺌", "小"),
    ]
    for a, b in extra_variant_links:
        adj[a].add(b)
        adj[b].add(a)

    for ent, uni_char in CHISE_ENTITY_UNICODE_MAP.items():
        adj[ent].add(uni_char)
        adj[uni_char].add(ent)

    # 推移的閉包（連結成分）による双方向等価グループの構築
    visited: set[str] = set()
    equiv_groups: dict[str, list[str]] = {}
    for node in list(adj.keys()):
        if node not in visited:
            component: set[str] = set()
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                component.add(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            for m in component:
                equiv_groups[m] = sorted([x for x in component if x != m])

    CANONICAL_COMPONENT_MAP = canonical_map
    EQUIV_GROUPS = equiv_groups


# モジュール読み込み時に等価辞書を初期化
load_equivalent_unified_ideographs()

# ==============================================================================
# 4. CHISE エンティティおよび部品の正規化関数
# ==============================================================================


def normalize_entity(entity: str) -> str:
    """CHISE IDS 内の XML 実体参照 (&...;) を正規化する.

    - &I-CDP-XXXX; -> &CDP-XXXX; （&I-M-, &I-J90-, &I-C1- 等も同様に正規化）
    - &o-UU+4343; -> 䍃 (U+4343) などの &o- プレフィックス除去およびUnicode Hex変換
    - &CDP-i001-8BD9; -> &CDP-8BD9; などの i001- プレフィックス除去
    - CHISE_ENTITY_UNICODE_MAP に収録された単一文字対応エンティティの直接変換
    - &U-i001+2FF1; などの 2FF0..2FFF は直接 IDC 演算子文字に変換
    """
    if not (entity.startswith("&") and entity.endswith(";")):
        return entity

    # 1. &o- プレフィックスの除去 (&o-UU+4343; -> &UU+4343;)
    if entity.startswith("&o-"):
        entity = "&" + entity[3:]

    # 2. &I- プレフィックスの正規化 (&I-CDP-XXXX; -> &CDP-XXXX; 等)
    if entity.startswith("&I-"):
        entity = "&" + entity[3:]

    # 3. i001- 等の異体字プレフィックス除去 (&CDP-i001-8BD9; -> &CDP-8BD9; 等)
    entity = re.sub(r"^&CDP-i\d+-", "&CDP-", entity)

    # 4. CHISE 単一 Unicode 文字対応マップ
    if entity in CHISE_ENTITY_UNICODE_MAP:
        return CHISE_ENTITY_UNICODE_MAP[entity]

    # 5. Unicode Hex 表記エンティティの変換
    # 例: &U-i001+2FF1;, &U-v002+5807;, &hanaJU+2E73F;, &A-compU+7530;, &A-IWDSU+7A74;, &UU+9F9C;, &U+5E7A;, &UU+4343;
    m = re.match(
        r"^&(?:U-[iv]?\d*\+|hanaJU\+|A-compU\+|A-IWDSU\+|UU\+|U\+)([0-9A-Fa-f]+);$",
        entity,
    )
    if not m:
        # 例: &U-00020006;, &U-20006;
        m = re.match(r"^&U-([0-9A-Fa-f]{4,8});$", entity)

    if m:
        try:
            codepoint = int(m.group(1), 16)
            return chr(codepoint)
        except (ValueError, OverflowError):
            pass

    return entity


def normalize_component(token: str) -> str:
    """構成要素トークンを標準代表字（カノニカル形式）へ正規化する.

    ⺍ (U+2E8D) -> 𭕄 (U+2D544)、康熙部首 -> 統合漢字など
    """
    return CANONICAL_COMPONENT_MAP.get(token, token)


def extract_region_tags(ids_str: str) -> tuple[str, list[str]]:
    """IDS 文字列の末尾に付与された地域タグ [GJKTV...] を抽出し除去する."""
    region_tags: list[str] = []
    ids_str = ids_str.strip()
    while True:
        m = re.search(r"\s*\[([A-Za-z0-9_ -]+)\]\s*$", ids_str)
        if not m:
            break
        tag_content = m.group(1).strip()
        if "," in tag_content:
            tags = [t.strip() for t in tag_content.split(",") if t.strip()]
        else:
            tags = [tag_content]
        region_tags = tags + region_tags
        ids_str = ids_str[: m.start()].strip()
    return ids_str, region_tags


# ==============================================================================
# 5. 字句解析 (Tokenization)
# ==============================================================================


class TokenList(list):
    """地域タグ属性 (region_tags) を保持可能なトークンリスト."""

    def __init__(self, iterable=(), region_tags: list[str] | None = None):
        super().__init__(iterable)
        self.region_tags: list[str] = region_tags if region_tags is not None else []


def tokenize_ids(
    ids_str: str,
    normalize: bool = True,
    return_tags: bool = False,
) -> list[str] | tuple[list[str], list[str]]:
    """IDS 文字列を IDC 演算子、&...; エンティティ、または単一 Unicode 文字へ分解する.

    末尾の [GJKTV...] 地域タグを除去し保存します。
    """
    clean_str, tags = extract_region_tags(ids_str)
    pattern = re.compile(r"&[^;\s]+;|[^\s]")
    raw_tokens = pattern.findall(clean_str)

    if normalize:
        tokens = [normalize_entity(t) for t in raw_tokens]
    else:
        tokens = raw_tokens

    result_list = TokenList(tokens, region_tags=tags)

    if return_tags:
        return result_list, tags
    return result_list


# ==============================================================================
# 6. 構文木解析 (AST Parsing)
# ==============================================================================


def parse_ids(
    ids_input: str | list[str],
    compute_bbox: bool = False,
) -> dict[str, Any]:
    """前置記法 IDS 表現を構文木（AST 辞書）に変換する.

    戻り値の AST 構造:
    - 演算子ノード: {"type": "op", "op": tok, "op_info": IDC_INFO[tok], "children": [...]}
    - 文字ノード:   {"type": "char", "char": canonical_tok, "raw_char": raw_tok}
    """
    if isinstance(ids_input, str):
        tok_list = tokenize_ids(ids_input, normalize=False)
        raw_tokens = list(tok_list)
        region_tags = getattr(tok_list, "region_tags", [])
    else:
        raw_tokens = list(ids_input)
        region_tags = getattr(ids_input, "region_tags", [])

    pos = [0]

    def parse_node() -> dict[str, Any]:
        if pos[0] >= len(raw_tokens):
            return {
                "type": "char",
                "char": "？",
                "raw_char": "？",
                "missing": True,
            }
        raw_tok = raw_tokens[pos[0]]
        pos[0] += 1

        norm_tok = normalize_entity(raw_tok)

        if norm_tok in IDC_INFO:
            op = norm_tok
            op_info = IDC_INFO[op]
            children = []
            for _ in range(op_info["arity"]):
                children.append(parse_node())
            node: dict[str, Any] = {
                "type": "op",
                "op": op,
                "op_info": op_info,
                "children": children,
            }
            if raw_tok != norm_tok:
                node["raw_op"] = raw_tok
            return node
        else:
            canonical_tok = normalize_component(norm_tok)
            return {
                "type": "char",
                "char": canonical_tok,
                "raw_char": raw_tok,
            }

    trees: list[dict[str, Any]] = []
    while pos[0] < len(raw_tokens):
        trees.append(parse_node())

    # 不正・未解析シーケンスの優雅な救済（トップレベルが複数ある場合は暗黙の「⿰」等でラップ）
    if not trees:
        root: dict[str, Any] = {"type": "char", "char": "", "raw_char": ""}
    elif len(trees) == 1:
        root = trees[0]
    elif len(trees) == 2:
        root = {
            "type": "op",
            "op": "⿰",
            "op_info": IDC_INFO["⿰"],
            "children": trees,
            "implicit": True,
        }
    elif len(trees) == 3:
        root = {
            "type": "op",
            "op": "⿲",
            "op_info": IDC_INFO["⿲"],
            "children": trees,
            "implicit": True,
        }
    else:
        curr = trees[0]
        for t in trees[1:]:
            curr = {
                "type": "op",
                "op": "⿰",
                "op_info": IDC_INFO["⿰"],
                "children": [curr, t],
                "implicit": True,
            }
        root = curr

    if region_tags:
        root["region_tags"] = region_tags

    if compute_bbox:
        compute_bboxes(root)

    return root


# ==============================================================================
# 7. 2次元空間バウンディングボックス計算 (compute_bboxes)
# ==============================================================================


# 空間配置の比率調整用部首セット
SMALL_TOP_RADICALS: set[str] = {
    "𭕄", "⺍", "⺌", "丷", "䒑", "亠"
}
TOP_RADICALS: set[str] = {
    "𰃮", "艹", "⺾", "宀", "冖", "爫", "⺤", "罒", "⺫",
    "竹", "⺮", "雨", "⻗", "穴", "𠂉", "𠆢", "亼"
}
BOTTOM_RADICALS: set[str] = {
    "𠃌", "灬", "⺣", "皿", "儿", "八", "丷", "一", "心",
    "土", "日", "巾", "貝", "石", "火", "又"
}
HEAVY_TOP_COMPONENTS: set[str] = {
    "莫", "其", "𫩠", "尚", "𡨄", "執", "辟", "敬", "敝", "敢", "般", "曼", "曽", "曾"
}
LEFT_NARROW_RADICALS: set[str] = {"氵", "亻", "忄", "彳", "犭", "礻", "衤"}
LEFT_RADICALS: set[str] = {
    "氵", "扌", "亻", "口", "木", "糸", "糹", "言", "訁", "金", "釒", "虫",
    "土", "女", "日", "月", "⺼", "火", "石", "禾", "立", "米", "舟", "車",
    "馬", "魚", "阝", "⻖", "彳", "忄", "犭", "礻", "衤", "飠", "弓", "目",
    "耳", "足", "⻊", "貝"
}
RIGHT_NARROW_RADICALS: set[str] = {
    "刂", "卩", "⻏", "阝", "彡", "戈", "斤", "欠", "殳", "页", "頁", "隹", "力", "刀"
}


def _get_enclosure_peripheral_rects(
    role_label: str,
    node_char: str,
    rounded_box: list[float],
) -> list[list[float]] | None:
    """包囲構え・垂れ・繞の外枠ノードに対して中空周辺ストリップ矩形リストを返す."""
    rx, ry, rw, rh = rounded_box
    eff_role = role_label
    if eff_role not in ("外囲", "上囲", "下囲", "左囲", "垂れ", "包み", "繞", "右囲", "右下囲"):
        if node_char in ("囗", "口"):
            eff_role = "外囲"
        elif node_char in ("冂", "几", "𠔼"):
            eff_role = "上囲"
        elif node_char == "凵":
            eff_role = "下囲"
        elif node_char in ("匚", "匸"):
            eff_role = "左囲"
        elif node_char in ("广", "厂", "疒", "尸", "戶", "戸", "虍", "𠂆"):
            eff_role = "垂れ"
        elif node_char in ("勹", "气", "⺄"):
            eff_role = "包み"
        elif node_char in ("辶", "⻌", "廴", "走", "龰"):
            eff_role = "繞"
        elif node_char in ("戈", "弋", "𢦏"):
            eff_role = "右下囲"

    if eff_role == "外囲":
        th = round(max(0.04, rh * 0.26), 4)
        tw = round(max(0.04, rw * 0.22), 4)
        return [
            [rx, ry, rw, th],
            [rx, round(ry + rh - th, 4), rw, th],
            [rx, ry, tw, rh],
            [round(rx + rw - tw, 4), ry, tw, rh],
        ]
    elif eff_role == "上囲":
        top_r = 0.38 if node_char == "𠔼" else 0.28
        th = round(max(0.04, rh * top_r), 4)
        tw = round(max(0.04, rw * 0.24), 4)
        return [
            [rx, ry, rw, th],
            [rx, ry, tw, rh],
            [round(rx + rw - tw, 4), ry, tw, rh],
        ]
    elif eff_role == "下囲":
        th = round(max(0.04, rh * 0.28), 4)
        tw = round(max(0.04, rw * 0.24), 4)
        return [
            [rx, round(ry + rh - th, 4), rw, th],
            [rx, ry, tw, rh],
            [round(rx + rw - tw, 4), ry, tw, rh],
        ]
    elif eff_role == "左囲":
        th = round(max(0.04, rh * 0.24), 4)
        tw = round(max(0.04, rw * 0.26), 4)
        return [
            [rx, ry, rw, th],
            [rx, round(ry + rh - th, 4), rw, th],
            [rx, ry, tw, rh],
        ]
    elif eff_role == "垂れ":
        th = round(max(0.04, rh * 0.32), 4)
        tw = round(max(0.04, rw * 0.32), 4)
        return [
            [rx, ry, rw, th],
            [rx, ry, tw, rh],
        ]
    elif eff_role == "包み":
        top_r = 0.40 if node_char == "气" else 0.32
        th = round(max(0.04, rh * top_r), 4)
        tw = round(max(0.04, rw * 0.35), 4)
        return [
            [rx, ry, rw, th],
            [round(rx + rw - tw, 4), ry, tw, rh],
        ]
    elif eff_role == "繞":
        if node_char == "𫠠":
            th = round(max(0.04, rh * 0.12), 4)
            tw = round(max(0.04, rw * 0.16), 4)
            return [
                [round(rx + rw * 0.05, 4), round(ry + rh * 0.22, 4), round(rw * 0.80, 4), th],
                [round(rx + rw * 0.52, 4), ry, tw, rh],
                [round(rx + rw * 0.55, 4), round(ry + rh * 0.78, 4), round(rw * 0.40, 4), round(rh * 0.22, 4)],
            ]
        left_r = 0.46 if node_char == "走" else 0.32
        th = round(max(0.04, rh * 0.32), 4)
        tw = round(max(0.04, rw * left_r), 4)
        return [
            [rx, ry, tw, rh],
            [rx, round(ry + rh - th, 4), rw, th],
        ]
    elif eff_role == "右囲":
        th = round(max(0.04, rh * 0.32), 4)
        tw = round(max(0.04, rw * 0.32), 4)
        return [
            [round(rx + rw - tw, 4), ry, tw, rh],
            [rx, round(ry + rh - th, 4), rw, th],
        ]
    elif eff_role == "右下囲":
        th = round(max(0.04, rh * 0.26), 4)
        tw = round(max(0.04, rw * 0.32), 4)
        if node_char in ("戈", "弋", "𢦏"):
            return [
                [round(rx + rw - tw, 4), ry, tw, rh],
                [rx, round(ry + rh * 0.33, 4), rw, round(rh * 0.14, 4)],
            ]
        return [
            [round(rx + rw - tw, 4), ry, tw, rh],
            [rx, round(ry + rh - th, 4), rw, th],
        ]
    return None


def compute_bboxes(
    ast_node: dict[str, Any],
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    path: str = "0",
    role_label: str = "全体",
) -> dict[str, Any]:
    """構文木内の各ノードに対して bbox、path、role_label を再帰的に算出・付与する.

    - bbox: [x, y, w, h] (小数点以下4桁四捨五入)
    - path: ノード階層パス ("0", "0.0", "0.1" など)
    - role_label: 各要素の空間役割名 ("上", "下", "左", "右", "外囲", "内側" など)
    """
    x, y, w, h = bbox
    rounded_box = [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]
    rx, ry, rw, rh = rounded_box
    ast_node["bbox"] = rounded_box
    ast_node["path"] = path
    ast_node["role_label"] = role_label

    node_char = ast_node.get("char") or ast_node.get("raw_char") or ""

    # 明朝体印刷書体に合わせたクリップ矩形（clip_rects）およびヒット領域（hit_rects）の精密設定
    if node_char == "冖" and y > 0:
        # 冠下部の冖: 上部バーと左右の垂れのみをクリップし、中央の空隙（虫の突出部）を除外
        ast_node["clip_rects"] = [
            [round(x, 4), round(y, 4), round(w, 4), round(h * 0.44, 4)],
            [round(x, 4), round(y, 4), round(w * 0.20, 4), round(h * 1.12, 4)],
            [round(x + w * 0.78, 4), round(y, 4), round(w * 0.22, 4), round(h * 1.05, 4)],
        ]
    elif node_char == "𰃮" and h < 0.6:
        # 冠全体の𰃮: 𭕄と冖を含め、虫の上部縦画先端と干渉しないよう左右垂れを含めてクリップ
        ast_node["clip_rects"] = [
            [round(x, 4), round(y, 4), round(w, 4), round(h * 0.72, 4)],
            [round(x, 4), round(y, 4), round(w * 0.20, 4), round(h * 1.06, 4)],
            [round(x + w * 0.78, 4), round(y, 4), round(w * 0.22, 4), round(h * 1.02, 4)],
        ]
    elif node_char in ("虫", "中") and 0.30 <= y <= 0.45 and w >= 0.7:
        # 冠の下にある虫または中: 冠垂れ（x < 0.20, x > 0.78, y < 0.412）と干渉しないよう除外しつつ、
        # 中央の突出縦画先端（x: 0.42..0.58, y: 0.285..0.38）を確実に捕捉
        ast_node["clip_rects"] = [
            [round(x + w * 0.42, 4), round(max(0.0, y - 0.095), 4), round(w * 0.16, 4), round(0.10, 4)],
            [round(x, 4), round(max(y, 0.412), 4), round(w, 4), round(max(0.0, y + h - max(y, 0.412)), 4)],
            [round(x + w * 0.20, 4), round(y, 4), round(w * 0.58, 4), round(max(0.0, min(y + h, 0.412) - y), 4)],
        ]
    elif node_char == "𠃌" and y >= 0.35 and role_label == "下":
        # 虫の下部𠃌: 口（y < 0.64）と重複せず、下部ハネ（y: 0.74..0.97）と右点（x: 0.65..0.94, y: 0.65..0.95）を捕捉
        ast_node["clip_rects"] = [
            [round(x, 4), round(y + h * 0.28, 4), round(w, 4), round(h * 0.72, 4)],
            [round(x + w * 0.62, 4), round(y, 4), round(w * 0.38, 4), round(h * 0.35, 4)],
        ]
    elif node_char == "𠃌" and role_label == "包み":
        # 司・句などの右上包囲外枠としての𠃌: 上部水平ストロークと右縦画・ハネを捕捉
        ast_node["clip_rects"] = [
            [round(x, 4), round(y, 4), round(w, 4), round(h * 0.28, 4)],
            [round(x + w * 0.65, 4), round(y, 4), round(w * 0.35, 4), round(h, 4)],
        ]
        ast_node["hit_rects"] = ast_node["clip_rects"]
    elif node_char == "乚":
        # 縦ハネ画: 右縦幹と下部水平ハネ
        vx = round(x + w * 0.15, 4)
        vw = round(max(0.04, w * 0.35), 4)
        hh = round(max(0.04, h * 0.22), 4)
        ast_node["clip_rects"] = [
            [round(x + w - vw, 4), y, vw, h],
            [vx, round(y + h - hh, 4), round(w * 0.85, 4), hh],
        ]
        ast_node["hit_rects"] = ast_node["clip_rects"]
    elif node_char == "一" and path != "0":
        th = round(min(rh, 0.12), 4)
        ast_node["clip_rects"] = [[rx, ry, rw, th]]
        ast_node["bbox"] = ast_node["clip_rects"][0]
        ast_node["hit_rects"] = ast_node["clip_rects"]
    elif node_char == "丶" and path != "0":
        tw = round(min(rw, 0.22), 4)
        th = round(min(rh, 0.22), 4)
        ast_node["clip_rects"] = [[rx, ry, tw, th]]
        ast_node["hit_rects"] = ast_node["clip_rects"]
    elif node_char in ("丨", "亅") and path != "0":
        max_w = 0.18 if node_char == "亅" else 0.12
        tw = round(min(rw, max_w), 4)
        ast_node["clip_rects"] = [[rx, ry, tw, rh]]
        ast_node["hit_rects"] = ast_node["clip_rects"]
    else:
        enc_rects = _get_enclosure_peripheral_rects(role_label, node_char, rounded_box)
        if enc_rects:
            ast_node["clip_rects"] = enc_rects
            if node_char != "口" or role_label == "外囲":
                ast_node["hit_rects"] = enc_rects
        else:
            ast_node["clip_rects"] = [rounded_box]

    if ast_node.get("type") == "op":
        op = ast_node.get("op", "")
        children = ast_node.get("children", [])
        parts = ast_node.get("op_info", {}).get("parts", [])
        child_boxes: list[tuple[float, float, float, float]] = []

        if len(children) == 2:
            c0 = children[0]
            c1 = children[1]
            is_flanking = (
                c0.get("op") == "⿰"
                and len(c0.get("children", [])) == 2
                and (
                    (
                        c0.get("char") in ("行", "辡", "玨", "門", "鬥", "丱", "臼", "𨙵", "犾")
                        and op in ("⿴", "⿵", "⿶", "⿻", "⿱")
                    )
                    or (
                        c0.get("char") == "林"
                        and (
                            op in ("⿴", "⿵", "⿶", "⿻")
                            or (
                                op == "⿱"
                                and (
                                    c1.get("char") in ("缶", "爻", "夕")
                                    or (c1.get("children") and c1["children"][0].get("char") in ("缶", "爻", "夕"))
                                )
                            )
                        )
                    )
                )
            )
            if is_flanking:
                c0["is_flanking"] = True
                c0["path"] = f"{path}.0"
                c0["role_label"] = "両脇"
                is_bottom_split = (
                    c1.get("op") == "⿱"
                    and len(c1.get("children", [])) == 2
                    and c1["children"][1].get("char") in ("冖", "宀", "大", "廾", "手", "石", "虫")
                )
                if is_bottom_split:
                    flank_h = round(h * 0.68, 4)
                    compute_bboxes(c0["children"][0], (x, y, round(w * 0.34, 4), flank_h), f"{path}.0.0", "左脇")
                    compute_bboxes(c0["children"][1], (round(x + w * 0.66, 4), y, round(w * 0.34, 4), flank_h), f"{path}.0.1", "右脇")
                    c0["bbox"] = [round(x, 4), round(y, 4), round(w, 4), flank_h]

                    c1["path"] = f"{path}.1"
                    c1["role_label"] = "中央・下"
                    c1["bbox"] = [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]
                    compute_bboxes(c1["children"][0], (round(x + w * 0.33, 4), y, round(w * 0.34, 4), flank_h), f"{path}.1.0", "中央")
                    compute_bboxes(c1["children"][1], (x, round(y + h * 0.66, 4), w, round(h * 0.34, 4)), f"{path}.1.1", "下")
                    c1["clip_rects"] = [c1["children"][0]["bbox"], c1["children"][1]["bbox"]]
                    c1["hit_rects"] = [c1["children"][0]["bbox"], c1["children"][1]["bbox"]]
                else:
                    compute_bboxes(c0["children"][0], (x, y, round(w * 0.33, 4), h), f"{path}.0.0", "左脇")
                    compute_bboxes(c0["children"][1], (round(x + w * 0.67, 4), y, round(w * 0.33, 4), h), f"{path}.0.1", "右脇")
                    c0["bbox"] = [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]
                    if c0.get("char") in ("門", "鬥"):
                        c1_box = (round(x + w * 0.24, 4), round(y + h * 0.36, 4), round(w * 0.52, 4), round(h * 0.58, 4))
                    else:
                        c1_box = (round(x + w * 0.32, 4), y, round(w * 0.36, 4), h)
                    compute_bboxes(c1, c1_box, f"{path}.1", "中央")

                c0["clip_rects"] = [c0["children"][0]["bbox"], c0["children"][1]["bbox"]]
                c0["hit_rects"] = [c0["children"][0]["bbox"], c0["children"][1]["bbox"]]
                return ast_node

        if op == "⿰" and len(children) == 2:
            c0_char = children[0].get("char") or children[0].get("raw_char") or ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or ""
            if c0_char and c0_char == c1_char:
                left_ratio = 0.50
            elif c0_char in LEFT_RADICALS and c1_char in RIGHT_NARROW_RADICALS:
                left_ratio = 0.50
            elif c0_char in LEFT_NARROW_RADICALS:
                left_ratio = 0.33
            elif c0_char in LEFT_RADICALS:
                left_ratio = 0.38
            elif c1_char in RIGHT_NARROW_RADICALS:
                left_ratio = 0.64
            else:
                left_ratio = 0.50
            child_boxes = [
                (x, y, w * left_ratio, h),
                (x + w * left_ratio, y, w * (1.0 - left_ratio), h),
            ]
        elif op == "⿱" and len(children) == 2:
            c0_char = children[0].get("char") or children[0].get("raw_char") or ""
            c0_op = children[0].get("op", "")
            c1_char = children[1].get("char") or children[1].get("raw_char") or ""
            if role_label == "繞" and node_char == "走":
                # 走（⿺走...）内部の土（左上）と龰（下繞）
                child_boxes = [
                    (x, y, w * 0.48, h * 0.50),
                    (x, y + h * 0.48, w, h * 0.52),
                ]
            elif c0_char == "一":
                # 王（⿱一土）・天（⿱一大）・百（⿱一白）・更など: 上部横一画
                # 二（⿱一一）は均等2分割、三（⿱一𠄞）は均等3分割
                if c1_char == "一":
                    top_ratio = 0.50
                elif c1_char in ("𠄞", "二"):
                    top_ratio = 0.3333
                elif c1_char in ("丨", "亅"):
                    top_ratio = 0.13
                else:
                    top_ratio = 0.13

                if c1_char in ("丨", "亅"):
                    c1_w = round(min(w, 0.12), 4)
                    child_boxes = [
                        (x, y, w, round(h * top_ratio, 4)),
                        (round(x + (w - c1_w) / 2.0, 4), round(y + h * top_ratio, 4), c1_w, round(h * (1.0 - top_ratio), 4)),
                    ]
                else:
                    child_boxes = [
                        (x, y, w, round(h * top_ratio, 4)),
                        (x, round(y + h * top_ratio, 4), w, round(h * (1.0 - top_ratio), 4)),
                    ]
            elif c1_char in ("丨", "亅"):
                # 丁（⿱一亅）・干（⿱二丨）など: 下部中央縦画
                top_ratio = 0.20 if c0_char in ("一", "二") else 0.40
                c1_w = round(min(w, 0.12), 4)
                child_boxes = [
                    (x, y, w, h * top_ratio),
                    (round(x + (w - c1_w) / 2.0, 4), round(y + h * top_ratio, 4), c1_w, round(h * (1.0 - top_ratio), 4)),
                ]
            elif c0_char in SMALL_TOP_RADICALS:
                if c1_char == "冖":
                    # 𰃮（⿱⺍冖）など冠内部で冖の上に載る3点
                    top_ratio = 0.38 if path == "0" else 0.50
                elif c1_char == "一":
                    # 光の上部（⿱⺌一）や亠（⿱丶一）・䒑（⿱丷一）など下線が横一画のみの場合
                    top_ratio = 0.82
                elif path == "0" or role_label == "垂れ" or c1_char in ("厂", "广", "疒", "尸", "戶", "戸"):
                    # 巣（⿱𭕄果）・単（⿱𭕄甲）・当（⿱⺌彐）・尚（⿱⺌冋）・厳の垂れ（⿱𭕄厂）
                    top_ratio = 0.22
                else:
                    top_ratio = 0.35
                child_boxes = [
                    (x, y, w, h * top_ratio),
                    (x, y + h * top_ratio, w, h * (1.0 - top_ratio)),
                ]
            elif c0_char in TOP_RADICALS or c0_op == "⿲":
                if path == "0":
                    # ルートレベルのかんむり（例: 蛍 = ⿱𰃮虫）
                    top_ratio = 0.38
                else:
                    # 入子のかんむり
                    top_ratio = 0.50
                child_boxes = [
                    (x, y, w, h * top_ratio),
                    (x, y + h * top_ratio, w, h * (1.0 - top_ratio)),
                ]
            elif c1_char in BOTTOM_RADICALS:
                # あし部首（例: 虫 = ⿱中𠃌, 墓 = ⿱莫土, 幕 = ⿱莫巾, 暮 = ⿱莫日）
                if c0_char and c0_char == c1_char:
                    top_ratio = 0.50
                elif c1_char == "一":
                    top_ratio = 0.72
                elif (
                    (
                        children[0].get("type") == "op"
                        and children[0].get("op") != "⿻"
                        and not children[0].get("is_atomic_fallback")
                        and c0_char not in COMPONENT_SUBDECOMPOSITIONS
                    )
                    or c0_char in HEAVY_TOP_COMPONENTS
                ):
                    top_ratio = 0.65
                else:
                    top_ratio = 0.58
                c0_box = (x, y, w, h * top_ratio)
                if c1_char == "𠃌":
                    c1_box = (x + w * 0.06, y + h * 0.44, w * 0.88, h * 0.52)
                else:
                    c1_box = (x, y + h * top_ratio, w, h * (1.0 - top_ratio))
                child_boxes = [c0_box, c1_box]
            else:
                top_ratio = 0.50
                child_boxes = [
                    (x, y, w, h * top_ratio),
                    (x, y + h * top_ratio, w, h * (1.0 - top_ratio)),
                ]
        elif op == "⿲":
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if c1_char in ("丨", "亅"):
                mw = round(min(w / 3.0, 0.12), 4)
                side_w = round((w - mw) / 2.0, 4)
                child_boxes = [
                    (x, y, side_w, h),
                    (round(x + side_w, 4), y, mw, h),
                    (round(x + side_w + mw, 4), y, side_w, h),
                ]
            else:
                child_boxes = [(x + i * w / 3.0, y, w / 3.0, h) for i in range(3)]
        elif op == "⿳":
            child_boxes = [(x, y + i * h / 3.0, w, h / 3.0) for i in range(3)]
        elif op == "⿴":
            c0_char = children[0].get("char") or children[0].get("raw_char") or "" if len(children) > 0 else ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if c0_char in ("囗", "口") and c1_char == "一":
                # 日（⿴囗一）: 内部中央の横画
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.15, 4), round(y + h * 0.38, 4), round(w * 0.70, 4), round(h * 0.24, 4)),
                ]
            elif c0_char in ("囗", "口") and c1_char == "二":
                # 目（⿴囗二）: 内部中央の二本横画
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.15, 4), round(y + h * 0.24, 4), round(w * 0.70, 4), round(h * 0.52, 4)),
                ]
            elif c0_char == "㗊" or (children[0].get("children") and any(k.get("char") in ("吅", "㗊") for k in children[0].get("children", []))):
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.15, 4), round(y + h * 0.20, 4), round(w * 0.70, 4), round(h * 0.75, 4)),
                ]
            else:
                child_boxes = [
                    (x, y, w, h),
                    (x + w * 0.2, y + h * 0.2, w * 0.6, h * 0.6),
                ]
        elif op == "⿵":
            c0_char = children[0].get("char") or children[0].get("raw_char") or "" if len(children) > 0 else ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if c1_char == "一" and c0_char == "冂":
                # 𠔼（⿵冂一）: 内部上方の横画
                child_boxes = [
                    (x, y, w, h),
                    (x + w * 0.20, y + h * 0.20, w * 0.60, h * 0.20),
                ]
            elif c0_char == "𠔼":
                # 同（⿵𠔼口）など: 𠔼の横画の下に収まる内側要素
                child_boxes = [
                    (x, y, w, h),
                    (x + w * 0.20, y + h * 0.38, w * 0.60, h * 0.52),
                ]
            elif c1_char == "丶":
                # 太（⿵大丶）など: 大の下部中央の点
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.38, 4), round(y + h * 0.60, 4), round(w * 0.24, 4), round(h * 0.20, 4)),
                ]
            else:
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.24, 4), round(y + h * 0.28, 4), round(w * 0.52, 4), round(h * 0.70, 4)),
                ]
        elif op == "⿶":
            child_boxes = [
                (x, y, w, h),
                (round(x + w * 0.24, 4), round(y + h * 0.04, 4), round(w * 0.52, 4), round(h * 0.68, 4)),
            ]
        elif op == "⿷":
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if c1_char == "丶":
                # 玉（⿷王丶）: 王の右下の点
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.65, 4), round(y + h * 0.60, 4), round(w * 0.22, 4), round(h * 0.22, 4)),
                ]
            else:
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.26, 4), round(y + h * 0.24, 4), round(w * 0.70, 4), round(h * 0.52, 4)),
                ]
        elif op == "⿸":
            child_boxes = [
                (x, y, w, h),
                (x + w * 0.26, y + h * 0.26, w * 0.72, h * 0.72),
            ]
        elif op == "⿹":
            c0_char = children[0].get("char") or children[0].get("raw_char") or "" if len(children) > 0 else ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if c0_char == "刀" and c1_char in ("丿", "丶"):
                # 刃（⿹刀丿）: 刀の内部左寄りの点・短画
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.25, 4), round(y + h * 0.40, 4), round(w * 0.22, 4), round(h * 0.22, 4)),
                ]
            else:
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.04, 4), round(y + h * 0.26, 4), round(w * 0.70, 4), round(h * 0.70, 4)),
                ]
        elif op == "⿺":
            c0_char = children[0].get("char") or children[0].get("raw_char") or "" if len(children) > 0 else ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if c1_char == "丶":
                # 弋（⿺𫠠丶）: 右上の点
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.65, 4), round(y + h * 0.04, 4), round(w * 0.22, 4), round(h * 0.22, 4)),
                ]
            elif c0_char == "乀" and c1_char == "丿":
                # 水の右部（⿺乀丿）: 下部ハライの乀と上部ハライの丿
                child_boxes = [
                    (x, round(y + h * 0.38, 4), w, round(h * 0.62, 4)),
                    (round(x + w * 0.05, 4), round(y + h * 0.20, 4), round(w * 0.90, 4), round(h * 0.35, 4)),
                ]
            else:
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.26, 4), round(y + h * 0.04, 4), round(w * 0.70, 4), round(h * 0.70, 4)),
                ]
        elif op == "⿼":
            child_boxes = [
                (x, y, w, h),
                (round(x + w * 0.04, 4), round(y + h * 0.16, 4), round(w * 0.72, 4), round(h * 0.68, 4)),
            ]
        elif op == "⿽":
            c0_char = children[0].get("char") or children[0].get("raw_char") or "" if len(children) > 0 else ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if c0_char in ("戈", "弋", "𢦏") and c1_char in ("十", "口"):
                # 𢦏（⿽戈十）や哉（⿽戈口）: 戈の左上空間に収まる十/口
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.05, 4), round(y + h * 0.05, 4), round(w * 0.45, 4), round(h * 0.35, 4)),
                ]
            else:
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.04, 4), round(y + h * 0.04, 4), round(w * 0.70, 4), round(h * 0.70, 4)),
                ]
        elif op == "⿻":
            c0_char = children[0].get("char") or children[0].get("raw_char") or "" if len(children) > 0 else ""
            c1_char = children[1].get("char") or children[1].get("raw_char") or "" if len(children) > 1 else ""
            if len(children) == 2 and c0_char == "弋" and c1_char == "丿":
                # 戈（⿻弋丿）: 弋の骨格に下部払いの丿が交差
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.08, 4), round(y + h * 0.38, 4), round(w * 0.55, 4), round(h * 0.55, 4)),
                ]
            elif len(children) == 2 and c0_char == "一" and c1_char == "乚":
                # 𫠠（⿻一乚）: 上部横画の一と縦ハネの乚
                child_boxes = [
                    (round(x + w * 0.05, 4), round(y + h * 0.22, 4), round(w * 0.80, 4), round(h * 0.12, 4)),
                    (round(x + w * 0.55, 4), y, round(w * 0.42, 4), h),
                ]
            elif len(children) == 2 and (c1_char == "丶" or c0_char == "丶"):
                # アクセント点画部品（丸: ⿻九丶, 斥: ⿻斤丶, 氷: ⿻水丶, 豖: ⿻豕丶 など）
                base_char = c0_char if c1_char == "丶" else c1_char
                if base_char == "王":
                    dot_box = (round(x + w * 0.65, 4), round(y + h * 0.58, 4), round(w * 0.20, 4), round(h * 0.20, 4))
                elif base_char == "九":
                    dot_box = (round(x + w * 0.28, 4), round(y + h * 0.48, 4), round(w * 0.22, 4), round(h * 0.22, 4))
                elif base_char == "刀":
                    dot_box = (round(x + w * 0.25, 4), round(y + h * 0.38, 4), round(w * 0.22, 4), round(h * 0.22, 4))
                elif base_char == "斤":
                    dot_box = (round(x + w * 0.42, 4), round(y + h * 0.52, 4), round(w * 0.24, 4), round(h * 0.20, 4))
                elif base_char == "水":
                    dot_box = (round(x + w * 0.12, 4), round(y + h * 0.15, 4), round(w * 0.22, 4), round(h * 0.22, 4))
                elif base_char == "豕":
                    dot_box = (round(x + w * 0.65, 4), round(y + h * 0.15, 4), round(w * 0.22, 4), round(h * 0.22, 4))
                elif base_char in ("大", "夫"):
                    dot_box = (round(x + w * 0.65, 4), round(y + h * 0.12, 4), round(w * 0.22, 4), round(h * 0.20, 4))
                else:
                    dot_box = (round(x + w * 0.52, 4), round(y + h * 0.35, 4), round(w * 0.22, 4), round(h * 0.20, 4))

                if c1_char == "丶":
                    child_boxes = [(x, y, w, h), dot_box]
                else:
                    child_boxes = [dot_box, (x, y, w, h)]
            elif len(children) == 2 and (c1_char in ("丨", "亅") or c0_char in ("丨", "亅")):
                if c1_char in ("丨", "亅"):
                    child_boxes = [
                        (x + w * 0.16, y + h * 0.03, w * 0.68, h * 0.66),
                        (x + w * 0.44, max(0.0, y - h * 0.25), w * 0.12, h * 1.45),
                    ]
                else:
                    child_boxes = [
                        (x + w * 0.44, max(0.0, y - h * 0.25), w * 0.12, h * 1.45),
                        (x + w * 0.16, y + h * 0.03, w * 0.68, h * 0.66),
                    ]
            elif len(children) == 2 and (c0_char == "一" or c1_char == "一"):
                if c0_char == "一":
                    child_boxes = [
                        (x, y + h * 0.40, w, h * 0.22),
                        (x, y, w, h),
                    ]
                else:
                    child_boxes = [
                        (x, y, w, h),
                        (x, y + h * 0.40, w, h * 0.22),
                    ]
            elif len(children) == 2 and (
                (c0_char in ("日", "白", "目", "廿") and c1_char in ("木", "电", "乂", "人", "儿", "乚", "十", "申", "大"))
                or (c0_char == "口" and c1_char in ("丄", "龶", "儿", "𠀁"))
                or (c0_char in ("羊", "冖") and (c1_char in ("隹", "誩") or not c1_char))
                or (c0_char in ("土", "⺕") and c1_char in ("丷", "人"))
                or (c0_char in ("二", "卝") and c1_char in ("儿", "乚", "巾", "𠈌", "𰀁"))
            ):
                # 上下貫通・重畳構造（果: ⿻日木, 更: ⿻日乂, 電: ⿻日乚, 善: ⿻羊⿱, 甴: ⿻口丄 など）
                child_boxes = [
                    (round(x + w * 0.14, 4), round(y, 4), round(w * 0.72, 4), round(h * 0.46, 4)),
                    (round(x, 4), round(y + h * 0.36, 4), round(w, 4), round(h * 0.64, 4)),
                ]
            elif len(children) == 2 and c0_char == "二" and c1_char == "人":
                # 夫（⿻二人）: 二が上部横二本、人が中央縦＋左右払い
                child_boxes = [
                    (round(x + w * 0.10, 4), y, round(w * 0.80, 4), round(h * 0.44, 4)),
                    (x, y, w, h),
                ]
            elif len(children) == 2 and c0_char == "𠃍" and c1_char == "大":
                # 夬（⿻𠃍大）: 大が主骨格全体、𠃍が右上カギ画
                child_boxes = [
                    (round(x + w * 0.35, 4), y, round(w * 0.60, 4), round(h * 0.45, 4)),
                    (x, y, w, h),
                ]
            elif len(children) == 2 and (
                c0_char in ("十", "木", "大", "干", "夫")
                and c1_char in ("丷", "从", "𠓜", "皕", "弓", "人")
            ):
                # 骨格＋下部・脇部展開（木: ⿻十丷, 平: ⿻干丷, 來: ⿻木从, 夾: ⿻大从 など）
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.05, 4), round(y + h * 0.38, 4), round(w * 0.90, 4), round(h * 0.60, 4)),
                ]
            elif len(children) == 2 and c0_char in ("冂", "勹"):
                # 門構え・包み風の重畳（内: ⿻冂人, 包: ⿻勹巳, 匁: ⿻勹乂 など）
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.20, 4), round(y + h * 0.20, 4), round(w * 0.60, 4), round(h * 0.65, 4)),
                ]
            elif len(children) == 2 and c0_char in ("戈", "弋", "𢦏") and c1_char in ("二", "一", "十", "口"):
                # 㦮（⿻戈二）や哉（⿻戈口）など: 戈の左上空間に収まる横画/二/口
                child_boxes = [
                    (x, y, w, h),
                    (round(x + w * 0.08, 4), round(y + h * 0.12, 4), round(w * 0.50, 4), round(h * 0.28, 4)),
                ]
            else:
                child_boxes = [
                    (x, y, w, h),
                    (x + w * 0.12, y + h * 0.12, w * 0.76, h * 0.76),
                ]
        elif op in ("⿾", "⿿"):
            child_boxes = [
                (x, y, w, h),
            ]
        else:
            n = max(len(children), 1)
            child_boxes = [(x + i * w / n, y, w / n, h) for i in range(n)]

        for i, child in enumerate(children):
            c_box = child_boxes[i] if i < len(child_boxes) else (x, y, w, h)
            c_label = parts[i] if i < len(parts) else f"要素{i+1}"
            c_path = f"{path}.{i}"
            compute_bboxes(child, bbox=c_box, path=c_path, role_label=c_label)

        if op in ("⿴", "⿵", "⿶", "⿷", "⿸", "⿹", "⿺", "⿼", "⿽") and len(children) == 2:
            c0 = children[0]
            c1 = children[1]
            c0_char = c0.get("char") or c0.get("raw_char") or ""
            c1_char = c1.get("char") or c1.get("raw_char") or ""
            if not c0.get("children"):
                enc_rects = _get_enclosure_peripheral_rects(c0.get("role_label", ""), c0_char, c0["bbox"])
                if enc_rects:
                    if not c0.get("hit_rects"):
                        c0["hit_rects"] = enc_rects
                    if c1_char == "丶" and c0.get("children"):
                        # 玉（⿷王丶）など本体＋点の構造では、王の中央筆画がクリップで欠けないよう clip_rects は全領域を維持
                        c0["clip_rects"] = [c0["bbox"]]
                    elif len(c0.get("clip_rects", [])) <= 1:
                        c0["clip_rects"] = enc_rects
            elif c0_char == "㗊" or (c0.get("children") and any(k.get("char") in ("吅", "㗊") for k in c0.get("children", []))):
                c1_corridors = [
                    [round(x, 4), round(y, 4), round(w, 4), round(h * 0.55, 4)],
                    [round(x + w * 0.46, 4), round(y, 4), round(w * 0.54, 4), round(h, 4)],
                ]
                c1["clip_rects"] = c1_corridors
                c1["hit_rects"] = c1_corridors
                c0_corners = [
                    [round(x, 4), round(y, 4), round(w * 0.46, 4), round(h * 0.40, 4)],
                    [round(x + w * 0.54, 4), round(y, 4), round(w * 0.46, 4), round(h * 0.40, 4)],
                    [round(x, 4), round(y + h * 0.55, 4), round(w * 0.46, 4), round(h * 0.45, 4)],
                    [round(x + w * 0.53, 4), round(y + h * 0.55, 4), round(w * 0.35, 4), round(h * 0.40, 4)],
                ]
                c0["clip_rects"] = c0_corners
                c0["hit_rects"] = c0_corners

    return ast_node


# ==============================================================================
# 8. CHISE / CJKVI IDS 辞書の遅延読み込みと文字分解
# ==============================================================================

_GLOBAL_IDS_DICT: dict[str, str] | None = None


def load_ids_dict(
    chise_dir: Path | str | None = None,
    cjkvi_path: Path | str | None = None,
) -> dict[str, str]:
    """CHISE IDS ファイル群および CJKVI IDS から文字→IDSの対応辞書を読み込む."""
    global _GLOBAL_IDS_DICT

    base_dir = Path(__file__).resolve().parent / "data"
    if chise_dir is None:
        chise_dir = base_dir / "chise-ids"
    else:
        chise_dir = Path(chise_dir)

    if cjkvi_path is None:
        cjkvi_path = base_dir / "cjkvi-ids.txt"
    else:
        cjkvi_path = Path(cjkvi_path)

    ids_dict: dict[str, str] = {}

    # 1. CHISE IDS ファイル群の読み込み（IDS-UCS-*.txt, IDS-JIS-*.txt を優先）
    if chise_dir.exists():
        ucs_files = sorted(glob.glob(str(chise_dir / "IDS-UCS-*.txt")))
        jis_files = sorted(glob.glob(str(chise_dir / "IDS-JIS-*.txt")))
        other_files = [p for p in glob.glob(str(chise_dir / "IDS-*.txt")) if p not in ucs_files and p not in jis_files]
        for path in ucs_files + jis_files + other_files:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith(";;") or not line.strip():
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 3:
                        raw_char = parts[1].strip()
                        char_tok = normalize_entity(raw_char)
                        alt_key = f"&{parts[0].strip()};"
                        ids_val = parts[2].split("\t")[0].strip()
                        if ids_val and ids_val != raw_char and ids_val != alt_key:
                            if char_tok not in ids_dict:
                                ids_dict[char_tok] = ids_val
                            if alt_key not in ids_dict:
                                ids_dict[alt_key] = ids_val

    # 2. CJKVI-IDS による補完（丸数字 \u2460-\u2473 を含む未符号化枝を除外）
    if cjkvi_path.exists():
        with open(cjkvi_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 3:
                    raw_char = parts[1].strip()
                    char_tok = normalize_entity(raw_char)
                    ids_val = parts[2].split("\t")[0].strip()
                    if re.search(r"[\u2460-\u2473]", ids_val):
                        branches = [b.strip() for b in re.split(r"[|\t]", ids_val) if b.strip()]
                        valid = [b for b in branches if not re.search(r"[\u2460-\u2473]", b)]
                        if valid:
                            ids_val = valid[0]
                        else:
                            continue
                    if ids_val and ids_val != raw_char:
                        if char_tok not in ids_dict or re.search(r"[\u2460-\u2473]", ids_dict.get(char_tok, "")):
                            ids_dict[char_tok] = ids_val

    # 3. COMPONENT_SUBDECOMPOSITIONS（特にCHISE複合エンティティや主要文字）の辞書への統合
    for k, v in COMPONENT_SUBDECOMPOSITIONS.items():
        ids_dict[k] = v
        norm_k = normalize_entity(k)
        if norm_k != k:
            ids_dict[norm_k] = v

    _GLOBAL_IDS_DICT = ids_dict
    return ids_dict


def get_ids_dict() -> dict[str, str]:
    """キャッシュされた IDS 辞書を取得する（未ロードの場合はロード）."""
    global _GLOBAL_IDS_DICT
    if _GLOBAL_IDS_DICT is None:
        _GLOBAL_IDS_DICT = load_ids_dict()
    return _GLOBAL_IDS_DICT


def get_character_ids(
    char: str,
    ids_dict: dict[str, str] | None = None,
) -> str | None:
    """指定した文字の IDS 文字列を検索する."""
    d = ids_dict if ids_dict is not None else get_ids_dict()
    # 文字そのもの、または正規化文字で検索
    if char in d:
        return d[char]
    norm = normalize_component(char)
    if norm in d:
        return d[norm]
    return None


# ==============================================================================
# 9. 再帰的木展開 (expand_tree, decompose_character)
# ==============================================================================


def expand_tree(
    ast_node: dict[str, Any],
    ids_dict: dict[str, str] | None = None,
    max_depth: int = 10,
    use_atomic: bool = True,
    expand_strokes: bool = False,
    _ancestors: set[str] | None = None,
) -> dict[str, Any]:
    """構文木内の文字ノードをさらに下位構造へ再帰的に展開する.

    - ids_dict: 漢字辞書（未指定時は CHISE IDS データベースを使用）
    - max_depth: 最大展開深度
    - use_atomic: True の場合、CHISE で原子要素となる基本漢字・部首を下位分解定義で展開
    - expand_strokes: False の場合、COMPONENT_SUBDECOMPOSITIONS の部品単位で展開を停止し、
      STROKE_SUBDECOMPOSITIONS による筆画レベルへの展開は行わない。True の場合、筆画レベルまで展開。
    """
    if max_depth <= 0:
        return ast_node

    if _ancestors is None:
        _ancestors = set()

    node_type = ast_node.get("type")

    if node_type == "op":
        ast_node["children"] = [
            expand_tree(
                c,
                ids_dict=ids_dict,
                max_depth=max_depth,
                use_atomic=use_atomic,
                expand_strokes=expand_strokes,
                _ancestors=set(_ancestors),
            )
            for c in ast_node.get("children", [])
        ]
        return ast_node

    elif node_type == "char":
        ch = ast_node.get("char", "")
        raw = ast_node.get("raw_char", "")
        candidates = [c for c in (ch, raw) if c]

        # 循環参照の防止
        if any(c in _ancestors for c in candidates):
            return ast_node

        sub_ids: str | None = None
        is_atomic = False

        # 1. IDS 辞書での検索
        for c in candidates:
            found = get_character_ids(c, ids_dict=ids_dict)
            if found and found not in candidates:
                sub_ids = found
                break

        # 2. 辞書にない場合、または原子要素の場合に COMPONENT_SUBDECOMPOSITIONS / STROKE_SUBDECOMPOSITIONS を確認
        if not sub_ids and use_atomic:
            for c in candidates:
                if c in COMPONENT_SUBDECOMPOSITIONS:
                    sub_ids = COMPONENT_SUBDECOMPOSITIONS[c]
                    is_atomic = True
                    break
                elif expand_strokes and c in STROKE_SUBDECOMPOSITIONS:
                    sub_ids = STROKE_SUBDECOMPOSITIONS[c]
                    is_atomic = True
                    break

        # 展開対象の IDS が存在する場合、サブツリーをパースして再帰展開
        if sub_ids and sub_ids not in candidates:
            sub_ast = parse_ids(sub_ids)
            sub_ast["char"] = ch
            sub_ast["raw_char"] = raw
            if is_atomic:
                sub_ast["is_atomic_fallback"] = True
            next_ancestors = set(_ancestors) | set(candidates)
            sub_ast = expand_tree(
                sub_ast,
                ids_dict=ids_dict,
                max_depth=max_depth - 1,
                use_atomic=use_atomic,
                expand_strokes=expand_strokes,
                _ancestors=next_ancestors,
            )
            return sub_ast

    return ast_node


def decompose_character(
    char_or_ids: str,
    ids_dict: dict[str, str] | None = None,
    max_depth: int = 10,
    use_atomic: bool = True,
    expand_strokes: bool = False,
    compute_bbox: bool = True,
) -> dict[str, Any]:
    """文字または IDS 文字列を受け取り、指定深度まで再帰展開した構文木を返す便利関数."""
    clean_input, region_tags = extract_region_tags(char_or_ids)
    is_single = len(clean_input) == 1 or (
        clean_input.startswith("&") and clean_input.endswith(";")
    )

    canonical_char: str | None = None
    raw_char: str | None = None
    is_atomic = False

    if is_single:
        norm_ent = normalize_entity(clean_input)
        canonical_char = normalize_component(norm_ent)
        raw_char = char_or_ids
        ids_str = get_character_ids(canonical_char, ids_dict=ids_dict)
        if not ids_str:
            ids_str = get_character_ids(clean_input, ids_dict=ids_dict)
        if not ids_str or ids_str in (canonical_char, clean_input):
            if use_atomic and (
                canonical_char in COMPONENT_SUBDECOMPOSITIONS
                or clean_input in COMPONENT_SUBDECOMPOSITIONS
                or canonical_char in ("𭕄", "⺍")
                or clean_input in ("𭕄", "⺍")
            ):
                ids_str = (
                    COMPONENT_SUBDECOMPOSITIONS.get(canonical_char)
                    or COMPONENT_SUBDECOMPOSITIONS.get(clean_input)
                    or STROKE_SUBDECOMPOSITIONS.get(canonical_char)
                    or STROKE_SUBDECOMPOSITIONS.get(clean_input)
                )
                is_atomic = True
            elif expand_strokes and (
                canonical_char in STROKE_SUBDECOMPOSITIONS
                or clean_input in STROKE_SUBDECOMPOSITIONS
            ):
                ids_str = (
                    STROKE_SUBDECOMPOSITIONS.get(canonical_char)
                    or STROKE_SUBDECOMPOSITIONS.get(clean_input)
                )
                is_atomic = True
            else:
                ids_str = clean_input
    else:
        ids_str = char_or_ids

    ast = parse_ids(ids_str)
    if is_single:
        ast["char"] = canonical_char
        ast["raw_char"] = raw_char
        if is_atomic:
            ast["is_atomic_fallback"] = True

    if max_depth > 0:
        ast = expand_tree(
            ast,
            ids_dict=ids_dict,
            max_depth=max_depth - 1,
            use_atomic=use_atomic,
            expand_strokes=expand_strokes,
        )

    if compute_bbox:
        compute_bboxes(ast)

    return ast


# ==============================================================================
# 10. テキスト表示用フォーマッタ
# ==============================================================================


def format_tree_text(ast_node: dict[str, Any], indent: int = 0) -> str:
    """構文木を読みやすい日本語ツリー形式のテキストに整形する."""
    prefix = "  " * indent
    lines: list[str] = []

    node_type = ast_node.get("type")
    path = ast_node.get("path", "")
    role = ast_node.get("role_label", "")
    bbox = ast_node.get("bbox", [])

    if node_type == "op":
        op = ast_node.get("op", "")
        name = ast_node.get("op_info", {}).get("name", "")
        if "char" in ast_node and ast_node["char"]:
            ch = ast_node["char"]
            raw = ast_node.get("raw_char", ch)
            char_desc = f"{ch}" if ch == raw else f"{ch} (原表記: {raw})"
            lines.append(
                f"{prefix}[構成字・演算子] {char_desc} [{op} {name}] | パス: {path} | 役割: {role} | 領域: {bbox}"
            )
        else:
            lines.append(
                f"{prefix}[演算子] {op} ({name}) | パス: {path} | 役割: {role} | 領域: {bbox}"
            )
        for child in ast_node.get("children", []):
            lines.append(format_tree_text(child, indent + 1))
    else:
        ch = ast_node.get("char", "")
        raw = ast_node.get("raw_char", "")
        char_desc = f"{ch}" if ch == raw else f"{ch} (原表記: {raw})"
        lines.append(
            f"{prefix}[構成字] {char_desc} | パス: {path} | 役割: {role} | 領域: {bbox}"
        )

    return "\n".join(lines)


# ==============================================================================
# 11. 単体テストおよび動作検証実行 (CLI)
# ==============================================================================


def main() -> None:
    """モジュール検証テストを実行する."""
    print("=" * 70)
    print("IDS パーサー（ids_parser.py）検証テスト")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # テスト 1: 全 16 種の IDC 演算子の登録確認
    # --------------------------------------------------------------------------
    print("\n【テスト 1】全 16 種の IDC 演算子メタデータの確認")
    expected_idcs = [
        "⿰",
        "⿱",
        "⿲",
        "⿳",
        "⿴",
        "⿵",
        "⿶",
        "⿷",
        "⿸",
        "⿹",
        "⿺",
        "⿻",
        "⿼",
        "⿽",
        "⿾",
        "⿿",
    ]
    assert len(IDC_INFO) == 16, f"IDC演算子数が不足しています: {len(IDC_INFO)}"
    for idc in expected_idcs:
        assert idc in IDC_INFO, f"演算子 {idc} が未登録です"
        info = IDC_INFO[idc]
        assert "arity" in info and "name" in info and "parts" in info
        print(f"  {idc} : {info['name']} (アリティ {info['arity']}, 部品: {info['parts']})")
    print("  -> 合格: 全 16 種類の IDC 演算子が正しく定義されています。")

    # --------------------------------------------------------------------------
    # テスト 2: CHISE エンティティ正規化
    # --------------------------------------------------------------------------
    print("\n【テスト 2】CHISE 実体参照エンティティの正規化")
    entity_tests = [
        ("&U-i001+2FF1;", "⿱"),
        ("&U-i001+2FFB;", "⿻"),
        ("&U-i001+5E7A;", "幺"),
        ("&I-CDP-89B2;", "&CDP-89B2;"),
        ("&I-M-02329;", "&M-02329;"),
        ("&I-J90-3021;", "&J90-3021;"),
        ("&I-C1-2462;", "&C1-2462;"),
        ("&hanaJU+2E73F;", "𮜿"),
        ("&A-compU+7530;", "田"),
        ("&A-IWDSU+7A74;", "穴"),
    ]
    for ent, expected in entity_tests:
        res = normalize_entity(ent)
        assert res == expected, f"{ent} の正規化結果が不一致: {res} != {expected}"
        print(f"  {ent:18} -> {res}")
    print("  -> 合格: CHISE エンティティの変換が正常に動作しています。")

    # --------------------------------------------------------------------------
    # テスト 3: 部首等価性辞書と「⺍」->「𭕄」の正規化および視覚的部首の保持
    # --------------------------------------------------------------------------
    print("\n【テスト 3】部首等価性と ⺍ (U+2E8D) -> 𭕄 (U+2D544) 正規化、視覚的部首の保持")
    assert (
        CANONICAL_COMPONENT_MAP.get("⺍") == "𭕄"
    ), f"⺍ の正規化先が不正です: {CANONICAL_COMPONENT_MAP.get('⺍')}"
    assert "⺍" in EQUIV_GROUPS.get(
        "𭕄", []
    ), f"𭕄 の等価グループに ⺍ が含まれていません: {EQUIV_GROUPS.get('𭕄')}"
    assert "𭕄" in EQUIV_GROUPS.get(
        "⺍", []
    ), f"⺍ の等価グループに 𭕄 が含まれていません: {EQUIV_GROUPS.get('⺍')}"
    print(f"  normalize_component('⺍') -> '{normalize_component('⺍')}'")
    print(f"  EQUIV_GROUPS['𭕄'] -> {EQUIV_GROUPS.get('𭕄')}")
    print(f"  EQUIV_GROUPS['⺍'] -> {EQUIV_GROUPS.get('⺍')}")

    # 康熙部首の確認 (例: ⾍ -> 虫)
    assert (
        normalize_component("⾍") == "虫"
    ), f"康熙部首 ⾍ の正規化に失敗: {normalize_component('⾍')}"
    print("  normalize_component('⾍') -> '虫'")

    # CJK部首補助の視覚字形保持確認（⺼, ⻖ は canonical_map に登録されず、EQUIV_GROUPS にのみ登録）
    assert (
        CANONICAL_COMPONENT_MAP.get("⺼") is None
    ), f"⺼ は canonical_map で上書きすべきではありません: {CANONICAL_COMPONENT_MAP.get('⺼')}"
    assert (
        "肉" in EQUIV_GROUPS.get("⺼", []) and "月" in EQUIV_GROUPS.get("⺼", [])
    ), f"⺼ の等価グループに 肉/月 が含まれていません: {EQUIV_GROUPS.get('⺼')}"
    assert (
        CANONICAL_COMPONENT_MAP.get("⻖") is None
    ), f"⻖ は canonical_map で上書きすべきではありません: {CANONICAL_COMPONENT_MAP.get('⻖')}"
    assert (
        "阝" in EQUIV_GROUPS.get("⻖", [])
    ), f"⻖ の等価グループに 阝 が含まれていません: {EQUIV_GROUPS.get('⻖')}"
    assert (
        "水" in EQUIV_GROUPS.get("氵", [])
    ), f"氵 の等価グループに 水 が含まれていません: {EQUIV_GROUPS.get('氵')}"
    print(f"  EQUIV_GROUPS['⺼'] -> {EQUIV_GROUPS.get('⺼')}")
    print(f"  EQUIV_GROUPS['⻖'] -> {EQUIV_GROUPS.get('⻖')}")
    print(f"  EQUIV_GROUPS['氵'] -> {EQUIV_GROUPS.get('氵')}")
    print("  -> 合格: ⺍ と 𭕄 の統合、視覚的部首の保持、および部首変形リンクが正しく設定されています。")

    # --------------------------------------------------------------------------
    # テスト 4: 「𰃮」の構文解析 (「⿱⺍冖」 -> 正規化「𭕄」+「冖」)
    # --------------------------------------------------------------------------
    print("\n【テスト 4】「𰃮」の構文解析 (「⿱⺍冖」の正規化)")
    ast_300ee = parse_ids("⿱⺍冖", compute_bbox=True)
    assert ast_300ee["type"] == "op" and ast_300ee["op"] == "⿱"
    assert len(ast_300ee["children"]) == 2
    c0, c1 = ast_300ee["children"]
    assert (
        c0["char"] == "𭕄" and c0["raw_char"] == "⺍"
    ), f"𰃮の第1要素が不正です: {c0}"
    assert (
        c1["char"] == "冖" and c1["raw_char"] == "冖"
    ), f"𰃮の第2要素が不正です: {c1}"
    assert c0["role_label"] == "上" and c0["bbox"] == [0.0, 0.0, 1.0, 0.38]
    assert c1["role_label"] == "下" and c1["bbox"] == [0.0, 0.38, 1.0, 0.62]
    print("  解析結果構文木:")
    print(format_tree_text(ast_300ee, indent=2))
    print(
        "  -> 合格: 「𰃮」が正しく正規化され、char='𭕄' かつ raw_char='⺍' となっています。"
    )

    # --------------------------------------------------------------------------
    # テスト 5: 「蛍」の構文解析 (「⿱𰃮虫」)
    # --------------------------------------------------------------------------
    print("\n【テスト 5】「蛍」の構文解析 (「⿱𰃮虫」)")
    ast_hotaru = parse_ids("⿱𰃮虫", compute_bbox=True)
    assert ast_hotaru["type"] == "op" and ast_hotaru["op"] == "⿱"
    assert len(ast_hotaru["children"]) == 2
    hc0, hc1 = ast_hotaru["children"]
    assert hc0["char"] == "𰃮" and hc0["role_label"] == "上"
    assert hc1["char"] == "虫" and hc1["role_label"] == "下"
    print("  解析結果構文木:")
    print(format_tree_text(ast_hotaru, indent=2))
    print("  -> 合格: 「蛍」が正しく構文解析され、バウンディングボックスが付与されました。")

    # --------------------------------------------------------------------------
    # テスト 6: 再帰的木展開 (「蛍」の部品階層展開および「𭕄」の筆画展開)
    # --------------------------------------------------------------------------
    print("\n【テスト 6】再帰的木展開 (「蛍」の部品階層展開および「𭕄」の筆画展開)")

    # 6-1: 「蛍」の部品階層展開 (expand_strokes=False)
    # 𰃮 は展開されるが、末端の部品 𭕄 (0.0.0) および 冖 (0.0.1) は筆画に分解されず部品ノードとして保持される
    expanded_hotaru = decompose_character(
        "蛍",
        max_depth=4,
        use_atomic=True,
        expand_strokes=False,
        compute_bbox=True,
    )
    print("  (1) 「蛍」の再帰展開木 (expand_strokes=False):")
    print(format_tree_text(expanded_hotaru, indent=2))

    # 構造および中間ノードの char / raw_char 保持の検証
    # ルート: ⿱ (蛍全体)
    assert expanded_hotaru["type"] == "op" and expanded_hotaru["op"] == "⿱"
    assert expanded_hotaru.get("char") == "蛍", f"ノード 0 に '蛍' が保持されていません: {expanded_hotaru.get('char')}"
    top_node = expanded_hotaru["children"][0]
    # 𰃮 の展開: ⿱ (char='𰃮')
    assert top_node["type"] == "op" and top_node["op"] == "⿱"
    assert top_node.get("char") == "𰃮", f"ノード 0.0 に '𰃮' が保持されていません: {top_node.get('char')}"
    assert top_node.get("path") == "0.0"

    kammuri_node = top_node["children"][0]
    # 𭕄 は筆画展開されず部品ノード（type='char'）として保持される
    assert kammuri_node["type"] == "char", f"ノード 0.0.0 は char ノードである必要があります: {kammuri_node}"
    assert kammuri_node.get("char") == "𭕄", f"ノード 0.0.0 に '𭕄' が保持されていません: {kammuri_node.get('char')}"
    assert kammuri_node.get("raw_char") == "⺍", f"ノード 0.0.0 の原表記が '⺍' ではありません: {kammuri_node.get('raw_char')}"
    assert kammuri_node.get("path") == "0.0.0"
    assert kammuri_node.get("role_label") == "上"

    # 冖 の検証 (0.0.1)
    wa_node = top_node["children"][1]
    assert wa_node["type"] == "char" and wa_node.get("char") == "冖", f"ノード 0.0.1 に '冖' が保持されていません: {wa_node}"
    assert wa_node.get("path") == "0.0.1"

    # 虫 の展開: ⿱中𠃌 (char='虫', COMPONENT_SUBDECOMPOSITIONS により展開)
    bottom_node = expanded_hotaru["children"][1]
    assert bottom_node.get("char") == "虫", f"ノード 0.1 に '虫' が保持されていません: {bottom_node.get('char')}"
    assert bottom_node["children"][0].get("char") == "中", f"ノード 0.1.0 に '中' が保持されていません: {bottom_node['children'][0].get('char')}"

    print("\n  「蛍」ノード同定検証:")
    print(f"    ノード 0     : 字={expanded_hotaru.get('char')}, 演算子={expanded_hotaru.get('op')}")
    print(f"    ノード 0.0   : 字={top_node.get('char')}, 演算子={top_node.get('op')}")
    print(f"    ノード 0.0.0 : 字={kammuri_node.get('char')}(原表記:{kammuri_node.get('raw_char')}), 種類={kammuri_node.get('type')}, 領域={kammuri_node.get('bbox')}")
    print(f"    ノード 0.0.1 : 字={wa_node.get('char')}, 種類={wa_node.get('type')}, 領域={wa_node.get('bbox')}")
    print(f"    ノード 0.1   : 字={bottom_node.get('char')}, 演算子={bottom_node.get('op')}")
    print(f"    ノード 0.1.0 : 字={bottom_node['children'][0].get('char')}, 演算子={bottom_node['children'][0].get('op')}")

    # 6-2: 「𭕄」単体の展開 (ルートとしての筆画展開)
    expanded_tsu = decompose_character(
        "𭕄",
        max_depth=4,
        use_atomic=True,
        compute_bbox=True,
    )
    print("\n  (2) 「𭕄」単体の再帰展開木:")
    print(format_tree_text(expanded_tsu, indent=2))

    assert expanded_tsu["type"] == "op" and expanded_tsu["op"] == "⿲"
    assert expanded_tsu.get("char") == "𭕄"
    assert expanded_tsu.get("is_atomic_fallback") is True
    assert len(expanded_tsu["children"]) == 3
    s0, s1, s2 = expanded_tsu["children"]
    assert s0["char"] == "丶" and s0["role_label"] == "左" and s0["path"] == "0.0"
    assert s1["char"] == "丶" and s1["role_label"] == "中" and s1["path"] == "0.1"
    assert s2["char"] == "丿" and s2["role_label"] == "右" and s2["path"] == "0.2"
    assert s0["bbox"] == [0.0, 0.0, 0.3333, 1.0]
    assert s1["bbox"] == [0.3333, 0.0, 0.3333, 1.0]
    assert s2["bbox"] == [0.6667, 0.0, 0.3333, 1.0]

    print("\n  「𭕄」筆画ノード検証:")
    print(f"    第1画 (点): パス={s0['path']}, 役割={s0['role_label']}, 領域={s0['bbox']}")
    print(f"    第2画 (点): パス={s1['path']}, 役割={s1['role_label']}, 領域={s1['bbox']}")
    print(f"    第3画 (払): パス={s2['path']}, 役割={s2['role_label']}, 領域={s2['bbox']}")

    # 6-3: 「蛍」の完全筆画展開 (expand_strokes=True)
    expanded_hotaru_strokes = decompose_character(
        "蛍",
        max_depth=4,
        use_atomic=True,
        expand_strokes=True,
        compute_bbox=True,
    )
    top_stroke = expanded_hotaru_strokes["children"][0]["children"][0]
    assert top_stroke["type"] == "op" and top_stroke["op"] == "⿲"
    assert top_stroke.get("char") == "𭕄" and top_stroke.get("raw_char") == "⺍"
    assert len(top_stroke["children"]) == 3

    print(
        "  -> 合格: 「蛍」の部品階層保持 (𭕄, 冖) および「𭕄」単体の筆画展開 (⿲丶丶丿) を確認しました。"
    )

    print("\n" + "=" * 70)
    print("すべての検証テストに正常に合格しました。")
    print("=" * 70)


if __name__ == "__main__":
    main()
