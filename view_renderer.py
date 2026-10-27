"""全構成要素の並置プレビュー（Side-by-Side View）HTMLおよびSVGレンダラーモジュール。

KanjiVG筆画ハイライトおよび明朝体ベクター分解タイルカードを動的に合成し、
ブラウザでの全階層構造並置検証用HTMLを生成します。
すべてのユーザー向けラベル・文字列は日本語で表現されます。
"""

from __future__ import annotations

import html
import json
from typing import Any
import urllib.parse

import glyph_service
import ids_parser


def _render_audit_card(
    path_label: str,
    char_label: str,
    role_label: str,
    role_style: str,
    svg_html: str,
    footer_left: str,
    footer_right: str,
) -> str:
    """並置検証用タイルカードのHTML片を生成します。"""
    role_attr = f' style="{role_style}"' if role_style else ""
    return f'''
    <div class="audit-card">
      <div class="audit-card-header">
        <span class="audit-card-path">{html.escape(path_label)}</span>
        <span class="audit-card-char">{html.escape(char_label)}</span>
        <span class="audit-card-role"{role_attr}>{html.escape(role_label)}</span>
      </div>
      <div class="canvas-stage-wrapper audit-card-stage">
        <div class="canvas-grid-overlay"></div>
        <div class="canvas-svg-container">{svg_html}</div>
      </div>
      <div class="audit-card-footer">
        <span>{footer_left}</span>
        <span>{footer_right}</span>
      </div>
    </div>
    '''


