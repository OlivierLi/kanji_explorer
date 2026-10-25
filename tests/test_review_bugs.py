"""review.md に記載された全14件の不具合に対する厳密な回帰テストスイート."""

import io
from pathlib import Path
import re
import pytest

import ids_parser
import glyph_service
import server
import view_renderer


def _decompose(char: str):
    ids = (
        ids_parser.get_character_ids(char)
        or ids_parser.COMPONENT_SUBDECOMPOSITIONS.get(char)
        or char
    )
    tree = ids_parser.decompose_character(
        ids, max_depth=8, use_atomic=True, compute_bbox=True
    )
    tree["char"] = char
    return tree


class TestBug1LeftRightGapOverride:
    """Bug 1: 左右構造（⿰/⿲）における最大間隙（best_gap）による右側複合要素強奪の防止."""

    @pytest.mark.parametrize("char,left_char,right_char", [
        ("億", "亻", "意"),
        ("樹", "木", "尌"),
        ("測", "氵", "則"),
        ("湖", "氵", "胡"),
        ("働", "亻", "動"),
        ("織", "糸", "戠"),
    ])
    def test_left_right_split_does_not_steal_right_component(self, char, left_char, right_char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}

        # 0.0 は左要素、0.1 は右要素
        l0 = layers.get("0.0")
        l1 = layers.get("0.1")
        assert l0 is not None and l1 is not None

        # 左要素の幅は最大でも文字の 0.45 以内であること（右要素を強奪して 0.70〜0.90 に肥大化していないこと）
        assert l0["bbox"][2] <= 0.45, (
            f"文字 '{char}' の左要素 '{left_char}' の幅が異常に大きいです: bbox={l0['bbox']}"
        )
        # 右要素の幅は少なくとも 0.50 以上を維持していること
        assert l1["bbox"][2] >= 0.50, (
            f"文字 '{char}' の右要素 '{right_char}' の幅が異常に狭いです: bbox={l1['bbox']}"
        )


class TestBug2TopBottomMidArchesAndGaps:
    """Bug 2: 上下構造（⿱/⿳）におけるアーチ判定（mid_arches）による下部部品強奪の防止."""

    def test_tsutsu_bamboo_does_not_steal_dou_frame(self):
        """筒 (⿱竹同): 上の「竹」が下の「同」の外枠「冂」を強奪しないこと."""
        tree = _decompose("筒")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        take = layers.get("0.0")
        dou = layers.get("0.1")
        assert take is not None and dou is not None

        # 竹は上部（y2 <= 0.35）に収まっていること
        take_y2 = take["bbox"][1] + take["bbox"][3]
        assert take_y2 <= 0.35, f"筒の竹のy2が下部に侵入しています: {take['bbox']}"
        # 同は y1 >= 0.28 から始まっており、外枠が含まれていること
        assert dou["bbox"][1] >= 0.28
        assert dou["bbox"][3] >= 0.60

    def test_haka_mo_does_not_lose_body_to_tsuchi(self):
        """墓 (⿱莫土): 下の「土」が「日＋大」まで強奪しないこと."""
        tree = _decompose("墓")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        mo = layers.get("0.0")
        tsuchi = layers.get("0.1")
        assert mo is not None and tsuchi is not None

        # 莫は文字の過半を占めること (h >= 0.60)
        assert mo["bbox"][3] >= 0.60, f"墓の莫の高さが不足しています: {mo['bbox']}"
        # 土は下部 (y1 >= 0.55) に位置すること
        assert tsuchi["bbox"][1] >= 0.55, f"墓の土の位置が高すぎます: {tsuchi['bbox']}"


