"""日本語漢字メタデータ定義モジュール。

康熙部首一覧（214部首）、Unicodeブロック判定、学年・頻度バッジ整形、
KanjiVG筆画名（kvg:type）の日本語マッピングを提供する。
すべて標準ライブラリのみで実装され、文字列およびラベルは100%日本語である。
"""

from __future__ import annotations

import re
from typing import Any

# ==============================================================================
# 1. 康熙部首（214部首）辞書
# ==============================================================================

KANGXI_RADICALS: dict[int, dict[str, Any]] = {
    1: {"char": "一", "variants": [], "name": "一（いち）"},
    2: {"char": "丨", "variants": [], "name": "丨（ぼう・たてぼう）"},
    3: {"char": "丶", "variants": [], "name": "丶（てん・ちょぼ）"},
    4: {"char": "丿", "variants": ["乀", "乁"], "name": "丿（の・はらいぼう）"},
    5: {"char": "乙", "variants": ["乚", "乛"], "name": "乙（おつ・おつにょう・つりばり）"},
    6: {"char": "亅", "variants": [], "name": "亅（はねぼう・かぎ）"},
    7: {"char": "二", "variants": [], "name": "二（に）"},
    8: {"char": "亠", "variants": [], "name": "亠（なべぶた・けいさんかんむり）"},
    9: {"char": "人", "variants": ["亻", "𠆢"], "name": "人（ひと・にんべん・ひとやね）"},
    10: {"char": "儿", "variants": [], "name": "儿（にんにょう・ひとあし）"},
    11: {"char": "入", "variants": [], "name": "入（いる・いりがしら・いりやね）"},
    12: {"char": "八", "variants": ["丷"], "name": "八（はち・はちがしら）"},
    13: {"char": "冂", "variants": [], "name": "冂（けいがまえ・まきがまえ・どうがまえ）"},
    14: {"char": "冖", "variants": [], "name": "冖（わかんむり・べきかんむり）"},
    15: {"char": "冫", "variants": [], "name": "冫（にすい）"},
    16: {"char": "几", "variants": [], "name": "几（つくえ・つくえきにょう・かぜかんむり）"},
    17: {"char": "凵", "variants": [], "name": "凵（かんにょう・うけばこ）"},
    18: {"char": "刀", "variants": ["刂"], "name": "刀（かたな・りっとう）"},
    19: {"char": "力", "variants": [], "name": "力（ちから）"},
    20: {"char": "勹", "variants": [], "name": "勹（つつみがまえ）"},
    21: {"char": "匕", "variants": [], "name": "匕（ひ・さじ・さじのひ）"},
    22: {"char": "匚", "variants": [], "name": "匚（はこがまえ）"},
    23: {"char": "匸", "variants": [], "name": "匸（かくしがまえ）"},
    24: {"char": "十", "variants": [], "name": "十（じゅう）"},
    25: {"char": "卜", "variants": [], "name": "卜（ぼく・ぼくのと・うらない）"},
    26: {"char": "卩", "variants": ["㔾"], "name": "卩（ふしづくり・まげわりふ）"},
    27: {"char": "厂", "variants": [], "name": "厂（がんだれ）"},
    28: {"char": "厶", "variants": [], "name": "厶（む）"},
    29: {"char": "又", "variants": [], "name": "又（また）"},
    30: {"char": "口", "variants": [], "name": "口（くち・くちへん）"},
    31: {"char": "囗", "variants": [], "name": "囗（くにがまえ）"},
    32: {"char": "土", "variants": [], "name": "土（つち・つちへん）"},
    33: {"char": "士", "variants": [], "name": "士（さむらい・さむらいかんむり）"},
    34: {"char": "夂", "variants": [], "name": "夂（ふゆがしら・ちかんむり）"},
    35: {"char": "夊", "variants": [], "name": "夊（すいにょう・なつのあし）"},
    36: {"char": "夕", "variants": [], "name": "夕（ゆう・ゆうべ）"},
    37: {"char": "大", "variants": [], "name": "大（だい・だいかんむり・だいかしら）"},
    38: {"char": "女", "variants": [], "name": "女（おんな・おんなへん）"},
    39: {"char": "子", "variants": [], "name": "子（こ・こへん・こどものこ）"},
    40: {"char": "宀", "variants": [], "name": "宀（うかんむり）"},
    41: {"char": "寸", "variants": [], "name": "寸（すん）"},
    42: {"char": "小", "variants": ["⺌", "⺍"], "name": "小（しょう・しょうがしら・なおがしら）"},
    43: {"char": "尢", "variants": ["尣"], "name": "尢（だいのまげあし・もっとも）"},
    44: {"char": "尸", "variants": [], "name": "尸（しかばね・しかばねかんむり・かばね）"},
    45: {"char": "屮", "variants": [], "name": "屮（てつ・くさのめ）"},
    46: {"char": "山", "variants": [], "name": "山（やま・やまへん・やまかんむり）"},
    47: {"char": "巛", "variants": ["川", "巜"], "name": "巛（まがりかわ・さんぼんがわ・かわ）"},
    48: {"char": "工", "variants": [], "name": "工（こう・たくみ・たくみへん）"},
    49: {"char": "己", "variants": ["已", "巳"], "name": "己（こ・き・おのれ）"},
    50: {"char": "巾", "variants": [], "name": "巾（はば・はばへん・きんべん）"},
    51: {"char": "干", "variants": [], "name": "干（かん・いちじゅう）"},
    52: {"char": "幺", "variants": [], "name": "幺（よう・いとがしら）"},
    53: {"char": "广", "variants": [], "name": "广（まだれ）"},
    54: {"char": "廴", "variants": [], "name": "廴（えんにょう・いんにょう）"},
    55: {"char": "廾", "variants": [], "name": "廾（きょう・こまぬき・にじゅうあし）"},
    56: {"char": "弋", "variants": [], "name": "弋（よく・しきがまえ）"},
    57: {"char": "弓", "variants": [], "name": "弓（ゆみ・ゆみへん）"},
    58: {"char": "彐", "variants": ["彑"], "name": "彐（けいがしら・いのこがしら）"},
    59: {"char": "彡", "variants": [], "name": "彡（さんづくり・けかざり）"},
    60: {"char": "彳", "variants": [], "name": "彳（ぎょうにんべん）"},
    61: {"char": "心", "variants": ["忄", "⺗"], "name": "心（こころ・りっしんべん・したごころ）"},
    62: {"char": "戈", "variants": [], "name": "戈（ほこ・ほこづくり・かのほこ）"},
    63: {"char": "戶", "variants": ["戸", "户"], "name": "戶（と・とかんむり・とびらのと）"},
    64: {"char": "手", "variants": ["扌"], "name": "手（て・てへん）"},
    65: {"char": "支", "variants": [], "name": "支（しにょう・えだにょう・じゅうまた）"},
    66: {"char": "攴", "variants": ["攵"], "name": "攴（ぼくづくり・ぼくにょう・のぶん・とまた）"},
    67: {"char": "文", "variants": [], "name": "文（ぶん・ぶんにょう）"},
    68: {"char": "斗", "variants": [], "name": "斗（と・とます）"},
    69: {"char": "斤", "variants": [], "name": "斤（おの・おのづくり）"},
    70: {"char": "方", "variants": [], "name": "方（ほう・ほうへん・かたへん）"},
    71: {"char": "无", "variants": ["旡"], "name": "无（なし・むにょう・すでのつくり）"},
    72: {"char": "日", "variants": [], "name": "日（ひ・ひへん・にちへん）"},
    73: {"char": "曰", "variants": [], "name": "曰（ひらび・いわく）"},
    74: {"char": "月", "variants": [], "name": "月（つき・つきへん）"},
    75: {"char": "木", "variants": [], "name": "木（き・きへん）"},
    76: {"char": "欠", "variants": [], "name": "欠（あくび・かける）"},
    77: {"char": "止", "variants": [], "name": "止（とめる・とめへん）"},
    78: {"char": "歹", "variants": ["歺"], "name": "歹（がつ・がつへん・かばねへん・いちたへん）"},
    79: {"char": "殳", "variants": [], "name": "殳（ほこづくり・るまた）"},
    80: {"char": "毋", "variants": ["母"], "name": "毋（なかれ・はは・ははのかん）"},
    81: {"char": "比", "variants": [], "name": "比（ならびひ・くらべる）"},
    82: {"char": "毛", "variants": [], "name": "毛（け）"},
    83: {"char": "氏", "variants": [], "name": "氏（うじ）"},
    84: {"char": "气", "variants": [], "name": "气（きがまえ）"},
    85: {"char": "水", "variants": ["氵", "氺"], "name": "水（みず・さんずい・したみず）"},
    86: {"char": "火", "variants": ["灬"], "name": "火（ひ・ひへん・れっか・れんが）"},
    87: {"char": "爪", "variants": ["爫"], "name": "爪（つめ・そうにょう・つめかんむり）"},
    88: {"char": "父", "variants": [], "name": "父（ちち）"},
    89: {"char": "爻", "variants": [], "name": "爻（こう・めめ）"},
    90: {"char": "爿", "variants": [], "name": "爿（しょう・しょうへん）"},
    91: {"char": "片", "variants": [], "name": "片（かた・かたへん）"},
    92: {"char": "牙", "variants": [], "name": "牙（きば・きばへん）"},
    93: {"char": "牛", "variants": ["牜"], "name": "牛（うし・うしへん）"},
    94: {"char": "犬", "variants": ["犭"], "name": "犬（いぬ・けものへん）"},
    95: {"char": "玄", "variants": [], "name": "玄（げん）"},
    96: {"char": "玉", "variants": ["王"], "name": "玉（たま・たまへん・おうへん）"},
    97: {"char": "瓜", "variants": [], "name": "瓜（うり）"},
    98: {"char": "瓦", "variants": [], "name": "瓦（かわら）"},
    99: {"char": "甘", "variants": [], "name": "甘（あまい・かん）"},
    100: {"char": "生", "variants": [], "name": "生（いきる・うまれる・せい）"},
    101: {"char": "用", "variants": [], "name": "用（もちいる・よう）"},
    102: {"char": "田", "variants": [], "name": "田（た・たへん）"},
    103: {"char": "疋", "variants": ["⺪"], "name": "疋（ひき・ひきへん）"},
    104: {"char": "疒", "variants": [], "name": "疒（やまいだれ）"},
    105: {"char": "癶", "variants": [], "name": "癶（はつがしら）"},
    106: {"char": "白", "variants": [], "name": "白（しろ・しろへん）"},
    107: {"char": "皮", "variants": [], "name": "皮（けがわ・ひのかわ）"},
    108: {"char": "皿", "variants": [], "name": "皿（さら）"},
    109: {"char": "目", "variants": [], "name": "目（め・めへん）"},
    110: {"char": "矛", "variants": [], "name": "矛（ほこ・ほこへん）"},
    111: {"char": "矢", "variants": [], "name": "矢（や・やへん）"},
    112: {"char": "石", "variants": [], "name": "石（いし・いしへん）"},
    113: {"char": "示", "variants": ["礻", "⺬"], "name": "示（しめす・しめすへん・ねへん）"},
    114: {"char": "禸", "variants": [], "name": "禸（ぐうのあし）"},
    115: {"char": "禾", "variants": [], "name": "禾（のぎ・のぎへん）"},
    116: {"char": "穴", "variants": [], "name": "穴（あな・あなかんむり）"},
    117: {"char": "立", "variants": [], "name": "立（たつ・たつへん）"},
    118: {"char": "竹", "variants": ["⺮"], "name": "竹（たけ・たけかんむり）"},
    119: {"char": "米", "variants": [], "name": "米（こめ・こめへん）"},
    120: {"char": "糸", "variants": ["糹"], "name": "糸（いと・いとへん）"},
    121: {"char": "缶", "variants": [], "name": "缶（ほとぎ・ほとぎへん・ふ）"},
    122: {"char": "网", "variants": ["罒", "⺲", "⺳", "罓"], "name": "网（あみがしら・あみめ・よんがしら）"},
    123: {"char": "羊", "variants": ["⺶", "⺷"], "name": "羊（ひつじ・ひつじへん）"},
    124: {"char": "羽", "variants": ["羽"], "name": "羽（はね）"},
    125: {"char": "老", "variants": ["耂"], "name": "老（おい・おいかんむり・おいがしら）"},
    126: {"char": "而", "variants": [], "name": "而（しこうして・しかして）"},
    127: {"char": "耒", "variants": [], "name": "耒（らいすき・らいへん・すきへん）"},
    128: {"char": "耳", "variants": [], "name": "耳（みみ・みみへん）"},
    129: {"char": "聿", "variants": [], "name": "聿（いつ・ふでづくり）"},
    130: {"char": "肉", "variants": ["⺼", "月"], "name": "肉（にく・にくづき）"},
    131: {"char": "臣", "variants": [], "name": "臣（しん）"},
    132: {"char": "自", "variants": [], "name": "自（じ・みずから）"},
    133: {"char": "至", "variants": [], "name": "至（いたる・いたるへん）"},
    134: {"char": "臼", "variants": [], "name": "臼（うす）"},
    135: {"char": "舌", "variants": [], "name": "舌（した・したへん）"},
    136: {"char": "舛", "variants": [], "name": "舛（まいあし・ます）"},
    137: {"char": "舟", "variants": [], "name": "舟（ふね・ふねへん）"},
    138: {"char": "艮", "variants": [], "name": "艮（ごん・ごんづくり・ねづくり・うしとら）"},
    139: {"char": "色", "variants": [], "name": "色（いろ）"},
    140: {"char": "艸", "variants": ["艹", "⺾", "⺿"], "name": "艸（くさ・くさかんむり）"},
    141: {"char": "虍", "variants": ["⻁"], "name": "虍（とらかんむり・とらがしら）"},
    142: {"char": "虫", "variants": [], "name": "虫（むし・むしへん）"},
    143: {"char": "血", "variants": [], "name": "血（ち）"},
    144: {"char": "行", "variants": [], "name": "行（ぎょうがまえ・ゆきがまえ）"},
    145: {"char": "衣", "variants": ["衤"], "name": "衣（ころも・ころもへん）"},
    146: {"char": "襾", "variants": ["覀", "西"], "name": "襾（にし・おおいかんむり・かなめまど）"},
    147: {"char": "見", "variants": [], "name": "見（みる）"},
    148: {"char": "角", "variants": [], "name": "角（つの・つのへん）"},
    149: {"char": "言", "variants": [], "name": "言（ことば・げん・ごんべん）"},
    150: {"char": "谷", "variants": [], "name": "谷（たに・たにへん）"},
    151: {"char": "豆", "variants": [], "name": "豆（まめ・まめへん）"},
    152: {"char": "豕", "variants": [], "name": "豕（いのこ・いのこへん・ぶた）"},
    153: {"char": "豸", "variants": [], "name": "豸（むじなへん）"},
    154: {"char": "貝", "variants": [], "name": "貝（かい・かいへん・こがい）"},
    155: {"char": "赤", "variants": [], "name": "赤（あか・あかへん）"},
    156: {"char": "走", "variants": [], "name": "走（はしる・そうにょう）"},
    157: {"char": "足", "variants": ["⻊"], "name": "足（あし・あしへん）"},
    158: {"char": "身", "variants": [], "name": "身（み・みへん）"},
    159: {"char": "車", "variants": [], "name": "車（くるま・くるまへん）"},
    160: {"char": "辛", "variants": [], "name": "辛（しん・からい）"},
    161: {"char": "辰", "variants": [], "name": "辰（しんのたつ）"},
    162: {"char": "辵", "variants": ["辶", "⻌", "⻍"], "name": "辵（しんにょう・しんにゅう）"},
    163: {"char": "邑", "variants": ["⻏", "阝"], "name": "邑（むら・おおざと）"},
    164: {"char": "酉", "variants": [], "name": "酉（とりへん・ひよみのとり・さけのとり）"},
    165: {"char": "釆", "variants": [], "name": "釆（のごめ・のごめへん）"},
    166: {"char": "里", "variants": [], "name": "里（さと・さとへん）"},
    167: {"char": "金", "variants": [], "name": "金（かね・かねへん）"},
    168: {"char": "長", "variants": ["镸"], "name": "長（ながい）"},
    169: {"char": "門", "variants": [], "name": "門（もん・もんがまえ・かどがまえ）"},
    170: {"char": "阜", "variants": ["阝", "⻖"], "name": "阜（おか・こざと・こざとへん）"},
    171: {"char": "隶", "variants": [], "name": "隶（れいづくり）"},
    172: {"char": "隹", "variants": [], "name": "隹（ふるとり）"},
    173: {"char": "雨", "variants": ["⻗"], "name": "雨（あめ・あめかんむり）"},
    174: {"char": "靑", "variants": ["青"], "name": "靑（あお）"},
    175: {"char": "非", "variants": [], "name": "非（あらず）"},
    176: {"char": "面", "variants": [], "name": "面（めん）"},
    177: {"char": "革", "variants": [], "name": "革（かわへん・つくりがわ）"},
    178: {"char": "韋", "variants": [], "name": "韋（なめしがわ）"},
    179: {"char": "韭", "variants": [], "name": "韭（にら）"},
    180: {"char": "音", "variants": [], "name": "音（おと・おとへん）"},
    181: {"char": "頁", "variants": [], "name": "頁（おおがい）"},
    182: {"char": "風", "variants": [], "name": "風（かぜ）"},
    183: {"char": "飛", "variants": [], "name": "飛（とぶ）"},
    184: {"char": "食", "variants": ["飠", "𩙿"], "name": "食（しょく・しょくへん）"},
    185: {"char": "首", "variants": [], "name": "首（くび）"},
    186: {"char": "香", "variants": [], "name": "香（かおり）"},
    187: {"char": "馬", "variants": [], "name": "馬（うま・うまへん）"},
    188: {"char": "骨", "variants": [], "name": "骨（ほね・ほねへん）"},
    189: {"char": "高", "variants": [], "name": "高（たかい）"},
    190: {"char": "髟", "variants": [], "name": "髟（かみかんむり・かみがしら）"},
    191: {"char": "鬥", "variants": [], "name": "鬥（とうがまえ・たたかいがまえ）"},
    192: {"char": "鬯", "variants": [], "name": "鬯（ちょう・においざけ）"},
    193: {"char": "鬲", "variants": [], "name": "鬲（かなえ・れき）"},
    194: {"char": "鬼", "variants": [], "name": "鬼（おに・きにょう）"},
    195: {"char": "魚", "variants": ["⻥"], "name": "魚（さかな・うお・うおへん）"},
    196: {"char": "鳥", "variants": ["⻦"], "name": "鳥（とり・とりへん）"},
    197: {"char": "鹵", "variants": [], "name": "鹵（しお・ろ）"},
    198: {"char": "鹿", "variants": [], "name": "鹿（しか）"},
    199: {"char": "麥", "variants": ["麦"], "name": "麥（むぎ・ばくにょう）"},
    200: {"char": "麻", "variants": [], "name": "麻（あさ・あさかんむり）"},
    201: {"char": "黃", "variants": ["黄"], "name": "黃（き・きいろ）"},
    202: {"char": "黍", "variants": [], "name": "黍（きび）"},
    203: {"char": "黑", "variants": ["黒"], "name": "黑（くろ・くろへん）"},
    204: {"char": "黹", "variants": [], "name": "黹（ぬいとり・ふつへん・ち）"},
    205: {"char": "黽", "variants": [], "name": "黽（べんあし・べん・かえる）"},
    206: {"char": "鼎", "variants": [], "name": "鼎（かなえ・てい）"},
    207: {"char": "鼓", "variants": [], "name": "鼓（つづみ）"},
    208: {"char": "鼠", "variants": ["鼡"], "name": "鼠（ねずみ・ねずみへん）"},
    209: {"char": "鼻", "variants": [], "name": "鼻（はな・はなへん）"},
    210: {"char": "齊", "variants": ["斉"], "name": "齊（せい）"},
    211: {"char": "齒", "variants": ["歯"], "name": "齒（は・はへん）"},
    212: {"char": "龍", "variants": ["竜"], "name": "龍（りゅう）"},
    213: {"char": "龜", "variants": ["亀"], "name": "龜（かめ）"},
    214: {"char": "龠", "variants": [], "name": "龠（やく・ふえ）"},
}