def render_side_by_side_html(
    canonical_char: str,
    meta: dict[str, Any],
    params: dict[str, list[str]],
    prev_char: str = "",
    next_char: str = "",
    joyo_index: int | None = None,
    joyo_total: int = 0,
) -> str:
    """指定された漢字とその構成要素群の並置プレビューHTML文字列をレンダリングします。"""
    theme = params.get("theme", ["dark"])[0]
    if theme not in ("dark", "light"):
        theme = "dark"

    mode = params.get("mode", ["kvg"])[0]
    if mode not in ("kvg", "mincho"):
        mode = "kvg"

    # 1. 構文木・ベクターSVG分解
    tree = ids_parser.decompose_character(canonical_char, max_depth=6, compute_bbox=True)
    interactive_svg = glyph_service.build_interactive_ids_svg(tree)
    base_path = interactive_svg.get("base_path", "")
    layers = [l for l in interactive_svg.get("component_layers", []) if l.get("path") and l.get("path") != "0"]
    layers.sort(key=lambda l: (len(l.get("path", "").split(".")), l.get("path", "")))

    # KanjiVG ストロークデータの抽出（収録されている場合は筆画単位ハイライトを実施）
    kvg_res = glyph_service.extract_kanjivg_stroke_layers(canonical_char, tree)
    has_kvg = kvg_res.get("has_kvg", False)
    use_kvg = has_kvg and (mode == "kvg")
    all_kvg_strokes = kvg_res.get("all_strokes", [])
    layer_kvg_stroke_ids = kvg_res.get("layer_strokes", {})

    # 2. タイルカード生成
    cards_html: list[str] = []

    # 全体カード (Tile 0)
    if use_kvg and all_kvg_strokes:
        tile0_svg = f'''<svg viewBox="0 0 109 109" class="kvg-svg">
          <g class="kvg-root" style="stroke: var(--text-primary); fill: none; stroke-width: 3.4px; stroke-linecap: square; stroke-linejoin: miter; stroke-miterlimit: 4;">
            {"".join(f'<path d="{s["d"]}" class="kvg-stroke" style="opacity: 0.95;" />' for s in all_kvg_strokes)}
          </g>
        </svg>'''
    elif base_path:
        tile0_svg = f'''<svg viewBox="0 0 1024 1024" class="kvg-svg print-style-svg">
          <g class="kvg-root" data-path="0">
            <path d="{base_path}" transform="translate(0, 880) scale(1, -1)" class="print-base-glyph" />
          </g>
        </svg>'''
    else:
        tile0_svg = f'<div style="font-size: 7rem; font-family: var(--font-kanji);">{html.escape(canonical_char)}</div>'

    footer_tile0 = f"筆画: {len(all_kvg_strokes)}画 (KanjiVG)" if use_kvg else "全体アウトライン (明朝体)"
    cards_html.append(
        _render_audit_card(
            path_label="全文字 (0)",
            char_label=canonical_char,
            role_label="原字",
            role_style="background: rgba(110, 119, 129, 0.15); color: var(--text-secondary);",
            svg_html=tile0_svg,
            footer_left="全体表示",
            footer_right=footer_tile0,
        )
    )

    # 各部品カード (Tile 1..N)
    for idx, layer in enumerate(layers, 1):
        l_path = layer.get("path", "")
        l_char = layer.get("char") or layer.get("raw_char") or ""
        l_role = layer.get("role_label") or "部品"
        depth = len(l_path.split(".")) - 1
        bbox = layer.get("bbox") or [0, 0, 1, 1]

        active_stroke_ids = layer_kvg_stroke_ids.get(l_path, [])
        if use_kvg and active_stroke_ids:
            active_set = set(active_stroke_ids)
            bg_paths = "".join(
                f'<path d="{s["d"]}" class="kvg-stroke" />'
                for s in all_kvg_strokes if s["id"] not in active_set
            )
            fg_paths = "".join(
                f'<path d="{s["d"]}" class="kvg-stroke active-stroke" />'
                for s in all_kvg_strokes if s["id"] in active_set
            )
            tile_svg = f'''<svg viewBox="0 0 109 109" class="kvg-svg">
              <g class="kvg-root">
                <g class="kvg-bg-strokes" style="opacity: 0.18; stroke: var(--text-primary); fill: none; stroke-width: 3.2px; stroke-linecap: square; stroke-linejoin: miter; stroke-miterlimit: 4;">
                  {bg_paths}
                </g>
                <g class="kvg-active-strokes" style="opacity: 1.0; stroke: #ff5a36; fill: none; stroke-width: 4.2px; stroke-linecap: square; stroke-linejoin: miter; stroke-miterlimit: 4;">
                  {fg_paths}
                </g>
              </g>
            </svg>'''
            footer_detail = f"筆画: {len(active_stroke_ids)}画"
        else:
            clip_rects = layer.get("clip_rects") or [bbox]
            slice_path = layer.get("slice_path") or base_path
            should_clip = layer.get("needs_clip") is not False or not layer.get("slice_path") or layer.get("slice_path") == base_path
            uid = f"t{idx}"
            safe_path = l_path.replace(".", "_")

            rect_tags = []
            for cr in clip_rects:
                rx = int(round(cr[0] * 1024))
                ry = int(round(cr[1] * 1024))
                rw = int(round(cr[2] * 1024))
                rh = int(round(cr[3] * 1024))
                rect_tags.append(f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" />')
            defs_html = f'<defs><clipPath id="clip-{uid}-{safe_path}">{"".join(rect_tags)}</clipPath></defs>'
            clip_attr = f' clip-path="url(#clip-{uid}-{safe_path})"' if should_clip else ''

            tile_svg = f'''<svg viewBox="0 0 1024 1024" class="kvg-svg print-style-svg">
              {defs_html}
              <g class="kvg-root has-hovered-child" data-path="0">
                <path d="{base_path}" transform="translate(0, 880) scale(1, -1)" class="print-base-glyph" />
                <g class="component-vector-layer kvg-group hovered" data-path="{l_path}">
                  <g class="print-component-glow-wrapper">
                    <g class="print-component-slice-group"{clip_attr}>
                      <path d="{slice_path}" transform="translate(0, 880) scale(1, -1)" class="print-component-slice" />
                    </g>
                  </g>
                </g>
              </g>
            </svg>'''
            footer_detail = f"[{bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}, {bbox[3]:.2f}]"

        cards_html.append(
            _render_audit_card(
                path_label=l_path,
                char_label=l_char,
                role_label=l_role,
                role_style="",
                svg_html=tile_svg,
                footer_left=f"第{depth}階層",
                footer_right=footer_detail,
            )
        )

    grade_text = f"小学{meta.get('grade')}年" if meta.get("grade") else (meta.get("tier") or "漢字")
    strokes_text = f"{meta.get('stroke_count')}画" if meta.get("stroke_count") else ""
    radical_text = meta.get("radical", "")
    on_text = " / ".join(meta.get("on_readings", [])) if meta.get("on_readings") else "-"
    kun_text = " / ".join(meta.get("kun_readings", [])) if meta.get("kun_readings") else "-"
    ids_formula = ids_parser.get_character_ids(canonical_char) or tree.get("ids", "") or canonical_char
    joyo_badge_str = f"常用漢字 {joyo_index}/{joyo_total}" if joyo_index else "常用漢字外"

    theme_query = f"&theme={theme}" if "theme" in params else ""
    prev_link = f'<a href="/view?char={urllib.parse.quote(prev_char)}&mode={mode}{theme_query}" class="audit-btn nav-btn" title="前の漢字 (← キー)">◀ {html.escape(prev_char)}</a>' if prev_char else '<span class="audit-btn nav-btn" style="opacity:0.4;">◀ 前</span>'
    next_link = f'<a href="/view?char={urllib.parse.quote(next_char)}&mode={mode}{theme_query}" class="audit-btn nav-btn" title="次の漢字 (→ キー)">{html.escape(next_char)} ▶</a>' if next_char else '<span class="audit-btn nav-btn" style="opacity:0.4;">次 ▶</span>'

    full_html = f'''<!DOCTYPE html>
<html lang="ja" data-theme="{theme}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>【{html.escape(canonical_char)}】構成要素選択ハイライト並置ビュー | 漢字構造・部首ドリルダウン探索器</title>
  <link rel="stylesheet" href="/static/styles.css">
  <style>
    body.audit-view {{
      background: var(--bg-primary);
      color: var(--text-primary);
      font-family: var(--font-ui);
      margin: 0;
      padding: 0;
      min-height: 100vh;
    }}
    .audit-navbar {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-secondary);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    }}
    .audit-title-group {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .audit-char-badge {{
      font-family: var(--font-kanji);
      font-size: 2.2rem;
      line-height: 1;
      font-weight: bold;
      color: var(--accent-vermilion);
    }}
    .audit-meta-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .audit-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 0.78rem;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-secondary);
    }}
    .audit-badge.highlight {{
      border-color: var(--accent-vermilion);
      color: var(--accent-vermilion);
      font-weight: 600;
    }}
    .audit-controls {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .audit-search-form {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .audit-input {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 0.9rem;
      width: 140px;
    }}
    .audit-btn {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.85rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      transition: all 0.15s ease;
    }}
    .audit-btn:hover {{
      border-color: var(--accent-vermilion);
      color: var(--accent-vermilion);
    }}
    .audit-btn.nav-btn {{
      font-weight: 600;
    }}
    .audit-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 20px;
      padding: 24px;
      max-width: 1600px;
      margin: 0 auto;
    }}
    .audit-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
      display: flex;
      flex-direction: column;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    .audit-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.15);
    }}
    .audit-card-header {{
      padding: 10px 14px;
      background: var(--bg-secondary);
      border-bottom: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .audit-card-path {{
      font-family: monospace;
      font-size: 0.82rem;
      color: var(--text-muted);
    }}
    .audit-card-char {{
      font-family: var(--font-kanji);
      font-size: 1.25rem;
      font-weight: 600;
    }}
    .audit-card-role {{
      font-size: 0.78rem;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(255, 90, 54, 0.12);
      color: var(--accent-vermilion);
      font-weight: 500;
    }}
    .audit-card-stage {{
      aspect-ratio: 1 / 1;
      position: relative;
      background: var(--canvas-bg);
      padding: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .audit-card-stage .canvas-svg-container {{
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .audit-card-stage .kvg-svg {{
      width: 100%;
      height: 100%;
      max-width: 100%;
      max-height: 100%;
    }}
    .audit-card-footer {{
      padding: 8px 14px;
      background: var(--bg-secondary);
      border-top: 1px solid var(--border-color);
      font-size: 0.75rem;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
    }}
    .hide-bboxes .audit-bbox-outline {{
      display: none !important;
    }}
    .audit-btn.active {{
      background: var(--accent-vermilion);
      color: #fff !important;
      border-color: var(--accent-vermilion);
      font-weight: 600;
    }}
    .audit-mode-group {{
      display: inline-flex;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      overflow: hidden;
    }}
    .audit-mode-group .audit-btn {{
      border: none;
      border-radius: 0;
    }}
    .kvg-active-strokes .kvg-stroke,
    .kvg-stroke.active-stroke {{
      stroke: var(--accent-vermilion) !important;
      opacity: 1 !important;
      stroke-width: 4.2px !important;
    }}
    .kvg-bg-strokes .kvg-stroke {{
      opacity: 0.18 !important;
      stroke: var(--text-primary) !important;
      stroke-width: 3.2px !important;
    }}
    .toggle-checkbox-label {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.82rem;
      color: var(--text-secondary);
      cursor: pointer;
      user-select: none;
    }}
  </style>
</head>
<body class="audit-view hide-bboxes">
  <header class="audit-navbar">
    <div class="audit-title-group">
      <span class="audit-char-badge">{html.escape(canonical_char)}</span>
      <div>
        <div style="font-weight: 600; font-size: 1.05rem;">{html.escape(canonical_char)} ({html.escape(meta.get('codepoint', ''))}) 並置検証ビュー</div>
        <div class="audit-meta-group" style="margin-top: 4px;">
          <span class="audit-badge highlight">{joyo_badge_str}</span>
          <span class="audit-badge">{grade_text}</span>
          <span class="audit-badge">{strokes_text}</span>
          <span class="audit-badge">{html.escape(radical_text)}</span>
          <span class="audit-badge">IDS: {html.escape(ids_formula)}</span>
          <span class="audit-badge">音: {html.escape(on_text)}</span>
          <span class="audit-badge">訓: {html.escape(kun_text)}</span>
        </div>
      </div>
    </div>

    <div class="audit-controls">
      <div class="audit-mode-group">
        <a href="/view?char={urllib.parse.quote(canonical_char)}&mode=kvg{theme_query}" class="audit-btn {'active' if mode == 'kvg' else ''}">🖌 筆画表示 (KanjiVG)</a>
        <a href="/view?char={urllib.parse.quote(canonical_char)}&mode=mincho{theme_query}" class="audit-btn {'active' if mode == 'mincho' else ''}">🔤 印刷書体 (明朝体)</a>
      </div>
      <form class="audit-search-form" action="/view" method="get">
        <input type="hidden" name="mode" value="{mode}">
        {f'<input type="hidden" name="theme" value="{theme}">' if "theme" in params else ''}
        <input type="text" name="char" class="audit-input" placeholder="漢字・部品..." value="{html.escape(canonical_char)}">
        <button type="submit" class="audit-btn">表示</button>
      </form>
      <div style="display: flex; gap: 4px;">
        {prev_link}
        {next_link}
      </div>
      <label class="toggle-checkbox-label">
        <input type="checkbox" onchange="toggleBBox(this)">
        <span>BBox枠表示</span>
      </label>
      <button class="audit-btn" onclick="toggleTheme()" title="明暗テーマ切替">🌓</button>
      <a href="/?char={urllib.parse.quote(canonical_char)}" class="audit-btn" title="メイン探索器で開く">🎨 メイン画面</a>
    </div>
  </header>

  <main class="audit-grid">
    {''.join(cards_html)}
  </main>

  <script>
    const prevUrl = {json.dumps(f"/view?char={urllib.parse.quote(prev_char)}&mode={mode}{theme_query}" if prev_char else "")};
    const nextUrl = {json.dumps(f"/view?char={urllib.parse.quote(next_char)}&mode={mode}{theme_query}" if next_char else "")};

    function toggleTheme() {{
      const cur = document.documentElement.getAttribute('data-theme') || 'dark';
      const nxt = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', nxt);
      localStorage.setItem('kanji_theme', nxt);
    }}
    const urlParams = new URLSearchParams(window.location.search);
    const paramTheme = urlParams.get('theme');
    if (!paramTheme) {{
      const saved = localStorage.getItem('kanji_theme');
      if (saved) {{
        document.documentElement.setAttribute('data-theme', saved);
      }}
    }}
    function toggleBBox(cb) {{
      document.body.classList.toggle('hide-bboxes', !cb.checked);
    }}
    document.addEventListener('keydown', (e) => {{
      if (e.target.tagName === 'INPUT') return;
      if (e.key === 'ArrowLeft' && prevUrl) window.location.href = prevUrl;
      if (e.key === 'ArrowRight' && nextUrl) window.location.href = nextUrl;
    }});
  </script>
</body>
</html>'''

    return full_html
