# Systemic correctness and maintainability study

Completed on 2026-11-03 on `codex_improvements`, starting from `31fc35a` and the preceding uncommitted glyph repair. The investigation followed shared mechanisms through parsing, print rendering, KanjiVG allocation, ETL, packaged data, database queries, frontend requests, asset loading, and HTTP delivery. Each reproduced problem was repaired and committed separately, with regression coverage.

## Findings and general repairs

| Problem reproduced | Shared mechanism introduced or corrected | Commit |
| --- | --- | --- |
| Inner strokes of closed frames lost KanjiVG mappings. | Allocate from enclosure structure and stroke order; generalize the former 日-only rule. Match on a private layout tree and index AST nodes by path. | `39817bb` |
| Character/component requests had generation checks, while words depended on cancellation alone. Delayed JSON or stale errors could replace current word results. | One request-scope abstraction supplies cancellation and an identity check to each independent panel. Failed word requests clear stale data/counts. | `b162e9d` |
| Rendering a mutable tree twice changed output for 71 graded characters. | Print rendering owns its working copy; parsed trees and returned geometry do not alias. Diagnostics consume explicit layer ownership and geometry. | `c7c4a3a`, `fc785bf` |
| Character usage and reverse search used different direct/indirect rules. SQL grouping could also combine a path length with another row's `via_char`. | Both views share a query that selects one coherent path per target: direct first, then shortest indirect path, with deterministic ties. Counts and limits apply to distinct targets. | `39a5b83` |
| Concurrent first starts shared an extraction temporary filename. Failed extraction left temporary state. | Unique temporary files, complete-file atomic publication, cleanup on failure, and per-thread read-only connections. | `c8d4a3f` |
| ETL explored primary paths before alternative direct edges. An indirect discovery could hide a direct edge or a shorter route. | A reusable `ComponentGraph` seeds all direct edges before breadth-first traversal. Primary descendants and the six-level policy remain explicit. | `ca55563` |
| In-memory search matched substrings, stopped counting at the result limit, and advertised every match as direct. | Fallback search uses whole IDS tokens and the same graph traversal. It computes complete counts before limiting results and implements indirect/AND searches. Metadata-dependent queries return unavailable when their source is absent. | `9d718b3` |
| A temporary database failure could permanently cache unknown metadata or an empty navigation list. Mutable summaries could alias between nodes. | Request-local metadata reuse with independent node summaries; current navigation snapshots; failed stroke-count reads do not populate the cache. SQLite paths use escaped file URIs. | `88f9a76` |
| Cold parallel font requests intermittently raised `KeyError`. FontTools shares lazy table/file/glyph state. | Serialize loading and drawing under one manager lock, publish font/cmap pairs together, and close partially loaded resources on failure. | `c89db5c` |
| Missing/damaged glyph assets could become permanently cached absence. Truncated KanjiVG archives could raise uncaught read errors. | Cache font paths only after a usable font snapshot exists. Publish KanjiVG indexes only after successful loading and permit retries. | `d7863b6` |
| `U+110000` became the letter `U`; documented `u2d544` notation failed. Parser, routes, and glyph APIs disagreed about notation. | Shared scalar/entity notation parsing, explicit rejection of invalid scalars, consistent bare/wrapped entity handling, and matching frontend query preservation. | `260ebda` |
| Reading search ignored every chip after the first. | A dedicated reading-query helper applies every term with AND semantics while retaining display notation and kana variants. | `7b4fa62` |
| Bounding-box containment assigned 34 holes to the wrong outer contour. Bounding-box overlap could also select an island with no ink inside the component clip. | Pure polygon operations check actual straight-contour containment and clipped area. Empty assignments fall back to the clipped original outline, preserving winding. Curved contours retain their existing assignment when polygon estimates cannot establish emptiness. | `2900fa0` |
| Absolute paths, traversal, and symlinks could make a glyph name read SVG files outside the cache. | Resolve candidate paths and enforce the cache-directory boundary. | `037d406` |
| A writer committing between count and row queries produced a total of two with one returned row in all three search families. | A shared, nested read-snapshot wrapper keeps totals, rows, and usage categories consistent without committing a caller's transaction. | `808a00b` |
| HTML, JSON, SVG, and error HEAD responses still contained bodies in WSGI. HTTP clients had hidden this in earlier tests. | All response bodies go through one method-aware writer. GET lengths are retained; static HEAD avoids streaming the file. OPTIONS advertises HEAD support. | `01f57ef` |