# ==============================================================================
# 2. Unicodeブロック判定関数
# ==============================================================================

def get_unicode_block_jp(token: str) -> dict[str, Any]:
    """文字またはCHISEエンティティトークンからUnicodeブロック情報を判定する。

    引数:
        token: 1文字（例: '蛍', '𭕄', '𰃮'）または
               CHISEエンティティ（例: '&CDP-8BD9;', '&GT-K00059;', '&M-04518;'）、
               またはコードポイント文字列（例: 'U+86CD'）。

    戻り値:
        dict:
            - codepoint: コードポイント（例: 'U+86CD', 'U+2D544', 'CDP-8BD9'）
            - block_name: 日本語ブロック名
            - tier: 日本語区分ラベル（例: '基本漢字', '拡張A', '外字・部品' 等）
            - sort_priority: ソート優先順位（1: 基本漢字, 2: 拡張A/互換, 3: 部首, 4: 拡張B〜J, 5: 外字）
    """
    token = token.strip()
    if not token:
        return {
            "codepoint": "",
            "block_name": "CJK関連文字・部品",
            "tier": "外字・部品",
            "sort_priority": 5,
        }

    # 1. CHISE外字エンティティの判定 (&...; 形式または識別接頭辞)
    is_entity = False
    entity_code = ""

    if token.startswith("&") and token.endswith(";"):
        is_entity = True
        entity_code = token[1:-1]
    elif token.startswith("&"):
        is_entity = True
        entity_code = token[1:].rstrip(";")
    elif re.match(r"^(CDP|GT|MH?|MJ|C[1-7]|J90|JSP|JX|CB)[-_0-9A-Za-z]", token):
        is_entity = True
        entity_code = token

    if is_entity:
        codepoint = entity_code
        tier = "外字・部品"
        sort_priority = 5

        if entity_code.startswith("CDP-") or entity_code.startswith("CDP"):
            block_name = "CHISE外字（台湾・中央研究院 CDP外字）"
        elif entity_code.startswith("GT-") or entity_code.startswith("GT"):
            block_name = "CHISE外字（東大・GT書体プロジェクト）"
        elif entity_code.startswith("M-") or entity_code.startswith("MH-"):
            block_name = "諸橋大漢和辞典 文字番号"
        elif entity_code.startswith("MJ"):
            block_name = "文字情報基盤（MJ文字）"
        elif re.match(r"^C[1-7]-", entity_code):
            block_name = "CNS 11643 台湾標準文字"
        elif (
            entity_code.startswith("J90-")
            or entity_code.startswith("JSP-")
            or entity_code.startswith("JX")
        ):
            block_name = "JIS漢字コード"
        elif entity_code.startswith("CB"):
            block_name = "CBETA外字"
        else:
            block_name = "CJK関連文字・部品"

        return {
            "codepoint": codepoint,
            "block_name": block_name,
            "tier": tier,
            "sort_priority": sort_priority,
        }

    # 2. Unicodeコードポイントの判定
    cp: int | None = None
    if (token.startswith("U+") or token.startswith("u+")) and len(token) > 2:
        try:
            cp = int(token[2:], 16)
        except ValueError:
            pass
    elif len(token) == 1:
        cp = ord(token)

    if cp is None:
        return {
            "codepoint": token,
            "block_name": "CJK関連文字・部品",
            "tier": "外字・部品",
            "sort_priority": 5,
        }

    codepoint = f"U+{cp:04X}"

    # 基本多言語面 CJK統合漢字
    if 0x4E00 <= cp <= 0x9FFF:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字（基本多言語面）",
            "tier": "基本漢字",
            "sort_priority": 1,
        }
    # 拡張A
    elif 0x3400 <= cp <= 0x4DBF:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張A",
            "tier": "拡張A",
            "sort_priority": 2,
        }
    # 拡張B
    elif 0x20000 <= cp <= 0x2A6DF:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張B",
            "tier": "拡張B",
            "sort_priority": 4,
        }
    # 拡張C
    elif 0x2A700 <= cp <= 0x2B73F:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張C",
            "tier": "拡張C",
            "sort_priority": 4,
        }
    # 拡張D
    elif 0x2B740 <= cp <= 0x2B81D:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張D",
            "tier": "拡張D",
            "sort_priority": 4,
        }
    # 拡張E
    elif 0x2B820 <= cp <= 0x2CEAD:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張E",
            "tier": "拡張E",
            "sort_priority": 4,
        }
    # 拡張F
    elif 0x2CEB0 <= cp <= 0x2EBE0:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張F",
            "tier": "拡張F",
            "sort_priority": 4,
        }
    # 拡張I
    elif 0x2EBF0 <= cp <= 0x2EE5D:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張I",
            "tier": "拡張I",
            "sort_priority": 4,
        }
    # 拡張G
    elif 0x30000 <= cp <= 0x3134A:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張G",
            "tier": "拡張G",
            "sort_priority": 4,
        }
    # 拡張H
    elif 0x31350 <= cp <= 0x323AF:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張H",
            "tier": "拡張H",
            "sort_priority": 4,
        }
    # 拡張J
    elif 0x323B0 <= cp <= 0x33479:
        return {
            "codepoint": codepoint,
            "block_name": "CJK統合漢字拡張J",
            "tier": "拡張J",
            "sort_priority": 4,
        }
    # 互換漢字
    elif 0xF900 <= cp <= 0xFAFF:
        return {
            "codepoint": codepoint,
            "block_name": "CJK互換漢字",
            "tier": "互換漢字",
            "sort_priority": 2,
        }
    # 互換漢字補助
    elif 0x2F800 <= cp <= 0x2FA1F:
        return {
            "codepoint": codepoint,
            "block_name": "CJK互換漢字補助",
            "tier": "互換漢字補助",
            "sort_priority": 2,
        }
    # 部首・筆画関連
    elif 0x2E80 <= cp <= 0x2EFF:
        return {
            "codepoint": codepoint,
            "block_name": "CJK部首補助",
            "tier": "部首・筆画",
            "sort_priority": 3,
        }
    elif 0x2F00 <= cp <= 0x2FD5:
        return {
            "codepoint": codepoint,
            "block_name": "康熙部首",
            "tier": "部首・筆画",
            "sort_priority": 3,
        }
    elif 0x31C0 <= cp <= 0x31EF:
        return {
            "codepoint": codepoint,
            "block_name": "CJKの筆画",
            "tier": "部首・筆画",
            "sort_priority": 3,
        }
    elif 0x2FF0 <= cp <= 0x2FFF:
        return {
            "codepoint": codepoint,
            "block_name": "漢字構成記述文字（IDC）",
            "tier": "部首・筆画",
            "sort_priority": 3,
        }
    else:
        return {
            "codepoint": codepoint,
            "block_name": "CJK関連文字・部品",
            "tier": "外字・部品",
            "sort_priority": 5,
        }


