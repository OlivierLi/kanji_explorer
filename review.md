# Correctness review

**Status:** The historical findings below have been addressed in the working tree. See the [resolution addendum](#resolution-addendum--2026-11-02) for fixes, regression coverage, verification, and limits.

Reviewed on 2026-11-02 against commit `65d38e565b0b448c063de1867806b0d0d3a2ea70`, the current working tree, bundled source datasets, fonts, and local SQLite database. The working tree was clean at the start. This review adds documentation and reproduction artifacts; it does not change application code or rebuild the database.

**Assessment: the application has reproducible user-facing correctness defects despite all 510 existing tests passing.** The most consequential errors misidentify highlighted components, silently show another request's results, invent metadata after failures, or omit valid reading matches. The findings below concern observable behavior and learning accuracy, not style or preferred architecture.

Three agents investigated frontend/rendering, parser/glyph behavior, and metadata/ETL independently. The coordinating reviewer examined their evidence, reran the frontend and backend reproductions, inspected the rendered highlight image, and investigated server search behavior. All findings below are P2: substantive defects to fix in normal development. None of the evidence establishes a release-wide outage or warrants a P0/P1 claim. Numbering is for reference, not a strict ranking.

## Confirmed findings

### 1. Inner components of 日 and 目 highlight unrelated frame strokes

**Location:** `ids_parser.py:1341–1351`; connected-island fallback in `glyph_service.py:911–914,962–965`.

Load 日 in print/明朝体 mode and hover the inner 一 at path `0.1`. The highlight includes substantial segments of both outside vertical strokes, instead of just the internal horizontal stroke. The same problem affects 二 inside 目. A learner following the decomposition is shown incorrect boundaries for the named component.

The parser assigns fixed interior rectangles, and the glyph allocator gives both children the same connected ink island with clipping enabled. For 日 the API emits `[0.15,0.38,0.7,0.12]` for the interior clip; for 目 it emits `[0.15,0.24,0.7,0.52]`. These rectangles reach into the actual font's sidebars. Unlike the specialized 中 handling, these cases do not refine the interior against the holes.

The repository's 256-pixel raster model measures 620 shared pixels out of 1,512 inner-component pixels for 日, and 2,824 out of 5,328 for 目. These measurements were checked visually; they are not merely antialiasing or touching stroke junctions.

![日: outer component on the left, inner 一 on the right; selected ink is red](review_assets/day_component_highlights.png)

**Fix and verification:** derive the interior clips from the actual ink/hole boundaries so the frame retains its sidebars. Verify rendered masks for 日, 目, and nested occurrences. Do not treat every sibling overlap as an error: some decompositions legitimately share ink.

### 2. Both 匕 children of 比 in 麟 select the same right-hand strokes

**Location:** `glyph_service.py:2675–2683`, triggered by matching at `2959–2967`.

Load 麟 in KanjiVG mode, descend through 鹿 to 比, then select each 匕 child. Both children map to the right-hand pair. The left-hand pair belongs to the parent but is missing from both child mappings:

```text
0.0.1     [s8, s9, s10, s11]
0.0.1.0   [s10, s11]
0.0.1.1   [s10, s11]
```

These are the actual `/api/char?q=麟` mappings, with the common `kvg:09e9f-` prefix omitted above. The source KanjiVG names only the right-hand group 匕. Greedy equivalent-symbol matching assigns it to the first, left AST child, whose raw token is `&CDP-895F;`. Sequential fallback preserves that earlier assignment, advances its offset, and assigns the same pair again to the right child.

This is a component identity error, not an approximate highlight boundary. **Fix and verification:** reconcile position and existing stroke ownership before filling unmatched children. For this 比, require left `[s8,s9]`, right `[s10,s11]`, and complete parent coverage. Avoid a universal prohibition on shared strokes; the bundled 織 grouping legitimately overlaps.

### 3. A slower character request overwrites the latest selection

**Location:** `static/app.js:475–477,535–550`.

Start inspection of 日, then 月, and let 月 complete before 日. Execution of the actual frontend functions produces:

```text
CHAR_RACE {"currentChar":"日","selectedHistory":"月"}
```

Every response is applied unconditionally. There is no request generation check after fetching or parsing JSON. An older request can replace the glyph, decomposition, metadata, reverse search, and words while the history still identifies the newer choice. Different generation/cache costs make out-of-order completion a realistic condition during quick navigation. Alternative-structure requests use the same unguarded path.

**Fix and verification:** apply character data only if the request is still current; cancellation can supplement that check. Exercise out-of-order fetch and JSON completion, including a structure change followed by navigation to another character.

### 4. Reverse lookup can display results for an obsolete component

**Location:** `static/app.js:3727–3729,3762–3763`.

Search 木, change the chip to 水, and complete 水 before 木. The controlled frontend reproduction finishes with:

```text
FIND_RACE {"chips":["水"],"rendered":{"results":[{"char":"林"}],"keywords":["木"]}}
```

The function captures chips and filters before awaiting the request, then renders without checking whether they remain current. The visible relationship can therefore claim a result belongs to the current component when it belongs to an earlier one. Clearing all chips also fails to invalidate pending requests, allowing old results to reappear.

**Fix and verification:** independently invalidate reverse-search requests on chip, filter, and empty-search changes. Check that cards, highlighted tokens, and counts all belong to the latest query. This needs its own fix even after character request ordering is corrected, because users can change chips and filters without changing the character.

### 5. Back navigation leaves Forward disabled and the breadcrumb selection stale

**Location:** `static/app.js:4384–4396`; breadcrumb handler `4233–4235`; update guard `460–468`.

With history `[中,日]` at 日, click Back. The character changes to 中, but Forward remains disabled, Back remains enabled, and the breadcrumb selection is not refreshed. The actual frontend functions reproduce:

```text
BACK_BUTTONS { index: 0, backDisabled: false, forwardDisabled: true }
```

The handlers change `historyIndex` and call `inspectCharacter(..., false)`. All breadcrumb updates inside that function are conditional on recording history, so navigation skips them. The user cannot use Forward to undo the Back action, despite the forward entry still existing.

**Fix and verification:** refresh navigation controls whenever the index changes, independently of recording a new entry. Test Back, Forward, and direct breadcrumb selection, including both ends of history.

### 6. Multi-character input selects an old occurrence instead of the new sequence

**Location:** `static/app.js:451`.

Starting with history `[中,日]` at 日, enter 中国. The application appends the word's characters but locates the active entry with `history.indexOf(chars[0])`. It selects the earlier 中:

```text
WORD_HISTORY {"history":["中","日","中","国"],"index":0,"next":"日"}
```

Forward consequently targets 日 rather than the intended next character 国. This breaks the documented multi-character exploration flow and remains after fixing the stale controls in finding 5.

**Fix and verification:** track the start index of the newly added sequence, accounting for consecutive-character deduplication. Test a word whose first character already occurs earlier in history and a word starting with the current last entry.

### 7. API failure silently fabricates character facts

**Location:** `static/app.js:483–508`, rendered at `3381–3382`.

Return HTTP 500 for inspection of 一. The actual metadata card shows:

```text
10画 ／ 部首情報取得中...
```

The fallback hardcodes `stroke_count:10`, a CJK block, a normal-character tier, and a basic-character badge. It does not visibly identify these as fabricated fallback values. Network failures and other non-OK responses reach the same branch. The user receives false educational facts precisely when authoritative data is unavailable; 一's stroke count is an especially clear example.

**Fix and verification:** expose an unavailable/error state and unknown fields, or explicitly label trustworthy cached data. Never invent stroke counts or classifications to fill a failed request. Cover HTTP errors and rejected requests, including characters outside the embedded presets.

### 8. Ordinary kana searches miss readings containing dictionary notation

**Location:** `server.py:1203–1217`.

The database stores KANJIDIC okurigana separators in readings: 食 has `た.べる`, 読 has `よ.む`, and 書 has `か.く`. Reading search applies `LIKE` directly to these stored strings without normalizing the notation.

Actual endpoint results with `limit=500`:

```text
/api/ids-find?components=たべる  -> total 1, [噇], missing 食
/api/ids-find?components=よむ    -> total 0, missing 読
```

These omissions are not result truncation. Searching the literal dotted reading does not solve the problem: `た.べる` fails the all-kana test and is handled as a component query. Learners cannot reliably find familiar characters using their ordinary readings.

**Fix and verification:** normalize reading notation for matching while retaining the original form for display. Test full inflected dictionary readings such as たべる/よむ, kana variants, and notation boundaries so normalization does not create spurious matches across separate readings.

### 9. Unihan fallback stores romanization that the kana search cannot match

**Location:** `build_db.py:388–402`; exposed by `server.py:1203–1220`.

When KANJIDIC readings are absent, the ETL copies `kJapaneseOn` and `kJapaneseKun` unchanged. Their uppercase romanization then suppresses the later kana-valued `kJapanese` fallback. The bundled source for 嫫 contains:

```text
kJapanese     モ ボ しこめ
kJapaneseOn   BO MO
kJapaneseKun  SHIKOME
```

Yet `/api/char?q=嫫` returns on-readings `["BO","MO"]` and kun-readings `["SHIKOME"]`. `/api/ids-find?components=しこめ&limit=500` returns only 𡠜, omitting 嫫. Copying the romanized display text into search is not a workaround: non-kana text follows component search. A read-only count found 1,129 character rows containing uppercase Latin text in the reading columns.

**Fix and verification:** use the available kana source or normalize romanized fallback data into the supported representation before storage, then regenerate the packaged database. Verify both metadata and kana lookup for 嫫. A display-only conversion does not repair search. This is separate from finding 8: removing okurigana separators cannot fix incompatible source encoding.

### 10. Adjectives and interjections are mislabeled as verbs

**Location:** `scripts/build_words_db.py:43–46,59–60`; word-card badge at `static/app.js:4132–4137`.

`map_pos_title` tests the substring `動詞` before the specific categories `形容動詞` and `感動詞`. Both specific names contain the substring, so both take the verb branch. The error is stored in the database and displayed unchanged.

```text
map_pos_title("形容動詞") -> 動詞
map_pos_title("感動詞")   -> 動詞
/api/words?kanji=大&keyword=大切&scope=direct -> 大切, pos 動詞
```

The current database also labels 稀有 and 緻密 as 動詞. The agent's source-to-database scan found 1,199 shape-adjective source records and 30 interjection source records matched to verb-labeled rows. These are matched source-record counts, not a claim about distinct monosemous lemmas. No 形容動詞 or 感動詞 category exists in the bundled words table.

**Fix and verification:** match specific categories before broad substrings, or parse exact categories, and rebuild the words database. Test common adjective 大切 and an interjection through the API, not just the mapping helper. The existing behavior teaches the wrong grammatical category.

### 11. Audit pages render classification codes as impossible school years

**Location:** `view_renderer.py:187`.

The renderer turns every nonzero `grade` into `小学{grade}年`. Real routed HTML shows:

```text
/view?char=蛍 -> 小学8年
/view?char=凜 -> 小学9年
```

Elsewhere the same application correctly formats grade 8 as 常用漢字 and grade 9 as 人名用漢字. The audit page therefore presents false educational classifications, not just an inconsistent wording choice.

**Fix and verification:** use the existing grade semantics; restrict primary-school years to codes 1–6 and handle classification codes separately. Verify grades 1, 6, 8, 9, 10, and missing data using actual rendered HTML.

### 12. Indirect search counts and returned results use different classification rules

**Location:** `server.py:1307–1325,1334–1353`.

Actual query `/api/ids-find?components=食&mode=indirect&limit=500` reports `total:101` but returns **108 distinct results**. Equivalent component forms can have both direct and indirect closure rows for the same target. The count groups first and uses `MAX(is_direct)`, classifying any direct match as direct; the result query instead filters to indirect rows before grouping, retaining those mixed targets.

The displayed total is thus smaller than the number of returned cards. A target may also be labeled direct in the all-results view and indirect after filtering. The problem is the inconsistent aggregation, regardless of whether the product chooses exclusive categories or permits membership in both.

**Fix and verification:** choose one category rule and apply it consistently to counts, filtering, and result badges after equivalent forms are combined. Reproduce with 食 and check a target with both kinds of equivalence matches. Ensure a complete, untruncated result set agrees with its advertised total.

## Reproducing the evidence

From the repository root:

```bash
python3 -m pytest -q
node --check static/app.js
python3 review_assets/reproduce_backend.py
node review_assets/reproduce_frontend.cjs
python3 review_assets/reproduce_glyphs.py
```

The backend script exercises actual WSGI routes and the local database without opening a port. The frontend script executes actual `app.js` functions in a Node VM with a minimal DOM and controlled fetch promises. It prints defect states; it is not a browser end-to-end test or a regression suite asserting desired behavior. The glyph script prints actual API stroke mappings and raster measurements. Raster checks require the dependencies already used by `scripts/fuzz/raster.py`.

The observed backend output includes missing 食/読/嫫, `INDIRECT_COUNT advertised 101 returned 108`, `WORD_POS [('大切','動詞')]`, romanized 嫫 readings, and the impossible grade labels. Frontend output is quoted in findings 3–7. The scripts are evidence artifacts; a future fix should replace these defect observations with assertions of correct behavior.

## Scope, test results, and limits

| Area | Evidence gathered | Interpretation |
| --- | --- | --- |
| Existing suite | `510 passed in 7.72s` | The present assertions pass; they do not cover the reproduced defects sufficiently. |
| Frontend syntax | `node --check static/app.js` passed | Syntax is valid; this does not establish interaction correctness. |
| Frontend interactions | Controlled asynchronous execution and real function calls | Confirms request/state and history errors. No real-browser layout, pointer-hit testing, or accessibility certification. |
| Server and metadata | WSGI routes, read-only SQL, ETL source, bundled raw datasets | Confirms current persisted and returned errors. Full ETL was not rerun against the user's database. |
| Parser and print glyphs | Source review, existing corpus, raster scan of all 2,136 characters returned by `get_joyo_characters()` | Agent reported no scan exceptions or empty-highlight B4 failures, 13 investigated top-level/one-parent-level B2 overlap warnings, and no B3 coverage warnings at that scope. This does not certify every deeper component or rare character. |
| KanjiVG | Existing-corpus sibling mapping scan and targeted API/source checks | 麟 confirmed. 織 overlap follows the source grouping and was excluded; 塞 remained unproven and was not promoted to a finding. |

The 13 raster warnings are investigation signals, not 13 additional bugs. 日 and 目 were verified as one shared defect. Other speculative observations and cosmetic discrepancies were excluded. Existing tests mentioning an earlier `review.md` were treated as tests, not evidence that historical findings still apply.

The review did not perform a full rare-character audit, a browser/device matrix, a fresh deployment with compressed-database extraction, or a comprehensive security/performance audit. It establishes the concrete defects above and records what was checked; it does not claim the rest of the application is bug-free.

**Recommended repair order:** protect request consistency and remove fabricated facts; repair history navigation and reading lookup; correct source metadata and rebuild packaged data; fix confirmed component mappings and grade/count presentation. For each repair, add a regression that checks the user's observable result rather than a broad geometric bound or successful HTTP status alone.

---

## Resolution addendum — 2026-11-02

The findings, source locations, measurements, and image above are preserved as the historical review of the pre-fix revision. Their line references and defect outputs describe that revision, not the repaired working tree. The following changes address all 12 confirmed findings; this is a record of the checked cases, not a claim of universal correctness.

| Finding | Implemented resolution | Regression coverage |
| --- | --- | --- |
| 1 | Print glyph allocation derives 日/目 interior bars and frame clips from actual counter boundaries, including nested occurrences. Rechecking the original 256-pixel measurements yielded 8 shared pixels out of 520 interior pixels for 日 and 16 out of 1,040 for 目, attributable to boundary rounding rather than highlighted sidebars. | `tests/test_glyph_review_fixes.py`: rendered masks for 日, 目, 明, 相, and multiple levels of 晶; nonempty bars, bounded boundary overlap, and parent coverage. |
| 2 | Repeated KanjiVG children reconcile stroke ownership before fallback allocation. 麟 now assigns left 匕 `[s8,s9]` and right 匕 `[s10,s11]`, together covering 比. Legitimate shared source strokes remain supported. | `tests/test_glyph_review_fixes.py`: exact 麟 stroke pairs and preservation of 織's shared stroke. |
| 3 | Character requests use a generation check after asynchronous completion, including JSON parsing and failed requests; obsolete structure requests cannot replace later navigation. | `tests/frontend_review.cjs`, executed by `tests/test_frontend_review.py`: controlled fetch/JSON ordering and stale structure-request failure. |
| 4 | Reverse searches have an independent request generation, invalidated by new searches and clearing chips. Stale successes and failures cannot replace the current cards, keywords, or counts. | Frontend regression files above: delayed JSON, filter-only changes, stale HTTP failure, and clearing chips during a pending request. |
| 5 | Breadcrumbs and Back/Forward controls refresh independently of recording a new history entry. | Frontend regression files above: actual Back, Forward, and breadcrumb click handlers, including history endpoints. |
| 6 | Multi-character input records the start of the newly appended sequence, accounting for deduplication against the current final entry. | Frontend regression files above: an earlier occurrence of 中, a sequence starting at the last entry, and repeated consecutive characters. |
| 7 | Embedded demo character and reverse-search data were removed. Failed character requests show Japanese unavailable messages and unknown metadata, with no invented stroke counts, classifications, or structures. Failed notation/entity/IDS queries leave the codepoint unknown rather than treating the query prefix as a character. Failed reverse searches show unavailable results and `未詳` counts. | Frontend regression files above: HTTP and rejected requests, including former embedded preset characters and notation/entity/IDS queries, actual metadata-card rendering, and unavailable reverse-search counts. |
| 8 | Reading matching normalizes dictionary notation and kana variants while retaining reading boundaries and original display notation. | `tests/test_backend_review_fixes.py`: route results for たべる/タベル and よむ/ヨム, plus a fixture preventing matches across separate readings. |
| 9 | Unihan import uses available kana and converts legacy romanized fallback readings. A targeted repair updated persisted reading metadata and the packaged database. | `tests/test_backend_review_fixes.py`: source conversion, persisted 嫫 readings, しこめ lookup, and extraction of the repaired compressed database. |
| 10 | Specific part-of-speech categories precede the broad 動詞 match. A targeted source-backed repair corrected persisted adjective/interjection labels. | `tests/test_backend_review_fixes.py`: mapping categories, actual 大切 and interjection API results, and packaged data. |
| 11 | Audit HTML distinguishes primary-school years 1–6 from 常用漢字/人名用漢字 classification codes. | `tests/test_backend_review_fixes.py`: rendered HTML for grades 1, 6, 8, 9, 10, and missing data. |
| 12 | Counts, filtering, and result badges classify targets after equivalent component forms are combined, with direct matches taking precedence. | `tests/test_backend_review_fixes.py`: actual 食 queries, full-result totals, mutually exclusive categories, and matching badges. |

The metadata repair updated 1,129 character rows and 1,223 word part-of-speech rows, then regenerated `data/kanji_explorer.db.gz`. The pre-repair backup is at `/tmp/kanji-review-metadata-uwr6s9ax` in this workspace. The repair is targeted; no full ETL rebuild was performed. Regression coverage extracts the packaged database, checks SQLite integrity, and verifies repaired representative records and nonempty component closure data. Independent bidirectional SQL `EXCEPT` comparisons against the backup returned zero differences in both directions for every character column except `ja_on`/`ja_kun`, every word column except `pos`, and the complete `component_edges`, `component_closure`, and `word_kanji` tables. The repaired local database passed SQLite integrity checking, and the SHA-256 of the decompressed packaged database exactly matched the repaired database snapshot.

The coordinating check reran the original reproducers and observed the reported cases corrected. Chrome DOM checks also passed for character/reverse request ordering, unavailable-result counts, Back/Forward, and multi-character exploration. Visual inspection of the corrected 日/目/明/相 masks found no highlighted sidebars in the inner components. The final combined suite passed **540 tests in 16.77 seconds**; `node --check static/app.js` and the focused frontend regression also passed. The original evidence scripts remain historical diagnostic tools; the new regression files assert the desired behavior.

These checks do not certify every rare character, every nested geometry, every metadata record, or a browser/device matrix. Small raster boundary overlap remains expected, and KanjiVG source groupings can legitimately share strokes.