## Stored-data repair

Before repair, **6,758 direct edges across 4,084 characters** were classified as indirect. `scripts/repair_component_closure.py` reconstructs the graph from stored edge provenance, backs up the database and package, and changes only derived closure paths in a transaction. It requires no raw-source downloads or full metadata rebuild.

The repair updated **25,996 paths**, inserted **17**, and deleted **none**. Updates include direct promotion, shorter paths, and deterministic `via_char` selection. The packaged database was regenerated from a consistent SQLite snapshot. Bidirectional SQL `EXCEPT` comparisons against the backup found **zero changes** in `characters`, `words`, `word_kanji`, and `component_edges`. Packaged SQLite integrity passed.

The workspace backup is `/tmp/kanji-component-closure-eyp_mby0`; this temporary location is not a deployment artifact. The repair script and graph regressions are committed. A fixture verifies repair idempotence and preservation of unrelated tables, and a packaged-data regression checks that stored direct edges are direct.

## Verification

The closing checks passed:

- **705 tests**, including controlled asynchronous completion, concurrent extraction, source recovery, concurrent font access, live/WSGI routes, graph cycles/depth limits, and writers committing between search queries.
- JavaScript syntax and expanded Vulture analysis, including `component_graph.py` and `geometry.py`.
- All **1,481,503 stored paths** passed independent SQL checks for missing direct edges, invalid indirect entry points, self-paths, invalid depths, and shortest-path violations along primary edges.
- All **2,999 graded characters** rendered repeatedly without mutating input trees or changing output. All **6,026 straight-contour holes** had containing outer contours; every graded character had a print glyph.
- Comparing KanjiVG output before and after contour ownership/recovery changes found **zero changed mappings** across those 2,999 characters.
- Four cold real-font trials with eight concurrent workers matched sequential outlines. The pre-fix experiment failed in two trials; the regression suite also exercises lazy access under controlled concurrency.
- Native Chrome SVG checks and visual inspection confirmed recovery for 滝, 紡, and 揃 and removal of unrelated hole-contour ink from 十 in 直. Raster rounding was examined separately from actual SVG rendering.

Repeat the checks with:

```bash
python3 -m pytest -q
node --check static/app.js
python3 -m vulture ids_parser.py glyph_service.py server.py view_renderer.py component_graph.py geometry.py vulture_whitelist.py --min-confidence 60
python3 scripts/audit_systemic_invariants.py
```

The audit command opens the extracted runtime database read-only and checks the full graded corpus. Start the server once to extract the packaged database if necessary, or supply `--database PATH`. Regression tests use temporary databases for concurrent writes and extraction failures.

## Maintainer contracts

- Parsed IDS structure is caller-owned. Renderers return independent geometry; consumers use layer fields for rendered bounds and sharing information.
- Known stroke-order rules are structural. Unmatched KanjiVG groups still use the existing geometry heuristic; replacing it wholesale with raw theoretical boxes lost valid mappings during investigation.
- Graph traversal seeds primary and alternative direct edges together, follows primary descendants, excludes self-cycles, and counts before pagination.
- SQL views share path classification and run related reads in one snapshot. Word direct/carrier membership remains intentionally overlapping when a word matches both routes.
- Request cancellation and result ownership are separate checks. Panels have independent scopes; every asynchronous completion must still own its scope before changing state.
- Unavailable sources must remain retryable. Mutable response data belongs to a request; static successful font snapshots may be reused.
- Asset reads stay within their configured directory. Only complete extracted databases are published. HTTP bodies obey the request method at a shared boundary.

No additional concrete systemic defect remained after the closing pass over these mechanisms. Glyph matching for unnamed components remains heuristic, and corpus-wide checks here cover the graded characters. Rare-character semantic accuracy and a full browser/device matrix require their own evidence.