# ==============================================================================
# 3. 学年・JLPT・頻度バッジ整形関数
# ==============================================================================

def format_grade_jp(
    grade: int | None,
    jlpt: int | None,
    freq: int | None,
) -> list[str]:
    """配当学年、旧JLPT級、新聞頻度順位から日本語ステータスバッジのリストを生成する。

    引数:
        grade: 小学校学年（1〜6）または常用漢字区分（8: 常用漢字, 9/10: 人名用漢字）
        jlpt: 旧JLPT級（1〜4）
        freq: 新聞頻度順位

    戻り値:
        list[str]: 日本語バッジ文字列のリスト
    """
    badges: list[str] = []

    if grade is not None:
        if 1 <= grade <= 6:
            badges.append(f"教育漢字（小学{grade}年）")
            badges.append("常用漢字")
        elif grade == 8:
            badges.append("常用漢字")
        elif grade in (9, 10):
            badges.append("人名用漢字")

    if freq is not None:
        badges.append(f"新聞頻度 #{freq}")

    if jlpt is not None:
        badges.append(f"旧JLPT {jlpt}級")

    return badges


# ==============================================================================
# 4. KanjiVG 筆画タイプマッピング辞書
# ==============================================================================

STROKE_TYPE_JP: dict[str, str] = {
    # 基本筆画（Unicode CJK筆画ブロック U+31C0〜U+31E3）
    "㇐": "横画（一）",
    "㇑": "縦画（丨）",
    "㇒": "左払い（丿）",
    "㇏": "右払い（乀）",
    "㇔": "点（丶）",
    "㇀": "跳ね上げ（㇀）",
    "㇕": "折れ（㇕）",
    "㇖": "横鉤（乛）",
    "㇚": "縦鉤（亅）",
    "㇟": "曲がり鉤（乚）",
    "㇡": "横折れ折れ鉤（㇡）",
    "㇇": "横払い（㇇）",
    "㇌": "横払い曲がり鉤（㇌）",
    "㇁": "弧状鉤（㇁）",
    "㇂": "斜め鉤（㇂）",
    "㇃": "心の反り鉤（㇃）",
    "㇄": "縦折れ（㇄）",
    "㇅": "横折れ折れ（㇅）",
    "㇆": "横折れ鉤（㇆）",
    "㇈": "横曲がり鉤（㇈）",
    "㇉": "縦曲がり鉤（㇉）",
    "㇊": "横折れ跳ね（㇊）",
    "㇋": "横折れ折れ払い（㇋）",
    "㇍": "横折れ曲がり（㇍）",
    "㇎": "横三重折れ（㇎）",
    "㇓": "縦払い（㇓）",
    "㇗": "縦折れ（㇗）",
    "㇘": "縦曲がり折れ（㇘）",
    "㇙": "縦跳ね（㇙）",
    "㇛": "払い点（㇛）",
    "㇜": "払い折れ（㇜）",
    "㇝": "提捺（㇝）",
    "㇞": "縦折れ折れ（㇞）",
    "㇠": "横斜め曲がり鉤（㇠）",
    "㇢": "払い鉤（㇢）",
    "㇣": "丸（〇）",
    # 接筆属性記号（KanjiVG仕様）
    "a": "中接（他画の中途に接する）",
    "b": "端接（他画の端に接する）",
    "c": "交差（他画と交差する）",
    # KanjiVGで頻出する接筆結合タイプ
    "㇐a": "横画・中接（一）",
    "㇐b": "横画・端接（一）",
    "㇐c": "横画・交差（一）",
    "㇑a": "縦画・中接（丨）",
    "㇑b": "縦画・端接（丨）",
    "㇕a": "折れ・中接（㇕）",
    "㇕b": "折れ・端接（㇕）",
    "㇕c": "折れ・交差（㇕）",
    "㇆a": "横折れ鉤・中接（㇆）",
    "㇆v": "横折れ鉤（垂直変形）",
    "㇖a": "横鉤・中接（乛）",
    "㇖b": "横鉤・端接（乛）",
    "㇟a": "曲がり鉤・中接（乚）",
    "㇟b": "曲がり鉤・端接（乚）",
    "㇗a": "縦折れ・中接（㇗）",
    "㇈a": "横曲がり鉤・中接（㇈）",
    "㇈b": "横曲がり鉤・端接（㇈）",
    "㇇a": "横払い・中接（㇇）",
    "㇄a": "縦折れ・中接（㇄）",
    "㇔a": "点・中接（丶）",
    "㇏a": "右払い・中接（乀）",
    "㇔/㇏": "点または右払い",
    "㇀/㇐": "跳ね上げまたは横画",
    # 常用漢字・基本字形表記互換用
    "一": "横画（一）",
    "丨": "縦画（丨）",
    "丿": "左払い（丿）",
    "丶": "点（丶）",
    "亅": "縦鉤（亅）",
    "乚": "曲がり鉤（乚）",
    "乛": "横鉤（乛）",
    "乀": "右払い（乀）",
}