class TestBug3EnclosureTareNyouOperators:
    """Bug 3: 包囲・垂れ・繞構造における _assign_enclosure の正確な内外判定."""

    @pytest.mark.parametrize("char", [
        "近",
        "進",
        "道",
        "通",
        "病",
        "痛",
        "同",
        "国",
        "団",
        "園",
        "起",
    ])
    def test_enclosure_inner_not_starved(self, char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        outer = layers.get("0.0")
        inner = layers.get("0.1")
        assert outer is not None and inner is not None

        # 内側要素が空（幅または高さが0）や単なる小さな点（幅<0.2かつ高<0.2）に縮退していないこと
        iw, ih = inner["bbox"][2], inner["bbox"][3]
        assert iw >= 0.25 and ih >= 0.25, (
            f"文字 '{char}' の内側部品 '{inner.get('char')}' が極小化しています: bbox={inner['bbox']}"
        )
        # 外枠が外周に存在すること
        assert outer["bbox"][2] >= 0.70 and outer["bbox"][3] >= 0.70

    def test_dou_outer_and_inner_not_swapped(self):
        """同 (⿵𠔼口): 外枠と口が100%反転していないこと."""
        tree = _decompose("同")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        waku = layers["0.0"]
        kuchi = layers["0.1"]
        # 外枠 (𠔼) は全高・全幅に近い
        assert waku["bbox"][2] >= 0.70 and waku["bbox"][3] >= 0.70
        # 口は中央内部に位置し、幅・高さともに 0.60 未満
        assert kuchi["bbox"][2] <= 0.60 and kuchi["bbox"][3] <= 0.60
        assert kuchi["bbox"][0] >= 0.20 and kuchi["bbox"][1] >= 0.30


class TestBug4SpanningCandFilter:
    """Bug 4: 跨ぎインク島（spanning）の充足判定と _expected_min_islands."""

    @pytest.mark.parametrize("char", ["当", "光", "尚"])
    def test_spanning_stroke_shared_and_clipped(self, char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        top = layers.get("0.0")
        bottom = layers.get("0.1")
        assert top is not None and bottom is not None

        # 下部要素が中央縦画を独占して未クリップ (needs_clip=False) になっていないこと
        assert bottom["needs_clip"] is True or bottom["bbox"][3] < 0.85, (
            f"文字 '{char}' の下部要素がクリップなしで文字全体を覆っています: {bottom}"
        )


class TestBug5UnclippedBaseFallback:
    """Bug 5: インク島未配分ノードが未クリップ全体グリフ（base_path）に縮退するバグの防止."""

    @pytest.mark.parametrize("char", ["夢", "停", "厎", "嵈", "爚", "鬱"])
    def test_no_subpart_renders_unclipped_base(self, char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        base_path = out["base_path"]

        for layer in out["component_layers"]:
            # 全体 base_path をスライスとして使用している場合、必ず needs_clip が True であること
            if layer["slice_path"] == base_path:
                assert layer["needs_clip"] is True, (
                    f"文字 '{char}' の階層 '{layer['path']}' ({layer['char']}) が未クリップの全体グリフを描画しています。"
                )


class TestBug6TightenBboxSyncClipRects:
    """Bug 6: インク島外接矩形引き締め時の clip_rects / hit_rects 再同期."""

    @pytest.mark.parametrize("char", ["語", "休", "相", "説"])
    def test_leaf_clip_rects_synchronized_with_bbox(self, char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)

        for layer in out["component_layers"]:
            if not layer.get("clip_rects"):
                continue
            cr0 = layer["clip_rects"][0]
            bbox = layer["bbox"]
            # 葉ノードまたは単一クリップ矩形の場合、clip_rects[0] と bbox が整合していること
            if len(layer["clip_rects"]) == 1:
                assert abs(cr0[0] - bbox[0]) < 0.05
                assert abs(cr0[1] - bbox[1]) < 0.05


class TestBug7HardcodedGeometryScoping:
    """Bug 7: 単一文字向けハードコード幾何が他文字を破壊しないことの検証."""

    def test_tsukasa_hook_preserves_top_horizontal_bar(self):
        """司 (⿹𠃌𠮛): 𠃌のクリップ枠が上部水平バーを切り落としていないこと."""
        tree = _decompose("司")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        hook = layers["0.0"]
        # 𠃌 のクリップ矩形は上部 (y <= 0.10) をカバーしていること
        min_y = min(cr[1] for cr in hook["clip_rects"])
        assert min_y <= 0.10, f"司の𠃌のクリップ矩形から上部水平バーが脱落しています: {hook['clip_rects']}"

    def test_kaiko_vertical_line_does_not_pierce_ten(self):
        """蚕 (⿱天虫): 虫内部の丨が上の「天」を貫通しないこと (vy1 >= 0.30)."""
        tree = _decompose("蚕")
        glyph_service.build_interactive_ids_svg(tree)

        def find_vertical_line(n):
            if n.get("char") == "丨" or n.get("raw_char") == "丨":
                return n
            for ch in n.get("children", []):
                r = find_vertical_line(ch)
                if r is not None:
                    return r
            return None

        line_node = find_vertical_line(tree)
        assert line_node is not None
        assert line_node["bbox"][1] >= 0.30, (
            f"蚕の虫内部の丨のy座標が天の領域まで突き抜けています: {line_node['bbox']}"
        )


class TestBug8FlankingThresholdAndEnclosureHitbox:
    """Bug 8: 挟み込み構造（is_flanking）の幅閾値と包囲構え中空ヒットボックス."""

    def test_han_right_king_not_dropped(self):
        """班 (⿴玨刂): 右の「王」が両脇から脱落せず、中央の刂が独立していること."""
        tree = _decompose("班")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        flank = layers.get("0.0")
        center = layers.get("0.1")
        assert flank is not None and center is not None
        # 中央 刂 の幅は 0.40 以下
        assert center["bbox"][2] <= 0.40

    @pytest.mark.parametrize("char", ["問", "開", "間", "風", "国", "広"])
    def test_enclosure_has_peripheral_hit_rects(self, char):
        """包囲構えの外枠ノードが中空ストリップの hit_rects を持つこと."""
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        outer = layers["0.0"]
        hit_rects = outer.get("hit_rects")
        assert hit_rects is not None and len(hit_rects) >= 2, (
            f"文字 '{char}' の外枠 '{outer.get('char')}' が中空 hit_rects を持っていません: {outer}"
        )


class TestBug9SmallTopRadicalsRatio:
    """Bug 9: 3点冠部首の比率分離（SMALL_TOP_RADICALS）."""

    @pytest.mark.parametrize("char", ["巣", "単", "当", "尚"])
    def test_small_top_radicals_ratio_around_22_percent(self, char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        top = layers.get("0.0")
        assert top is not None
        # 3点冠部首の高さ比率は 0.26 以下であること（0.38で下部を切り落とさない）
        assert top["bbox"][3] <= 0.26, (
            f"文字 '{char}' の上部3点冠の高さが過大です: {top['bbox']}"
        )


class TestBug10PrintComponentFallbackSelector:
    """Bug 10: ベクターフォールバック時におけるロック対象部品の減光セレクタ."""

    def test_css_selector_for_locked_scope(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
        css_text = css_path.read_text(encoding="utf-8")

        # 誤ったセレクタが存在しないこと
        assert ".print-component-fallback:not(.locked-scope)" not in css_text

        # 正しい親指定セレクタが存在すること
        pattern = r"\.component-vector-layer:not\(\.locked-scope\)\s+\.print-component-fallback"
        assert re.search(pattern, css_text) is not None, (
            "styles.css に正しい親指定の .component-vector-layer:not(.locked-scope) セレクタが見つかりません。"
        )


class TestBug11KanjiVgLockedScopeStyles:
    """Bug 11: KanjiVGフォールバック描画におけるロック状態スタイル."""

    def test_kanjivg_lock_styles_exist_in_css(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
        css_text = css_path.read_text(encoding="utf-8")
        assert ".kvg-root.has-locked-scope" in css_text
        assert ".kvg-group.locked-scope" in css_text

    def test_app_js_toggles_kanjivg_lock_classes(self):
        js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        js_text = js_path.read_text(encoding="utf-8")
        assert "kvg-group" in js_text
        assert "locked-scope" in js_text


class TestBug12DropShadowGlowWrapper:
    """Bug 12: clip-path 境界による drop-shadow グローの直線的断絶防止."""

    def test_glow_wrapper_exists_in_app_js(self):
        js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        js_text = js_path.read_text(encoding="utf-8")
        assert "print-component-glow-wrapper" in js_text

    def test_drop_shadow_applied_to_wrapper_in_css(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
        css_text = css_path.read_text(encoding="utf-8")
        pattern = r"\.print-component-glow-wrapper"
        assert re.search(pattern, css_text) is not None


class TestBug13CanvasEmptyHoverClear:
    """Bug 13: キャンバス内空白領域移動時にホバー解除されるイベント設計."""

    def test_mouseout_and_mouseover_clear_handlers_in_js(self):
        js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        js_text = js_path.read_text(encoding="utf-8")
        assert "mouseout" in js_text
        assert "clearComponentHover" in js_text


class TestBug14GlyphApiContrastAndTheme:
    """Bug 14: 外字グリフ配信（/api/glyph）の高コントラスト色とテーマCSSフィルター."""

    def test_glyph_svg_fill_not_d0d7de(self):
        svg = glyph_service.get_glyph_svg("蛍")
        assert '#d0d7de' not in svg
        assert '#57606a' in svg

    def test_entity_glyph_img_theme_filters_in_css(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
        css_text = css_path.read_text(encoding="utf-8")
        assert ".entity-glyph-img" in css_text
        assert "brightness(0)" in css_text


class TestScreenshotBugSuKudamonoIchiHighlight:
    """スクリーンショット不具合: 巣 (⿱𭕄果) の果(⿻日木)内部「一」(0.1.0.1) 選択時の木侵入ハイライト防止."""

    def test_su_kudamono_inner_ichi_bounded_above_ki(self):
        """0.1.0.1 (一) のバウンディングボックスおよびクリップ矩形が木 (y >= 0.50) に侵入せず、上部日内部に厳密に収まること."""
        tree = _decompose("巣")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}

        layer_ichi = layers.get("0.1.0.1")
        assert layer_ichi is not None, "巣の 0.1.0.1 (一) レイヤーが見つかりません"
        bbox = layer_ichi["bbox"]
        # y1 >= 0.30 かつ y2 <= 0.46 (木の下部 0.50 に絶対に届かない)
        y1 = bbox[1]
        y2 = bbox[1] + bbox[3]
        h = bbox[3]
        assert y1 >= 0.30, f"0.1.0.1 の開始 y が上すぎます: {bbox}"
        assert y2 <= 0.46, f"0.1.0.1 の終了 y が木 (y>=0.50) まで侵入しています: {bbox}"
        assert h <= 0.12, f"0.1.0.1 (一) の高さが異常に大きいです（横画ではなく巨大矩形）: {bbox}"

        # クリップ矩形も同様に木に侵入していないこと
        clip_rects = layer_ichi.get("clip_rects", [])
        assert len(clip_rects) > 0
        for cr in clip_rects:
            cr_y2 = cr[1] + cr[3]
            assert cr_y2 <= 0.46, f"クリップ矩形が木まで延びています: {cr}"

    def test_su_kudamono_hi_and_ki_subcomponents_partition(self):
        """巣における果の分解（0.1.0 日 と 0.1.1 木）が上下に明瞭に分離されていること."""
        tree = _decompose("巣")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}

        hi = layers.get("0.1.0")
        ki = layers.get("0.1.1")
        assert hi is not None and ki is not None

        # 日 (0.1.0) は果の上半部に収まっていること (y2 <= 0.60)
        hi_y2 = hi["bbox"][1] + hi["bbox"][3]
        assert hi_y2 <= 0.60, f"日のy2が過大です: {hi['bbox']}"

        # 木 (0.1.1) は果の下半部に位置すること (y1 >= 0.45)
        assert ki["bbox"][1] >= 0.45, f"木のy1が果の上部まで侵入しています: {ki['bbox']}"


class TestBug15KanjivgHierarchyContainment:
    """Bug 15: KanjiVGストローク対応付けにおける部分木境界越え・親要素逸脱ストローク強奪の防止."""

    def test_gi_hitsuji_does_not_steal_ware_strokes(self):
        """『議』において、0.1.0 (羊) が下部の我 (0.1.1) の筆画 (s14, s18, s19, s20等) を強奪せず、羊の6画のみを保持すること."""
        tree = _decompose("議")
        res = glyph_service.extract_kanjivg_stroke_layers("議", tree)
        assert res.get("has_kvg"), "議 のKanjiVGデータが取得できません"

        s_hitsuji = res["layer_strokes"].get("0.1.0", [])
        s_ware = res["layer_strokes"].get("0.1.1", [])

        # 羊は6画（s8〜s13）
        assert len(s_hitsuji) == 6, f"羊の筆画数が不正です: {len(s_hitsuji)} (strokes: {s_hitsuji})"
        assert set(s_hitsuji) == {
            "kvg:08b70-s8", "kvg:08b70-s9", "kvg:08b70-s10",
            "kvg:08b70-s11", "kvg:08b70-s12", "kvg:08b70-s13",
        }

        # 我の筆画 (s14〜s20) が羊に一切混入していないこと
        ware_strokes = {
            "kvg:08b70-s14", "kvg:08b70-s15", "kvg:08b70-s16",
            "kvg:08b70-s17", "kvg:08b70-s18", "kvg:08b70-s19", "kvg:08b70-s20",
        }
        assert not (set(s_hitsuji) & ware_strokes), "我の筆画が羊に漏洩しています"
        assert set(s_ware) == ware_strokes

    @pytest.mark.parametrize("char", [
        "議", "話", "語", "調", "高", "玉", "草", "前", "園", "橋", "喜", "憲", "善", "端", "歓"
    ])
    def test_kanjivg_group_hierarchy_invariants(self, char):
        """全グループの割り当てパスがKanjiVG木構造の親パスに厳密に包含されていること (祖先スコープ逸脱ゼロ)."""
        tree = _decompose(char)
        res = glyph_service.extract_kanjivg_stroke_layers(char, tree)
        assert res.get("has_kvg")

        mismatches = []
        def check_hierarchy(g, parent_path=""):
            g_path = g.get("path", "")
            gid = g.get("id", "")
            elem = g.get("element", "")
            if g_path and parent_path and parent_path != "0":
                if not (g_path.startswith(parent_path + ".") or g_path == parent_path):
                    mismatches.append((gid, elem, parent_path, g_path))
            eff_path = g_path if g_path else parent_path
            for c in g.get("children", []):
                check_hierarchy(c, eff_path)

        check_hierarchy(res["kvg_tree"])
        assert len(mismatches) == 0, f"{char} に階層逸脱グループが存在します: {mismatches}"


class TestBug16ContainerBoundingBox:
    """Bug 16: 囲み構造（⿶/⿵/⿷）における内部要素のバウンディングボックス逸脱・外枠侵入の防止."""

    def test_utsu_kanna_container_bbox(self):
        """『鬱』において、0.1.0.0.0 (凵) の内部要素 0.1.0.0.1 (𠂭/※) が凵の側壁や底辺を突き抜けないこと."""
        tree = _decompose("鬱")
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}

        kanna = layers.get("0.1.0.0.0")  # 凵
        inner = layers.get("0.1.0.0.1")  # 𠂭 / ※
        assert kanna is not None and inner is not None

        kx, ky, kw, kh = kanna["bbox"]
        ix, iy, iw, ih = inner["bbox"]

        # 内部要素の左端・右端が凵の側壁内側（左右20%〜80%の範囲内）に収まっていること
        assert ix >= kx + kw * 0.20, f"内部要素の左端が凵の左側壁に侵入しています: inner={inner['bbox']}, 凵={kanna['bbox']}"
        assert ix + iw <= kx + kw * 0.80, f"内部要素の右端が凵の右側壁に侵入しています: inner={inner['bbox']}, 凵={kanna['bbox']}"
        # 内部要素の下端が凵の底部（底辺壁の手前、75%以内）に収まっていること
        assert iy + ih <= ky + kh * 0.75, f"内部要素の下端が凵の底壁を突き抜けています: inner={inner['bbox']}, 凵={kanna['bbox']}"

    @pytest.mark.parametrize("char", ["凶", "函"])
    def test_shita_kakomi_inner_stays_inside_walls(self, char):
        """下囲（⿶）文字において、内部要素が外枠の側壁と底壁の内部に配置されること."""
        tree = _decompose(char)
        c0 = tree["children"][0]
        c1 = tree["children"][1]
        cx, cy, cw, ch = c0["bbox"]
        ix, iy, iw, ih = c1["bbox"]

        assert ix >= cx + cw * 0.20
        assert ix + iw <= cx + cw * 0.80
        assert iy + ih <= cy + ch * 0.75


class TestBug17StrokeDisjointnessAndPrimitiveDecomposition:
    """Bug 17: 末端構成要素（巣の木、当の彐、堂の冖、光の乚、鬱の𠂭）における筆画分離・無重複性検証."""

    def test_su_tree_does_not_steal_top_dots(self):
        """『巣』において、下部 0.1.1 (木) が冠部 0.0 (𭕄) の冠筆画 (s1) を強奪せず、互いに排他的であること."""
        tree = _decompose("巣")
        res = glyph_service.extract_kanjivg_stroke_layers("巣", tree)
        assert res.get("has_kvg")

        top_dots = set(res["layer_strokes"].get("0.0", []))
        wood = set(res["layer_strokes"].get("0.1.1", []))

        assert top_dots == {"kvg:05de3-s1", "kvg:05de3-s2", "kvg:05de3-s3"}
        assert wood == {"kvg:05de3-s8", "kvg:05de3-s9", "kvg:05de3-s10", "kvg:05de3-s11"}
        assert not (top_dots & wood), "巣の木が上部の点を巻き込んでいます"

    def test_tou_radical_equivalence_clean_split(self):
        """『当』(⿱⺌彐) において、0.0 (⺌, 3画) と 0.1 (彐/⺕, 3画) が完全に3画ずつ分離されること."""
        tree = _decompose("当")
        res = glyph_service.extract_kanjivg_stroke_layers("当", tree)
        s0 = set(res["layer_strokes"].get("0.0", []))
        s1 = set(res["layer_strokes"].get("0.1", []))

        assert len(s0) == 3
        assert len(s1) == 3
        assert not (s0 & s1)

    def test_hikari_legs_clean_split(self):
        """『光』(⿱⺌兀) において、0.1.0 (丿) が s5、0.1.1 (乚) が s6 に1画ずつ正確に配分されること."""
        tree = _decompose("光")
        res = glyph_service.extract_kanjivg_stroke_layers("光", tree)
        s_left = set(res["layer_strokes"].get("0.1.0", []))
        s_right = set(res["layer_strokes"].get("0.1.1", []))

        assert s_left == {"kvg:05149-s5"}
        assert s_right == {"kvg:05149-s6"}
        assert not (s_left & s_right)

    def test_utsu_kanna_and_chou_disjoint(self):
        """『鬱』において、0.1.0.0.0 (凵) の2画 (s23, s24) と 0.1.0.0.1 (𠂭) の6画 (s17..s22) が重複なく完全分離されること."""
        tree = _decompose("鬱")
        res = glyph_service.extract_kanjivg_stroke_layers("鬱", tree)
        s_kanna = set(res["layer_strokes"].get("0.1.0.0.0", []))
        s_chou = set(res["layer_strokes"].get("0.1.0.0.1", []))

        assert s_kanna == {"kvg:09b31-s23", "kvg:09b31-s24"}
        assert s_chou == {
            "kvg:09b31-s17", "kvg:09b31-s18", "kvg:09b31-s19",
            "kvg:09b31-s20", "kvg:09b31-s21", "kvg:09b31-s22",
        }
        assert not (s_kanna & s_chou)


class TestCompositeClipRectSolid:
    """複合要素ノードが子要素の断片化クリップ矩形（union_clips）によって不要なゼブラ縞・縞模様で切り抜かれないことを検証."""

    @pytest.mark.parametrize("char,node_path,expected_char", [
        ("厳", "0.1", "敢"),
        ("巣", "0.1", "果"),
        ("病", "0.1", "丙"),
        ("墓", "0.0.1", "旲"),
    ])
    def test_composite_node_clip_rect_is_solid(self, char, node_path, expected_char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        layer = layers.get(node_path)
        assert layer is not None, f"文字 '{char}' にノード '{node_path}' が見つかりません"
        assert layer["char"] == expected_char
        # 複合親ノードは単一の完全な矩形（自身の bbox）でクリップされ、子要素の中空フレーム等による断片化がないこと
        assert len(layer["clip_rects"]) == 1
        assert layer["clip_rects"][0] == layer["bbox"]

    @pytest.mark.parametrize("char,node_path,expected_char", [
        ("厳", "0.1", "敢"),
        ("病", "0.1", "丙"),
        ("痛", "0.1", "甬"),
        ("店", "0.1", "占"),
    ])
    def test_enclosure_inner_component_does_not_steal_outer_frame(self, char, node_path, expected_char):
        tree = _decompose(char)
        out = glyph_service.build_interactive_ids_svg(tree)
        layers = {l["path"]: l for l in out["component_layers"]}
        layer = layers.get(node_path)
        assert layer is not None
        assert layer["char"] == expected_char
        # 独立したインク島を持つ内側要素は外枠（广、厂、疒等）を不当に共有せず、クリップ不要で鮮明に発色すること
        assert layer["needs_clip"] is False


class TestKanjiVGUnnamedNodeHierarchyAlignment:
    """KanjiVGとCHISEでトポロジーが異なる漢字（厳、帯、滞など）において、無名中間ノードの誤マッチングにより筆画が子要素に正しく配分されない問題を検証."""

    def test_gen_tare_and_subparts_strokes(self):
        """『厳』において、0.0.0 (𭕄) に s1..s3、0.0.1 (厂) に s4..s5、0.1 (敢) に s6..s17 が正確に割り当てられること."""
        tree = _decompose("厳")
        res = glyph_service.extract_kanjivg_stroke_layers("厳", tree)
        ls = res["layer_strokes"]

        assert set(ls.get("0.0.0", [])) == {"kvg:053b3-s1", "kvg:053b3-s2", "kvg:053b3-s3"}
        assert set(ls.get("0.0.1", [])) == {"kvg:053b3-s4", "kvg:053b3-s5"}
        assert set(ls.get("0.0", [])) == {"kvg:053b3-s1", "kvg:053b3-s2", "kvg:053b3-s3", "kvg:053b3-s4", "kvg:053b3-s5"}

        daring_strokes = {f"kvg:053b3-s{i}" for i in range(6, 18)}
        assert set(ls.get("0.1", [])) == daring_strokes
        # 敢 (0.1) の左側 0.1.0 (⿱一耳) は s6..s13、うち 0.1.0.1 (耳) は s8..s13
        assert set(ls.get("0.1.0", [])) == {f"kvg:053b3-s{i}" for i in range(6, 14)}
        assert set(ls.get("0.1.0.1", [])) == {f"kvg:053b3-s{i}" for i in range(8, 14)}
        # 敢 (0.1) の右側 0.1.1 (攵) は s14..s17
        assert set(ls.get("0.1.1", [])) == {"kvg:053b3-s14", "kvg:053b3-s15", "kvg:053b3-s16", "kvg:053b3-s17"}

    def test_daring_standalone_strokes(self):
        """『敢』単体において、左側 (⿱一耳) と右側 (攵) の筆画が正確に分離され、攵の筆画が左側に混入しないこと."""
        tree = _decompose("敢")
        res = glyph_service.extract_kanjivg_stroke_layers("敢", tree)
        ls = res["layer_strokes"]

        # 0.0 は左側 (s1..s8)、0.1 は右側 攵 (s9..s12)
        s_left = set(ls.get("0.0", []))
        s_right = set(ls.get("0.1", []))
        assert not (s_left & s_right)
        assert len(s_left) == 8
        assert len(s_right) == 4

    @pytest.mark.parametrize("char", [
        "厳", "蛍", "墓", "常", "億", "樹", "道", "問", "同", "国", "病", "司", "蚕", "班", "辯", "当", "光", "巣", "鬱", "敢", "金", "掴"
    ])
    def test_sibling_stroke_disjointness_across_corpus(self, char):
        """兄弟ノード間で筆画の重複・強奪・漏洩が一切存在しないこと（兄弟間排他性の不変条件）."""
        tree = _decompose(char)
        res = glyph_service.extract_kanjivg_stroke_layers(char, tree)
        if not res["has_kvg"]:
            return
        ls = res["layer_strokes"]

        def check_siblings(node):
            children = node.get("children", [])
            for i in range(len(children)):
                for j in range(i + 1, len(children)):
                    pa = children[i].get("path")
                    pb = children[j].get("path")
                    sa = set(ls.get(pa, []))
                    sb = set(ls.get(pb, []))
                    overlap = sa & sb
                    assert not overlap, f"文字 '{char}' において兄弟ノード {pa} と {pb} が筆画 {overlap} を重複保持しています"
            for c in children:
                check_siblings(c)

        check_siblings(tree)

    def test_kin_and_tsukamu_layer_strokes(self):
        """『金』および『掴』において、王・土・十・一・丷および囗の筆画配分が完全かつ高精度であること."""
        # 1. 金 (U+91D1)
        tree_kin = _decompose("金")
        res_kin = glyph_service.extract_kanjivg_stroke_layers("金", tree_kin)
        ls_kin = res_kin["layer_strokes"]
        assert ls_kin.get("0.0") == ["kvg:091d1-s1", "kvg:091d1-s2"]
        assert ls_kin.get("0.1.0") == ["kvg:091d1-s3", "kvg:091d1-s4", "kvg:091d1-s5", "kvg:091d1-s8"]
        assert ls_kin.get("0.1.0.0") == ["kvg:091d1-s3"]
        assert ls_kin.get("0.1.0.1") == ["kvg:091d1-s4", "kvg:091d1-s5", "kvg:091d1-s8"]
        assert ls_kin.get("0.1.0.1.0") == ["kvg:091d1-s4", "kvg:091d1-s5"]
        assert ls_kin.get("0.1.0.1.1") == ["kvg:091d1-s8"]
        assert ls_kin.get("0.1.1") == ["kvg:091d1-s6", "kvg:091d1-s7"]
        assert ls_kin.get("0.1.1.0") == ["kvg:091d1-s6"]
        assert ls_kin.get("0.1.1.1") == ["kvg:091d1-s7"]

        # 2. 掴 (U+63B4)
        tree_tsukamu = _decompose("掴")
        res_tsukamu = glyph_service.extract_kanjivg_stroke_layers("掴", tree_tsukamu)
        ls_tsukamu = res_tsukamu["layer_strokes"]
        assert ls_tsukamu.get("0.0") == ["kvg:063b4-s1", "kvg:063b4-s2", "kvg:063b4-s3"]
        assert ls_tsukamu.get("0.1.0") == ["kvg:063b4-s4", "kvg:063b4-s5", "kvg:063b4-s11"]  # 囗の底辺(s11)が正しく結合
        assert ls_tsukamu.get("0.1.1.0") == ["kvg:063b4-s6", "kvg:063b4-s7", "kvg:063b4-s8", "kvg:063b4-s9"]
        assert ls_tsukamu.get("0.1.1.0.0") == ["kvg:063b4-s6"]
        assert ls_tsukamu.get("0.1.1.0.1") == ["kvg:063b4-s7", "kvg:063b4-s8", "kvg:063b4-s9"]
        assert ls_tsukamu.get("0.1.1.0.1.0") == ["kvg:063b4-s7", "kvg:063b4-s8"]  # 十: 縦棒(s7)＋横棒(s8)
        assert ls_tsukamu.get("0.1.1.0.1.1") == ["kvg:063b4-s9"]  # 一: 底辺横棒
        assert ls_tsukamu.get("0.1.1.1") == ["kvg:063b4-s10"]  # 丶: 点

    def test_recursive_stroke_allocation_na_michi_machi(self):
        """『名』(夕/丶)、『道』(首/䒑/一)、『街』(亍/一/丁) の下位筆画が餓死せず完全配分されること."""
        # 1. 名 (夕 -> 𠂊 + 丶)
        res_na = glyph_service.extract_kanjivg_stroke_layers("名")
        ls_na = res_na["layer_strokes"]
        assert ls_na.get("0.0.0") == ["kvg:0540d-s1", "kvg:0540d-s2"]
        assert ls_na.get("0.0.0.0") == ["kvg:0540d-s1"]
        assert ls_na.get("0.0.0.1") == ["kvg:0540d-s2"]
        assert ls_na.get("0.0.1") == ["kvg:0540d-s3"]

        # 2. 道 (首 -> 䒑 + 自, 䒑 -> 丷 + 一)
        res_michi = glyph_service.extract_kanjivg_stroke_layers("道")
        ls_michi = res_michi["layer_strokes"]
        assert ls_michi.get("0.1.0") == ["kvg:09053-s1", "kvg:09053-s2", "kvg:09053-s3"]
        assert ls_michi.get("0.1.0.0") == ["kvg:09053-s1", "kvg:09053-s2"]
        assert ls_michi.get("0.1.0.0.0") == ["kvg:09053-s1"]
        assert ls_michi.get("0.1.0.0.1") == ["kvg:09053-s2"]
        assert ls_michi.get("0.1.0.1") == ["kvg:09053-s3"]

        # 3. 街 (亍 -> 一 + 丁)
        res_machi = glyph_service.extract_kanjivg_stroke_layers("街")
        ls_machi = res_machi["layer_strokes"]
        assert ls_machi.get("0.0.1.0") == ["kvg:08857-s1"]
        assert ls_machi.get("0.0.1.1") == ["kvg:08857-s2", "kvg:08857-s3"]
        assert ls_machi.get("0.0.1.1.0") == ["kvg:08857-s2"]
        assert ls_machi.get("0.0.1.1.1") == ["kvg:08857-s3"]


class TestCodeSimplificationAndDeduplication:
    """リファクタリングによる重複排除・簡素化および整合性検証テスト."""

    def test_get_equivalent_symbols_transitive_closure(self):
        """get_equivalent_symbols が全部品記号の推移的閉包を正確に生成すること."""
        eqs_sa = glyph_service.get_equivalent_symbols("⺕")
        assert "彐" in eqs_sa
        assert "ヨ" in eqs_sa

        eqs_sui = glyph_service.get_equivalent_symbols("氵")
        assert "水" in eqs_sui

        eqs_tsu = glyph_service.get_equivalent_symbols("⺍")
        assert "𭕄" in eqs_tsu

    def test_fallback_and_db_meta_schema_identical(self):
        """get_fallback_character_meta と row_to_meta が同一のメタデータキー体系を保持すること."""
        fallback = server.get_fallback_character_meta("名", "名")
        conn = server.get_db_connection()
        if conn is not None:
            cur = conn.execute("SELECT * FROM characters WHERE char = '名'")
            row = cur.fetchone()
            if row is not None:
                db_meta = server.row_to_meta(row, "名")
                assert set(fallback.keys()) == set(db_meta.keys())
                assert fallback["char"] == "名"
                assert db_meta["char"] == "名"

    def test_build_tier_and_stroke_filters(self):
        """区分および画数フィルターの条件節とパラメータが正しく生成されること."""
        clauses, params = server._build_tier_and_stroke_filters("joyo", 5, 10)
        assert len(clauses) == 3
        assert "c.grade IN" in clauses[0]
        assert "c.stroke_count >= ?" in clauses[1]
        assert "c.stroke_count <= ?" in clauses[2]
        assert params == [5, 10]

    def test_get_joyo_characters_cached(self):
        """常用漢字リストのキャッシュ取得が正常に機能すること."""
        joyo1 = server.get_joyo_characters()
        joyo2 = server.get_joyo_characters()
        assert joyo1 is joyo2
        if joyo1:
            assert len(joyo1) == 2136
            assert "名" in joyo1

    def test_render_audit_card_generation(self):
        """_render_audit_card が適切なHTMLカード構造を生成すること."""
        card_html = view_renderer._render_audit_card(
            path_label="0.1",
            char_label="木",
            role_label="旁",
            role_style="",
            svg_html="<svg></svg>",
            footer_left="第1階層",
            footer_right="筆画: 4画",
        )
        assert "audit-card" in card_html
        assert "0.1" in card_html
        assert "木" in card_html
        assert "旁" in card_html
        assert "第1階層" in card_html


class TestStopThirdColumnHoverUpdate:
    """ホバー時の第3カラム（検索結果）更新停止とクリック連動UXの一貫性検証."""

    def test_hover_handlers_do_not_trigger_search(self):
        js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        js_text = js_path.read_text(encoding="utf-8")

        # handleComponentHover 内でプレビュー検索APIが呼ばれていないこと
        assert "previewFindResults" not in js_text

        # handleComponentHover 内に executeFindSearch が存在しないこと
        match_hover = re.search(r"function handleComponentHover\([^\)]*\)\s*\{([\s\S]*?)\n\}", js_text)
        assert match_hover is not None
        assert "executeFindSearch" not in match_hover.group(1)

        # clearComponentHover 内に executeFindSearch が存在しないこと
        match_clear = re.search(r"function clearComponentHover\([^\)]*\)\s*\{([\s\S]*?)\n\}", js_text)
        assert match_clear is not None
        assert "executeFindSearch" not in match_clear.group(1)

    def test_click_triggers_search_and_locks_scope(self):
        js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        js_text = js_path.read_text(encoding="utf-8")

        # lockComponentScope 内で findChips 更新および executeFindSearch が呼ばれること
        match_lock = re.search(r"function lockComponentScope\([^\)]*\)\s*\{([\s\S]*?)\n\}", js_text)
        assert match_lock is not None
        body = match_lock.group(1)
        assert "state.findChips" in body
        assert "executeFindSearch()" in body

    def test_ui_and_css_coherent_ux(self):
        html_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
        html_text = html_path.read_text(encoding="utf-8")

        css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
        css_text = css_path.read_text(encoding="utf-8")

        # 不要となったリアルタイムホバープレビュートグルが除去されていること
        assert "realtimeHoverPreview" not in html_text
        assert ".realtime-preview-toggle" not in css_text

        # クリック連動のUXガイドが提供されていること
        assert "find-guide-hint" in html_text
        assert ".find-guide-hint" in css_text

        # HUDヒントがホバー＝字形確認、クリック＝選択・逆引き検索を案内していること
        assert "部品ホバーで字形確認 / クリックで選択・逆引き検索" in html_text


class TestFourthColumnWordsUI:
    """第4カラム（収録熟語・語彙検索 / 国語辞典）のUIおよび連携テスト."""

    def test_fourth_column_html_structure(self):
        html_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
        html_text = html_path.read_text(encoding="utf-8")

        # 第4カラム要素の存在検証
        assert 'id="columnWords"' in html_text
        assert "収録熟語・語彙（国語辞典）" in html_text
        assert 'id="wordsKeywordInput"' in html_text
        assert 'id="filterWordPosition"' in html_text
        assert 'id="filterWordTier"' in html_text
        assert 'id="wordsGrid"' in html_text
        assert 'id="wordsTotalCount"' in html_text

    def test_fourth_column_css_styling(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
        css_text = css_path.read_text(encoding="utf-8")

        # 4カラムグリッド定義とカードスタイルの存在検証
        assert ".words-grid" in css_text
        assert ".word-card" in css_text
        assert ".word-lemma" in css_text
        assert ".badge-freq-top" in css_text
        assert ".badge-pos" in css_text
        assert ".badge-position" in css_text

    def test_fourth_column_js_logic(self):
        js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        js_text = js_path.read_text(encoding="utf-8")

        # 熟語取得・描画ロジックの存在検証
        assert "loadWordsForCurrentKanji" in js_text
        assert "renderWordsGrid" in js_text
        assert "/api/words" in js_text
        assert "wordsFilter" in js_text


class TestBugRadicalFormMapAlignment:
    """Bug: glyph_service.RADICAL_FORM_MAP における部首対応ずれの防止."""

    def test_radical_form_map_correct_associations(self):
        # ⻗ (U+2ED7: CJK RADICAL RAIN) は「雨」と同値（「青」ではないこと）
        rain_equivs = glyph_service.get_equivalent_symbols("⻗")
        assert "雨" in rain_equivs
        assert "青" not in rain_equivs

        # ⻩ (U+2EE9: CJK RADICAL SIMPLIFIED YELLOW) は「黄」と同値（「麦」ではないこと）
        yellow_equivs = glyph_service.get_equivalent_symbols("⻩")
        assert "黄" in yellow_equivs or "黃" in yellow_equivs
        assert "麦" not in yellow_equivs and "麥" not in yellow_equivs

        # ⻨ (U+2EE8: CJK RADICAL SIMPLIFIED WHEAT) は「麦」と同値（「鹿」ではないこと）
        wheat_equivs = glyph_service.get_equivalent_symbols("⻨")
        assert "麦" in wheat_equivs or "麥" in wheat_equivs
        assert "鹿" not in wheat_equivs

        # ⻪ (U+2EEA: CJK RADICAL C-SIMPLIFIED FROG) は「黽」と同値（「麻」ではないこと）
        frog_equivs = glyph_service.get_equivalent_symbols("⻪")
        assert "黽" in frog_equivs or "黾" in frog_equivs
        assert "麻" not in frog_equivs

        # ⻈ (U+2EC8: CJK RADICAL C-SIMPLIFIED SPEECH) は「言」と同値（「谷」ではないこと）
        speech_equivs = glyph_service.get_equivalent_symbols("⻈")
        assert "言" in speech_equivs or "讠" in speech_equivs
        assert "谷" not in speech_equivs

        # ⺺ (U+2EBA: CJK RADICAL BRUSH ONE) は「肀/聿」と同値（「肉/月」ではないこと）
        brush_equivs = glyph_service.get_equivalent_symbols("⺺")
        assert "肀" in brush_equivs or "聿" in brush_equivs
        assert "肉" not in brush_equivs


class TestBugWordsQueryDeduplication:
    """Bug: 同一熟語内に同一漢字が複数出現する単語（日曜日、日日 等）の重複返却防止."""

    def test_query_words_no_duplicates(self):
        conn = server.get_db_connection()
        if conn is None:
            pytest.skip("SQLite DBが存在しません")
        res = server.query_words_db(conn, "日", position="all", limit=100)
        lemmas = [r["lemma"] for r in res["results"]]
        # 100件取得時に重複語が存在しないこと
        assert len(lemmas) == len(set(lemmas)), f"重複単語が存在します: {[w for w in set(lemmas) if lemmas.count(w) > 1]}"
        if "日曜日" in lemmas:
            assert lemmas.count("日曜日") == 1
        if "日日" in lemmas:
            assert lemmas.count("日日") == 1


class TestBugApiGlyphCodepointAndParam:
    """Bug: /api/glyph における U+XXXX コードポイント表記および q パラメータの解決."""

    def test_api_glyph_resolves_codepoint_and_q(self):
        handler = server.KanjiExplorerHandler.__new__(server.KanjiExplorerHandler)

        # U+86CD (蛍) のコードポイント表記指定
        handler.send_response = lambda code: None
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None
        handler.wfile = io.BytesIO()

        # q パラメータでの取得
        handler.handle_api_glyph({"q": ["蛍"]})
        svg_q = handler.wfile.getvalue().decode("utf-8")
        assert "<svg" in svg_q
        assert "path" in svg_q

        # c パラメータに U+86CD を指定
        handler.wfile = io.BytesIO()
        handler.handle_api_glyph({"c": ["U+86CD"]})
        svg_cp = handler.wfile.getvalue().decode("utf-8")
        assert "<svg" in svg_cp
        # 蛍のアウトラインが描画され、単なる "U+86CD" テキストフォールバックになっていないこと
        assert 'transform="translate(0, 880) scale(1, -1)"' in svg_cp











