"""
tests/test_fuzz_golden.py
fuzz.md Step 7: ファジング・ゴールデンコーパス回帰テストスイート。

tests/fuzz_golden.json に定義された実測インクシェア許容バンドと
構造不変条件（A1/A2/B1/B4）を検証し、リグレッションを自動防止します。
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import numpy as np

import ids_parser
import glyph_service
from scripts.fuzz import raster

GOLDEN_PATH = Path(__file__).resolve().parent / "fuzz_golden.json"


def load_golden_cases():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


GOLDEN_CASES = load_golden_cases()


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: f"{c['char']}_{c['description'][:10]}")
def test_fuzz_golden_ink_bands(case):
    char = case["char"]
    tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
    out = glyph_service.build_interactive_ids_svg(tree)
    R, layer_masks = raster.compute_all_layer_masks(char, out)
    tot_ink = float(np.sum(R))
    assert tot_ink > 50, f"文字 '{char}' のインクが取得できていません"

    layers_by_path = {l["path"]: l for l in out.get("component_layers", [])}

    for check in case.get("checks", []):
        path = check["path"]
        assert path in layers_by_path, f"レイヤー {path} が {char} の出力に見つかりません"
        layer = layers_by_path[path]

        # 1. 実測インクシェアの検証
        assert path in layer_masks, f"レイヤー {path} のインクマスクが生成されていません"
        mask = layer_masks[path]
        ink_pixels = float(np.sum(mask))
        ink_share = ink_pixels / tot_ink

        if "min_ink_share" in check:
            assert ink_share >= check["min_ink_share"], (
                f"文字 '{char}' パス {path} ({check.get('component')}) のインクシェアが過小です: "
                f"実測 {ink_share*100:.1f}%, 許容最小 {check['min_ink_share']*100:.1f}%"
            )
        if "max_ink_share" in check:
            assert ink_share <= check["max_ink_share"], (
                f"文字 '{char}' パス {path} ({check.get('component')}) のインクシェアが過大です (巣バグ型): "
                f"実測 {ink_share*100:.1f}%, 許容最大 {check['max_ink_share']*100:.1f}%"
            )

        # 2. 幾何境界の検証
        bbox = layer.get("bbox", [0, 0, 1, 1])
        h = bbox[3]
        y1 = bbox[1]
        y2 = bbox[1] + bbox[3]

        if "max_h" in check:
            assert h <= check["max_h"], (
                f"文字 '{char}' パス {path} の高さが過大です: h={h:.3f}, 上限={check['max_h']}"
            )
        if "max_y2" in check:
            assert y2 <= check["max_y2"], (
                f"文字 '{char}' パス {path} の下端が侵入しています: y2={y2:.3f}, 上限={check['max_y2']}"
            )
        if "min_y1" in check:
            assert y1 >= check["min_y1"], (
                f"文字 '{char}' パス {path} の上端が侵入しています: y1={y1:.3f}, 下限={check['min_y1']}"
            )


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: f"{c['char']}_oracles")
def test_fuzz_golden_oracles_clean(case):
    char = case["char"]
    tree = ids_parser.decompose_character(char, max_depth=6, compute_bbox=True)
    out = glyph_service.build_interactive_ids_svg(tree)

    # Oracle B において深刻な空インク (B4) や過大点灯 (B1) が対象パスで発生しないこと
    v_b = raster.check_oracle_b(char, tree=tree, out_svg_data=out)
    target_paths = {c["path"] for c in case.get("checks", [])}

    critical_b = [v for v in v_b if v.path in target_paths and v.oracle in ("B1", "B4", "B5", "B6")]
    assert not critical_b, f"文字 '{char}' のゴールデン対象レイヤーで深刻なインク違反が検出されました: {critical_b}"