def get_stroke_type_jp(stroke_type: str) -> str:
    """KanjiVGのkvg:type属性値から日本語の筆画名称を取得する。

    完全一致しない場合はスラッシュ分割や接頭辞一致で検索する。
    """
    if not stroke_type:
        return "筆画"
    if stroke_type in STROKE_TYPE_JP:
        return STROKE_TYPE_JP[stroke_type]

    # 複数候補（例: '㇔/㇏'）の処理
    if "/" in stroke_type:
        parts = stroke_type.split("/")
        names = [get_stroke_type_jp(p.strip()) for p in parts]
        return "または".join(names)

    # 前方一致による検索
    for prefix in STROKE_TYPE_JP:
        if stroke_type.startswith(prefix):
            return STROKE_TYPE_JP[prefix]

    return "筆画"


# ==============================================================================
# 自己テストおよび動作検証
# ==============================================================================

if __name__ == "__main__":
    # 1. 康熙部首辞書検証
    assert len(KANGXI_RADICALS) == 214, f"部首数が214ではありません: {len(KANGXI_RADICALS)}"
    assert KANGXI_RADICALS[1] == {"char": "一", "variants": [], "name": "一（いち）"}
    assert KANGXI_RADICALS[9] == {"char": "人", "variants": ["亻", "𠆢"], "name": "人（ひと・にんべん・ひとやね）"}
    assert KANGXI_RADICALS[85] == {"char": "水", "variants": ["氵", "氺"], "name": "水（みず・さんずい・したみず）"}
    assert KANGXI_RADICALS[140] == {"char": "艸", "variants": ["艹", "⺾", "⺿"], "name": "艸（くさ・くさかんむり）"}
    assert KANGXI_RADICALS[142] == {"char": "虫", "variants": [], "name": "虫（むし・むしへん）"}

    for idx, data in KANGXI_RADICALS.items():
        assert 1 <= idx <= 214
        assert "char" in data and isinstance(data["char"], str) and len(data["char"]) == 1
        assert "variants" in data and isinstance(data["variants"], list)
        assert "name" in data and isinstance(data["name"], str)

    # 2. Unicodeブロック判定検証
    # 例: "蛍" (U+86CD)
    b_hotaru = get_unicode_block_jp("蛍")
    assert b_hotaru["codepoint"] == "U+86CD"
    assert b_hotaru["block_name"] == "CJK統合漢字（基本多言語面）"
    assert b_hotaru["tier"] == "基本漢字"
    assert b_hotaru["sort_priority"] == 1

    # 例: "𭕄" (U+2D544, 拡張F)
    b_ext_f = get_unicode_block_jp("𭕄")
    assert b_ext_f["codepoint"] == "U+2D544"
    assert b_ext_f["block_name"] == "CJK統合漢字拡張F"
    assert b_ext_f["tier"] == "拡張F"
    assert b_ext_f["sort_priority"] == 4

    # 例: "𰃮" (U+300EE, 拡張G)
    b_ext_g = get_unicode_block_jp("𰃮")
    assert b_ext_g["codepoint"] == "U+300EE"
    assert b_ext_g["block_name"] == "CJK統合漢字拡張G"
    assert b_ext_g["tier"] == "拡張G"
    assert b_ext_g["sort_priority"] == 4

    # 例: CHISE CDP外字
    b_cdp = get_unicode_block_jp("&CDP-8BD9;")
    assert b_cdp["codepoint"] == "CDP-8BD9"
    assert b_cdp["block_name"] == "CHISE外字（台湾・中央研究院 CDP外字）"
    assert b_cdp["tier"] == "外字・部品"
    assert b_cdp["sort_priority"] == 5

    # 例: GT外字
    b_gt = get_unicode_block_jp("&GT-K00059;")
    assert b_gt["codepoint"] == "GT-K00059"
    assert b_gt["block_name"] == "CHISE外字（東大・GT書体プロジェクト）"
    assert b_gt["tier"] == "外字・部品"
    assert b_gt["sort_priority"] == 5

    # 例: 諸橋大漢和辞典
    b_m = get_unicode_block_jp("&M-04518;")
    assert b_m["codepoint"] == "M-04518"
    assert b_m["block_name"] == "諸橋大漢和辞典 文字番号"
    assert b_m["tier"] == "外字・部品"
    assert b_m["sort_priority"] == 5

    # 3. 学年・JLPT・頻度バッジ整形検証
    assert format_grade_jp(1, 4, 100) == ["教育漢字（小学1年）", "常用漢字", "新聞頻度 #100", "旧JLPT 4級"]
    assert format_grade_jp(8, None, None) == ["常用漢字"]
    assert format_grade_jp(9, None, 500) == ["人名用漢字", "新聞頻度 #500"]
    assert format_grade_jp(None, 1, None) == ["旧JLPT 1級"]
    assert format_grade_jp(None, None, None) == []

    # 4. 筆画タイプマッピング検証
    assert STROKE_TYPE_JP["㇐"] == "横画（一）"
    assert STROKE_TYPE_JP["㇑"] == "縦画（丨）"
    assert STROKE_TYPE_JP["㇒"] == "左払い（丿）"
    assert STROKE_TYPE_JP["㇏"] == "右払い（乀）"
    assert STROKE_TYPE_JP["㇔"] == "点（丶）"
    assert STROKE_TYPE_JP["㇀"] == "跳ね上げ（㇀）"
    assert STROKE_TYPE_JP["㇕"] == "折れ（㇕）"
    assert STROKE_TYPE_JP["㇖"] == "横鉤（乛）"
    assert STROKE_TYPE_JP["㇚"] == "縦鉤（亅）"
    assert STROKE_TYPE_JP["㇟"] == "曲がり鉤（乚）"
    assert STROKE_TYPE_JP["a"] == "中接（他画の中途に接する）"
    assert STROKE_TYPE_JP["b"] == "端接（他画の端に接する）"
    assert STROKE_TYPE_JP["c"] == "交差（他画と交差する）"

    assert get_stroke_type_jp("㇐") == "横画（一）"
    assert get_stroke_type_jp("㇐a") == "横画・中接（一）"
    assert get_stroke_type_jp("㇔/㇏") == "点または右払い"

    print("すべてのテストに成功しました（214部首、Unicodeブロック判定、バッジ整形、筆画マッピング）。")
