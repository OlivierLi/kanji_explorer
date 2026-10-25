# 漢字構造・部品探索システム (CHISE IDS Kanji Component Explorer)

A local, 100% offline interactive web application for decomposing kanji into hierarchical sub-components/radicals (downward exploration, e.g., `蛍` ➔ `𰃮` ➔ `𭕄` `U+2D544`) and performing reverse component lookups (`ids-find` upward exploration, ordered from most common to least common).

---

## Core Design Constraints (Read Before Modifying)

1. **100% Japanese UI & Metadata**:
   - Every label, badge, tooltip, IDC operator description, and database metadata field MUST remain in Japanese. Do not add English dictionary glosses or English UI strings.
2. **Print Style (`明朝体 / 印刷書体`) Vector Rendering**:
   - The interactive canvas renders true Mincho vector outlines extracted offline from `Jigmo.ttf`, `Jigmo2.ttf`, and `Jigmo3.ttf` (covering Unicode Basic through CJK Extensions A–J).
   - There is no 2D spatial block map (`空間分割マップ`); the SVG canvas occupies the full stage.
3. **Progressive Click-to-Lock Hierarchy Navigation (`段階的ロック階層探索`)**:
   - Loading a character always starts at **Level 1 (`第1階層`)** (`state.lockedPath = null`), where hovering highlights only direct Level 1 components (`depth === 1`).
   - **Clicking** a highlighted component on the canvas locks it in (`state.lockedPath = clickedPath`), dims sibling components outside the locked scope, updates the right-column reverse lookup (`逆引き検索`) to that component, and advances hover hit-testing to its direct children at the next level (`第2階層` ➔ `第3階層` ...).
   - Clicking `↺ 選択解除（リセット）` (`#btnResetLock`), `◀ 1階層戻る` (`#btnLockStepUp`), or pressing `Escape` unlocks and returns to Level 1.
4. **Stroke-Aware & Ink-Island Highlighting**:
   - Component highlighting is driven by connected ink islands (`_extract_ink_islands` and `_assign_ink_islands_to_tree` in `glyph_service.py`) combined with stroke-shaped/hollow-frame `clip_rects` rather than lighting up an entire rectangular bounding box.

---

## Repository Structure

| File | Responsibility |
| :--- | :--- |
| [`server.py`](server.py) | Zero-dependency Python HTTP server serving `/`, `/static/*`, `/api/char`, `/api/ids-find`, and `/api/glyph`. |
| [`ids_parser.py`](ids_parser.py) | Tokenizer and recursive AST parser for all 16 Unicode IDC operators (`⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻⿼⿽⿾⿿`), CHISE entity resolution (`CHISE_ENTITY_UNICODE_MAP`), sub-component decomposition (`COMPONENT_SUBDECOMPOSITIONS`), CJKVI circled-number placeholder filtering (`①`–`⑳`), and 2D spatial/stroke clip geometry (`compute_bboxes`). |
| [`glyph_service.py`](glyph_service.py) | Offline TrueType outline extractor (`Jigmo*.ttf`), connected ink-island & hole-contour analyzer (`_extract_ink_islands`), recursive island-to-AST partitioner (`_assign_ink_islands_to_tree`), and interactive SVG payload builder (`build_interactive_ids_svg`). |
| [`jp_metadata.py`](jp_metadata.py) | Japanese character metadata formatter, Unicode CJK block classifier, 214 Kangxi radical dictionary (`KANGXI_RADICALS`), and radical/variant equivalence table (`⺍` `U+2E8D` ⇄ `𭕄` `U+2D544`). |
| [`build_db.py`](build_db.py) | Offline ETL pipeline that builds `data/kanji_explorer.db` (SQLite) from `data/chise-ids/`, `data/cjkvi-ids.txt`, `data/kanjidic2.xml.gz`, `data/kanjivg.xml.gz`, `data/Unihan.zip`, and `data/EquivalentUnifiedIdeograph.txt`. |
| [`static/index.html`](static/index.html) | 3-column application layout (Left: Interactive Canvas + Progressive Lock Bar + HUD + Attributes; Middle: Alternative IDS Selector + Recursive Decomposition Tree; Right: `ids-find` Reverse Component Lookup). |
| [`static/styles.css`](static/styles.css) | Dark (`墨色`) & Light (`和紙`) theme styles, Mincho SVG slice/lock/hover transitions, and tree/card layout rules. |
| [`static/app.js`](static/app.js) | Frontend state management, SVG layer & `<clipPath>` rendering, progressive click-to-lock hit-testing, multi-character word breadcrumb splitting, and bidirectional canvas/tree/reverse-lookup synchronization. |

---

## Runtime & Deployment Assets

To enable zero-setup deployment on PythonAnywhere and offline WSGI environments:

- `data/kanji_explorer.db.gz`: Compressed SQLite database (~83 MB) containing characters, words, and component closures. Auto-extracted to `data/kanji_explorer.db` on first start.
- `data/kanjivg.xml.gz`: KanjiVG vector stroke data (~3.5 MB) used by `glyph_service.py` to render hand-drawn stroke orders.
- `data/chise-ids/` & `data/cjkvi-ids.txt`: CHISE and CJKVI IDS tables used by `ids_parser.py` for recursive character decomposition.
- `data/EquivalentUnifiedIdeograph.txt`: Unicode radical equivalence table used for Kangxi radical normalization.
- `static/fonts/Jigmo*.ttf`: Offline TrueType fonts used by both the browser and `glyph_service.py`.

## Uncommitted Local Assets (Ignored via `.gitignore`)

The following files are generated at runtime or used only when re-running the offline ETL build pipeline:

- `data/kanji_explorer.db`, `*.db-shm`, `*.db-wal`: Extracted SQLite database files.
- `data/kanjidic2.xml.gz`, `data/Unihan.zip`, `data/BCCWJ-LUW.zip`, `data/ja-extract.jsonl.gz`, `data/wnjpn.db.gz`: Raw datasets used only by `build_db.py` and `scripts/build_words_db.py`.

---

## Critical Technical Invariants & Gotchas

### 1. TrueType Contour Winding & Inner Holes (`glyph_service.py`)
- `Jigmo*.ttf` uses TrueType quadratic curves in a `1024×1024` EM square (`ascent = 880`).
- When transformed to screen coordinates via `(x, 880.0 - y)`:
  - **Outer stroke contours** have **positive** signed Shoelace area (`a >= 0`).
  - **Inner hole contours** (e.g., the enclosed counters inside `口`, `日`, `月`, `田`, `目`) have **negative** signed area (`a < 0`).
- `_extract_ink_islands` attaches each inner hole contour (`a < 0`) to its smallest enclosing outer contour (`a >= 0`) and records its normalized coordinates in `hole_boxes`. Never treat hole contours as standalone islands, or enclosing strokes will lose their counters and render as solid blocks.

### 2. SVG `clip-path` Coordinate Space (`static/app.js`)
- In `renderSvgInto()`, each `.print-component-slice` `<path>` has `transform="translate(0, 880) scale(1, -1)"` to flip font coordinates into screen coordinates.
- The `clip-path="url(#clip-...)"` attribute **must** be placed on the parent `<g class="print-component-slice-group">` wrapper (which is in `0..1024` screen space), **never** on the transformed `<path>` element itself.

### 3. Special Structural Geometries (`ids_parser.py` & `glyph_service.py`)
- **Overlay (`⿻`) & Multi-Dot Components (`𠂭`, `桜`)**:
  - `_assign_ink_islands_to_tree` partitions `large_spanning` islands (such as `㐅` in `𠂭` `⿻㐅⿳丶⿰丶丶丶`) from `small_local` islands (the 4 `丶` dots).
  - In `⿱`/`⿳` and `⿰`/`⿲`, children whose expected island count (`_expected_min_islands`, e.g., `3` for `⺍`/`𭕄`) is already satisfied by non-spanning islands do not inherit spanning islands.
- **Flanking Components (`挟み込み構造`: `林` in `鬱`, `行` in `街`, `辡` in `辯`, `玨` in `班`)**:
  - Detected in `compute_bboxes` (`c0["is_flanking"] = True`, `role_label = "両脇"`).
  - Emits two separate bounding boxes in `clip_rects` and `hit_rects` (`[left_flank_bbox, right_flank_bbox]`).
  - `renderSvgInto` in `static/app.js` renders one `<rect class="component-layer-hitbox">` per entry in `layer.hit_rects` so the center component (`缶` in `鬱`, `圭` in `街`) is never blocked by the flanking parent's hitbox.
- **Hole-Aware Hollow Frame for `口` / `中` (`蛍` ➔ `虫` ➔ `中` ➔ `口`)**:
  - `口` and `囗` generate 4 outer frame bars in `clip_rects` rather than a solid rectangle.
  - When `中` (`⿻口丨`) has an island with two side-by-side `hole_boxes` (`hl`, `hr`), `口`'s 4 frame bars are computed directly from the hole boundaries (excluding the `[hl[2], hr[0]]` gap where `丨` passes), `丨` is tightened to the vertical strip between the two holes, and composite nodes use the union of their children's `clip_rects`.

---

## Running & Verifying

### Start the Server
```bash
python3 server.py --port 8888
```
Then open `http://localhost:8888/` in a browser.

### Rebuild the SQLite Database (Only if changing ETL / DB schema)
```bash
python3 build_db.py
```

### Quick Verification Commands
```bash
# 1. Check frontend JavaScript syntax
node --check static/app.js

# 2. Test character decomposition & SVG layer generation
curl -s "http://localhost:8888/api/char?q=%E8%9B%8D" | python3 -m json.tool | head -n 40

# 3. Test reverse component lookup (ordered from most to least common)
curl -s "http://localhost:8888/api/ids-find?components=%F0%AD%95%84" | python3 -m json.tool | head -n 40
```
