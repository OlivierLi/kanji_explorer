/**
 * 漢字構造・部首ドリルダウン探索器 フロントエンド制御スクリプト
 * 100% 日本語UI、CHISE IDS・KanjiVG・Unicodeブロック統合、双方向連動ホバー、
 * マウスホイール階層切替、多要素逆引き（ids-find）対応
 */

// =============================================================================
// 1. 定数
// =============================================================================

// IDC 演算子日本語メタデータ
const IDC_OPERATORS = {
  "⿰": { name: "左右構造", short: "左右", parts: ["左", "右"] },
  "⿱": { name: "上下構造", short: "上下", parts: ["上", "下"] },
  "⿲": { name: "左中右構造", short: "左中右", parts: ["左", "中", "右"] },
  "⿳": { name: "上中下構造", short: "上中下", parts: ["上", "中", "下"] },
  "⿴": { name: "全包囲構造(国構え等)", short: "全包囲", parts: ["外囲", "内側"] },
  "⿵": { name: "上三方包囲(同構え等)", short: "上包囲", parts: ["上囲", "内側"] },
  "⿶": { name: "下三方包囲(凶構え等)", short: "下包囲", parts: ["下囲", "内側"] },
  "⿷": { name: "左三方包囲(区構え等)", short: "左包囲", parts: ["左囲", "内側"] },
  "⿸": { name: "左上包囲(垂れ)", short: "左上包囲", parts: ["垂れ", "内側"] },
  "⿹": { name: "右上包囲(包み構え)", short: "右上包囲", parts: ["包み", "内側"] },
  "⿺": { name: "左下包囲(繞・にょう)", short: "左下包囲", parts: ["繞", "内側"] },
  "⿻": { name: "重ね・交差構造", short: "重ね", parts: ["要素1", "要素2"] },
  "⿼": { name: "右三方包囲", short: "右包囲", parts: ["右囲", "内側"] },
  "⿽": { name: "右下包囲", short: "右下包囲", parts: ["右下囲", "内側"] },
  "⿾": { name: "反転(鏡像)", short: "反転", parts: ["反転対象"] },
  "⿿": { name: "回転", short: "回転", parts: ["回転対象"] }
};

// =============================================================================
// 2. アプリケーション状態管理
// =============================================================================

const state = {
  currentChar: "中",
  history: ["中"],
  historyIndex: 0,
  activeDisplayMode: "kvg", // 'kvg' (KanjiVG筆画表示 - デフォルト), 'mincho' (明朝体印刷書体)
  lockedPath: null,         // 段階的ロック階層パス (例: null, "0.0", "0.0.0")
  activeStructureIndex: 0,
  charData: null,
  hoveredPath: null,
  hoveredAncestors: [],
  wheelIndex: 0,
  findChips: new Set(["中"]),
  wordsData: null,
  wordsFilter: {
    position: "all",
    tier: "all",
    keyword: "",
    scope: "all"
  },
  theme: (typeof localStorage !== "undefined" && localStorage.getItem("kanji_theme")) || "light"
};

// Each panel owns one request scope. Aborting saves work; the identity check
// also rejects stale completions when cancellation arrives too late.
function createRequestScope() {
  let current = null;
  return {
    begin() {
      if (current) current.abort();
      const controller = new AbortController();
      current = controller;
      return {
        signal: controller.signal,
        isCurrent: () => current === controller && !controller.signal.aborted
      };
    }
  };
}

const characterRequests = createRequestScope();
const findRequests = createRequestScope();
const wordsRequests = createRequestScope();

/**
 * HTML/SVG属性値のエスケープ
 */
function escapeAttr(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// =============================================================================
// 3. ユーティリティ関数群
// =============================================================================

/**
 * コードポイント表記（U+XXXX, uXXXX, 0xXXXX, 4〜6桁16進数）かどうかを判定
 */
function isCodepointNotation(token) {
  if (!token || typeof token !== "string") return false;
  return /^(?:[Uu][+\s]|0[xX])/.test(token)
    || /^(?:[Uu][0-9a-fA-F]{1,6}|[0-9a-fA-F]{4,6})$/.test(token);
}

/**
 * CHISE外字実体参照表記（&...; または CDP-XXXX 等の裸表記）かどうかを判定
 */
function isEntityNotation(token) {
  if (!token || typeof token !== "string") return false;
  return /^&[0-9A-Za-z_+.'-]+;?$/.test(token)
    || /^(?:CDP|GT|MJ|M|C[1-7]|J90|CB|HZK|SW-JIGUGE)-[0-9A-Za-z_+.'-]+$/i.test(token);
}

/**
 * CHISE外字実体参照やUnicode文字を適切なHTML要素として描画
 */
function renderGlyphHTML(token, cssClass = "") {
  if (!token) return "";
  const isEntity = isEntityNotation(token);
  const entityToken = isEntity ? `&${token.replace(/^&|;$/g, "")};` : token;
  const safeCls = escapeAttr(cssClass);
  const safeTok = escapeAttr(entityToken);
  if (isEntity) {
    const safeSrc = `/api/glyph?c=${encodeURIComponent(entityToken)}`;
    return `<img src="${safeSrc}" class="entity-glyph-img ${safeCls}" alt="${safeTok}" onerror="this.outerHTML='<span class=\\'kanji-text\\'>${safeTok}</span>'">`;
  }
  return `<span class="kanji-text ${safeCls}">${safeTok}</span>`;
}

/**
 * コードポイントを16進表記文字列または実体識別子に変換
 */
function getCodepointHex(char) {
  if (!char) return "";
  if (isEntityNotation(char)) {
    const body = char.replace(/^&|;$/g, "");
    const match = body.match(/^(CDP|GT|MJ|M|C[1-7]|J90|CB|HZK|SW-JIGUGE)-(.+)$/i);
    if (match) {
      const parts = match[2].split("-").map(p => /^[0-9a-fA-F]{4,6}$/.test(p) ? p.toUpperCase() : p);
      return `${match[1].toUpperCase()}-${parts.join("-")}`;
    }
    return body;
  }
  if (isCodepointNotation(char)) {
    const m = char.match(/^(?:[Uu](?:\+|\s+)?|0[xX])([0-9a-fA-F]+)$/) || char.match(/^([0-9a-fA-F]{4,6})$/);
    if (m) {
      const cp = parseInt(m[1], 16);
      if (cp <= 0x10FFFF && (cp < 0xD800 || cp > 0xDFFF)) {
        return `U+${cp.toString(16).toUpperCase()}`;
      }
    }
    return char.toUpperCase();
  }
  if (Array.from(char).length === 1) {
    try {
      const cp = char.codePointAt(0);
      return `U+${cp.toString(16).toUpperCase()}`;
    } catch (e) {
      return char;
    }
  }
  return "未詳";
}

function tokenizeIds(idsStr) {
  return idsStr ? (idsStr.match(/&[^;\s]+;|[\s\S]/gu) || []) : [];
}

function renderIdsHTML(idsStr, highlightKeywords = []) {
  if (!idsStr) return "";
  const hlSet = new Set((highlightKeywords || []).map(k => k.trim()));
  return tokenizeIds(idsStr).map(tok => {
    const isHl = hlSet.has(tok) || (tok.startsWith("&") && hlSet.has(tok.slice(1, -1)));
    const html = tok in IDC_OPERATORS
      ? `<span class="ids-operator" title="${IDC_OPERATORS[tok].name}">${escapeAttr(tok)}</span>`
      : renderGlyphHTML(tok);
    return isHl ? `<span class="result-ids-highlight">${html}</span>` : html;
  }).join("");
}

// =============================================================================
// 4. データ取得 & 検査ロジック
// =============================================================================

/**
 * 指定文字の構文解析およびメタデータをロード
 * @param {string} charOrToken - 調査対象の漢字または文字トークン
 * @param {boolean} recordHistory - 探索履歴に記録するかどうか
 * @param {string} altIds - 構造切替時のカスタムIDS指定（省略時は標準構造）
 */
async function inspectCharacter(charOrToken, recordHistory = true, altIds = "") {
  if (!charOrToken) return;
  const token = charOrToken.trim();
  if (!token) return;

  const request = characterRequests.begin();

  const idcRegex = /^[⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻⿼⿽⿾⿿]/;
  const isCodepoint = isCodepointNotation(token);
  const isEntity = isEntityNotation(token);
  const isIdc = idcRegex.test(token);

  let effectiveToken = token;
  if (!isCodepoint && !isEntity && !isIdc) {
    const chars = Array.from(token.replace(/\s+/g, ""));
    if (chars.length > 1) {
      if (recordHistory && !altIds) {
        if (state.historyIndex < state.history.length - 1) {
          state.history = state.history.slice(0, state.historyIndex + 1);
        }
        const sequenceStart = state.history.length - (state.history.at(-1) === chars[0] ? 1 : 0);
        chars.forEach(ch => {
          if (state.history[state.history.length - 1] !== ch) {
            state.history.push(ch);
          }
        });
        state.historyIndex = sequenceStart;
      }
      effectiveToken = chars[0];
    }
  }

  // 履歴更新（構造切替時は新規文字扱いとしない）
  if (recordHistory && !altIds && effectiveToken === token) {
    if (state.historyIndex < state.history.length - 1) {
      state.history = state.history.slice(0, state.historyIndex + 1);
    }
    if (state.history[state.history.length - 1] !== effectiveToken) {
      state.history.push(effectiveToken);
      state.historyIndex = state.history.length - 1;
    }
  }

  updateBreadcrumbsUI();

  // APIリクエスト（/api/char?q=...&alt_ids=...）
  let data = null;
  try {
    const queryUrl = `/api/char?q=${encodeURIComponent(effectiveToken)}${altIds ? '&alt_ids=' + encodeURIComponent(altIds) : ''}`;
    const response = await fetch(queryUrl, { signal: request.signal });
    if (response.ok) {
      data = await response.json();
    }
  } catch (err) {
    if (!request.isCurrent()) return;
    console.warn("文字情報を取得できませんでした:", err);
  }

  // JSON解析中に開始された新しい調査も優先する。
  if (!request.isCurrent()) return;
  if (!data) {
    data = {
      unavailable: true,
      meta: {
        char: effectiveToken, literal: effectiveToken,
        codepoint: (!isCodepoint && !isEntity && !isIdc && Array.from(effectiveToken).length === 1) ? getCodepointHex(effectiveToken) : "未詳",
        tier: "情報取得不可", stroke_count: null, radical: "部首未詳",
        badges: ["文字情報を取得できませんでした。再度調査してください。"]
      },
      alternatives: [], tree: null, visual: { has_kanjivg: false }
    };
  }

  state.charData = data;
  state.lockedPath = null;

  if (!altIds) {
    state.currentChar = data.meta?.char || data.meta?.literal || effectiveToken;
    if (!data.unavailable && recordHistory && effectiveToken === token && state.historyIndex >= 0 && state.historyIndex < state.history.length) {
      state.history[state.historyIndex] = state.currentChar;
      if (state.historyIndex > 0 && state.history[state.historyIndex - 1] === state.currentChar) {
        state.history.splice(state.historyIndex, 1);
        state.historyIndex--;
      }
      updateBreadcrumbsUI();
    }
    if (!data.unavailable) {
      state.findChips = new Set([state.currentChar]);
      renderFindChips();
    }
    state.activeStructureIndex = 0;
  } else {
    state.currentChar = data.meta?.char || data.meta?.literal || state.currentChar || effectiveToken;
    const alts = data.alternatives || [];
    const matchIdx = alts.findIndex(a => a.ids === altIds);
    if (matchIdx >= 0) {
      state.activeStructureIndex = matchIdx;
    }
  }

  updateLockControllerUI();
  resetHud();

  // 表示モード制御: KanjiVG筆画データの有無に応じてトグルボタンの状態を同期
  const hasKvg = !!(data.visual && data.visual.has_kanjivg);
  const btnKvg = document.getElementById("btnModeKvg");
  const btnMincho = document.getElementById("btnModeMincho");

  if (!hasKvg) {
    state.activeDisplayMode = "mincho";
    if (btnKvg) {
      btnKvg.disabled = true;
      btnKvg.classList.remove("active");
      btnKvg.title = "この文字のKanjiVG筆画データは未収録です(明朝体印刷書体で表示)";
    }
    if (btnMincho) {
      btnMincho.classList.add("active");
      btnMincho.title = "印刷書体表示(明朝体)";
    }
  } else {
    if (btnKvg) {
      btnKvg.disabled = false;
      btnKvg.title = "筆画表示(KanjiVGベクター・筆画単位ハイライト - デフォルト)";
      if (state.activeDisplayMode === "kvg") {
        btnKvg.classList.add("active");
        if (btnMincho) btnMincho.classList.remove("active");
      }
    }
    if (btnMincho && state.activeDisplayMode === "mincho") {
      btnMincho.classList.add("active");
      if (btnKvg) btnKvg.classList.remove("active");
    }
  }

  // 画面レンダリング更新
  renderCanvas();
  renderAttributeCard();
  renderStructureSelector();
  renderIdsTokens();
  renderRecursiveTree();

  if (!data.unavailable) {
    // 逆引き検索を連動更新
    executeFindSearch();

    // 収録熟語・語彙検索を連動更新
    loadWordsForCurrentKanji();
  }
}

/**
 * 構文解析木から特定パスのノードを検索
 */
function findNodeByPath(node, targetPath) {
  if (!node || !targetPath) return null;
  if (node.path === targetPath) return node;
  if (node.children && node.children.length > 0) {
    for (const child of node.children) {
      const found = findNodeByPath(child, targetPath);
      if (found) return found;
    }
  }
  return null;
}

/**
 * KanjiVG グループ要素（漢字・部首）に対応する構文木パスをスマート探索
 */
function findTreePathForElement(treeNode, elementChar, searchPathPrefix = "") {
  if (!treeNode || !elementChar) return null;

  // 1. 接頭辞スコープ内の優先探索
  if (searchPathPrefix && searchPathPrefix !== "0") {
    const subRoot = findNodeByPath(treeNode, searchPathPrefix);
    if (subRoot) {
      const found = searchSubtree(subRoot);
      if (found) return found;
    }
    // 接頭辞スコープが指定されている場合、他コンポーネントの同名要素への誤マッチ（スコープ逸脱）を防ぐためnullを返す
    return null;
  }

  // 2. 木全体からの探索（スコープ未指定時のみ）
  return searchSubtree(treeNode);

  function searchSubtree(node) {
    if (!node) return null;
    if (node.char === elementChar || node.raw_char === elementChar) {
      return node.path;
    }
    if (node.children && node.children.length > 0) {
      for (const child of node.children) {
        const p = searchSubtree(child);
        if (p) return p;
      }
    }
    return null;
  }
}

// =============================================================================
// 5. 左カラム: キャンバス描画 & インタラクティブホバー
// =============================================================================

/**
 * キャンバスおよびツリー要素のロック中表示クラスを同期更新
 */
function updateCanvasLockClasses() {
  const container = document.getElementById("canvasSvgContainer");
  const lockedPath = state.lockedPath;

  if (container) {
    const roots = container.querySelectorAll(".kvg-root");
    roots.forEach(root => {
      root.classList.toggle("has-locked-scope", !!lockedPath);
    });

    container.querySelectorAll(".component-vector-layer").forEach(layer => {
      const lPath = layer.getAttribute("data-path");
      layer.classList.toggle("locked-scope", !!(lockedPath && lPath === lockedPath));
    });

    container.querySelectorAll(".kvg-group:not(.component-vector-layer)[data-path]").forEach(g => {
      const gPath = g.getAttribute("data-path") || "";
      const inScope = !!(lockedPath && (gPath === lockedPath || gPath.startsWith(lockedPath + ".")));
      g.classList.toggle("locked-scope", inScope);
      g.classList.toggle("locked-target", !!(lockedPath && gPath === lockedPath));
    });
  }

  document.querySelectorAll(".tree-node-card").forEach(card => {
    const cPath = card.getAttribute("data-path");
    card.classList.toggle("locked-node", !!(lockedPath && cPath === lockedPath));
  });

  if (typeof refreshCalligraphySumiCanvas === "function") {
    refreshCalligraphySumiCanvas();
  }
}

/**
 * 段階的ロック階層探索コントローラーUIの更新
 */
function updateLockControllerUI() {
  const badge = document.getElementById("depthStatusBadge");
  const btnStepUp = document.getElementById("btnLockStepUp");
  const btnReset = document.getElementById("btnResetLock");
  const trail = document.getElementById("depthLockTrail");

  if (!badge || !trail) return;

  if (!state.lockedPath) {
    badge.textContent = "第1階層(直接構成)";
    badge.className = "depth-status-badge level-1";
    if (btnStepUp) btnStepUp.disabled = true;
    if (btnReset) btnReset.disabled = true;
    trail.innerHTML = '<span class="depth-lock-hint">※ 第1階層の構成部品をクリックで固定・逆引き検索、「選択解除」で解除</span>';
    return;
  }

  const lockedNode = findNodeByPath(state.charData?.tree, state.lockedPath);
  const lockedDepth = state.lockedPath.split(".").length - 1;
  const hasChildren = lockedNode && Array.isArray(lockedNode.children) && lockedNode.children.length > 0;

  if (btnStepUp) btnStepUp.disabled = false;
  if (btnReset) btnReset.disabled = false;

  badge.className = "depth-status-badge is-locked";
  const charName = lockedNode?.char || lockedNode?.raw_char || "部品";
  badge.innerHTML = hasChildren
    ? `第${lockedDepth + 1}階層(${renderGlyphHTML(charName)}の内部)`
    : `第${lockedDepth}階層(末端部品: ${renderGlyphHTML(charName)})`;

  // 祖先パンくずリスト描画
  trail.innerHTML = "";
  const parts = state.lockedPath.split(".");
  const ancestorPaths = [];
  for (let i = 2; i <= parts.length; i++) {
    ancestorPaths.push(parts.slice(0, i).join("."));
  }

  ancestorPaths.forEach((p, idx) => {
    if (idx > 0) {
      const sep = document.createElement("span");
      sep.className = "depth-trail-sep";
      sep.textContent = "→";
      trail.appendChild(sep);
    }

    const n = findNodeByPath(state.charData?.tree, p);
    const d = p.split(".").length - 1;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "depth-trail-chip" + (p === state.lockedPath ? " active" : "");
    const chipChar = n?.char || n?.raw_char || n?.role_label || "部品";
    chip.innerHTML = `第${d}階層: ${renderGlyphHTML(chipChar)}`;
    chip.title = `第${d}階層「${chipChar}」にスコープを切り替えます`;
    chip.addEventListener("click", () => {
      lockComponentScope(p);
    });
    trail.appendChild(chip);
  });

  // 単体調査ボタン
  if (lockedNode && lockedNode.char && lockedNode.char !== state.currentChar) {
    const btnOpenMain = document.createElement("button");
    btnOpenMain.type = "button";
    btnOpenMain.className = "btn-open-locked-main";
    btnOpenMain.id = "btnOpenLockedMain";
    btnOpenMain.innerHTML = `「${renderGlyphHTML(lockedNode.char)}」を単体調査 →`;
    btnOpenMain.title = `「${lockedNode.char}」を主文字として詳細分解します`;
    btnOpenMain.addEventListener("click", () => {
      inspectCharacter(lockedNode.char);
    });
    trail.appendChild(btnOpenMain);
  }
}

/**
 * 指定パスの部品を探索スコープとして固定（ロック）
 */
function lockComponentScope(path) {
  if (!path || path === "0") {
    resetLockedScope();
    return;
  }

  state.lockedPath = path;
  const node = findNodeByPath(state.charData?.tree, path);

  // 右カラム逆引き検索をロック部品に連動
  const targetChar = node ? (node.char || node.raw_char) : null;
  if (targetChar) {
    state.findChips = new Set([targetChar]);
    renderFindChips();
    executeFindSearch();
  }

  applyHitTestDepth();
  updateLockControllerUI();
  clearComponentHover();
}

/**
 * 選択固定を解除して第1階層探索へリセット
 */
function resetLockedScope() {
  state.lockedPath = null;
  state.findChips = new Set([state.currentChar]);
  renderFindChips();
  executeFindSearch();
  applyHitTestDepth();
  updateLockControllerUI();
  clearComponentHover();
}

/**
 * 1つ上の祖先階層へ戻る
 */
function stepLockScopeUp() {
  if (!state.lockedPath) return;
  const parts = state.lockedPath.split(".");
  if (parts.length > 2) {
    parts.pop();
    const parentPath = parts.join(".");
    lockComponentScope(parentPath);
  } else {
    resetLockedScope();
  }
}

/**
 * 段階的ロック階層に基づくヒットテスト適用
 */
function applyHitTestDepth() {
  const container = document.getElementById("canvasSvgContainer");
  if (!container) return;

  const lockedPath = state.lockedPath;
  const lockedNode = lockedPath ? findNodeByPath(state.charData?.tree, lockedPath) : null;
  const hasChildren = lockedNode && Array.isArray(lockedNode.children) && lockedNode.children.length > 0;

  // 1. 明朝体ベクターレイヤー (.component-vector-layer)
  const layers = container.querySelectorAll(".component-vector-layer");
  layers.forEach(layer => {
    const layerPath = layer.getAttribute("data-path") || "";
    const hitboxes = layer.querySelectorAll(".component-layer-hitbox");
    if (hitboxes.length === 0) return;

    let targetPointerEvents = "none";
    if (!lockedPath) {
      // 第1階層部品のみ (root "0" の直接の子: "0.0", "0.1" -> split(".").length === 2)
      const isLevel1 = (layerPath.split(".").length === 2);
      targetPointerEvents = isLevel1 ? "all" : "none";
    } else {
      if (hasChildren) {
        // lockedPath の直接の子要素のみ有効化
        const isDirectChild = layerPath.startsWith(lockedPath + ".") &&
          layerPath.split(".").length === lockedPath.split(".").length + 1;
        targetPointerEvents = isDirectChild ? "all" : "none";
      } else {
        // 末端部品自身のみ有効化（再クリックで単体調査への遷移を可能にする）
        targetPointerEvents = (layerPath === lockedPath) ? "all" : "none";
      }
    }

    hitboxes.forEach(hb => {
      hb.style.pointerEvents = targetPointerEvents;
    });
  });

  // 2. フォールバック用 KanjiVG グループ (.kvg-group[data-path])
  if (layers.length === 0) {
    const kvgGroups = container.querySelectorAll(".kvg-group[data-path]");
    kvgGroups.forEach(g => {
      const gPath = g.getAttribute("data-path") || "";
      if (!lockedPath) {
        let isLevel1 = (gPath.split(".").length === 2);
        if (!isLevel1 && gPath.split(".").length > 2) {
          const l1Path = gPath.split(".").slice(0, 2).join(".");
          const hasL1Ancestor = !!container.querySelector(`.kvg-group[data-path="${l1Path}"]`);
          if (!hasL1Ancestor) {
            isLevel1 = true;
          }
        }
        g.style.pointerEvents = isLevel1 ? "all" : "none";
      } else {
        if (hasChildren) {
          const isDirectChild = gPath.startsWith(lockedPath + ".") &&
            gPath.split(".").length === lockedPath.split(".").length + 1;
          g.style.pointerEvents = isDirectChild ? "all" : "none";
        } else {
          g.style.pointerEvents = (gPath === lockedPath) ? "all" : "none";
        }
      }
    });
  }

  updateCanvasLockClasses();
}

/**
 * キャンバス描画（常に明朝体ベクターSVGをフルサイズ描画）
 */
function renderCanvas() {
  const container = document.getElementById("canvasSvgContainer");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  const visual = state.charData.visual || {};
  const tree = state.charData.tree || {};

  if (state.charData.unavailable) {
    container.textContent = "文字情報を取得できませんでした。再度調査してください。";
    return;
  }
  renderSvgInto(container, visual, tree);
  applyHitTestDepth();
}

/* =============================================================================
   瘦金體（Slender Gold Calligraphy）数理運筆エンジン (Jiucheng / Slender Physics)
   ============================================================================= */

const DEFAULT_SLENDER_PHYSICS = {
  thickness: 0.86,
  tonStrength: 1.08,
  waistRatio: 0.80,
  nibAngleDeg: -40,
  kasureAmount: 0.30,
  minTaperRatio: 0.10,
  // Physically-based Xuan paper, D2Q9 LBM ink dispersion, bristle & Kubelka-Munk optical parameters
  paperGrainIntensity: 1.35,
  coffeeRingIntensity: 1.45,
  nijimiIntensity: 1.40,
  bristleStriationIntensity: 1.35,
  dwellPoolingIntensity: 1.40,
  kmTransmittanceContrast: 1.35,
  glueChromaticWarmth: 1.25,
  // Physically-based traditional Chinese brush (Jianhao tuft, Cefeng posture, Elastica plasticity, WetBrush reservoir)
  coreMantleContrast: 1.35,
  cefengObliqueIntensity: 1.30,
  tuftPlasticityElasticity: 1.25,
  reservoirCompressionSqueeze: 1.35
};

const SLENDER_PHYSICS = { ...DEFAULT_SLENDER_PHYSICS };

const INK_PHYSICS_PRESETS = {
  standard: {
    label: "標準（生宣・兼毫中鋒）",
    values: { ...DEFAULT_SLENDER_PHYSICS }
  },
  raw_xuan: {
    label: "生宣・濃墨滲み（強め）",
    values: {
      ...DEFAULT_SLENDER_PHYSICS,
      paperGrainIntensity: 1.65,
      coffeeRingIntensity: 1.85,
      nijimiIntensity: 1.90,
      bristleStriationIntensity: 1.40,
      dwellPoolingIntensity: 1.75,
      kmTransmittanceContrast: 1.55,
      glueChromaticWarmth: 1.45,
      coreMantleContrast: 1.45,
      cefengObliqueIntensity: 1.35,
      tuftPlasticityElasticity: 1.30,
      reservoirCompressionSqueeze: 1.65,
      kasureAmount: 0.26
    }
  },
  sized_feibai: {
    label: "熟宣・渇筆飛白（掠れ強調）",
    values: {
      ...DEFAULT_SLENDER_PHYSICS,
      paperGrainIntensity: 1.70,
      coffeeRingIntensity: 1.20,
      nijimiIntensity: 0.75,
      bristleStriationIntensity: 1.95,
      dwellPoolingIntensity: 1.25,
      kmTransmittanceContrast: 1.50,
      glueChromaticWarmth: 1.15,
      coreMantleContrast: 1.75,
      cefengObliqueIntensity: 1.60,
      tuftPlasticityElasticity: 1.55,
      reservoirCompressionSqueeze: 1.20,
      kasureAmount: 0.45
    }
  },
  light_wash: {
    label: "淡墨・水墨階調（高透過）",
    values: {
      ...DEFAULT_SLENDER_PHYSICS,
      paperGrainIntensity: 1.60,
      coffeeRingIntensity: 1.70,
      nijimiIntensity: 1.65,
      bristleStriationIntensity: 1.50,
      dwellPoolingIntensity: 1.65,
      kmTransmittanceContrast: 1.85,
      glueChromaticWarmth: 1.65,
      coreMantleContrast: 1.60,
      cefengObliqueIntensity: 1.40,
      tuftPlasticityElasticity: 1.35,
      reservoirCompressionSqueeze: 1.50,
      kasureAmount: 0.34
    }
  },
  jianhao_cefeng: {
    label: "兼毫・側鋒抑揚（筆勢強調）",
    values: {
      ...DEFAULT_SLENDER_PHYSICS,
      paperGrainIntensity: 1.45,
      coffeeRingIntensity: 1.55,
      nijimiIntensity: 1.45,
      bristleStriationIntensity: 1.65,
      dwellPoolingIntensity: 1.60,
      kmTransmittanceContrast: 1.45,
      glueChromaticWarmth: 1.35,
      coreMantleContrast: 1.85,
      cefengObliqueIntensity: 1.85,
      tuftPlasticityElasticity: 1.75,
      reservoirCompressionSqueeze: 1.75,
      kasureAmount: 0.35
    }
  }
};

/**
 * 永字八法・筆画種別分類
 */
function classifyStrokeBehavior(stroke, origLen = 25) {
  const rawT = stroke.type || '';
  const primary = rawT.split('/')[0].trim();
  const t = primary;
  const name = (stroke.stroke_name || '').toLowerCase();
  const comp = (stroke.component || '').trim();

  const isLongComposite = origLen >= 18;
  const hasNaTail = isLongComposite && (rawT.includes('/㇏') || rawT.includes('/㇀'));
  const hasSweepTail = isLongComposite && (rawT.includes('/㇒') || rawT.includes('/㇓'));
  const isShortNaDot = t.includes('㇏') && origLen < 15;

  // In 子, 了, 孑, the top stroke is 横撇 (héng piě), even if tagged as ㇖ in KanjiVG
  const isZiHengPie = (comp === '子' || comp === '了' || comp === '孑') && (t.includes('㇖') || t.includes('㇇') || name.includes('横撇') || name.includes('piě'));
  const isCurvedBowHook = t.includes('㇁') || name.includes('wān gōu') || name.includes('彎鉤');
  const isRoofHook = (t.includes('㇖') || name.includes('横鉤') || name.includes('héng gōu')) && !isZiHengPie;

  // Authentic hooks: terminal flick strokes. Roof hook ㇖ is excluded because it renders as a continuous fold-and-taper stroke!
  const isHook = !isZiHengPie && !isRoofHook && (
    t.includes('㇚') || t.includes('㇈') || t.includes('㇂') || t.includes('㇆') ||
    t.includes('㇃') || t.includes('㇉') || t.includes('㇌') || t.includes('㇟') ||
    t.includes('㇠') || t.includes('㇡') || t.includes('㇢') ||
    isCurvedBowHook || name.includes('gōu') || name.includes('鉤')
  );

  const isRisingTi = t.includes('㇀') || name.includes('tí') || name.includes('提');
  const isVerticalTi = t.includes('㇙') || t.includes('㇊');
  const isVerticalSweep = t.includes('㇓');
  const isRightNa = (((t.includes('㇏') || name.includes('nà') || name.includes('捺')) && !t.includes('㇔') && !isShortNaDot) || (t.includes('㇔') && hasNaTail));
  const isCrownDot = (t === '㇑a' && (comp === '宀' || comp === '亠' || comp === '广' || comp === '疒' || comp === '穴' || comp === '立' || comp === '文' || comp === '言' || comp === '衣' || comp === '方' || comp === '主' || comp === '市' || comp === '亡' || comp === '高' || comp === '京' || comp === '玄' || comp === '率'));
  const isDot = (t.includes('㇔') || isShortNaDot || name.includes('diǎn') || name.includes('点')) && !isCrownDot && !isRightNa && !isRisingTi && !hasNaTail && !hasSweepTail;

  // isSweepEnd covers free-air left sweeps and folds that sweep
  const isSweepEnd = !isHook && !isDot && !isRightNa && !isRisingTi && !isVerticalTi && (
    t.includes('㇒') || t.includes('㇇') || t.includes('㇋') || isVerticalSweep || isZiHengPie || isRoofHook ||
    (t.includes('㇔') && hasSweepTail) ||
    name.includes('piě') || name.includes('撇')
  );

  const isFold = t.includes('㇕') || t.includes('㇄') || t.includes('㇅') || t.includes('㇆') ||
    t.includes('㇈') || t.includes('㇉') || t.includes('㇊') || t.includes('㇋') ||
    t.includes('㇌') || t.includes('㇍') || t.includes('㇎') || t.includes('㇇') ||
    t.includes('㇖') || t.includes('㇗') || t.includes('㇘') || t.includes('㇙') ||
    t.includes('㇛') || t.includes('㇜') || t.includes('㇞') || t.includes('㇟') ||
    t.includes('㇠') || t.includes('㇡') || isZiHengPie || isRoofHook ||
    name.includes('zhé') || name.includes('折');

  const isPieZhe = t.includes('㇜') || t.includes('㇛');

  const isHorizontal = t.includes('㇐') || name.includes('héng') || name.includes('横');
  const isVertical = t.includes('㇑') || name.includes('shù') || name.includes('竪');
  const isConnectingVertical = t.includes('㇑a');

  return {
    isZiHengPie,
    isCurvedBowHook,
    isRoofHook,
    isSweepEnd,
    isRisingTi,
    isVerticalTi,
    isVerticalSweep,
    isRightNa,
    isCrownDot,
    isDot,
    isHook,
    isFold,
    isPieZhe,
    isHorizontal,
    isVertical,
    isConnectingVertical
  };
}

/**
 * Chaikinのアルゴリズムによる開曲線スムージング
 */
function chaikinSmoothOpenChain(pts, iterations = 2) {
  if (!pts || pts.length < 3) return pts || [];
  let curr = pts;
  for (let it = 0; it < iterations; it++) {
    if (curr.length < 3) break;
    const next = [curr[0]];
    for (let i = 0; i < curr.length - 1; i++) {
      const p0 = curr[i];
      const p1 = curr[i + 1];
      next.push({
        x: 0.75 * p0.x + 0.25 * p1.x,
        y: 0.75 * p0.y + 0.25 * p1.y
      });
      next.push({
        x: 0.25 * p0.x + 0.75 * p1.x,
        y: 0.25 * p0.y + 0.75 * p1.y
      });
    }
    next.push(curr[curr.length - 1]);
    curr = next;
  }
  return curr;
}

let offscreenSvg = null;
let offscreenSamplerPath = null;

function getOffscreenSamplerPath() {
  if (typeof document === "undefined") return null;
  if (!offscreenSamplerPath) {
    try {
      offscreenSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      offscreenSvg.setAttribute("viewBox", "0 0 109 109");
      offscreenSvg.setAttribute("width", "0");
      offscreenSvg.setAttribute("height", "0");
      offscreenSvg.style.position = "absolute";
      offscreenSvg.style.top = "-9999px";
      offscreenSvg.style.left = "-9999px";
      offscreenSvg.style.visibility = "hidden";
      offscreenSamplerPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      offscreenSvg.appendChild(offscreenSamplerPath);
      const root = document.body || document.documentElement;
      if (root) {
        root.appendChild(offscreenSvg);
      }
    } catch (e) {
      return null;
    }
  } else if (offscreenSvg && !offscreenSvg.parentNode) {
    const root = document.body || document.documentElement;
    if (root) {
      root.appendChild(offscreenSvg);
    }
  }
  return offscreenSamplerPath;
}

/**
 * 階層木構造からKanjiVG筆画総数を計算
 */
function countKvgStrokes(group) {
  if (!group) return 0;
  let count = (group.strokes || []).length;
  if (group.children) {
    for (const child of group.children) {
      count += countKvgStrokes(child);
    }
  }
  return count;
}

const numFmt = n => (Number.isFinite(n) ? Number(n.toFixed(2)) : 0);

// Key of every slider/parameter that is baked into compileStrokePhysics() output; a mismatch forces a recompile.
function getBrushCompileKey(phys) {
  const p = phys || DEFAULT_SLENDER_PHYSICS;
  return [
    p.coreMantleContrast ?? 1.35,
    p.cefengObliqueIntensity ?? 1.30,
    p.tuftPlasticityElasticity ?? 1.25,
    p.reservoirCompressionSqueeze ?? 1.35,
    p.kasureAmount ?? 0.30,
    p.nibAngleDeg ?? -40
  ].join("_");
}

/**
 * 瘦金體（Slender Gold）運筆物理モデル・中心線サンプリング＆肉付けコンパイラ
 */
function compileStrokePhysics(stroke, boxX, boxY, boxSize, totalCharStrokes = 10) {
  const samplerPath = getOffscreenSamplerPath();
  if (!samplerPath || typeof samplerPath.getTotalLength !== "function") {
    return null;
  }
  samplerPath.setAttribute("d", stroke.d);
  const origLen = Math.max(0.1, samplerPath.getTotalLength());

  const step = 0.28;
  const numSamples = Math.max(50, Math.ceil(origLen / step));
  const rawPts = [];

  const scale = boxSize / 109;
  for (let i = 0; i <= numSamples; i++) {
    const s = (i / numSamples) * origLen;
    const pt = samplerPath.getPointAtLength(s);
    rawPts.push({
      s,
      u: i / numSamples,
      svgX: pt.x,
      svgY: pt.y
    });
  }

  const behavior = classifyStrokeBehavior(stroke, origLen);

  // Extension for 子 top connecting stroke to solidly overlap into stroke 7 entry head
  if (behavior.isZiHengPie && rawPts.length > 8) {
    const lastPt = rawPts[numSamples];
    const prevPt = rawPts[Math.max(0, numSamples - 3)];
    const edx = lastPt.svgX - prevPt.svgX;
    const edy = lastPt.svgY - prevPt.svgY;
    const emag = Math.hypot(edx, edy) || 1;
    const etx = edx / emag;
    const ety = edy / emag;
    const extDist = 2.2;
    const blendStart = Math.floor(numSamples * 0.85);
    for (let i = blendStart; i <= numSamples; i++) {
      const t = (i - blendStart) / (numSamples - blendStart);
      rawPts[i].svgX += etx * extDist * t;
      rawPts[i].svgY += ety * extDist * t;
    }
  }

  // Initial entry-tangent alignment for all non-dot strokes (eliminates initial vector spurs)
  if (!behavior.isDot && !behavior.isCrownDot && rawPts.length > 8 && origLen > 8) {
    const anchorS = Math.min(origLen * 0.20, 2.8);
    const lookS = Math.min(origLen * 0.42, 5.5);
    const anchorIdx = Math.min(numSamples - 2, Math.max(2, Math.round((anchorS / origLen) * numSamples)));
    const lookIdx = Math.min(numSamples, Math.max(anchorIdx + 2, Math.round((lookS / origLen) * numSamples)));

    const shaftDx = rawPts[lookIdx].svgX - rawPts[anchorIdx].svgX;
    const shaftDy = rawPts[lookIdx].svgY - rawPts[anchorIdx].svgY;
    const shaftMag = Math.hypot(shaftDx, shaftDy) || 1;
    const stx = shaftDx / shaftMag;
    const sty = shaftDy / shaftMag;

    for (let i = 0; i < anchorIdx; i++) {
      const blend = Math.pow(1.0 - (i / anchorIdx), 0.85);
      const distBack = (rawPts[anchorIdx].s - rawPts[i].s);
      const projX = rawPts[anchorIdx].svgX - stx * distBack;
      const projY = rawPts[anchorIdx].svgY - sty * distBack;
      rawPts[i].svgX = rawPts[i].svgX * (1.0 - 0.95 * blend) + projX * (0.95 * blend);
      rawPts[i].svgY = rawPts[i].svgY * (1.0 - 0.95 * blend) + projY * (0.95 * blend);
    }
  }

  // Turning angle analysis across a sliding window
  let hookFeature = null;
  const win = Math.max(2, Math.round(2.0 / step));

  for (let i = 0; i <= numSamples; i++) {
    if (i >= win && i <= numSamples - win) {
      const vx1 = rawPts[i].svgX - rawPts[i - win].svgX;
      const vy1 = rawPts[i].svgY - rawPts[i - win].svgY;
      const vx2 = rawPts[i + win].svgX - rawPts[i].svgX;
      const vy2 = rawPts[i + win].svgY - rawPts[i].svgY;
      const m1 = Math.hypot(vx1, vy1) || 1;
      const m2 = Math.hypot(vx2, vy2) || 1;
      const dot = Math.max(-1, Math.min(1, (vx1 * vx2 + vy1 * vy2) / (m1 * m2)));
      rawPts[i].turnAngle = Math.acos(dot);
      rawPts[i].turnSign = (vx1 * vy2 - vy1 * vx2) >= 0 ? 1 : -1;
    } else {
      rawPts[i].turnAngle = 0;
      rawPts[i].turnSign = 1;
    }
  }

  // Hook Apex Detection & Flick Guide
  if (behavior.isHook && origLen > 13) {
    const searchStart = Math.max(Math.floor(numSamples * 0.70), numSamples - Math.ceil(15.0 / step));
    let bestIdx = -1;
    let maxTurn = 0.28;
    for (let i = searchStart; i <= numSamples - 2; i++) {
      if (rawPts[i].turnAngle > maxTurn) {
        maxTurn = rawPts[i].turnAngle;
        bestIdx = i;
      }
    }
    let maxY = -Infinity;
    let maxYIdx = -1;
    for (let i = searchStart; i <= numSamples - 1; i++) {
      if (rawPts[i].svgY > maxY) {
        maxY = rawPts[i].svgY;
        maxYIdx = i;
      }
    }
    if (maxYIdx > searchStart && maxY - rawPts[numSamples].svgY > 0.8) {
      bestIdx = maxYIdx;
    }

    // Verify that the detected apex is a genuine terminal flick:
    // Remaining distance after turn must be <= 12 SVG units and <= 25% of stroke length
    if (bestIdx !== -1) {
      const remLen = origLen - rawPts[bestIdx].s;
      const remRatio = remLen / origLen;
      if (remLen > 12.0 || remRatio > 0.25 || rawPts[bestIdx].u < 0.72) {
        // Not a terminal hook flick — this is a compound corner fold (e.g. 横撇 or 横折)
        bestIdx = -1;
      }
    }

    if (bestIdx !== -1) {
      if (behavior.isCurvedBowHook && maxYIdx > searchStart) {
        bestIdx = maxYIdx;
      }
      const apexPt = rawPts[bestIdx];
      const endPt = rawPts[numSamples];
      let fdx = endPt.svgX - apexPt.svgX;
      let fdy = endPt.svgY - apexPt.svgY;

      // Hook Classification: Leftward vs Upward vs DownLeft
      const isDownLeftHook = false; // Roof hooks are now continuous isRoofHook strokes!
      const isVerticalLeftHook = fdx < -0.2; // 永 s2, 成 s3, 泉 s6, 学 s7
      const isUpwardHook = !isVerticalLeftHook; // 嵐 s5, 九 s2, 成 s4

      let hookUx = -0.92;
      let hookUy = -0.39;

      if (isVerticalLeftHook) {
        // Push left and slightly upward (~23° above horizontal: 永字八法・趯)
        hookUx = -0.92;
        hookUy = -0.39;
      } else {
        // Push steep upward for right-side hooks (嵐 s5, 九 s2, 成 s4)
        hookUy = -0.988;
        hookUx = 0.15;
      }

      const heelIdx = behavior.isCurvedBowHook ? Math.max(4, bestIdx - 2) : Math.max(4, bestIdx - 4);
      hookFeature = {
        index: bestIdx,
        heelIdx: heelIdx,
        u: rawPts[bestIdx].u,
        s: rawPts[bestIdx].s,
        angle: Math.max(1.3, rawPts[bestIdx].turnAngle),
        isUpwardHook,
        isVerticalLeftHook,
        isDownLeftHook: false,
        isCurvedBowHook: behavior.isCurvedBowHook,
        flickUx: hookUx,
        flickUy: hookUy,
        kind: "hook"
      };
    }
  }

  // Corner features detection (excluding hook region)
  const cornerFeatures = [];
  const minCornerS = Math.min(5.0, origLen * 0.22);
  const maxCornerS = hookFeature ? hookFeature.s - 6.5 : origLen - Math.min(4.5, origLen * 0.22);
  const minSep = Math.max(4, Math.round(3.2 / step));

  for (let i = win + 2; i < numSamples - win - 2; i++) {
    const s = rawPts[i].s;
    if (s < minCornerS || s > maxCornerS) continue;
    const a = rawPts[i].turnAngle;
    if (a > 0.55) {
      let isPeak = true;
      for (let k = -minSep; k <= minSep; k++) {
        if (k !== 0 && i + k >= 0 && i + k <= numSamples && rawPts[i + k].turnAngle > a) {
          isPeak = false;
          break;
        }
      }
      if (isPeak) {
        cornerFeatures.push({
          index: i,
          u: rawPts[i].u,
          s: rawPts[i].s,
          angle: a,
          turnSign: rawPts[i].turnSign,
          kind: "corner"
        });
      }
    }
  }

  // Cumulative arc-lengths & scaled canvas coordinates
  let cumS = 0;
  for (let i = 0; i <= numSamples; i++) {
    if (i > 0) {
      cumS += Math.hypot(rawPts[i].svgX - rawPts[i - 1].svgX, rawPts[i].svgY - rawPts[i - 1].svgY);
    }
    rawPts[i].s = cumS;
    rawPts[i].x = boxX + rawPts[i].svgX * scale;
    rawPts[i].y = boxY + rawPts[i].svgY * scale;
  }
  const totalLen = Math.max(0.1, cumS);
  for (let i = 0; i <= numSamples; i++) {
    rawPts[i].u = rawPts[i].s / totalLen;
  }
  if (hookFeature) {
    hookFeature.s = rawPts[hookFeature.index].s;
    hookFeature.u = rawPts[hookFeature.index].u;
  }
  for (const cf of cornerFeatures) {
    cf.s = rawPts[cf.index].s;
    cf.u = rawPts[cf.index].u;
  }

  // Compute Tangents & Normals
  for (let i = 0; i <= numSamples; i++) {
    let iPrev = Math.max(0, i - 4);
    let iNext = Math.min(numSamples, i + 4);
    if (iPrev === iNext) {
      iPrev = Math.max(0, i - 1);
      iNext = Math.min(numSamples, i + 1);
    }
    let dx = rawPts[iNext].x - rawPts[iPrev].x;
    let dy = rawPts[iNext].y - rawPts[iPrev].y;

    const mag = Math.hypot(dx, dy) || 1;
    rawPts[i].tx = dx / mag;
    rawPts[i].ty = dy / mag;
  }

  // Smooth (tx, ty) with 2 passes of [0.25, 0.5, 0.25] filtering
  for (let pass = 0; pass < 2; pass++) {
    const nextTx = rawPts.map(p => p.tx);
    const nextTy = rawPts.map(p => p.ty);
    for (let i = 1; i < numSamples; i++) {
      nextTx[i] = 0.25 * rawPts[i - 1].tx + 0.50 * rawPts[i].tx + 0.25 * rawPts[i + 1].tx;
      nextTy[i] = 0.25 * rawPts[i - 1].ty + 0.50 * rawPts[i].ty + 0.25 * rawPts[i + 1].ty;
    }
    for (let i = 0; i <= numSamples; i++) {
      const mag = Math.hypot(nextTx[i], nextTy[i]) || 1;
      rawPts[i].tx = nextTx[i] / mag;
      rawPts[i].ty = nextTy[i] / mag;
      rawPts[i].nx = -rawPts[i].ty;
      rawPts[i].ny = rawPts[i].tx;
      rawPts[i].angle = Math.atan2(rawPts[i].ty, rawPts[i].tx);
    }
  }

  const features = [...cornerFeatures];
  if (hookFeature) features.push(hookFeature);

  const initTx = rawPts[0].tx;
  const initTy = rawPts[0].ty;
  const isDownEntry = initTy > 0.48 && Math.abs(initTx) < 0.85;
  const isRightToLeftSweep = initTx < -0.42;

  // Full muscular stroke weight
  const densityScale = totalCharStrokes >= 13 ? 0.95 : (totalCharStrokes >= 9 ? 1.04 : 1.14);
  const curveWeightBoost = 1.08;
  const baseShaftRadius = (boxSize * 0.024) * SLENDER_PHYSICS.thickness * densityScale * curveWeightBoost;
  // Scale down radius on short strokes (totalLen < 18 SVG units) so length-to-width ratio is always >= 2.65
  const maxShortRadius = Math.max(2.0, (totalLen * scale) / 5.8);
  const shaftRadius = Math.min(baseShaftRadius, maxShortRadius);
  const tonMult = SLENDER_PHYSICS.tonStrength;
  const waistMult = SLENDER_PHYSICS.waistRatio;

  // Calculate width envelopes wL & wR
  const rawWL = new Float32Array(numSamples + 1);
  const rawWR = new Float32Array(numSamples + 1);
  const rawPoolWeight = new Float32Array(numSamples + 1);

  for (let i = 0; i <= numSamples; i++) {
    const p = rawPts[i];
    const u = p.u;
    const s = p.s;

    let wL = 1.0;
    let wR = 1.0;
    let poolWeight = 0.25;

    if (behavior.isCrownDot) {
      const entryRise = Math.min(1.0, u / 0.18);
      const entryFactor = 0.72 + 0.28 * Math.sin(entryRise * Math.PI * 0.5);
      const taper = 1.0 - 0.42 * Math.pow(u, 1.05);
      wL = 0.90 * entryFactor * taper;
      wR = 0.86 * entryFactor * taper;
      poolWeight = 0.75 * (1.0 - 0.6 * u);
    } else if (behavior.isDot) {
      if (u <= 0.22) {
        const t = u / 0.22;
        const sCurve = Math.sin(t * Math.PI * 0.5);
        wL = 0.66 + 0.24 * sCurve;
        wR = 0.64 + 0.24 * sCurve;
        poolWeight = 0.35 + 0.45 * sCurve;
      } else if (u <= 0.64) {
        const t = (u - 0.22) / 0.42;
        wL = 0.90 - 0.02 * t;
        wR = 0.88 - 0.02 * t;
        poolWeight = 0.80 - 0.10 * t;
      } else {
        const t = (u - 0.64) / 0.36;
        const decay = 1.0 - 0.52 * Math.pow(t, 1.05);
        wL = 0.88 * decay;
        wR = 0.86 * decay;
        poolWeight = 0.70 * decay;
      }
    } else if (behavior.isRisingTi) {
      // 提 (tí) - rising stroke with steady calligraphic slope attack to sharp point
      const headZone = Math.min(totalLen * 0.28, 4.8);
      if (s < headZone) {
        const t = s / headZone;
        const blend = 0.5 * (1 + Math.cos(t * Math.PI));
        wL = 0.84 + (0.14 * tonMult) * blend;
        wR = 0.88 + (0.18 * tonMult) * blend;
        poolWeight = 0.85;
      } else {
        const t = (s - headZone) / Math.max(0.1, totalLen - headZone);
        const taper = 1.0 - 0.88 * Math.pow(t, 0.92);
        wL = 0.92 * taper;
        wR = 0.94 * taper;
        poolWeight = 0.35 * (1 - t);
      }
    } else if (behavior.isRightNa) {
      // 捺 (nà / 磔) - clean gradual press to wave foot at u=0.72 without mid-stroke bulge, then crisp taper to point
      const footU = 0.72;
      if (u <= footU) {
        const t = u / footU;
        const swell = Math.pow(t, 1.15);
        wL = 0.68 + (0.88 - 0.68) * swell;
        wR = 0.68 + (0.98 - 0.68) * swell;
        poolWeight = 0.30 + 0.65 * swell;
      } else {
        const tFoot = (u - footU) / (1.0 - footU);
        const decay = 1.0 - 0.90 * Math.pow(tFoot, 1.05);
        wL = 0.88 * decay;
        wR = 0.98 * decay;
        poolWeight = 0.95 * decay;
      }
    } else {
      // General strokes
      const waistArch = Math.sin(u * Math.PI);
      const shaftTension = 1.0 - (1.0 - waistMult) * 0.65 * waistArch;
      wL = shaftTension;
      wR = shaftTension;

      // C1 Smooth Entry Press: entry width starts smoothly without initial spur
      const headLen = Math.min(totalLen * 0.22, 6.0);
      if (s < headLen) {
        const uEntry = s / headLen;
        const entrySwell = Math.sin(uEntry * Math.PI * 0.5);
        const entryWidthFactor = 0.68 + (1.0 - 0.68) * entrySwell;
        const blend = 0.5 * (1 + Math.cos(uEntry * Math.PI));
        poolWeight = 0.85 * blend + 0.25;

        if (isDownEntry) {
          wL += (0.22 * tonMult) * blend;
          wR += (0.10 * tonMult) * blend;
        } else if (isRightToLeftSweep) {
          wR += (0.22 * tonMult) * blend;
          wL += (0.12 * tonMult) * blend;
        } else {
          wL = shaftTension * (1.0 + 0.06 * blend);
          wR = shaftTension * (1.0 + 0.10 * blend);
        }
        wL *= entryWidthFactor;
        wR *= entryWidthFactor;
      }

      // Smooth outer corner shoulders
      for (const cf of cornerFeatures) {
        const d = s - cf.s;
        if (d >= -4.5 && d <= 4.5) {
          const t = d / 4.5;
          const bell = 0.5 * (1 + Math.cos(t * Math.PI));
          poolWeight = Math.max(poolWeight, 0.95 * bell);
          const isAcute = behavior.isPieZhe && cf.angle > 1.0;
          const outerBoost = (isAcute ? 0.0 : 0.16) * tonMult;
          const innerPinch = isAcute ? 0.52 : 0.14;
          const innerFloor = isAcute ? 0.20 : 0.68;

          if (cf.turnSign >= 0) {
            wR += outerBoost * bell;
            wL = Math.max(innerFloor, wL - innerPinch * bell);
          } else {
            wL += outerBoost * bell;
            wR = Math.max(innerFloor, wR - innerPinch * bell);
          }
        }
      }

      // Hook Resting Heel & Flick
      if (hookFeature) {
        const hs = hookFeature.s;
        const isSharpHook = hookFeature.angle >= 1.85;
        const outerIsL = (hookFeature.flickUx < 0 && p.tx < 0.3) || (hookFeature.flickUy < -0.5 && p.turnSign < 0);
        if (s < hs) {
          const dHeel = hs - s;
          const heelRange = (behavior.isCurvedBowHook || (stroke.type || "").includes("㇈") || (stroke.type || "").includes("㇃") || (stroke.type || "").includes("㇆") || (stroke.type || "").includes("㇟")) ? 16.0 : 7.0;
          if (dHeel < heelRange) {
            const tHeel = dHeel / heelRange;
            const heelBell = 0.5 * (1 + Math.cos(tHeel * Math.PI));
            const heelAmp = (isSharpHook ? 0.18 : 0.11) * tonMult;
            if (outerIsL) {
              wL += heelAmp * heelBell;
            } else {
              wR += heelAmp * heelBell;
            }
            poolWeight = Math.max(poolWeight, 0.95 * heelBell);
          }
        } else {
          const tFlick = (s - hs) / Math.max(0.1, totalLen - hs);
          const flickExp = isSharpHook ? 0.85 : 0.94;
          const flickTaper = 1.0 - 0.90 * Math.pow(tFlick, flickExp);
          wL *= flickTaper;
          wR *= flickTaper;
          poolWeight = Math.max(0.1, 0.8 * (1.0 - tFlick));
        }
      } else if (behavior.isRoofHook) {
        const cornerU = cornerFeatures[0] ? cornerFeatures[0].u : 0.78;
        if (u > cornerU) {
          const tHook = (u - cornerU) / (1 - cornerU);
          const taper = 1.0 - 0.90 * Math.pow(tHook, 0.78);
          wL *= taper;
          wR *= taper;
        }
      } else if (behavior.isVerticalTi) {
        const lastCf = cornerFeatures[cornerFeatures.length - 1];
        const cornerU = lastCf ? lastCf.u : 0.75;
        if (u > cornerU) {
          const tTi = (u - cornerU) / (1 - cornerU);
          const taper = 1.0 - 0.90 * Math.pow(tTi, 0.78);
          wL *= taper;
          wR *= taper;
        }
      } else if (behavior.isSweepEnd) {
        if (behavior.isZiHengPie) {
          const cornerU = cornerFeatures[0] ? cornerFeatures[0].u : 0.60;
          if (u > cornerU) {
            const tSweep = (u - cornerU) / (1 - cornerU);
            const taper = 1.0 - 0.60 * tSweep;
            wL *= taper;
            wR *= taper;
          }
        } else {
          const lastCf = cornerFeatures.length > 0 ? cornerFeatures[cornerFeatures.length - 1] : null;
          const isPostCornerSweep = !!(lastCf && lastCf.u > 0.44);
          const sweepStart = isPostCornerSweep ? lastCf.u : 0.43;
          if (u > sweepStart) {
            const tSweep = (u - sweepStart) / (1 - sweepStart);
            const exp = isPostCornerSweep ? 0.82 : 0.98;
            const taper = 1.0 - 0.90 * Math.pow(tSweep, exp);
            wL *= taper;
            wR *= taper;
          }
        }
      } else if (behavior.isPieZhe) {
        const cornerU = cornerFeatures[0] ? cornerFeatures[0].u : 0.45;
        if (u > cornerU) {
          const tLeg = (u - cornerU) / Math.max(0.1, 1.0 - cornerU);
          const taper = 1.0 - 0.36 * Math.pow(tLeg, 0.95);
          wL *= taper;
          wR *= taper;
        }
      } else if (behavior.isVertical && !behavior.isFold) {
        const endDist = totalLen - s;
        const tomeZone = Math.min(5.5, totalLen * 0.28);
        if (endDist < tomeZone) {
          const t = 1 - (endDist / tomeZone);
          const smoothT = 0.5 * (1 - Math.cos(t * Math.PI));
          if (behavior.isConnectingVertical) {
            wL += (0.03 * tonMult) * smoothT;
            wR += (0.03 * tonMult) * smoothT;
          } else {
            wL += (0.06 * tonMult) * smoothT;
            wR += (0.06 * tonMult) * smoothT;
            poolWeight = Math.max(poolWeight, 0.85 * smoothT);
          }
        }
      } else {
        const endDist = totalLen - s;
        const tomeZone = Math.min(5.5, totalLen * 0.28);
        if (endDist < tomeZone) {
          const t = 1 - (endDist / tomeZone);
          const smoothT = 0.5 * (1 - Math.cos(t * Math.PI));
          wL += (0.05 * tonMult) * smoothT;
          wR += (0.07 * tonMult) * smoothT;
          poolWeight = Math.max(poolWeight, 0.88 * smoothT);
        }
      }
    }

    rawWL[i] = wL;
    rawWR[i] = wR;
    rawPoolWeight[i] = poolWeight;
  }

  // ===========================================================================
  // Virtual Chinese Brush Mechanics Pass (Chu & Tai 2002/2004;
  // Xie et al. 2013; Xu et al. 2003/2004; Chen et al. 2015 WetBrush; Strassmann 1986)
  // ===========================================================================
  const coreMantleParam = SLENDER_PHYSICS.coreMantleContrast ?? 1.35;
  const cefengParam = SLENDER_PHYSICS.cefengObliqueIntensity ?? 1.30;
  const plasticityParam = SLENDER_PHYSICS.tuftPlasticityElasticity ?? 1.25;
  const squeezeParam = SLENDER_PHYSICS.reservoirCompressionSqueeze ?? 1.35;
  const nibRad = ((SLENDER_PHYSICS.nibAngleDeg ?? -40) * Math.PI) / 180.0;

  function wrapAnglePi(ang) {
    let a = ang;
    while (a > Math.PI) a -= 2.0 * Math.PI;
    while (a < -Math.PI) a += 2.0 * Math.PI;
    return a;
  }

  // Heavier tuft load => slower, more deliberate travel (shared by the running and per-sample estimates)
  function tuftSpeedEst(pLoad) {
    return Math.max(0.32, 1.30 - 0.45 * Math.min(1.5, pLoad));
  }

  // WetBrush inter-hair packing density psi from load, dwell pooling and tuft obliqueness (Chen et al. 2015 Sec. 5.1)
  function bristlePacking(pLoad, poolWeight, sinPsi) {
    return Math.max(0.10, Math.min(0.92, 0.36 * pLoad + 0.24 * poolWeight + 0.16 * Math.abs(sinPsi)));
  }

  // Initial entry attack posture (Lufeng 露鋒 oblique tip attack vs. Cangfeng 藏鋒 pore-pinned entry)
  const thetaMotion0 = Math.atan2(rawPts[0].ty, rawPts[0].tx);
  const entryAttackDelta = wrapAnglePi(nibRad - thetaMotion0);
  const isConcealedEntry = !!(behavior.isHorizontal || behavior.isVertical) && !behavior.isDot && !behavior.isCrownDot;
  let psiOblique = Math.max(
    -0.58,
    Math.min(0.58, (isConcealedEntry ? 0.34 : 0.46) * Math.sin(entryAttackDelta) * (0.55 + 0.45 * Math.min(1.8, cefengParam)))
  );
  let plasticRho = 0.45 * psiOblique;
  let wBelly = 0.96;
  let wTip = 0.94;
  let tuftEllipticity = 1.0 + 0.32 * Math.abs(Math.sin(psiOblique));
  const charTuftLen = Math.max(2.2, 3.8 * (shaftRadius / Math.max(0.5, scale)));

  for (let i = 0; i <= numSamples; i++) {
    const p = rawPts[i];
    const u = p.u;
    const s = p.s;
    const pLoad = 0.5 * (rawWL[i] + rawWR[i]);

    if (i > 0) {
      const pPrev = rawPts[i - 1];
      const dsStep = Math.max(0.05, s - pPrev.s);
      const thetaPrev = Math.atan2(pPrev.ty, pPrev.tx);
      const thetaCur = Math.atan2(p.ty, p.tx);
      const dTheta = wrapAnglePi(thetaCur - thetaPrev);

      // Paper pore blocking lead distance L = a*t + b*u + c, t = max(|beta| - gamma, 0) (Chu & Tai 2004 p. 80, Fig. 5):
      // tilt beyond the critical angle gamma lengthens the blocking lead, so the pores straighten the tip faster
      const tiltExcess = Math.max(0.0, Math.abs(psiOblique) - 0.10);
      const poreLead = Math.max(0.20, Math.min(0.86, 0.26 + 0.50 * (1.0 - Math.min(1.0, pLoad)) + 0.55 * tiltExcess));

      // Xu et al. (2004) Eq. 18: Differential tuft rotation (Zhuan 轉) vs. sharp corner folding (Zhe 折)
      let cornerKick = 0.0;
      for (let c = 0; c < cornerFeatures.length; c++) {
        const cf = cornerFeatures[c];
        const distC = s - cf.s;
        if (distC >= -1.2 && distC <= 6.5) {
          const decayC = Math.exp(-Math.max(0.0, distC) / 3.8);
          cornerKick += 0.24 * cf.turnSign * Math.min(1.2, cf.angle) * decayC * (0.55 + 0.45 * plasticityParam);
        }
      }

      // Wet tuft capillary plasticity zero-shifting rho = clamp(theta', -alpha(w), alpha(w)) (Chu & Tai 2002 Sec. 4.2.3; Chu & Tai 2004 p. 79)
      // Zero-shifted rest angle rho = clamp(theta', -alpha, alpha) from the previous frame's bend theta' (= psiOblique here)
      const alphaWet = 0.30 * wTip * Math.min(1.75, 0.45 + 0.55 * plasticityParam);
      plasticRho = Math.max(-alphaWet, Math.min(alphaWet, psiOblique));

      // Quasi-static elastica restoring relaxation toward zero-shifted plastic rest angle
      const relaxRate = Math.max(0.04, Math.min(0.46, (dsStep * poreLead / (charTuftLen * 0.16)) * (0.68 + 0.32 * plasticityParam)));
      const zhuanCoupling = 0.35 + 0.10 * Math.min(1.8, cefengParam); // Smooth curve rotation absorbs into tuft roll (Zhuan) vs. obliqueness (Cefeng)
      psiOblique = (1.0 - relaxRate) * (psiOblique - zhuanCoupling * dTheta + cornerKick) + relaxRate * plasticRho;
      psiOblique = Math.max(-0.82, Math.min(0.82, psiOblique));

      // Cross-sectional double-half-ellipse flattening a_i / b_i (Xu et al. 2004 Eqs. 12, 18; Chu & Tai 2002 Sec. 4.1.2)
      const targetEllip = 1.0 + 0.44 * Math.abs(Math.sin(psiOblique)) + 0.28 * Math.max(0.0, pLoad - 0.72) + 0.22 * rawPoolWeight[i];
      tuftEllipticity = 0.72 * tuftEllipticity + 0.28 * targetEllip;

      // WetBrush inter-hair packing density & spherical-cap compression release (Chen et al. 2015 Sec. 5.1, Eqs. 12-13)
      const packPsi = bristlePacking(pLoad, rawPoolWeight[i], Math.sin(psiOblique));
      const potCapMPrime = Math.max(0.22, 1.0 - 0.50 * packPsi);
      const pClamp = Math.min(1.2, pLoad);
      const contactCapM = potCapMPrime - 0.24 * pClamp * pClamp * (1.0 - 0.25 * pClamp);
      // Xu et al. 2004 Eqs. 14/17: ink loss grows with distance travelled, so blend an absolute 60-unit reference with the
      // per-stroke normalisation (Strassmann 1986 Sec. 4.1 sets the dip per stroke length) instead of fully normalising
      const stepFrac = dsStep / Math.max(24.0, 0.5 * (origLen + 60.0));
      const speedEst = tuftSpeedEst(pLoad);
      const innerStress = (pLoad * tuftEllipticity * speedEst) / Math.max(0.22, wTip);
      const chiInteract = speedEst * innerStress * stepFrac;
      const compSqueeze = Math.max(0.0, wBelly - contactCapM) * (0.60 + 0.40 * squeezeParam) + 0.28 * rawPoolWeight[i] * squeezeParam;

      // Two-compartment axial wetness depletion (Xu et al. 2004 Eq. 17); the belly-to-tip capillary recharge term is a heuristic of this model, not taken from a paper
      wTip = Math.max(
        0.20,
        Math.min(1.0, wTip - 0.30 * chiInteract + 0.24 * (wBelly - wTip) + 0.10 * compSqueeze * stepFrac)
      );
      wBelly = Math.max(
        0.28,
        Math.min(1.0, wBelly - 0.14 * chiInteract - 0.07 * compSqueeze * stepFrac)
      );
    }

    const sinPsi = Math.sin(psiOblique);
    // WetBrush instantaneous compression squeeze-out & inner stress (Chen et al. 2015 Eqs. 12-13; Xu et al. 2004 Eqs. 12, 14; Xu et al. 2003 Sec. 3.1)
    const packHere = bristlePacking(pLoad, rawPoolWeight[i], sinPsi);
    const capHere = Math.max(0.22, 1.0 - 0.50 * packHere) - 0.20 * Math.min(1.2, pLoad) * Math.min(1.2, pLoad);
    const squeezeHere = (Math.max(0.0, wBelly - capHere) * 0.65 + 0.32 * rawPoolWeight[i]) * (0.55 + 0.45 * squeezeParam);
    const speedHere = tuftSpeedEst(pLoad);
    const stressHere = (pLoad * tuftEllipticity * speedHere) / Math.max(0.22, wTip);

    // Jianhao (兼毫) stiff rabbit/weasel inner core vs. compliant goat-hair outer mantle contact fraction (Chu & Tai 2002 Sec. 3)
    const coreFracHere = Math.max(
      0.34,
      Math.min(0.58, 0.46 - 0.08 * (pLoad - 0.80) + 0.05 * (1.0 - wTip) + 0.03 * (coreMantleParam - 1.35))
    );

    // Area/width-conserving Zhongfeng (中鋒) vs. Cefeng (側鋒) double-half-ellipse lateral shift
    // Preserves rawWL[i] + rawWR[i] exactly while shifting the stiff tip toward one boundary and the soft belly toward the other
    const uStartFade = u < 0.06 ? (u / 0.06) * (u / 0.06) * (3.0 - 2.0 * (u / 0.06)) : 1.0;
    const uEndFade = u > 0.90 ? ((1.0 - u) / 0.10) * ((1.0 - u) / 0.10) * (3.0 - 2.0 * ((1.0 - u) / 0.10)) : 1.0;
    const wTot = rawWL[i] + rawWR[i];
    const cefengShift = Math.max(-0.095, Math.min(0.095, 0.075 * cefengParam * sinPsi * uStartFade * uEndFade));
    const shiftedL = rawWL[i] - 0.5 * wTot * cefengShift;
    rawWL[i] = wTot > 0.16 ? Math.max(0.08, Math.min(wTot - 0.08, shiftedL)) : rawWL[i];
    rawWR[i] = wTot - rawWL[i];

    p.tuftObliqueness = psiOblique;
    p.cefengBias = sinPsi * (0.35 + 0.50 * Math.min(1.8, cefengParam));
    p.plasticLag = plasticRho;
    p.tuftEllipticity = tuftEllipticity;
    p.tuftWetness = wTip;
    p.bellyReservoir = wBelly;
    p.compressionSqueeze = squeezeHere;
    p.tuftStress = stressHere;
    p.coreMantleRadiusFrac = coreFracHere;
  }

  // Curvature-clamped inner offset
  const clampedRL = new Float32Array(numSamples + 1);
  const clampedRR = new Float32Array(numSamples + 1);
  for (let i = 0; i <= numSamples; i++) {
    let rL = shaftRadius * rawWL[i];
    let rR = shaftRadius * rawWR[i];
    const iPrev = Math.max(0, i - 1);
    const iNext = Math.min(numSamples, i + 1);
    const dTheta = Math.hypot(rawPts[iNext].tx - rawPts[iPrev].tx, rawPts[iNext].ty - rawPts[iPrev].ty);
    const ds = Math.max(0.1, (rawPts[iNext].s - rawPts[iPrev].s) * scale);
    const kappa = dTheta / ds;
    if (kappa > 1e-4) {
      const nearAcuteCf = behavior.isPieZhe && cornerFeatures.some(cf => cf.angle > 1.0 && Math.abs(rawPts[i].s - cf.s) <= 4.5);
      const floorMult = nearAcuteCf ? 0.22 : 0.78;
      const maxR = Math.max(shaftRadius * floorMult, 0.90 / kappa);
      const cross = rawPts[iPrev].tx * rawPts[iNext].ty - rawPts[iPrev].ty * rawPts[iNext].tx;
      if (cross > 0) {
        rL = Math.min(rL, maxR);
      } else if (cross < 0) {
        rR = Math.min(rR, maxR);
      }
    }
    clampedRL[i] = rL;
    clampedRR[i] = rR;
  }

  // Smooth clamped radii across neighbors
  for (let pass = 0; pass < 2; pass++) {
    const sRL = new Float32Array(clampedRL);
    const sRR = new Float32Array(clampedRR);
    for (let i = 1; i < numSamples; i++) {
      clampedRL[i] = 0.25 * sRL[i - 1] + 0.50 * sRL[i] + 0.25 * sRL[i + 1];
      clampedRR[i] = 0.25 * sRR[i - 1] + 0.50 * sRR[i] + 0.25 * sRR[i + 1];
    }
  }

  for (let i = 0; i <= numSamples; i++) {
    const p = rawPts[i];
    const rL = clampedRL[i];
    const rR = clampedRR[i];
    p.lx = p.x + p.nx * rL;
    p.ly = p.y + p.ny * rL;
    p.rx = p.x - p.nx * rR;
    p.ry = p.y - p.ny * rR;

    p.pressure = Math.max(0.08, (rL + rR) / (2 * shaftRadius));
    p.radius = Math.max(0.4, (rL + rR) * 0.5);
    p.poolWeight = rawPoolWeight[i];
    p.speedFactor = Math.max(0.32, 1.30 - 0.45 * Math.min(1.5, p.pressure));
  }

  // 4 passes of Laplacian smoothing all the way to numSamples - 1
  const smoothLimit = numSamples - 1;
  for (let pass = 0; pass < 4; pass++) {
    const nextLx = rawPts.map(p => p.lx);
    const nextLy = rawPts.map(p => p.ly);
    const nextRx = rawPts.map(p => p.rx);
    const nextRy = rawPts.map(p => p.ry);

    for (let i = 1; i < smoothLimit; i++) {
      nextLx[i] = 0.25 * rawPts[i - 1].lx + 0.50 * rawPts[i].lx + 0.25 * rawPts[i + 1].lx;
      nextLy[i] = 0.25 * rawPts[i - 1].ly + 0.50 * rawPts[i].ly + 0.25 * rawPts[i + 1].ly;
      nextRx[i] = 0.25 * rawPts[i - 1].rx + 0.50 * rawPts[i].rx + 0.25 * rawPts[i + 1].rx;
      nextRy[i] = 0.25 * rawPts[i - 1].ry + 0.50 * rawPts[i].ry + 0.25 * rawPts[i + 1].ry;
    }
    for (let i = 1; i < smoothLimit; i++) {
      rawPts[i].lx = nextLx[i];
      rawPts[i].ly = nextLy[i];
      rawPts[i].rx = nextRx[i];
      rawPts[i].ry = nextRy[i];
    }
  }

  // Self-intersection loop collapsing
  function collapsePolylineLoops(pts, isLeft) {
    const getP = (idx) => isLeft ? { x: pts[idx].lx, y: pts[idx].ly } : { x: pts[idx].rx, y: pts[idx].ry };
    const setP = (idx, x, y) => {
      if (isLeft) {
        pts[idx].lx = x;
        pts[idx].ly = y;
      } else {
        pts[idx].rx = x;
        pts[idx].ry = y;
      }
    };
    function ccw(p1, p2, p3) {
      return (p3.y - p1.y) * (p2.x - p1.x) - (p2.y - p1.y) * (p3.x - p1.x);
    }
    function checkIntersect(p1, p2, p3, p4) {
      const min1x = Math.min(p1.x, p2.x), max1x = Math.max(p1.x, p2.x);
      const min1y = Math.min(p1.y, p2.y), max1y = Math.max(p1.y, p2.y);
      const min2x = Math.min(p3.x, p4.x), max2x = Math.max(p3.x, p4.x);
      const min2y = Math.min(p3.y, p4.y), max2y = Math.max(p3.y, p4.y);
      if (max1x < min2x || max2x < min1x || max1y < min2y || max2y < min1y) return false;
      const c1 = ccw(p1, p2, p3);
      const c2 = ccw(p1, p2, p4);
      const c3 = ccw(p3, p4, p1);
      const c4 = ccw(p3, p4, p2);
      return ((c1 > 0 && c2 < 0) || (c1 < 0 && c2 > 0)) && ((c3 > 0 && c4 < 0) || (c3 < 0 && c4 > 0));
    }

    let iterations = 0;
    while (iterations < 12) {
      let found = false;
      const n = pts.length;
      for (let i = 0; i < n - 1; i++) {
        const p1 = getP(i);
        const p2 = getP(i + 1);
        for (let j = i + 2; j < n - 1; j++) {
          const p3 = getP(j);
          const p4 = getP(j + 1);
          if (checkIntersect(p1, p2, p3, p4)) {
            const a = i;
            const b = j + 1;
            const pa = getP(a);
            const pb = getP(b);
            const isHookLoop = !!(hookFeature && b >= hookFeature.index - 2);
            if (isHookLoop) {
              for (let k = a + 1; k < b; k++) {
                const t = (k - a) / Math.max(1, b - a);
                setP(k, pa.x + t * (pb.x - pa.x), pa.y + t * (pb.y - pa.y));
              }
            } else {
              const midK = Math.floor((a + b) * 0.5);
              const pullW = behavior.isPieZhe ? 0.65 : 0.45;
              const targetX = pts[midK].x + (isLeft ? 1 : -1) * pts[midK].nx * (shaftRadius * 0.25);
              const targetY = pts[midK].y + (isLeft ? 1 : -1) * pts[midK].ny * (shaftRadius * 0.25);
              const vx = (1.0 - pullW) * (0.5 * (pa.x + pb.x)) + pullW * targetX;
              const vy = (1.0 - pullW) * (0.5 * (pa.y + pb.y)) + pullW * targetY;
              for (let k = a + 1; k < b; k++) {
                if (k <= midK) {
                  const t = (k - a) / Math.max(1, midK - a);
                  setP(k, pa.x + t * (vx - pa.x), pa.y + t * (vy - pa.y));
                } else {
                  const t = (k - midK) / Math.max(1, b - midK);
                  setP(k, vx + t * (pb.x - vx), vy + t * (pb.y - vy));
                }
              }
            }
            found = true;
            break;
          }
        }
        if (found) break;
      }
      if (!found) break;
      iterations++;
    }
  }

  // Pre-progression loop collapse
  collapsePolylineLoops(rawPts, true);
  collapsePolylineLoops(rawPts, false);

  // Forward-progression enforcement pass on (lx, ly) and (rx, ry)
  for (let iter = 0; iter < 6; iter++) {
    for (let i = 0; i < numSamples; i++) {
      const nearAcuteCorner = cornerFeatures.some(cf => cf.angle > 1.1 && (Math.abs(rawPts[i].s - cf.s) <= 2.2 || (i + 1 <= numSamples && Math.abs(rawPts[i + 1].s - cf.s) <= 2.2)));
      if (nearAcuteCorner) continue;

      const dLx = rawPts[i + 1].lx - rawPts[i].lx;
      const dLy = rawPts[i + 1].ly - rawPts[i].ly;
      const dotL = dLx * rawPts[i].tx + dLy * rawPts[i].ty;
      if (dotL < 0.05) {
        const neededL = 0.08 - dotL;
        if (i > 0) {
          rawPts[i].lx -= rawPts[i].tx * (neededL * 0.5);
          rawPts[i].ly -= rawPts[i].ty * (neededL * 0.5);
          rawPts[i + 1].lx += rawPts[i].tx * (neededL * 0.5);
          rawPts[i + 1].ly += rawPts[i].ty * (neededL * 0.5);
        } else {
          rawPts[i + 1].lx += rawPts[i].tx * neededL;
          rawPts[i + 1].ly += rawPts[i].ty * neededL;
        }
      }

      const dRx = rawPts[i + 1].rx - rawPts[i].rx;
      const dRy = rawPts[i + 1].ry - rawPts[i].ry;
      const dotR = dRx * rawPts[i].tx + dRy * rawPts[i].ty;
      if (dotR < 0.05) {
        const neededR = 0.08 - dotR;
        if (i > 0) {
          rawPts[i].rx -= rawPts[i].tx * (neededR * 0.5);
          rawPts[i].ry -= rawPts[i].ty * (neededR * 0.5);
          rawPts[i + 1].rx += rawPts[i].tx * (neededR * 0.5);
          rawPts[i + 1].ry += rawPts[i].ty * (neededR * 0.5);
        } else {
          rawPts[i + 1].rx += rawPts[i].tx * neededR;
          rawPts[i + 1].ry += rawPts[i].ty * neededR;
        }
      }
    }

    for (let i = 1; i < numSamples; i++) {
      const nearAcuteCorner = cornerFeatures.some(cf => cf.angle > 1.1 && (Math.abs(rawPts[i].s - cf.s) <= 2.2 || (i + 1 <= numSamples && Math.abs(rawPts[i + 1].s - cf.s) <= 2.2)));
      if (nearAcuteCorner) continue;

      const sLx = 0.2 * rawPts[i - 1].lx + 0.6 * rawPts[i].lx + 0.2 * rawPts[i + 1].lx;
      const sLy = 0.2 * rawPts[i - 1].ly + 0.6 * rawPts[i].ly + 0.2 * rawPts[i + 1].ly;
      const pDotL = (sLx - rawPts[i - 1].lx) * rawPts[i - 1].tx + (sLy - rawPts[i - 1].ly) * rawPts[i - 1].ty;
      const nDotL = (rawPts[i + 1].lx - sLx) * rawPts[i].tx + (rawPts[i + 1].ly - sLy) * rawPts[i].ty;
      if (pDotL >= 0.05 && nDotL >= 0.05) {
        rawPts[i].lx = sLx;
        rawPts[i].ly = sLy;
      }

      const sRx = 0.2 * rawPts[i - 1].rx + 0.6 * rawPts[i].rx + 0.2 * rawPts[i + 1].rx;
      const sRy = 0.2 * rawPts[i - 1].ry + 0.6 * rawPts[i].ry + 0.2 * rawPts[i + 1].ry;
      const pDotR = (sRx - rawPts[i - 1].rx) * rawPts[i - 1].tx + (sRy - rawPts[i - 1].ry) * rawPts[i - 1].ty;
      const nDotR = (rawPts[i + 1].rx - sRx) * rawPts[i].tx + (rawPts[i + 1].ry - sRy) * rawPts[i].ty;
      if (pDotR >= 0.05 && nDotR >= 0.05) {
        rawPts[i].rx = sRx;
        rawPts[i].ry = sRy;
      }
    }
  }

  // Post-progression loop collapse
  collapsePolylineLoops(rawPts, true);
  collapsePolylineLoops(rawPts, false);

  if (hookFeature) {
    const hStart = hookFeature.index;
    const hEnd = numSamples;
    if (hEnd - hStart >= 4) {
      const startW = Math.hypot(rawPts[hStart].rx - rawPts[hStart].lx, rawPts[hStart].ry - rawPts[hStart].ly);
      const endW = Math.hypot(rawPts[hEnd].rx - rawPts[hEnd].lx, rawPts[hEnd].ry - rawPts[hEnd].ly);
      for (let i = hStart + 1; i < hEnd; i++) {
        const t = (i - hStart) / (hEnd - hStart);
        const linearW = startW * (1.0 - t) + endW * t;
        const curW = Math.hypot(rawPts[i].rx - rawPts[i].lx, rawPts[i].ry - rawPts[i].ly);
        if (curW > linearW * 1.02 && curW > 1e-4) {
          const targetW = 0.25 * curW + 0.75 * linearW;
          const scaleW = targetW / curW;
          const mx = 0.5 * (rawPts[i].lx + rawPts[i].rx);
          const my = 0.5 * (rawPts[i].ly + rawPts[i].ry);
          rawPts[i].lx = mx + (rawPts[i].lx - mx) * scaleW;
          rawPts[i].ly = my + (rawPts[i].ly - my) * scaleW;
          rawPts[i].rx = mx + (rawPts[i].rx - mx) * scaleW;
          rawPts[i].ry = my + (rawPts[i].ry - my) * scaleW;
        }
      }
    }
  }
  collapsePolylineLoops(rawPts, true);
  collapsePolylineLoops(rawPts, false);

  const cleanLimit = hookFeature ? Math.max(4, hookFeature.index - 3) : numSamples;
  for (let pass = 0; pass < 2; pass++) {
    for (let i = 0; i < cleanLimit; i++) {
      const nearSharp = cornerFeatures.some(cf => cf.angle > 0.45 && (Math.abs(rawPts[i].s - cf.s) <= 4.5 || (i + 1 <= numSamples && Math.abs(rawPts[i + 1].s - cf.s) <= 4.5)));
      if (nearSharp) continue;

      const dLx = rawPts[i + 1].lx - rawPts[i].lx;
      const dLy = rawPts[i + 1].ly - rawPts[i].ly;
      const dotL = dLx * rawPts[i].tx + dLy * rawPts[i].ty;
      if (dotL < -0.08) {
        rawPts[i + 1].lx += rawPts[i].tx * (-0.05 - dotL);
        rawPts[i + 1].ly += rawPts[i].ty * (-0.05 - dotL);
      }
      const dRx = rawPts[i + 1].rx - rawPts[i].rx;
      const dRy = rawPts[i + 1].ry - rawPts[i].ry;
      const dotR = dRx * rawPts[i].tx + dRy * rawPts[i].ty;
      if (dotR < -0.08) {
        rawPts[i + 1].rx += rawPts[i].tx * (-0.05 - dotR);
        rawPts[i + 1].ry += rawPts[i].ty * (-0.05 - dotR);
      }
    }
  }

  // Expanded corner features for geometry and evaluation
  const evalCornerFeatures = [...cornerFeatures];
  // Also detect short-stroke flick corner like 心 s3 (origLen < 25)
  if (cornerFeatures.length === 0 && !hookFeature && !behavior.isCrownDot) {
    let bestA = 0;
    let bestI = -1;
    for (let i = 2; i < numSamples - 2; i++) {
      if (rawPts[i].turnAngle > bestA && rawPts[i].turnAngle > 0.36) {
        bestA = rawPts[i].turnAngle;
        bestI = i;
      }
    }
    if (bestI !== -1) {
      evalCornerFeatures.push({
        index: bestI,
        u: rawPts[bestI].u,
        s: rawPts[bestI].s,
        angle: bestA,
        turnSign: rawPts[bestI].turnSign,
        kind: "corner"
      });
    }
  }


  return {
    stroke,
    behavior,
    origLen,
    totalLen,
    shaftRadius,
    samples: rawPts,
    features,
    hookFeature,
    cornerFeatures: evalCornerFeatures,
    boxSize,
    sweepStartU: 0.43,
    _brushCompileKey: getBrushCompileKey(SLENDER_PHYSICS)
  };
}

/**
 * 筆画輪郭境界線のSVGパス文字列（外周）生成
 */
function traceSmoothStrokeContourPath(compiled, limitIdx, isHookTruncated = false) {
  const pts = compiled.samples;
  if (!pts || limitIdx < 1) return "";

  const isSharpTip = (compiled.behavior.isSweepEnd && !compiled.behavior.isZiHengPie) || compiled.behavior.isRoofHook || compiled.behavior.isRisingTi || compiled.behavior.isVerticalTi || compiled.behavior.isRightNa || !!compiled.hookFeature;
  const leftChain = [];
  const rightChain = [];
  const hf = compiled.hookFeature;
  const isUpHook = hf && hf.isUpwardHook;
  const leftLimit = (isHookTruncated && !isUpHook) ? Math.max(2, limitIdx - 5) : limitIdx;
  const rightLimit = (isHookTruncated && isUpHook) ? Math.max(2, limitIdx - 5) : limitIdx;
  for (let i = 0; i <= leftLimit; i++) {
    leftChain.push({ x: pts[i].lx, y: pts[i].ly });
  }
  for (let i = 0; i <= rightLimit; i++) {
    rightChain.push({ x: pts[i].rx, y: pts[i].ry });
  }
  const smoothL = chaikinSmoothOpenChain(leftChain, 2);
  const smoothR = chaikinSmoothOpenChain(rightChain, 2);

  if (smoothL.length === 0 || smoothR.length === 0) return "";

  let d = "M " + numFmt(smoothL[0].x) + " " + numFmt(smoothL[0].y);
  for (let i = 1; i < smoothL.length; i++) {
    d += " L " + numFmt(smoothL[i].x) + " " + numFmt(smoothL[i].y);
  }

  const lastL = smoothL[smoothL.length - 1];
  const lastR = smoothR[smoothR.length - 1];
  const endPt = pts[limitIdx];
  const tipExt = (compiled.hookFeature ? 1.2 : 1.8) * ((compiled.boxSize || 109) / 792);

  if (isHookTruncated) {
    d += " L " + numFmt(lastR.x) + " " + numFmt(lastR.y);
  } else if (isSharpTip && limitIdx >= pts.length - 2) {
    const tipX = (lastL.x + lastR.x) * 0.5 + endPt.tx * tipExt;
    const tipY = (lastL.y + lastR.y) * 0.5 + endPt.ty * tipExt;
    d += " L " + numFmt(tipX) + " " + numFmt(tipY) + " L " + numFmt(lastR.x) + " " + numFmt(lastR.y);
  } else if (compiled.behavior.isDot || compiled.behavior.isCrownDot) {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capMult = compiled.behavior.isCrownDot ? 0.16 : 0.20;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * capMult;
    d += " Q " + numFmt(endMidX + endPt.tx * capSpan) + " " + numFmt(endMidY + endPt.ty * capSpan) + " " + numFmt(lastR.x) + " " + numFmt(lastR.y);
  } else {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * 0.24;
    d += " Q " + numFmt(endMidX + endPt.tx * capSpan) + " " + numFmt(endMidY + endPt.ty * capSpan) + " " + numFmt(lastR.x) + " " + numFmt(lastR.y);
  }

  for (let i = smoothR.length - 2; i >= 0; i--) {
    d += " L " + numFmt(smoothR[i].x) + " " + numFmt(smoothR[i].y);
  }

  const firstL = smoothL[0];
  const firstR = smoothR[0];
  const p0 = pts[0];
  const entryRatio = (compiled.behavior.isDot || compiled.behavior.isCrownDot) ? 0.18 : 0.20;
  const entrySpan = Math.hypot(firstL.x - firstR.x, firstL.y - firstR.y) * entryRatio;
  const cp1x = firstR.x - p0.tx * (entrySpan * 0.4);
  const cp1y = firstR.y - p0.ty * (entrySpan * 0.4);
  const cp2x = firstL.x - p0.tx * (entrySpan * 0.4);
  const cp2y = firstL.y - p0.ty * (entrySpan * 0.4);
  d += " C " + numFmt(cp1x) + " " + numFmt(cp1y) + " " + numFmt(cp2x) + " " + numFmt(cp2y) + " " + numFmt(firstL.x) + " " + numFmt(firstL.y) + " Z";

  return d;
}

/**
 * 鉤部（趯・戈鉤・横鉤）の三次元的三角形ウェッジパス生成
 */
function drawFleshyHookWedgePath(compiled, limitIdx, heelIdx) {
  const hf = compiled.hookFeature;
  if (!hf) return "";
  const pts = compiled.samples;
  const H = pts[heelIdx];
  if (!H) return "";
  const tonStrength = SLENDER_PHYSICS.tonStrength || 1.08;
  const r = compiled.shaftRadius * (1.08 * tonStrength);

  const stx = H.tx;
  const sty = H.ty;
  let d = "";

  if (hf.isDownLeftHook) {
    const joinLIdx = Math.max(4, heelIdx - 8);
    const joinRIdx = Math.max(4, heelIdx - 7);
    const outerJoin = pts[joinLIdx];
    const innerJoin = pts[joinRIdx];
    if (!outerJoin || !innerJoin) return "";

    const endPt = pts[pts.length - 1];
    const tipX = endPt.x - r * 0.35;
    const tipY = endPt.y + r * 0.25;

    d += "M " + numFmt(outerJoin.lx) + " " + numFmt(outerJoin.ly);
    for (let k = joinLIdx + 1; k <= Math.min(pts.length - 1, heelIdx - 2); k++) {
      d += " L " + numFmt(pts[k].lx) + " " + numFmt(pts[k].ly);
    }
    d += " Q " + numFmt(H.x + r * 0.95) + " " + numFmt(H.y - r * 0.95) + " " + numFmt(H.x + r * 1.25) + " " + numFmt(H.y + r * 0.15);
    d += " Q " + numFmt(H.x + r * 0.65) + " " + numFmt(H.y + r * 1.35) + " " + numFmt(tipX) + " " + numFmt(tipY);
    d += " Q " + numFmt(H.x - r * 0.45) + " " + numFmt(H.y + r * 0.95) + " " + numFmt(innerJoin.rx) + " " + numFmt(innerJoin.ry);
    for (let k = joinRIdx - 1; k >= joinLIdx; k--) {
      d += " L " + numFmt(pts[k].rx) + " " + numFmt(pts[k].ry);
    }
    d += " Z";
  } else if (hf.isUpwardHook) {
    const outerIdx = Math.max(2, heelIdx - 6);
    const innerIdx = Math.max(2, heelIdx - 6);
    if (!pts[outerIdx] || !pts[innerIdx]) return "";

    const tipX = H.x + r * 0.35;
    const tipY = H.y - r * 3.0;
    const heelBottomX = H.x + r * 1.15;
    const heelBottomY = H.y + r * 0.95;

    d += "M " + numFmt(pts[outerIdx].lx) + " " + numFmt(pts[outerIdx].ly);
    for (let k = outerIdx + 1; k <= heelIdx; k++) {
      d += " L " + numFmt(pts[k].lx) + " " + numFmt(pts[k].ly);
    }
    d += " Q " + numFmt(pts[heelIdx].lx + r * 0.45) + " " + numFmt(H.y + r * 1.05) + " " + numFmt(heelBottomX) + " " + numFmt(heelBottomY);
    d += " Q " + numFmt(H.x + r * 1.35) + " " + numFmt(H.y - r * 0.45) + " " + numFmt(tipX) + " " + numFmt(tipY);
    d += " Q " + numFmt(pts[heelIdx].rx + r * 0.05) + " " + numFmt(H.y - r * 0.55) + " " + numFmt(pts[innerIdx].rx) + " " + numFmt(pts[innerIdx].ry) + " Z";
  } else {
    let ux = -0.93;
    let uy = -0.36;
    let hookLen = r * 3.15;

    const flickProgress = (limitIdx - heelIdx) / Math.max(1, pts.length - 1 - heelIdx);
    const curLen = Math.max(r * 1.6, hookLen * Math.min(1.0, flickProgress * 1.15));

    let tipX = H.x + ux * curLen;
    let tipY = H.y + uy * curLen;
    let heelBottomX = H.x + stx * r * 1.15;
    let heelBottomY = H.y + sty * r * 1.15;

    if (hf.isCurvedBowHook) {
      heelBottomX = H.x + stx * r * 0.85;
      heelBottomY = H.y + r * 0.90;
      tipX = H.x - r * 2.8;
      tipY = H.y - r * 0.70;
    }

    const outerIdx = Math.max(2, heelIdx - (hf.isCurvedBowHook ? 4 : 6));
    const innerIdx = Math.max(2, heelIdx - (hf.isCurvedBowHook ? 4 : 5));
    if (!pts[outerIdx] || !pts[innerIdx]) return "";

    d += "M " + numFmt(pts[outerIdx].rx) + " " + numFmt(pts[outerIdx].ry);
    for (let k = outerIdx + 1; k <= heelIdx; k++) {
      d += " L " + numFmt(pts[k].rx) + " " + numFmt(pts[k].ry);
    }
    d += " Q " + numFmt(pts[heelIdx].rx + stx * r * 0.8) + " " + numFmt(pts[heelIdx].ry + sty * r * 0.8) + " " + numFmt(heelBottomX) + " " + numFmt(heelBottomY);
    d += " Q " + numFmt((heelBottomX + tipX) * 0.5 + stx * r * 0.25) + " " + numFmt((heelBottomY + tipY) * 0.5 + sty * r * 0.25) + " " + numFmt(tipX) + " " + numFmt(tipY);
    d += " Q " + numFmt(pts[innerIdx].lx - (hf.isCurvedBowHook ? r * 0.20 : r * 0.45)) + " " + numFmt((tipY + pts[innerIdx].ly) * 0.5 + (hf.isCurvedBowHook ? 0 : r * 0.20)) + " " + numFmt(pts[innerIdx].lx) + " " + numFmt(pts[innerIdx].ly) + " Z";
  }

  return d;
}

/**
 * 長撇・掃筆の渇筆（かすれ）スリットパス生成（反時計回り閉曲線によりnonzeroで中抜き）
 */
function generateKasureSlitsPath(compiled, limitIdx) {
  const pts = compiled.samples;
  const origLen = compiled.origLen || 0;
  const cornersCount = compiled.cornerFeatures ? compiled.cornerFeatures.length : 0;
  if (!compiled.behavior.isSweepEnd || compiled.behavior.isZiHengPie || compiled.behavior.isRoofHook || compiled.behavior.isRisingTi || compiled.behavior.isVerticalTi || origLen <= 45 || compiled.behavior.isRightNa || compiled.hookFeature || cornersCount > 1) {
    return "";
  }

  const kScale = (SLENDER_PHYSICS.kasureAmount ?? 0.30) / 0.30;
  if (kScale <= 0) return "";
  const kasureChannels = [
    { lat: 0.38, startU: 0.76, endU: 0.94, widthFrac: 0.055 * kScale },
    { lat: 0.66, startU: 0.80, endU: 0.95, widthFrac: 0.055 * kScale }
  ];

  let slitPathD = "";

  for (const ch of kasureChannels) {
    const startIdx = Math.floor(pts.length * ch.startU);
    const endIdx = Math.min(limitIdx, Math.floor(pts.length * ch.endU));
    if (limitIdx <= startIdx || endIdx - startIdx < 2) continue;

    const rPts = [];
    const lPts = [];

    for (let i = startIdx; i <= endIdx; i++) {
      const p1 = pts[i];
      const uMid = p1.u;
      const t = Math.max(0, Math.min(1.0, (uMid - ch.startU) / (ch.endU - ch.startU)));
      const localWidth = Math.hypot(p1.rx - p1.lx, p1.ry - p1.ly);
      const env = Math.sin(Math.min(1.0, t / 0.35) * (Math.PI * 0.5)) * (1.0 - 0.25 * Math.pow(t, 2));
      const halfW = Math.max(0.12, localWidth * ch.widthFrac * env * 0.5);

      const bx = p1.lx + (p1.rx - p1.lx) * Math.max(0.28, Math.min(0.74, ch.lat - 0.04 * (p1.cefengBias || 0.0)));
      const by = p1.ly + (p1.ry - p1.ly) * Math.max(0.28, Math.min(0.74, ch.lat - 0.04 * (p1.cefengBias || 0.0)));

      rPts.push({ x: bx - p1.nx * halfW, y: by - p1.ny * halfW });
      lPts.push({ x: bx + p1.nx * halfW, y: by + p1.ny * halfW });
    }

    if (rPts.length < 2) continue;

    let chD = "M " + numFmt(rPts[0].x) + " " + numFmt(rPts[0].y);
    for (let i = 1; i < rPts.length; i++) {
      chD += " L " + numFmt(rPts[i].x) + " " + numFmt(rPts[i].y);
    }
    for (let i = lPts.length - 1; i >= 0; i--) {
      chD += " L " + numFmt(lPts[i].x) + " " + numFmt(lPts[i].y);
    }
    chD += " Z";

    slitPathD += (slitPathD ? " " : "") + chD;
  }

  return slitPathD;
}

/**
 * 瘦金體（Slender Gold）筆画コンパイラ
 * KanjiVG 中心線パス d (0..109 viewBox) を流麗な骨格・頓挫・渇筆を持つ輪郭パスへ変換
 */
function compileSlenderStrokePathD(d, type = "", index = 0, totalStrokes = 10, component = "") {
  if (typeof d === "object" && d !== null) {
    if (d.calligraphy_d) return d.calligraphy_d;
    type = type || d.type || "";
    index = index !== undefined ? index : (d.index || 0);
    component = component || d.component || "";
    d = d.d || "";
  }
  if (!d || typeof d !== "string") return "";

  try {
    const stroke = {
      d,
      type: type || "",
      index: index + 1,
      component: component || ""
    };
    const compiled = compileStrokePhysics(stroke, 0, 0, 109, totalStrokes);
    if (!compiled || !compiled.samples || compiled.samples.length < 2) {
      return d;
    }

    const rawPts = compiled.samples;
    const limit = rawPts.length - 1;
    const hf = compiled.hookFeature;
    const heelIdx = hf ? (hf.heelIdx || Math.max(4, hf.index - 4)) : -1;

    let pathD = traceSmoothStrokeContourPath(compiled, limit, false);

    // 長撇スリット渇筆（Kasure）
    const kasureD = generateKasureSlitsPath(compiled, limit);
    if (kasureD) {
      pathD += " " + kasureD;
    }

    return pathD;
  } catch (err) {
    console.warn("Slender compilation error:", err);
    return d;
  }
}

/***************************************************************************
 * 2D CANVAS SUMI-INK CALLIGRAPHY ENGINE
 ***************************************************************************/
let strokeBufferCanvas = null;
let strokeBufferCtx = null;

function getStrokeBufferCanvas(w, h) {
  if (typeof document === "undefined") return { bufferCanvas: null, bufferCtx: null };
  if (!strokeBufferCanvas || strokeBufferCanvas.width !== w || strokeBufferCanvas.height !== h) {
    strokeBufferCanvas = document.createElement("canvas");
    strokeBufferCanvas.width = w;
    strokeBufferCanvas.height = h;
    strokeBufferCtx = strokeBufferCanvas.getContext("2d");
  }
  return { bufferCanvas: strokeBufferCanvas, bufferCtx: strokeBufferCtx };
}

let xuanPaperSubstrateCache = null;
let lbmWorkspaceCache = null;
let kmOpticalLutCache = null;

/**
 * Physically-Based Multi-Layer Xuan Paper Substrate Generator
 * Grounded in:
 * - Chu & Tai (2005), "MoXi: Real-Time Ink Dispersion in Absorbent Paper", ACM TOG (SIGGRAPH 2005), Sec. 5.1, 5.3.1, 5.3.3, Eq. 6 & Eq. 9.
 * - Curtis, Anderson, Seims, Fleischer, Salesin (1997), "Computer-Generated Watercolor", SIGGRAPH '97, Sec. 4.1.
 *
 * Precomputes:
 * - zeroB5Grain: Anisotropic cellulose fiber network whose 5x5 integer box sums are identically zero
 *   (preventing step-quantization ripple along 5x5 spine sampling windows while giving crisp per-pixel fiber grain).
 * - macroFiber: Long-range laid bamboo screen lines (lianwen) & pulp flocculation clouds.
 * - height: Normalized paper surface topography h(x,y) in [0.05, 0.95].
 * - capacity: Local fluid-holding capacity c(x,y) = h(x,y)*(cMax - cMin) + cMin.
 * - blocking: Porous link blocking factor kappa_0(x,y) (Eq. 6: fiber density + alum sizing).
 * - pinning: Wet-dry contact-line disorder pinning threshold sigma_0(x,y) (Eq. 9).
 */
function getXuanPaperSubstrate(w, h) {
  if (xuanPaperSubstrateCache && xuanPaperSubstrateCache.w === w && xuanPaperSubstrateCache.h === h) {
    return xuanPaperSubstrateCache;
  }

  const n = w * h;
  const zeroB5Grain = new Float32Array(n);
  const filamentMap = new Float32Array(n);
  const macroFiber = new Float32Array(n);
  const height = new Float32Array(n);
  const capacity = new Float32Array(n);
  const blocking = new Float32Array(n);
  const pinning = new Float32Array(n);

  // 1. Synthesize tangled wingceltis (qingtan) & mulberry bark fiber filaments (paper-fibre texture after Chu & Tai 2005 Sec. 6.2, which uses scanned paper hair textures)
  let seed = 314159265;
  function rand01() {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296.0;
  }

  const numFilaments = 950;
  for (let f = 0; f < numFilaments; f++) {
    let fx = rand01() * w;
    let fy = rand01() * h;
    let ang = rand01() * Math.PI * 2.0;
    const curv = (rand01() - 0.5) * 0.032;
    const len = 18 + Math.floor(rand01() * 44);
    const strength = 0.24 + 0.28 * rand01();
    const isRidge = rand01() > 0.36 ? 1.0 : -0.85;

    for (let s = 0; s < len; s++) {
      const t = s / len;
      const env = Math.sin(Math.PI * t);
      const val = isRidge * strength * env;
      const ix = ((Math.round(fx) % w) + w) % w;
      const iy = ((Math.round(fy) % h) + h) % h;
      const idx = iy * w + ix;
      filamentMap[idx] += val;
      // 1-px lateral soft shoulder
      const ixL = (ix + w - 1) % w;
      const ixR = (ix + 1) % w;
      const iyU = (iy + h - 1) % h;
      const iyD = (iy + 1) % h;
      filamentMap[iy * w + ixL] += val * 0.45;
      filamentMap[iy * w + ixR] += val * 0.45;
      filamentMap[iyU * w + ix] += val * 0.45;
      filamentMap[iyD * w + ix] += val * 0.45;

      ang += curv;
      fx += Math.cos(ang);
      fy += Math.sin(ang);
    }
  }

  for (let i = 0; i < n; i++) {
    filamentMap[i] = Math.max(-1.0, Math.min(1.0, filamentMap[i] * 0.72));
  }

  const TWO_PI_5 = (2.0 * Math.PI) / 5.0;

  // 2. 1D row and column organic phase/envelope tables for curved cellulose fiber bundles (exact zero 5x5 box sum)
  const rowAmp1 = new Float32Array(h);
  const rowAmp2 = new Float32Array(h);
  const rowPhi1 = new Float32Array(h);
  const rowPhi2 = new Float32Array(h);
  const rowPhi3 = new Float32Array(h);
  const rowPhi4 = new Float32Array(h);

  for (let y = 0; y < h; y++) {
    rowAmp1[y] = 0.36 + 0.11 * Math.sin(y * 0.043 + 0.7) + 0.08 * Math.cos(y * 0.113 - 1.2);
    rowAmp2[y] = 0.24 + 0.09 * Math.cos(y * 0.061 + 2.1) + 0.06 * Math.sin(y * 0.157 + 0.4);
    rowPhi1[y] = 0.38 * y + 1.15 * Math.sin(y * 0.037 + 0.5) + 0.55 * Math.cos(y * 0.089 - 0.8);
    rowPhi2[y] = -0.52 * y + 1.30 * Math.cos(y * 0.041 + 1.9) + 0.60 * Math.sin(y * 0.097 + 1.1);
    rowPhi3[y] = 0.74 * y + 0.90 * Math.sin(y * 0.053 - 0.4);
    rowPhi4[y] = -0.31 * y + 1.05 * Math.cos(y * 0.067 + 2.6);
  }

  const colAmp1 = new Float32Array(w);
  const colAmp2 = new Float32Array(w);
  const colPsi1 = new Float32Array(w);
  const colPsi2 = new Float32Array(w);
  const colPsi3 = new Float32Array(w);
  const colPsi4 = new Float32Array(w);

  for (let x = 0; x < w; x++) {
    colAmp1[x] = 0.38 + 0.11 * Math.cos(x * 0.039 - 0.6) + 0.08 * Math.sin(x * 0.107 + 1.5);
    colAmp2[x] = 0.26 + 0.09 * Math.sin(x * 0.057 + 0.9) + 0.06 * Math.cos(x * 0.149 - 1.8);
    colPsi1[x] = 0.33 * x + 1.20 * Math.cos(x * 0.033 + 1.2) + 0.50 * Math.sin(x * 0.083 - 0.5);
    colPsi2[x] = -0.47 * x + 1.10 * Math.sin(x * 0.047 - 1.4) + 0.65 * Math.cos(x * 0.103 + 0.7);
    colPsi3[x] = 0.68 * x + 0.85 * Math.cos(x * 0.059 + 2.0);
    colPsi4[x] = -0.29 * x + 0.95 * Math.sin(x * 0.071 - 0.9);
  }

  // Exact 5-pixel harmonic cosine tables along x and y
  const cosX1 = new Float32Array(w);
  const sinX1 = new Float32Array(w);
  const cosX2 = new Float32Array(w);
  const sinX2 = new Float32Array(w);
  for (let x = 0; x < w; x++) {
    const a1 = TWO_PI_5 * x;
    const a2 = TWO_PI_5 * 2.0 * x;
    cosX1[x] = Math.cos(a1);
    sinX1[x] = Math.sin(a1);
    cosX2[x] = Math.cos(a2);
    sinX2[x] = Math.sin(a2);
  }

  const cosY1 = new Float32Array(h);
  const sinY1 = new Float32Array(h);
  const cosY2 = new Float32Array(h);
  const sinY2 = new Float32Array(h);
  for (let y = 0; y < h; y++) {
    const b1 = TWO_PI_5 * y;
    const b2 = TWO_PI_5 * 2.0 * y;
    cosY1[y] = Math.cos(b1);
    sinY1[y] = Math.sin(b1);
    cosY2[y] = Math.cos(b2);
    sinY2[y] = Math.sin(b2);
  }

  const cMin = 0.30;
  const cMax = 0.90;

  for (let y = 0; y < h; y++) {
    const rA1 = rowAmp1[y];
    const rA2 = rowAmp2[y];
    const cP1 = Math.cos(rowPhi1[y]), sP1 = Math.sin(rowPhi1[y]);
    const cP2 = Math.cos(rowPhi2[y]), sP2 = Math.sin(rowPhi2[y]);
    const cP3 = Math.cos(rowPhi3[y]), sP3 = Math.sin(rowPhi3[y]);
    const cP4 = Math.cos(rowPhi4[y]), sP4 = Math.sin(rowPhi4[y]);
    const cy1 = cosY1[y], sy1 = sinY1[y];
    const cy2 = cosY2[y], sy2 = sinY2[y];

    // Laid bamboo screen lines (lianwen: horizontal bamboo splints every ~11px)
    const screenRib = 0.34 * Math.sin(y * 0.56 + 0.25 * Math.sin(y * 0.08));
    const rowOff = y * w;

    for (let x = 0; x < w; x++) {
      const idx = rowOff + x;
      const cx1 = cosX1[x], sx1 = sinX1[x];
      const cx2 = cosX2[x], sx2 = sinX2[x];

      // Row-zero-sum fiber waves: cos(2*pi*m*x/5 + phi(y))
      const wRow =
        rA1 * ((cx1 * cP1 - sx1 * sP1) + 0.72 * (cx1 * cP2 - sx1 * sP2)) +
        rA2 * ((cx2 * cP3 - sx2 * sP3) + 0.65 * (cx2 * cP4 - sx2 * sP4));

      // Col-zero-sum fiber waves: cos(2*pi*n*y/5 + psi(x))
      const cQ1 = Math.cos(colPsi1[x]), sQ1 = Math.sin(colPsi1[x]);
      const cQ2 = Math.cos(colPsi2[x]), sQ2 = Math.sin(colPsi2[x]);
      const cQ3 = Math.cos(colPsi3[x]), sQ3 = Math.sin(colPsi3[x]);
      const cQ4 = Math.cos(colPsi4[x]), sQ4 = Math.sin(colPsi4[x]);
      const wCol =
        colAmp1[x] * ((cy1 * cQ1 - sy1 * sQ1) + 0.74 * (cy1 * cQ2 - sy1 * sQ2)) +
        colAmp2[x] * ((cy2 * cQ3 - sy2 * sQ3) + 0.62 * (cy2 * cQ4 - sy2 * sQ4));

      // 2D separable pore-lattice cross-harmonics (both row and col 5-px sums are identically 0)
      const wCross =
        0.28 * (cx1 * 0.82 - sx1 * 0.57) * (cy1 * 0.64 + sy1 * 0.77) +
        0.20 * (cx2 * 0.54 + sx2 * 0.84) * (cy1 * 0.91 - sy1 * 0.41) +
        0.16 * (cx1 * 0.36 + sx1 * 0.93) * (cy2 * 0.73 + sy2 * 0.68);

      const gZero = Math.max(-1.0, Math.min(1.0, 0.62 * (wRow + wCol + wCross)));
      zeroB5Grain[idx] = gZero;

      // Combine tangled bark filaments, laid bamboo screen lines, and pulp flocculation clouds
      const fil = filamentMap[idx];
      const f1 = Math.sin((x * 0.17 + y * 0.09) + 0.8 * Math.sin(x * 0.031 - y * 0.043));
      const f2 = Math.cos((x * 0.08 - y * 0.19) + 0.9 * Math.cos(x * 0.049 + y * 0.027));
      const floc = 0.5 * Math.sin(x * 0.053 + y * 0.061) * Math.cos(x * 0.079 - y * 0.047);
      const chainLine = 0.14 * Math.cos(x * 0.088);
      const mFib = Math.max(-1.0, Math.min(1.0, 0.46 * fil + 0.26 * f1 + 0.22 * f2 + 0.24 * floc + screenRib + chainLine));
      macroFiber[idx] = mFib;

      // Normalized paper height h(x,y) in [0.04, 0.96]
      const hVal = Math.max(0.04, Math.min(0.96, 0.50 + 0.28 * gZero + 0.20 * mFib));
      height[idx] = hVal;

      // Fluid capacity c = h * (c_max - c_min) + c_min (Curtis et al. 1997 Sec. 4.1): raised fibre ridges hold more capillary fluid
      capacity[idx] = hVal * (cMax - cMin) + cMin;

      // Alum sizing A(x,y) & porous blocking factor kappa_0(x,y) (Chu & Tai 2005 Eq. 6)
      const alum = 0.5 + 0.5 * Math.sin(x * 0.13 + y * 0.11 + 1.5 * gZero + 0.8 * fil);
      blocking[idx] = 0.14 + 0.28 * hVal + 0.14 * alum;

      // Pinning disorder texture P(x,y) & threshold sigma_0(x,y) (Chu & Tai 2005 Eq. 9)
      const disorder = 0.5 + 0.28 * gZero + 0.24 * mFib;
      pinning[idx] = 0.055 + 0.125 * Math.max(0.0, Math.min(1.0, disorder));
    }
  }

  xuanPaperSubstrateCache = { w, h, zeroB5Grain, filamentMap, macroFiber, height, capacity, blocking, pinning };
  return xuanPaperSubstrateCache;
}

// Tunable LBM constants (mutable so tests can isolate individual mechanisms)
const LBM_TUNING = {
  // Boundary evaporation eps_s per relaxation step at coffeeRingIntensity = 1 (paper: <= 0.005 over hundreds of steps)
  boundaryEvaporation: 0.006
};

/**
 * Reusable typed-array workspace for local bounding-box D2Q9 LBM percolation & pigment transport.
 */
function getLbmWorkspace(maxCells) {
  if (!lbmWorkspaceCache || lbmWorkspaceCache.maxCells < maxCells) {
    lbmWorkspaceCache = {
      maxCells,
      m0: new Float32Array(maxCells),
      mBlur: new Float32Array(maxCells),
      mTemp: new Float32Array(maxCells),
      dSpineSq: new Float32Array(maxCells),
      uField: new Float32Array(maxCells),
      vField: new Float32Array(maxCells),
      qField: new Float32Array(maxCells),
      surfInk: new Float32Array(maxCells),
      rho: new Float32Array(maxCells),
      pf: new Float32Array(maxCells),
      px: new Float32Array(maxCells),
      pfNext: new Float32Array(maxCells),
      rhoStart: new Float32Array(maxCells),
      uxField: new Float32Array(maxCells),
      uyField: new Float32Array(maxCells),
      f0: new Float32Array(maxCells),
      f1: new Float32Array(maxCells),
      f2: new Float32Array(maxCells),
      f3: new Float32Array(maxCells),
      f4: new Float32Array(maxCells),
      f5: new Float32Array(maxCells),
      f6: new Float32Array(maxCells),
      f7: new Float32Array(maxCells),
      f8: new Float32Array(maxCells),
      fn1: new Float32Array(maxCells),
      fn2: new Float32Array(maxCells),
      fn3: new Float32Array(maxCells),
      fn4: new Float32Array(maxCells),
      fn5: new Float32Array(maxCells),
      fn6: new Float32Array(maxCells),
      fn7: new Float32Array(maxCells),
      fn8: new Float32Array(maxCells)
    };
  }
  return lbmWorkspaceCache;
}

/**
 * Precomputed Exact Two-Flux Kubelka-Munk Hyperbolic Reflectance (R1) & Transmittance (T1) Lookup Tables
 * Grounded in Curtis et al. (1997), "Computer-Generated Watercolor", SIGGRAPH '97, Sec. 5.2 (unnumbered Kubelka-Munk equations):
 *   a = 1 + K / S,  b = sqrt(a^2 - 1)
 *   R1(x) = sinh(b*S*x) / (a*sinh(b*S*x) + b*cosh(b*S*x))
 *   T1(x) = b / (a*sinh(b*S*x) + b*cosh(b*S*x))
 */
function getKubelkaMunkOpticalLut() {
  if (kmOpticalLutCache) return kmOpticalLutCache;

  const N = 2048;
  const maxX = 2.0;
  const palettes = {
    // Pine-soot carbon sumi ink (songyan mo): warm brown-black carbon absorption + animal-glue scattering
    "sumi": {
      K: [2.04, 2.20, 2.38],
      S: [0.35, 0.30, 0.26],
      R2: [0.953, 0.929, 0.886]
    },
    // Cinnabar seal ink (zhusha, HgS): strong red scattering, strong green/blue absorption
    "vermilion": {
      K: [0.32, 2.85, 3.10],
      S: [1.48, 0.22, 0.19],
      R2: [0.953, 0.929, 0.886]
    },
    // Luminous mineral shell-white / silver sumi suspension for dark slate theme
    "dark-sumi": {
      K: [0.16, 0.14, 0.11],
      S: [1.85, 1.94, 2.06],
      R2: [0.071, 0.086, 0.122]
    }
  };

  kmOpticalLutCache = {};
  for (const [mode, pal] of Object.entries(palettes)) {
    const R1R = new Float32Array(N);
    const R1G = new Float32Array(N);
    const R1B = new Float32Array(N);
    const T1R = new Float32Array(N);
    const T1G = new Float32Array(N);
    const T1B = new Float32Array(N);

    const a = [0, 0, 0];
    const b = [0, 0, 0];
    for (let c = 0; c < 3; c++) {
      a[c] = 1.0 + pal.K[c] / pal.S[c];
      b[c] = Math.sqrt(Math.max(1e-8, a[c] * a[c] - 1.0));
    }

    for (let i = 0; i < N; i++) {
      const x = (i / (N - 1)) * maxX;
      for (let c = 0; c < 3; c++) {
        const arg = b[c] * pal.S[c] * x;
        const sh = Math.sinh(arg);
        const ch = Math.cosh(arg);
        const denom = a[c] * sh + b[c] * ch;
        const r1 = denom > 1e-9 ? sh / denom : 0.0;
        const t1 = denom > 1e-9 ? b[c] / denom : 1.0;
        if (c === 0) { R1R[i] = r1; T1R[i] = t1; }
        else if (c === 1) { R1G[i] = r1; T1G[i] = t1; }
        else { R1B[i] = r1; T1B[i] = t1; }
      }
    }

    kmOpticalLutCache[mode] = { N, maxX, R1R, R1G, R1B, T1R, T1G, T1B, R2: pal.R2 };
  }
  return kmOpticalLutCache;
}

function traceSmoothStrokeContour(ctx, compiled, limitIdx, isHookTruncated = false) {
  const pts = compiled.samples;
  if (!pts || limitIdx < 1) return;

  const isSharpTip = (compiled.behavior.isSweepEnd && !compiled.behavior.isZiHengPie) || compiled.behavior.isRoofHook || compiled.behavior.isRisingTi || compiled.behavior.isVerticalTi || compiled.behavior.isRightNa || !!compiled.hookFeature;

  // Standard smooth boundary chains up to limitIdx
  const leftChain = [];
  const rightChain = [];
  const hf = compiled.hookFeature;
  const isUpHook = hf && hf.isUpwardHook;
  const leftLimit = (isHookTruncated && !isUpHook) ? Math.max(2, limitIdx - 5) : limitIdx;
  const rightLimit = (isHookTruncated && isUpHook) ? Math.max(2, limitIdx - 5) : limitIdx;
  for (let i = 0; i <= leftLimit; i++) {
    leftChain.push({ x: pts[i].lx, y: pts[i].ly });
  }
  for (let i = 0; i <= rightLimit; i++) {
    rightChain.push({ x: pts[i].rx, y: pts[i].ry });
  }
  const smoothL = chaikinSmoothOpenChain(leftChain, 2);
  const smoothR = chaikinSmoothOpenChain(rightChain, 2);

  ctx.beginPath();
  ctx.moveTo(smoothL[0].x, smoothL[0].y);
  for (let i = 1; i < smoothL.length; i++) {
    ctx.lineTo(smoothL[i].x, smoothL[i].y);
  }

  const lastL = smoothL[smoothL.length - 1];
  const lastR = smoothR[smoothR.length - 1];
  const endPt = pts[limitIdx];
  const tipExt = (compiled.hookFeature ? 1.2 : 1.8) * ((compiled.boxSize || 792) / 792);

  if (isHookTruncated) {
    ctx.lineTo(lastR.x, lastR.y);
  } else if (isSharpTip && limitIdx >= pts.length - 2) {
    const tipX = (lastL.x + lastR.x) * 0.5 + endPt.tx * tipExt;
    const tipY = (lastL.y + lastR.y) * 0.5 + endPt.ty * tipExt;
    ctx.lineTo(tipX, tipY);
    ctx.lineTo(lastR.x, lastR.y);
  } else if (compiled.behavior.isDot || compiled.behavior.isCrownDot) {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capMult = compiled.behavior.isCrownDot ? 0.16 : 0.20;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * capMult;
    ctx.quadraticCurveTo(
      endMidX + endPt.tx * capSpan,
      endMidY + endPt.ty * capSpan,
      lastR.x,
      lastR.y
    );
  } else {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * 0.24;
    ctx.quadraticCurveTo(
      endMidX + endPt.tx * capSpan,
      endMidY + endPt.ty * capSpan,
      lastR.x,
      lastR.y
    );
  }

  for (let i = smoothR.length - 2; i >= 0; i--) {
    ctx.lineTo(smoothR[i].x, smoothR[i].y);
  }

  const firstL = smoothL[0];
  const firstR = smoothR[0];
  const p0 = pts[0];
  const entryRatio = (compiled.behavior.isDot || compiled.behavior.isCrownDot) ? 0.18 : 0.20;
  const entrySpan = Math.hypot(firstL.x - firstR.x, firstL.y - firstR.y) * entryRatio;
  ctx.bezierCurveTo(
    firstR.x - p0.tx * (entrySpan * 0.4),
    firstR.y - p0.ty * (entrySpan * 0.4),
    firstL.x - p0.tx * (entrySpan * 0.4),
    firstL.y - p0.ty * (entrySpan * 0.4),
    firstL.x,
    firstL.y
  );
  ctx.closePath();
}

function drawFleshyHookWedge(ctx, compiled, limitIdx, heelIdx) {
  const hf = compiled.hookFeature;
  if (!hf) return;
  const pts = compiled.samples;
  const H = pts[heelIdx];
  if (!H) return;
  const tonStrength = SLENDER_PHYSICS.tonStrength || 1.08;
  const r = compiled.shaftRadius * (1.08 * tonStrength);

  const stx = H.tx;
  const sty = H.ty;

  ctx.save();
  ctx.fillStyle = "#000000";

  if (hf.isDownLeftHook) {
    const joinLIdx = Math.max(4, heelIdx - 8);
    const joinRIdx = Math.max(4, heelIdx - 7);
    const outerJoin = pts[joinLIdx];
    const innerJoin = pts[joinRIdx];
    if (!outerJoin || !innerJoin) {
      ctx.restore();
      return;
    }

    const endPt = pts[pts.length - 1];
    const tipX = endPt.x - r * 0.35;
    const tipY = endPt.y + r * 0.25;

    ctx.beginPath();
    ctx.moveTo(outerJoin.lx, outerJoin.ly);
    for (let k = joinLIdx + 1; k <= Math.min(pts.length - 1, heelIdx - 2); k++) {
      ctx.lineTo(pts[k].lx, pts[k].ly);
    }
    ctx.quadraticCurveTo(
      H.x + r * 0.95,
      H.y - r * 0.95,
      H.x + r * 1.25,
      H.y + r * 0.15
    );
    ctx.quadraticCurveTo(
      H.x + r * 0.65,
      H.y + r * 1.35,
      tipX,
      tipY
    );
    ctx.quadraticCurveTo(
      H.x - r * 0.45,
      H.y + r * 0.95,
      innerJoin.rx,
      innerJoin.ry
    );
    for (let k = joinRIdx - 1; k >= joinLIdx; k--) {
      ctx.lineTo(pts[k].rx, pts[k].ry);
    }
    ctx.lineTo(outerJoin.lx, outerJoin.ly);
    ctx.closePath();
    ctx.fill();
  } else if (hf.isUpwardHook) {
    const outerIdx = Math.max(2, heelIdx - 6);
    const innerIdx = Math.max(2, heelIdx - 6);
    if (!pts[outerIdx] || !pts[innerIdx]) {
      ctx.restore();
      return;
    }

    const tipX = H.x + r * 0.35;
    const tipY = H.y - r * 3.0;

    const heelBottomX = H.x + r * 1.15;
    const heelBottomY = H.y + r * 0.95;

    ctx.beginPath();
    ctx.moveTo(pts[outerIdx].lx, pts[outerIdx].ly);
    for (let k = outerIdx + 1; k <= heelIdx; k++) {
      ctx.lineTo(pts[k].lx, pts[k].ly);
    }
    ctx.quadraticCurveTo(
      pts[heelIdx].lx + r * 0.45,
      H.y + r * 1.05,
      heelBottomX,
      heelBottomY
    );
    ctx.quadraticCurveTo(
      H.x + r * 1.35,
      H.y - r * 0.45,
      tipX,
      tipY
    );
    ctx.quadraticCurveTo(
      pts[heelIdx].rx + r * 0.05,
      H.y - r * 0.55,
      pts[innerIdx].rx,
      pts[innerIdx].ry
    );
    ctx.closePath();
    ctx.fill();
  } else {
    let ux = -0.93;
    let uy = -0.36;
    let hookLen = r * 3.15;

    const flickProgress = (limitIdx - heelIdx) / Math.max(1, pts.length - 1 - heelIdx);
    const curLen = Math.max(r * 1.6, hookLen * Math.min(1.0, flickProgress * 1.15));

    let tipX = H.x + ux * curLen;
    let tipY = H.y + uy * curLen;
    let heelBottomX = H.x + stx * r * 1.15;
    let heelBottomY = H.y + sty * r * 1.15;

    if (hf.isCurvedBowHook) {
      heelBottomX = H.x + stx * r * 0.85;
      heelBottomY = H.y + r * 0.90;
      tipX = H.x - r * 2.8;
      tipY = H.y - r * 0.70;
    }

    const outerIdx = Math.max(2, heelIdx - (hf.isCurvedBowHook ? 4 : 6));
    const innerIdx = Math.max(2, heelIdx - (hf.isCurvedBowHook ? 4 : 5));
    if (!pts[outerIdx] || !pts[innerIdx]) {
      ctx.restore();
      return;
    }

    ctx.beginPath();
    ctx.moveTo(pts[outerIdx].rx, pts[outerIdx].ry);
    for (let k = outerIdx + 1; k <= heelIdx; k++) {
      ctx.lineTo(pts[k].rx, pts[k].ry);
    }
    ctx.quadraticCurveTo(
      pts[heelIdx].rx + stx * r * 0.8,
      pts[heelIdx].ry + sty * r * 0.8,
      heelBottomX,
      heelBottomY
    );
    ctx.quadraticCurveTo(
      (heelBottomX + tipX) * 0.5 + stx * r * 0.25,
      (heelBottomY + tipY) * 0.5 + sty * r * 0.25,
      tipX,
      tipY
    );
    ctx.quadraticCurveTo(
      pts[innerIdx].lx - (hf.isCurvedBowHook ? r * 0.20 : r * 0.45),
      (tipY + pts[innerIdx].ly) * 0.5 + (hf.isCurvedBowHook ? 0 : r * 0.20),
      pts[innerIdx].lx,
      pts[innerIdx].ly
    );
    ctx.closePath();
    ctx.fill();
  }

  ctx.restore();
}

function renderKasureAndFrayedBristles(ctx, compiled, limitIdx) {
  const pts = compiled.samples;
  const origLen = compiled.origLen || 0;
  const cornersCount = compiled.cornerFeatures ? compiled.cornerFeatures.length : 0;
  if (!compiled.behavior.isSweepEnd || compiled.behavior.isZiHengPie || compiled.behavior.isRoofHook || compiled.behavior.isRisingTi || compiled.behavior.isVerticalTi || origLen <= 45 || compiled.behavior.isRightNa || compiled.hookFeature || cornersCount > 1) return;

  const kScale = (SLENDER_PHYSICS.kasureAmount ?? 0.30) / 0.30;
  if (kScale <= 0) return;
  const kasureChannels = [
    { lat: 0.38, startU: 0.76, endU: 0.94, widthFrac: 0.055 * kScale },
    { lat: 0.66, startU: 0.80, endU: 0.95, widthFrac: 0.055 * kScale }
  ];

  ctx.save();
  ctx.globalCompositeOperation = "destination-out";
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  for (const ch of kasureChannels) {
    const startIdx = Math.floor(pts.length * ch.startU);
    const endIdx = Math.min(limitIdx, Math.floor(pts.length * ch.endU));
    if (limitIdx <= startIdx) continue;

    for (let i = startIdx; i < endIdx; i++) {
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const uMid = (p1.u + p2.u) * 0.5;
      const t = Math.max(0, Math.min(1.0, (uMid - ch.startU) / (ch.endU - ch.startU)));

      const localWidth = Math.hypot(p1.rx - p1.lx, p1.ry - p1.ly);
      const env = Math.sin(Math.min(1.0, t / 0.35) * (Math.PI * 0.5)) * (1.0 - 0.25 * Math.pow(t, 2));
      ctx.lineWidth = Math.max(0.25, localWidth * ch.widthFrac * env);

      const alpha = 0.55 * Math.pow(Math.sin(Math.min(1.0, t / 0.30) * (Math.PI * 0.5)), 1.8);
      ctx.strokeStyle = "rgba(0, 0, 0, " + alpha.toFixed(3) + ")";

      const lat1 = Math.max(0.28, Math.min(0.74, ch.lat - 0.04 * (p1.cefengBias || 0.0)));
      const lat2 = Math.max(0.28, Math.min(0.74, ch.lat - 0.04 * (p2.cefengBias || 0.0)));
      const b1x = p1.lx + (p1.rx - p1.lx) * lat1;
      const b1y = p1.ly + (p1.ry - p1.ly) * lat1;
      const b2x = p2.lx + (p2.rx - p2.lx) * lat2;
      const b2y = p2.ly + (p2.ry - p2.ly) * lat2;

      ctx.beginPath();
      ctx.moveTo(b1x, b1y);
      ctx.lineTo(b2x, b2y);
      ctx.stroke();
    }
  }

  ctx.restore();
}

/**
 * Physically-Based Ink Dispersion (D2Q9 Lattice Boltzmann Method), Pigment Advection/Granulation,
 * Contact-Line Coffee-Ring Darkening, and Two-Flux Kubelka-Munk Optical Rendering.
 *
 * References:
 * 1. Chu & Tai (2005), "MoXi: Real-Time Ink Dispersion in Absorbent Paper", ACM TOG 24(3), 504-511.
 *    - Surface-to-flow seepage phi = clamp(s, 0, c - rho) (Sec. 5.2)
 *    - D2Q9 He-Luo incompressible LBM equilibrium with low-saturation advection modulation psi(rho) (Eqs. 7-8)
 *    - Anisotropic fiber-blocked streaming kappa_i & disorder pinning threshold sigma (Eqs. 4, 5, 6, 9)
 *    - Suspended (pf) to fixed (px) pigment advection & fixture (Sec. 5.4, Eq. 10)
 * 2. Curtis et al. (1997), "Computer-Generated Watercolor", SIGGRAPH '97, 421-430.
 *    - Outward capillary replenishment & contact-line edge darkening (Sec. 4.3.3, Eq. 3)
 *    - Paper valley granulation vs. ridge thinning (Sec. 4.5)
 *    - Exact two-flux Kubelka-Munk hyperbolic reflectance R1(x) & transmittance T1(x) (Sec. 5.2, unnumbered equations)
 * 3. Chu & Tai (2004), "Real-Time Painting with an Expressive Virtual Chinese Brush", IEEE CG&A 24(5), 76-85.
 *    - Dry-brush (feibai/kasure) peak catching on raised paper fibers (p. 81)
 */
function renderPhysicallyBasedInkDispersionAndOptics(ctx, compiled, limitIdx, toneMode = "sumi") {
  const pts = compiled.samples;
  if (!pts || limitIdx < 1) return;

  const W = ctx.canvas.width;
  const H = ctx.canvas.height;
  const paper = getXuanPaperSubstrate(W, H);
  const kmAll = getKubelkaMunkOpticalLut();
  const km = kmAll[toneMode] || kmAll["sumi"];

  // 1. Compute tight padded bounding box of the stroke up to limitIdx
  const baseR = compiled.shaftRadius || 8.0;
  const pad = Math.ceil(baseR * 1.65 + 10);
  let minX = W, minY = H, maxX = 0, maxY = 0;
  for (let i = 0; i <= limitIdx; i++) {
    const p = pts[i];
    if (p.lx < minX) minX = p.lx;
    if (p.rx < minX) minX = p.rx;
    if (p.x < minX) minX = p.x;
    if (p.lx > maxX) maxX = p.lx;
    if (p.rx > maxX) maxX = p.rx;
    if (p.x > maxX) maxX = p.x;

    if (p.ly < minY) minY = p.ly;
    if (p.ry < minY) minY = p.ry;
    if (p.y < minY) minY = p.y;
    if (p.ly > maxY) maxY = p.ly;
    if (p.ry > maxY) maxY = p.ry;
    if (p.y > maxY) maxY = p.y;
  }
  if (compiled.hookFeature) {
    const hPad = Math.ceil(baseR * 3.6);
    minX -= hPad;
    minY -= hPad;
    maxX += hPad;
    maxY += hPad;
  }
  const x0 = Math.max(0, Math.floor(minX - pad));
  const y0 = Math.max(0, Math.floor(minY - pad));
  const x1 = Math.min(W - 1, Math.ceil(maxX + pad));
  const y1 = Math.min(H - 1, Math.ceil(maxY + pad));
  const bw = x1 - x0 + 1;
  const bh = y1 - y0 + 1;
  if (bw <= 2 || bh <= 2) return;

  const nCells = bw * bh;
  const ws = getLbmWorkspace(nCells);
  const {
    m0, mBlur, mTemp, dSpineSq, uField, vField, qField, surfInk, rho, pf, px,
    pfNext, rhoStart, uxField, uyField,
    f0, f1, f2, f3, f4, f5, f6, f7, f8,
    fn1, fn2, fn3, fn4, fn5, fn6, fn7, fn8
  } = ws;

  // Read live physical rendering parameters from SLENDER_PHYSICS
  const phys = SLENDER_PHYSICS || DEFAULT_SLENDER_PHYSICS;
  const grainInt = phys.paperGrainIntensity ?? 1.35;
  const ringInt = phys.coffeeRingIntensity ?? 1.45;
  const nijimiInt = phys.nijimiIntensity ?? 1.40;
  const bristleInt = phys.bristleStriationIntensity ?? 1.35;
  const dwellInt = phys.dwellPoolingIntensity ?? 1.40;
  const kmContrast = phys.kmTransmittanceContrast ?? 1.35;
  const glueWarmth = phys.glueChromaticWarmth ?? 1.25;
  const coreMantleInt = phys.coreMantleContrast ?? 1.35;
  const cefengInt = phys.cefengObliqueIntensity ?? 1.30;
  const plasticityInt = phys.tuftPlasticityElasticity ?? 1.25;
  const squeezeInt = phys.reservoirCompressionSqueeze ?? 1.35;

  // Pre-step 48x48 Virtual Chinese Brush Bristle Array & Capillary Meniscus Split Map
  // (Strassmann 1986 Sec. 4.1-4.4; Chu & Tai 2004 Split/Dry Map; Chen et al. 2015 WetBrush Eqs. 12-13; Xu et al. 2004 Eqs. 5, 17)
  const N_BRUSH = 48;
  const uCefengLut = new Float32Array(N_BRUSH);
  const uWetnessLut = new Float32Array(N_BRUSH);
  const uSqueezeLut = new Float32Array(N_BRUSH);
  const uStressLut = new Float32Array(N_BRUSH);
  const uCoreFracLut = new Float32Array(N_BRUSH);
  const uPlasticLut = new Float32Array(N_BRUSH);
  const bristleLut = new Float32Array(N_BRUSH * N_BRUSH);

  // LUT rows are indexed by the stroke's *global* u in [0, 1] (the same coordinate the per-pixel pass samples),
  // so partial (animated) renders at limitIdx < pts.length - 1 match the final full render for u <= u(limitIdx).
  const fullPtIdx = Math.max(1, pts.length - 1);
  const maxPtIdx = Math.max(1, Math.min(limitIdx, fullPtIdx));
  for (let k = 0; k < N_BRUSH; k++) {
    const fPt = Math.min(maxPtIdx, (k / (N_BRUSH - 1)) * fullPtIdx);
    const idxA = Math.min(maxPtIdx, Math.floor(fPt));
    const idxB = Math.min(maxPtIdx, idxA + 1);
    const fr = fPt - idxA;
    const ptA = pts[idxA];
    const ptB = pts[idxB];
    uCefengLut[k] = (ptA.cefengBias ?? 0.0) + fr * ((ptB.cefengBias ?? 0.0) - (ptA.cefengBias ?? 0.0));
    uWetnessLut[k] = (ptA.tuftWetness ?? 0.88) + fr * ((ptB.tuftWetness ?? 0.88) - (ptA.tuftWetness ?? 0.88));
    uSqueezeLut[k] = (ptA.compressionSqueeze ?? 0.32) + fr * ((ptB.compressionSqueeze ?? 0.32) - (ptA.compressionSqueeze ?? 0.32));
    uStressLut[k] = (ptA.tuftStress ?? 0.65) + fr * ((ptB.tuftStress ?? 0.65) - (ptA.tuftStress ?? 0.65));
    uCoreFracLut[k] = (ptA.coreMantleRadiusFrac ?? 0.45) + fr * ((ptB.coreMantleRadiusFrac ?? 0.45) - (ptA.coreMantleRadiusFrac ?? 0.45));
    uPlasticLut[k] = Math.abs(ptA.plasticLag ?? 0.0) + fr * (Math.abs(ptB.plasticLag ?? 0.0) - Math.abs(ptA.plasticLag ?? 0.0));
  }

  // Evolve 1D cellular bristle reservoirs across u in [0, 1] with arcsin(|v|) contact thresholds & meniscus diffusion
  const bState = new Float32Array(N_BRUSH);
  const bNext = new Float32Array(N_BRUSH);
  const strokeSeed = Math.abs(Math.sin(pts[0].x * 12.9898 + pts[0].y * 78.233 + pts[fullPtIdx].x * 37.719) * 43758.5453);
  for (let m = 0; m < N_BRUSH; m++) {
    const vNorm = -1.0 + (2.0 * m) / (N_BRUSH - 1);
    const absV = Math.abs(vNorm);
    const clusterWave = 0.55 * Math.sin(6.5 * Math.PI * vNorm + (strokeSeed % 6.28)) + 0.45 * Math.cos(11.0 * Math.PI * vNorm - (strokeSeed % 3.14));
    const inCore = absV <= uCoreFracLut[0];
    // Initial per-bristle ink reservoirs (Strassmann 1986 Sec. 4.1: each bristle holds a finite quantity): core bristles start fuller than the outer goat-hair mantle (model choice)
    bState[m] = inCore ? (0.90 + 0.08 * clusterWave) : (0.74 + 0.18 * clusterWave);
  }

  for (let k = 0; k < N_BRUSH; k++) {
    const wCur = uWetnessLut[k];
    const biasCur = uCefengLut[k];
    const sqCur = uSqueezeLut[k];
    const strCur = uStressLut[k];
    const coreR = uCoreFracLut[k];
    // Capillary meniscus bridge diffusivity D_cap increases when brush is soaked (dilating tracks) and weakens as tuft dries
    const dCap = Math.min(0.32, 0.22 * wCur * wCur);
    let meanRow = 0.0;
    for (let m = 0; m < N_BRUSH; m++) {
      const vNorm = -1.0 + (2.0 * m) / (N_BRUSH - 1);
      const absV = Math.abs(vNorm);
      // Strassmann (1986) Sec. 4.4 round-tuft contact threshold: P_thresh(v) = (2/pi)*arcsin(|v|)
      const pThresh = (2.0 / Math.PI) * Math.asin(Math.min(1.0, absV));
      const leftQ = bState[Math.max(0, m - 1)];
      const rightQ = bState[Math.min(N_BRUSH - 1, m + 1)];
      let qVal = (1.0 - dCap) * bState[m] + 0.5 * dCap * (leftQ + rightQ);
      // Strassmann Sec. 4.3 "ink stealing" from wet adjacent bristle clusters
      if (qVal < 0.45 && (leftQ > 0.68 || rightQ > 0.68)) {
        qVal += 0.06 * (Math.max(leftQ, rightQ) - qVal);
      }
      // Depletion higher on outer mantle and on dragged Cefeng belly side (vNorm * biasCur < 0)
      const depRate = 0.012 * strCur * (0.85 + 0.45 * pThresh - 0.25 * biasCur * vNorm);
      const sqRecharge = 0.010 * sqCur * (absV <= coreR ? 1.15 : 0.70);
      bNext[m] = Math.max(0.20, Math.min(1.10, qVal - depRate + sqRecharge));
      meanRow += bNext[m];
    }
    meanRow /= N_BRUSH;
    const rowOff = k * N_BRUSH;
    for (let m = 0; m < N_BRUSH; m++) {
      bState[m] = bNext[m];
      bristleLut[rowOff + m] = bNext[m] - meanRow;
    }
  }

  const imgData = ctx.getImageData(x0, y0, bw, bh);
  const data = imgData.data;

  // 2. Initialize footprint mask M0(x) and clear local fields (including boundary LBM streaming buffers)
  const INF_DIST = 1e9;
  for (let i = 0; i < nCells; i++) {
    const a = data[i * 4 + 3] / 255.0;
    m0[i] = a;
    mBlur[i] = a;
    mTemp[i] = a;
    dSpineSq[i] = INF_DIST;
    rhoStart[i] = 0.0;
    uField[i] = 0.5;
    vField[i] = 0.0;
    qField[i] = 0.0;
    fn1[i] = 0.0; fn2[i] = 0.0; fn3[i] = 0.0; fn4[i] = 0.0;
    fn5[i] = 0.0; fn6[i] = 0.0; fn7[i] = 0.0; fn8[i] = 0.0;
  }

  // 3. Splat exact Euclidean distance to stroke spine segments [p_i, p_{i+1}], skeletal lateral coordinate v,
  //    and calligraphic tuft load (Hsu & Lee 1994 Skeletal Strokes; Strassmann 1986 Hairy Brushes)
  const corners = compiled.cornerFeatures || [];
  const hf = compiled.hookFeature;
  const isRightNa = !!(compiled.behavior && compiled.behavior.isRightNa);
  const isSweepTail = !!(
    compiled.behavior &&
    compiled.behavior.isSweepEnd &&
    !compiled.behavior.isZiHengPie &&
    !compiled.behavior.isRoofHook &&
    !compiled.behavior.isRisingTi &&
    !compiled.behavior.isVerticalTi &&
    !isRightNa &&
    !hf
  );

  for (let i = 0; i < limitIdx; i++) {
    const pA = pts[i];
    const pB = pts[i + 1];
    const ax = pA.x - x0;
    const ay = pA.y - y0;
    const bx = pB.x - x0;
    const by = pB.y - y0;
    const dx = bx - ax;
    const dy = by - ay;
    const lenSq = dx * dx + dy * dy;
    const invLenSq = lenSq > 1e-6 ? 1.0 / lenSq : 0.0;
    const segLen = Math.sqrt(lenSq);
    const nx = segLen > 1e-4 ? -dy / segLen : (pA.nx || 0.0);
    const ny = segLen > 1e-4 ? dx / segLen : (pA.ny || 1.0);

    const wA = Math.max(1.5, 0.5 * Math.hypot(pA.rx - pA.lx, pA.ry - pA.ly));
    const wB = Math.max(1.5, 0.5 * Math.hypot(pB.rx - pB.lx, pB.ry - pB.ly));
    const reach = Math.ceil(Math.max(wA, wB, baseR) + 6.0);

    const sMinX = Math.max(0, Math.floor(Math.min(ax, bx) - reach));
    const sMaxX = Math.min(bw - 1, Math.ceil(Math.max(ax, bx) + reach));
    const sMinY = Math.max(0, Math.floor(Math.min(ay, by) - reach));
    const sMaxY = Math.min(bh - 1, Math.ceil(Math.max(ay, by) + reach));

    // Calligraphic pause moisture/pigment enrichment (entry ton press, osae corners, hook heel, na foot)
    const uMid = 0.5 * ((pA.u ?? (i / limitIdx)) + (pB.u ?? ((i + 1) / limitIdx)));
    let qSeg = 0.22 * Math.exp(-((uMid - 0.045) * (uMid - 0.045)) / 0.0055);
    for (let c = 0; c < corners.length; c++) {
      if (limitIdx >= corners[c].index) {
        const di = i - corners[c].index;
        qSeg += 0.25 * Math.exp(-(di * di) / 36.0);
      }
    }
    if (hf && limitIdx >= hf.index) {
      const di = i - hf.index;
      qSeg += 0.28 * Math.exp(-(di * di) / 42.0);
    }
    if (isRightNa) {
      const du = uMid - 0.68;
      qSeg += 0.24 * Math.exp(-(du * du) / 0.014);
    }
    // WetBrush inter-hair compression squeeze-out & Elastica fold plasticity enrichment
    // (Chen et al. 2015 Sec. 5.1, Eqs. 12-13; Chu & Tai 2004 p. 79; Xu et al. 2004 Eq. 14)
    const segSqueeze = 0.5 * ((pA.compressionSqueeze ?? 0.30) + (pB.compressionSqueeze ?? 0.30));
    const segPlastic = 0.5 * (Math.abs(pA.plasticLag ?? 0.0) + Math.abs(pB.plasticLag ?? 0.0));
    qSeg += 0.09 * Math.max(0.0, segSqueeze - 0.26) * (0.55 + 0.45 * squeezeInt) + 0.07 * segPlastic * plasticityInt;

    const uA = pA.u ?? (i / Math.max(1, pts.length - 1));
    const uB = pB.u ?? ((i + 1) / Math.max(1, pts.length - 1));
    const biasSeg = 0.5 * ((pA.cefengBias ?? 0.0) + (pB.cefengBias ?? 0.0));

    for (let ly = sMinY; ly <= sMaxY; ly++) {
      const rowOff = ly * bw;
      const py = ly - ay;
      for (let lx = sMinX; lx <= sMaxX; lx++) {
        const pxRel = lx - ax;
        let t = (pxRel * dx + py * dy) * invLenSq;
        if (t < 0.0) t = 0.0;
        else if (t > 1.0) t = 1.0;
        const projX = pxRel - t * dx;
        const projY = py - t * dy;
        const d2 = projX * projX + projY * projY;
        const idx = rowOff + lx;
        if (d2 < dSpineSq[idx]) {
          dSpineSq[idx] = d2;
          uField[idx] = uA + t * (uB - uA);
          const wLoc = wA + t * (wB - wA);
          const signedLat = (projX * nx + projY * ny) / wLoc;
          // Hsu & Lee (1994) oblique tuft cross-section skew in Cefeng posture
          const skewedLat = signedLat + 0.06 * biasSeg * (1.0 - Math.min(1.0, signedLat * signedLat));
          vField[idx] = Math.max(-1.2, Math.min(1.2, skewedLat));
          qField[idx] = qSeg;
        }
      }
    }
  }

  // 4. Compute 3-pass Binomial-smoothed wet mask mBlur for multi-pixel contact-line coffee-ring rim & sub-rim depletion trough
  for (let pass = 0; pass < 3; pass++) {
    const src = (pass % 2 === 0) ? mBlur : mTemp;
    const dst = (pass % 2 === 0) ? mTemp : mBlur;
    for (let ly = 1; ly < bh - 1; ly++) {
      const rowOff = ly * bw;
      for (let lx = 1; lx < bw - 1; lx++) {
        const idx = rowOff + lx;
        dst[idx] =
          0.25 * src[idx] +
          0.125 * (src[idx - 1] + src[idx + 1] + src[idx - bw] + src[idx + bw]) +
          0.0625 * (src[idx - bw - 1] + src[idx - bw + 1] + src[idx + bw - 1] + src[idx + bw + 1]);
      }
    }
  }
  // After 3 passes (odd), result is in mTemp; copy to mBlur
  for (let i = 0; i < nCells; i++) {
    mBlur[i] = mTemp[i];
  }

  // 5. Initialize D2Q9 LBM fluid density rho, surface ink reservoir surfInk, and pigment layers pf, px
  // D2Q9 lattice weights (Chu & Tai 2005 Sec. 4): w0 = 4/9, w1..4 = 1/9 (axis), w5..8 = 1/36 (diag)
  const W0 = 4.0 / 9.0;
  const WA = 1.0 / 9.0;
  const WD = 1.0 / 36.0;
  const seepScale = Math.min(1.8, 0.35 + 0.35 * nijimiInt);

  for (let i = 0; i < nCells; i++) {
    const mask = m0[i];
    const q = qField[i] * dwellInt;
    const initRho = mask * (0.62 + 0.24 * q);
    surfInk[i] = mask * (0.24 + 0.20 * q) * Math.min(1.6, 0.5 + 0.5 * nijimiInt);
    rho[i] = initRho;
    pf[i] = mask * (0.46 + 0.22 * q);
    px[i] = mask * (0.28 + 0.14 * q);

    f0[i] = W0 * initRho;
    f1[i] = WA * initRho;
    f2[i] = WA * initRho;
    f3[i] = WA * initRho;
    f4[i] = WA * initRho;
    f5[i] = WD * initRho;
    f6[i] = WD * initRho;
    f7[i] = WD * initRho;
    f8[i] = WD * initRho;
  }

  // 6. Execute D2Q9 Lattice Boltzmann Percolation & Wet-Dry Boundary Pinning (Chu & Tai 2005 Eqs. 1-9)
  const omega = 0.54;
  const oneMinusOmega = 1.0 - omega;
  const alphaSat = 0.34;
  const SQRT2 = 1.41421356;
  const lbmSteps = nijimiInt <= 0.05 ? 1 : (nijimiInt >= 1.65 ? 5 : 4);

  for (let step = 0; step < lbmSteps; step++) {
    // 6a. Seepage from surface reservoir + BGK collision toward He-Luo low-saturation equilibrium
    for (let ly = 1; ly < bh - 1; ly++) {
      const rowOff = ly * bw;
      const gRowOff = (y0 + ly) * W + x0;
      for (let lx = 1; lx < bw - 1; lx++) {
        const idx = rowOff + lx;
        const gIdx = gRowOff + lx;

        // Surface-to-flow seepage phi = clamp(s, 0, seepScale*(c - rho))
        let r = rho[idx];
        const s = surfInk[idx];
        if (s > 1e-5) {
          const capRem = Math.max(0.0, paper.capacity[gIdx] - r);
          const phi = Math.min(s, seepScale * capRem);
          surfInk[idx] = s - phi;
          r += phi;
          rho[idx] = r;
          f0[idx] += W0 * phi;
          f1[idx] += WA * phi;
          f2[idx] += WA * phi;
          f3[idx] += WA * phi;
          f4[idx] += WA * phi;
          f5[idx] += WD * phi;
          f6[idx] += WD * phi;
          f7[idx] += WD * phi;
          f8[idx] += WD * phi;
        }

        rhoStart[idx] = r;
        if (r < 1e-4) {
          fn1[idx] = 0; fn2[idx] = 0; fn3[idx] = 0; fn4[idx] = 0;
          fn5[idx] = 0; fn6[idx] = 0; fn7[idx] = 0; fn8[idx] = 0;
          uxField[idx] = 0.0; uyField[idx] = 0.0;
          continue;
        }

        // Mean-field velocity from the density gradient (stand-in for MoXi Eq. 4, u = sum e_i f_i / rho_0) plus a small paper-slope
        // drift (cf. Curtis et al. 1997 Eqs. 1-2, where velocity responds to pressure and the height-field gradient)
        const dRhoX = rho[idx + 1] - rho[idx - 1];
        const dRhoY = rho[idx + bw] - rho[idx - bw];
        const dHX = paper.height[gIdx + 1] - paper.height[gIdx - 1];
        const dHY = paper.height[gIdx + W] - paper.height[gIdx - W];
        const ux = Math.max(-0.24, Math.min(0.24, -0.17 * dRhoX - 0.08 * dHX));
        const uy = Math.max(-0.24, Math.min(0.24, -0.17 * dRhoY - 0.08 * dHY));
        uxField[idx] = ux;
        uyField[idx] = uy;

        // Low-saturation advection weight psi(rho) = smoothstep(0, alphaSat, rho) (Chu & Tai Eq. 8)
        const tSat = Math.min(1.0, r / alphaSat);
        const psi = tSat * tSat * (3.0 - 2.0 * tSat);
        const uu = 1.5 * (ux * ux + uy * uy);

        f0[idx] = oneMinusOmega * f0[idx] + omega * W0 * (r - psi * uu);

        // Axis links: 1:(+1,0), 2:(-1,0), 3:(0,+1), 4:(0,-1)
        const eu1 = 3.0 * ux;
        fn1[idx] = oneMinusOmega * f1[idx] + omega * WA * (r + psi * (eu1 + 0.5 * eu1 * eu1 - uu));
        const eu2 = -3.0 * ux;
        fn2[idx] = oneMinusOmega * f2[idx] + omega * WA * (r + psi * (eu2 + 0.5 * eu2 * eu2 - uu));
        const eu3 = 3.0 * uy;
        fn3[idx] = oneMinusOmega * f3[idx] + omega * WA * (r + psi * (eu3 + 0.5 * eu3 * eu3 - uu));
        const eu4 = -3.0 * uy;
        fn4[idx] = oneMinusOmega * f4[idx] + omega * WA * (r + psi * (eu4 + 0.5 * eu4 * eu4 - uu));

        // Diagonal links: 5:(+1,+1), 6:(-1,+1), 7:(-1,-1), 8:(+1,-1)
        const eu5 = 3.0 * (ux + uy);
        fn5[idx] = oneMinusOmega * f5[idx] + omega * WD * (r + psi * (eu5 + 0.5 * eu5 * eu5 - uu));
        const eu6 = 3.0 * (-ux + uy);
        fn6[idx] = oneMinusOmega * f6[idx] + omega * WD * (r + psi * (eu6 + 0.5 * eu6 * eu6 - uu));
        const eu7 = 3.0 * (-ux - uy);
        fn7[idx] = oneMinusOmega * f7[idx] + omega * WD * (r + psi * (eu7 + 0.5 * eu7 * eu7 - uu));
        const eu8 = 3.0 * (ux - uy);
        fn8[idx] = oneMinusOmega * f8[idx] + omega * WD * (r + psi * (eu8 + 0.5 * eu8 * eu8 - uu));
      }
    }

    // 6b. Fiber-regulated streaming with symmetric link blocking kappa_i & disorder pinning sigma (Chu & Tai 2005 Eqs. 5, 6, 9)
    const pinScale = Math.max(0.45, 1.15 - 0.25 * nijimiInt);
    // Link tables: d = 0..7 <-> populations f1..f8, opposite link, upstream cell offsets (local grid and global paper grid)
    const FA = [f1, f2, f3, f4, f5, f6, f7, f8];
    const FN = [fn1, fn2, fn3, fn4, fn5, fn6, fn7, fn8];
    const opp = [1, 0, 3, 2, 6, 7, 4, 5];
    const srcOff = [-1, 1, -bw, bw, -bw - 1, -bw + 1, bw + 1, bw - 1];
    const gSrcOff = [-1, 1, -W, W, -W - 1, -W + 1, W + 1, W - 1];
    const kMaxLink = [0.88, 0.88, 0.88, 0.88, 0.90, 0.90, 0.90, 0.90];
    const pinThr = [WA, WA, WA, WA, SQRT2 * WD, SQRT2 * WD, SQRT2 * WD, SQRT2 * WD];
    for (let ly = 1; ly < bh - 1; ly++) {
      const rowOff = ly * bw;
      const gRowOff = (y0 + ly) * W + x0;
      for (let lx = 1; lx < bw - 1; lx++) {
        const idx = rowOff + lx;
        const gIdx = gRowOff + lx;
        const kSelf = paper.blocking[gIdx] + 0.14 * px[idx];
        const pinSelf = (paper.pinning[gIdx] + 0.08 * px[idx]) * pinScale;
        const dryHere = rhoStart[idx] < 0.015;

        for (let d = 0; d < 8; d++) {
          const s = idx + srcOff[d];
          const gs = gIdx + gSrcOff[d];
          const fnSrc = FN[d][s];
          const fnOwn = FN[opp[d]][idx];
          // Symmetric link blocking kappa_i: average of both linked sites (Eq. 5), identical from either end of the link
          let k = Math.min(kMaxLink[d], 0.5 * (kSelf + paper.blocking[gs] + 0.14 * px[s]));
          // Full bounce-back at pinned fronts (Sec. 5.3.3; diagonal thresholds scaled by sqrt(2)): a dry site stays pinned
          // while the packet aimed at it is too weak to depin it. Both ends of the link evaluate the same condition so no
          // mass is created or destroyed (the old code dropped the packet).
          if (dryHere) {
            if (fnSrc < pinThr[d] * pinSelf) k = 1.0;
          } else if (rhoStart[s] < 0.015 && fnOwn < pinThr[d] * (paper.pinning[gs] + 0.08 * px[s]) * pinScale) {
            k = 1.0;
          }
          FA[d][idx] = (1.0 - k) * fnSrc + k * fnOwn;
        }

        const newRho = f0[idx] + f1[idx] + f2[idx] + f3[idx] + f4[idx] + f5[idx] + f6[idx] + f7[idx] + f8[idx];
        const prevRho = rho[idx];
        rho[idx] = newRho;

        // Suspended pigment advection (Chu & Tai 2005 Sec. 5.4.2): flux-weighted inflow (Eq. 10) for sites that are
        // becoming wet, method-of-characteristics back-tracing for already wet sites, then paper hindrance
        pfNext[idx] = pf[idx];
        if (newRho > 1e-4) {
          let pStar = pf[idx];
          if (prevRho <= 1e-4) {
            const fSum = f1[idx] + f2[idx] + f3[idx] + f4[idx] + f5[idx] + f6[idx] + f7[idx] + f8[idx];
            if (fSum > 1e-6) {
              pStar = (
                f1[idx] * pf[idx - 1] + f2[idx] * pf[idx + 1] + f3[idx] * pf[idx - bw] + f4[idx] * pf[idx + bw] +
                f5[idx] * pf[idx - bw - 1] + f6[idx] * pf[idx - bw + 1] + f7[idx] * pf[idx + bw + 1] + f8[idx] * pf[idx + bw - 1]
              ) / fSum;
            }
          } else {
            const ux = uxField[idx];
            const uy = uyField[idx];
            const sx = ux >= 0.0 ? -1 : 1;
            const sy = uy >= 0.0 ? -1 : 1;
            const ax = Math.abs(ux);
            const ay = Math.abs(uy);
            const iX = idx + sx;
            const iY = idx + sy * bw;
            const iXY = idx + sx + sy * bw;
            // Never sample across the wet/dry boundary (any pf outside the boundary must not contribute)
            if (rho[iX] > 1e-4 && rho[iY] > 1e-4 && rho[iXY] > 1e-4) {
              pStar =
                (1.0 - ax) * (1.0 - ay) * pf[idx] + ax * (1.0 - ay) * pf[iX] +
                (1.0 - ax) * ay * pf[iY] + ax * ay * pf[iXY];
            }
          }
          // SimulateHindrance: gamma* = lerp(1, gamma, smoothstep(0, varsigma, |u|)); pf = lerp(pf*, pf, gamma*)
          const spd = Math.hypot(uxField[idx], uyField[idx]);
          const tHind = Math.min(1.0, spd / 0.12);
          const gammaStar = 1.0 + (0.35 - 1.0) * (tHind * tHind * (3.0 - 2.0 * tHind));
          pfNext[idx] = pStar + (pf[idx] - pStar) * gammaStar;
        }
      }
    }

    // 6c. Boundary evaporation of pinned wet-front sites (Chu & Tai 2005 Sec. 5.3.4; Curtis et al. 1997 edge darkening)
    // followed by MoXi pigment fixture (Sec. 5.4.3): water loss concentrates and settles pigment at the rim.
    // epsS is scaled up from the paper's 0 <= eps_s <= 0.005 because only a few relaxation steps are executed here.
    const epsS = LBM_TUNING.boundaryEvaporation * ringInt;
    const muFix = Math.max(0.0, Math.min(1.0, 0.30 + 0.10 * glueWarmth));
    // Phase A: decide every evaporation amount from the un-modified density field (raster-order independent).
    // mTemp is free here: it only served as the blur ping-pong buffer before the mask was copied into mBlur.
    const evapAmt = mTemp;
    for (let ly = 1; ly < bh - 1; ly++) {
      const rowOff = ly * bw;
      for (let lx = 1; lx < bw - 1; lx++) {
        const idx = rowOff + lx;
        const r0 = rho[idx];
        const onFront = r0 > 1e-4 && (rho[idx - 1] < 0.015 || rho[idx + 1] < 0.015 || rho[idx - bw] < 0.015 || rho[idx + bw] < 0.015);
        evapAmt[idx] = onFront ? Math.min(0.45 * r0, epsS) : 0.0;
      }
    }
    // Phase B: apply evaporation, concentrate pigment, and run the pigment fixture.
    for (let ly = 1; ly < bh - 1; ly++) {
      const rowOff = ly * bw;
      const gRowOff = (y0 + ly) * W + x0;
      for (let lx = 1; lx < bw - 1; lx++) {
        const idx = rowOff + lx;
        const r0 = rho[idx];
        let pfHere = pfNext[idx];
        if (r0 > 1e-4) {
          let rNow = r0;
          const evap = evapAmt[idx];
          if (evap > 0.0) {
            rNow = r0 - evap;
            const keep = rNow / r0;
            f0[idx] *= keep; f1[idx] *= keep; f2[idx] *= keep; f3[idx] *= keep; f4[idx] *= keep;
            f5[idx] *= keep; f6[idx] *= keep; f7[idx] *= keep; f8[idx] *= keep;
            rho[idx] = rNow;
            // Pigment mass is conserved while water leaves, so its concentration rises
            pfHere = Math.min(2.0, pfHere / keep);
          }
          const gIdx = gRowOff + lx;
          const startRho = rhoStart[idx];
          const wLoss = Math.max(startRho - rNow, 0.0);
          const lossFactor = startRho > 1e-4 ? Math.min(1.0, wLoss / startRho) : 0.0;
          const t = Math.min(1.0, rNow / Math.max(1e-4, muFix));
          const fixFactor = Math.max(lossFactor * (1.0 - t * t * (3.0 - 2.0 * t)), 0.16 * (1.24 - 0.48 * paper.height[gIdx]));
          px[idx] += fixFactor * pfHere;
          pfHere -= fixFactor * pfHere;
        }
        pf[idx] = pfHere;
      }
    }
  }

  // 7. Optical Pigment Thickness Synthesis & Two-Flux Kubelka-Munk Layer Evaluation
  // Calibrate baseline thickness into the active KM translucent glaze slope so valleys, filaments, and rims pop visually
  const rawBase = toneMode === "vermilion" ? 0.64 : (toneMode === "dark-sumi" ? 0.62 : 0.54);
  const coreSpineBoost = 0.056 * coreMantleInt;
  const baseThick = Math.max(0.32, Math.min(0.85, rawBase - 0.09 * (kmContrast - 1.0)));
  const spineRefThick = Math.min(0.88, baseThick + coreSpineBoost);
  const grainAmp = (toneMode === "dark-sumi" ? 0.085 : 0.108) * grainInt * (0.75 + 0.25 * kmContrast);
  const lutScale = (km.N - 1) / km.maxX;
  const R2BaseR = km.R2[0], R2BaseG = km.R2[1], R2BaseB = km.R2[2];

  // Exact numerical 2nd-order KM curvature compensation kappa2(spineRefThick) = -0.5 * D''(x0) / D'(x0)
  // Guarantees zero 2nd-order Jensen shift in 5x5 spine windows (M6) for any slider configuration
  function evalKmDarknessAt(xVal) {
    const fl = Math.min(km.N - 1.0001, Math.max(0.0, xVal * lutScale));
    const idx0 = fl | 0;
    const fr = fl - idx0;
    const r1g = km.R1G[idx0] + fr * (km.R1G[idx0 + 1] - km.R1G[idx0]);
    const t1g = km.T1G[idx0] + fr * (km.T1G[idx0 + 1] - km.T1G[idx0]);
    const aL = Math.max(0.14, Math.min(0.97, 1.0 - t1g / Math.max(1e-4, 1.0 - r1g * R2BaseG)));
    const rawG = toneMode === "vermilion"
      ? (r1g + (t1g * t1g * R2BaseG) / Math.max(1e-4, 1.0 - r1g * R2BaseG) - (1.0 - aL) * R2BaseG) / aL
      : Math.max(0.04, r1g / aL + 0.12 * t1g);
    return aL * (1.0 - rawG);
  }
  const hStep = 0.10;
  const d0 = evalKmDarknessAt(spineRefThick);
  const dPlus = evalKmDarknessAt(spineRefThick + hStep);
  const dMinus = evalKmDarknessAt(Math.max(0.05, spineRefThick - hStep));
  const dPrime = (dPlus - dMinus) / (2.0 * hStep);
  const dSecond = (dPlus - 2.0 * d0 + dMinus) / (hStep * hStep);
  const kappa2 = Math.abs(dPrime) > 1e-4 ? Math.max(0.0, Math.min(2.4, -0.5 * dSecond / dPrime)) : 1.15;

  for (let ly = 0; ly < bh; ly++) {
    const rowOff = ly * bw;
    const gRowOff = (y0 + ly) * W + x0;
    const isBorderY = (ly <= 1 || ly >= bh - 2);
    for (let lx = 0; lx < bw; lx++) {
      const idx = rowOff + lx;
      const mask = m0[idx];
      const isBorder = isBorderY || lx <= 1 || lx >= bw - 2;
      const lbmRho = isBorder ? 0.0 : rho[idx];
      if (mask < 1e-3 && lbmRho < 0.006) {
        data[idx * 4 + 3] = 0;
        continue;
      }

      const gIdx = gRowOff + lx;
      const gZero = paper.zeroB5Grain[gIdx];
      const fil = paper.filamentMap[gIdx];
      const mFib = paper.macroFiber[gIdx];
      const hVal = paper.height[gIdx];
      const u = uField[idx];
      const v = vField[idx];
      const dSpine = Math.sqrt(dSpineSq[idx]);

      // Core spine protector W_core(x) = smoothstep(2.85, 4.05, dSpine) (also active at entry/exit caps)
      let wCore = 0.0;
      if (dSpine > 2.85) {
        const tc = Math.min(1.0, (dSpine - 2.85) / 1.20);
        wCore = tc * tc * (3.0 - 2.0 * tc);
      }
      if (u < 0.08) {
        const te = Math.min(1.0, (0.08 - u) / 0.06);
        wCore = Math.max(wCore, te * te * (3.0 - 2.0 * te));
      } else if (u > 0.86) {
        const tx = Math.min(1.0, (u - 0.86) / 0.08);
        wCore = Math.max(wCore, tx * tx * (3.0 - 2.0 * tx));
      }

      // Dry-brush sweep tail transition: wet valley pooling (-gZero) -> dry bristle ridge catching (+gZero) (Chu & Tai 2004 p. 81)
      let valleySign = -1.0;
      let dryFactor = 0.0;
      if (isSweepTail && u > 0.68) {
        const td = Math.min(1.0, (u - 0.68) / 0.24);
        dryFactor = td * td * (3.0 - 2.0 * td);
        valleySign = -1.0 + 1.85 * dryFactor;
      }

      // Sample Virtual Chinese Brush longitudinal state at u (Chu & Tai 2002/2004; WetBrush 2015)
      const uLutF = Math.max(0.0, Math.min(N_BRUSH - 1.001, u * (N_BRUSH - 1)));
      const uIdx0 = uLutF | 0;
      const uFrac = uLutF - uIdx0;
      const cefengBiasHere = uCefengLut[uIdx0] + uFrac * (uCefengLut[uIdx0 + 1] - uCefengLut[uIdx0]);
      const coreRadiusHere = uCoreFracLut[uIdx0] + uFrac * (uCoreFracLut[uIdx0 + 1] - uCoreFracLut[uIdx0]);
      const squeezeHere = uSqueezeLut[uIdx0] + uFrac * (uSqueezeLut[uIdx0 + 1] - uSqueezeLut[uIdx0]);
      const plasticHere = uPlasticLut[uIdx0] + uFrac * (uPlasticLut[uIdx0 + 1] - uPlasticLut[uIdx0]);
      const wetnessHere = uWetnessLut[uIdx0] + uFrac * (uWetnessLut[uIdx0 + 1] - uWetnessLut[uIdx0]);

      // Sample evolved 48x48 Strassmann / Chu-Tai cellular bristle array at (u, v)
      const vClamped = Math.max(-1.0, Math.min(1.0, v));
      const vLutF = Math.max(0.0, Math.min(N_BRUSH - 1.001, (vClamped + 1.0) * 0.5 * (N_BRUSH - 1)));
      const vIdx0 = vLutF | 0;
      const vFrac = vLutF - vIdx0;
      const b00 = bristleLut[uIdx0 * N_BRUSH + vIdx0];
      const b01 = bristleLut[uIdx0 * N_BRUSH + vIdx0 + 1];
      const b10 = bristleLut[(uIdx0 + 1) * N_BRUSH + vIdx0];
      const b11 = bristleLut[(uIdx0 + 1) * N_BRUSH + vIdx0 + 1];
      const bCell = (b00 + vFrac * (b01 - b00)) + uFrac * ((b10 + vFrac * (b11 - b10)) - (b00 + vFrac * (b01 - b00)));

      // Coherent multi-scale bristle-cluster striations along skeletal (u, v) frame
      // (Strassmann 1986 Hairy Brushes; Hsu & Lee 1994 Skeletal Strokes; Chen et al. 2015 WetBrush)
      const bMicro =
        0.46 * Math.sin(18.0 * v + 1.3 * u) +
        0.34 * Math.cos(31.0 * v - 1.9 * u + 0.7) +
        0.20 * Math.sin(47.0 * v + 2.4 * u - 1.1);
      const absV = Math.abs(v);
      // Outer goat-hair mantle (|v| > coreRadiusHere) & dragged Cefeng belly side exhibit stronger capillary bristle splitting
      const mantleSplitBoost = absV > coreRadiusHere ? (1.0 + 0.38 * Math.min(1.0, (absV - coreRadiusHere) / 0.45)) : 0.86;
      const bCombined = (0.72 * bMicro + 1.35 * bCell) * mantleSplitBoost * (1.08 - 0.16 * wetnessHere);
      // Couple bristle striations with Xuan paper micro-topography (wet valleys vs. dry pore-resistance peaks)
      const bristlePaperCoupling =
        0.072 * bristleInt * bCombined * (0.55 + 0.75 * dryFactor + 0.40 * absV) * (1.0 + 0.70 * valleySign * (hVal - 0.5)) * wCore;

      // Jianhao (兼毫) Core-to-Mantle Radial Profile (Chu & Tai 2002 Sec. 3 on hard/soft/combination brushes; Chu & Tai 2004 "Chinese Brushes" sidebar)
      // Stiff rabbit/weasel inner core (|v| <= coreRadiusHere) delivers denser central ink than the compliant goat-hair mid-mantle
      let jianhaoProfile = 0.0;
      if (absV <= coreRadiusHere) {
        const radialCoreShape = Math.cos((absV / Math.max(0.2, coreRadiusHere)) * (Math.PI * 0.5));
        jianhaoProfile = (1.0 - wCore) * coreSpineBoost + wCore * coreSpineBoost * (0.35 + 0.65 * radialCoreShape);
      } else if (absV < 0.88) {
        const tMantle = (absV - coreRadiusHere) / Math.max(0.15, 0.88 - coreRadiusHere);
        jianhaoProfile = -0.064 * coreMantleInt * Math.sin(tMantle * Math.PI) * wCore;
      }

      // Zhongfeng (中鋒) vs. Cefeng (側鋒) Tip-Edge vs. Belly-Edge Tonal & Meniscus Asymmetry
      // (Xie et al. 2013 Sec. 4.1 upright vs. oblique style; Chu & Tai 2002 Sec. 2; Xu et al. 2004 Eq. 5)
      const cefengModulation = 0.052 * cefengInt * cefengBiasHere * Math.sin(vClamped * (Math.PI * 0.5)) * wCore;

      // Zero-B5 cellulose fiber granulation (active everywhere, including spine core)
      const gLin = valleySign * grainAmp * gZero;
      const deltaGrainCore = gLin + kappa2 * gLin * gLin;

      // Tangled mulberry/wingceltis bark filaments & laid screen valley granulation (active outside 2.85px spine core)
      const filamentRelief = valleySign * 0.095 * grainInt * (0.65 * fil + 0.35 * mFib) * wCore;

      // Multi-pixel contact-line coffee-ring rim & sub-rim capillary replenishment trough (Curtis et al. Sec. 4.3.3; Chu & Tai Sec. 5.3.4)
      const mb = mBlur[idx];
      // Rim peaks where 3-pass smoothed mask mb is in [0.22, 0.74] (the outer 1.0 - 2.6 px inside the stroke contour)
      const edgeSink = 4.0 * mb * (1.0 - mb) * mask;
      // Sub-rim capillary depletion trough where mb is in [0.74, 0.96] (2.8 - 5.5 px inside the boundary)
      const subRimDepletion = (mb > 0.73 && mb < 0.96)
        ? -0.095 * ringInt * Math.sin(((mb - 0.73) / 0.23) * Math.PI)
        : 0.0;
      const coffeeRing = (0.34 * ringInt * kmContrast * edgeSink * (0.62 + 0.76 * (1.0 - hVal)) + subRimDepletion) * wCore;

      // Calligraphic dwell pause pooling, WetBrush compression squeeze-out, & LBM fixed valley pigment accumulation
      // Concentrated in the brush belly/core (WetBrush Sec. 5; Chu & Tai 2002 Sec. 3) rather than flooding the mid-mantle
      const bellyRadialWeight = 1.18 - 0.55 * Math.min(1.0, absV);
      const squeezePool = (0.048 * squeezeInt * Math.max(0.0, squeezeHere - 0.28) + 0.036 * plasticityInt * plasticHere) * bellyRadialWeight * wCore;
      const pausePool = (0.24 * dwellInt * qField[idx] + 0.085 * dwellInt * (px[idx] - 0.28)) * bellyRadialWeight * wCore + squeezePool;

      // Total effective optical pigment thickness x_opt
      const xInterior = Math.max(
        0.04,
        Math.min(
          km.maxX,
          baseThick + deltaGrainCore + filamentRelief + bristlePaperCoupling + jianhaoProfile + cefengModulation + coffeeRing + pausePool
        )
      );

      // Outer percolated nijimi capillary fringe thickness from LBM density (Chu & Tai 2005 Sec. 5.3)
      // Pigment carried into the halo by the flow (pf + fixed px) sets how dark the fringe is: pigment-starved toes stay faint
      // (Chu & Tai 2005 Sec. 2.2 feathering; Curtis et al. 1997 Sec. 5.2, thickness from flow + deposition layers)
      const pigLoad = Math.max(0.0, Math.min(1.5, (pf[idx] + px[idx]) / 0.50));
      const pigFactor = 0.60 + 0.40 * pigLoad;
      const nijimiPotential = Math.max(
        0.0,
        lbmRho * pigFactor * (1.52 - 0.96 * hVal - 0.22 * fil) - 0.004 - 0.012 * Math.max(0.0, hVal - 0.48)
      ) * Math.min(2.2, 0.78 * nijimiInt);
      const xFringe = Math.min(0.18, 0.52 * nijimiPotential);

      const xOpt = mask > 0.01 ? (mask * xInterior + (1.0 - mask) * xFringe) : xFringe;
      if (xOpt < 1e-4) {
        data[idx * 4 + 3] = 0;
        continue;
      }

      // Exact Kubelka-Munk lookup with linear interpolation
      const fLut = Math.min(km.N - 1.0001, Math.max(0.0, xOpt * lutScale));
      const i0 = fLut | 0;
      const frac = fLut - i0;
      const i1 = i0 + 1;

      const r1R = km.R1R[i0] + frac * (km.R1R[i1] - km.R1R[i0]);
      const r1G = km.R1G[i0] + frac * (km.R1G[i1] - km.R1G[i0]);
      const r1B = km.R1B[i0] + frac * (km.R1B[i1] - km.R1B[i0]);
      const t1R = km.T1R[i0] + frac * (km.T1R[i1] - km.T1R[i0]);
      const t1G = km.T1G[i0] + frac * (km.T1G[i1] - km.T1G[i0]);
      const t1B = km.T1B[i0] + frac * (km.T1B[i1] - km.T1B[i0]);

      // Local Xuan paper reflectance modulation R2(x,y)
      const paperTint = 1.0 + 0.024 * (hVal - 0.5);
      const r2R = Math.min(0.99, R2BaseR * paperTint);
      const r2G = Math.min(0.99, R2BaseG * paperTint);
      const r2B = Math.min(0.99, R2BaseB * paperTint);

      // Kubelka optical layering equation: R_comp = R1 + (T1^2 * R2) / (1 - R1 * R2) (Curtis et al. 1997 Sec. 5.2)
      const rCompR = r1R + (t1R * t1R * r2R) / Math.max(1e-4, 1.0 - r1R * r2R);
      const rCompG = r1G + (t1G * t1G * r2G) / Math.max(1e-4, 1.0 - r1G * r2G);
      const rCompB = r1B + (t1B * t1B * r2B) / Math.max(1e-4, 1.0 - r1B * r2B);

      // Single-layer optical opacity alpha_KM = 1 - T1_G / (1 - R1_G * R2_G)
      const alphaLayer = Math.max(0.14, Math.min(0.97, 1.0 - t1G / Math.max(1e-4, 1.0 - r1G * r2G)));

      // Combine anti-aliased brush footprint with anisotropic LBM nijimi capillary halo (fringe alpha capped <= 30/255 = 0.118)
      const fringeAlpha = Math.min(0.118, nijimiPotential * 0.58);
      let finalAlpha;
      if (mask >= 0.999) {
        finalAlpha = alphaLayer;
      } else {
        const rawEdgeAlpha = mask * alphaLayer + (1.0 - mask) * fringeAlpha;
        if (rawEdgeAlpha < 0.118) {
          // Disorder pinning & capillary valley wicking in the outer wet-dry fringe (max 0.118 rounds to 30/255, below the 32 ink threshold)
          finalAlpha = Math.min(0.118, rawEdgeAlpha * Math.max(0.24, Math.min(1.38, 1.46 - 0.96 * hVal)));
        } else {
          finalAlpha = Math.min(0.97, rawEdgeAlpha);
        }
      }

      if (finalAlpha < 0.004) {
        data[idx * 4 + 3] = 0;
        continue;
      }

      // Extract un-premultiplied layer RGB with multi-front colloidal glue/soot chromatic separation (artistic choice; not from Chu & Tai 2005, where glue only enters kappa, sigma and the fixture rate)
      let cR, cG, cB;
      if (toneMode === "dark-sumi") {
        const lumBoost = 0.84 + 0.16 * r1B;
        const coolShift = 8.0 * glueWarmth * Math.max(0.0, 0.65 - xOpt) * wCore;
        cR = Math.round(Math.max(165, Math.min(254, 222 * lumBoost - 22 * gZero - coolShift)));
        cG = Math.round(Math.max(178, Math.min(254, 231 * lumBoost - 18 * gZero)));
        cB = Math.round(Math.max(192, Math.min(255, 244 * lumBoost - 14 * gZero + coolShift)));
      } else {
        const invA = 1.0 / Math.max(0.14, alphaLayer);
        let rawR, rawG, rawB;
        if (toneMode === "vermilion") {
          rawR = (rCompR - (1.0 - alphaLayer) * r2R) * invA;
          rawG = (rCompG - (1.0 - alphaLayer) * r2G) * invA;
          rawB = (rCompB - (1.0 - alphaLayer) * r2B) * invA;
        } else {
          rawR = Math.max(0.05, r1R * invA + 0.14 * t1R);
          rawG = Math.max(0.04, r1G * invA + 0.12 * t1G);
          rawB = Math.max(0.03, r1B * invA + 0.10 * t1B);
        }

        // Colloidal carbon & animal glue (nikawa) warm sepia shift in thinner washes/fringes vs. deep carbon black in thick pools
        const thinness = Math.max(0.0, 0.58 - xOpt) * glueWarmth * (toneMode === "vermilion" ? 0.45 : 1.0);
        const warmR = thinness * 42.0 * (0.45 + 0.55 * wCore);
        const warmG = thinness * 14.0 * (0.45 + 0.55 * wCore);
        const warmB = -thinness * 26.0 * (0.45 + 0.55 * wCore);

        cR = Math.round(Math.max(4, Math.min(245, rawR * 255.0 + warmR)));
        cG = Math.round(Math.max(3, Math.min(240, rawG * 255.0 + warmG)));
        cB = Math.round(Math.max(2, Math.min(235, rawB * 255.0 + warmB)));
      }

      const pOff = idx * 4;
      data[pOff] = cR;
      data[pOff + 1] = cG;
      data[pOff + 2] = cB;
      data[pOff + 3] = Math.round(Math.max(0, Math.min(255, finalAlpha * 255.0)));
    }
  }

  ctx.putImageData(imgData, x0, y0);
}

function renderPartialCompiledStroke(targetCtx, compiled, endIdx, options = {}) {
  const pts = compiled.samples;
  if (!pts || endIdx < 1) return;
  const limit = Math.min(pts.length - 1, endIdx);

  const W = targetCtx.canvas.width;
  const H = targetCtx.canvas.height;
  const toneMode = options.toneMode || "sumi";
  let compositeOp = "multiply";
  if (toneMode === "vermilion" || toneMode === "dark-sumi") {
    compositeOp = "source-over";
  }

  const p = SLENDER_PHYSICS || DEFAULT_SLENDER_PHYSICS;
  const cacheKey = `${limit}_${toneMode}_${W}_${H}_${p.kasureAmount}_${p.paperGrainIntensity}_${p.coffeeRingIntensity}_${p.nijimiIntensity}_${p.bristleStriationIntensity}_${p.dwellPoolingIntensity}_${p.kmTransmittanceContrast}_${p.glueChromaticWarmth}_${p.coreMantleContrast}_${p.cefengObliqueIntensity}_${p.tuftPlasticityElasticity}_${p.reservoirCompressionSqueeze}`;

  if (compiled._kmRenderCache && compiled._kmRenderCache.key === cacheKey && compiled._kmRenderCache.canvas) {
    targetCtx.save();
    targetCtx.globalCompositeOperation = compositeOp;
    targetCtx.globalAlpha = options.opacity ?? 1.0;
    targetCtx.drawImage(compiled._kmRenderCache.canvas, 0, 0);
    targetCtx.restore();
    return;
  }

  const { bufferCanvas, bufferCtx } = getStrokeBufferCanvas(W, H);
  if (!bufferCanvas || !bufferCtx) return;

  bufferCtx.clearRect(0, 0, W, H);

  // 1. Rasterize crisp brush contact footprint onto Xuan paper surface (no uniform shadowBlur)
  bufferCtx.save();
  bufferCtx.fillStyle = "#000000";

  bufferCtx.beginPath();
  traceSmoothStrokeContour(bufferCtx, compiled, limit, false);
  bufferCtx.fill();

  // Carve dry-brush (kasure/feibai) bristle splits on long sweeping tails
  renderKasureAndFrayedBristles(bufferCtx, compiled, limit);
  bufferCtx.restore();

  // 2. Run D2Q9 Lattice Boltzmann percolation, contact-line coffee-ring darkening,
  //    Xuan paper fiber granulation, and exact two-flux Kubelka-Munk optical rendering
  renderPhysicallyBasedInkDispersionAndOptics(bufferCtx, compiled, limit, toneMode);

  // 3. Cache full-stroke rendered canvas for instant interactive hover/lock redraws
  if (limit === pts.length - 1 && typeof document !== "undefined") {
    if (!compiled._kmRenderCache) {
      compiled._kmRenderCache = { key: "", canvas: document.createElement("canvas") };
    }
    const cCan = compiled._kmRenderCache.canvas;
    if (cCan.width !== W || cCan.height !== H) {
      cCan.width = W;
      cCan.height = H;
    }
    const cCtx = cCan.getContext("2d");
    if (cCtx) {
      cCtx.clearRect(0, 0, W, H);
      cCtx.drawImage(bufferCanvas, 0, 0);
      compiled._kmRenderCache.key = cacheKey;
    }
  }

  // 4. Composite onto targetCtx
  targetCtx.save();
  targetCtx.globalCompositeOperation = compositeOp;
  targetCtx.globalAlpha = options.opacity ?? 1.0;
  targetCtx.drawImage(bufferCanvas, 0, 0);
  targetCtx.restore();
}

function renderFullCompiledStroke(ctx, compiled, options = {}) {
  const pts = compiled.samples;
  if (!pts || pts.length < 2) return;
  renderPartialCompiledStroke(ctx, compiled, pts.length - 1, options);
}

function setupCalligraphySumiCanvas(targetElement, svgElem, strokeEntries) {
  if (typeof document === "undefined" || !strokeEntries || strokeEntries.length === 0) return;
  const canvas = document.createElement("canvas");
  canvas.className = "calligraphy-sumi-canvas";
  canvas.width = 792;
  canvas.height = 792;
  svgElem.classList.add("has-sumi-canvas");
  targetElement.insertBefore(canvas, svgElem);

  canvas._compiledStrokes = strokeEntries.map(entry => ({
    entry,
    totalStrokes: strokeEntries.length,
    compiled: compileStrokePhysics({
      d: entry.d,
      type: entry.type || "",
      component: entry.component || "",
      index: entry.index || 1
    }, 0, 0, 792, strokeEntries.length),
    pathEl: entry.pathEl,
    id: entry.id
  }));
  canvas._svgElem = svgElem;

  refreshCalligraphySumiCanvas(targetElement);
}

function refreshCalligraphySumiCanvas(rootEl = document) {
  if (typeof document === "undefined") return;
  const targetScope = rootEl || document;
  let canvases = [];
  if (targetScope.matches && targetScope.matches("canvas.calligraphy-sumi-canvas:not(.audit-sumi-canvas)")) {
    canvases = [targetScope];
  } else if (targetScope.querySelectorAll) {
    canvases = Array.from(targetScope.querySelectorAll("canvas.calligraphy-sumi-canvas:not(.audit-sumi-canvas)"));
  }
  const isDark = (document.documentElement.getAttribute("data-theme") || "dark") === "dark";
  const baseTone = isDark ? "dark-sumi" : "sumi";
  const p = SLENDER_PHYSICS || DEFAULT_SLENDER_PHYSICS;
  const expectedCompileKey = getBrushCompileKey(p);

  canvases.forEach(canvas => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const svgElem = canvas._svgElem;
    const hasHover = svgElem && svgElem.classList.contains("has-hovered-child");
    const hasLock = svgElem && svgElem.classList.contains("has-locked-scope");
    const bgList = [];
    const fgList = [];
    const compiledStrokes = canvas._compiledStrokes || [];
    compiledStrokes.forEach(item => {
      if (item.entry && (!item.compiled || item.compiled._brushCompileKey !== expectedCompileKey)) {
        item.compiled = compileStrokePhysics({
          d: item.entry.d,
          type: item.entry.type || "",
          component: item.entry.component || "",
          index: item.entry.index || 1
        }, 0, 0, 792, item.totalStrokes || compiledStrokes.length);
      }
      const pathEl = item.pathEl;
      const isActive = pathEl && (pathEl.classList.contains("active-stroke") || (pathEl.closest && !!pathEl.closest(".kvg-group.hovered")));
      const inLock = pathEl && pathEl.closest && !!pathEl.closest(".kvg-group.locked-scope");
      if (isActive) {
        fgList.push({ compiled: item.compiled, options: { toneMode: "vermilion", opacity: 1.0 } });
      } else if (hasHover) {
        bgList.push({ compiled: item.compiled, options: { toneMode: baseTone, opacity: 0.20 } });
      } else if (hasLock) {
        bgList.push({ compiled: item.compiled, options: { toneMode: baseTone, opacity: inLock ? 0.95 : 0.20 } });
      } else {
        bgList.push({ compiled: item.compiled, options: { toneMode: baseTone, opacity: 1.0 } });
      }
    });
    bgList.forEach(s => renderFullCompiledStroke(ctx, s.compiled, s.options));
    fgList.forEach(s => renderFullCompiledStroke(ctx, s.compiled, s.options));
  });
}

if (typeof window !== "undefined") {
  window.renderAllAuditCanvases = function() {
    const rawStrokes = (typeof window !== "undefined" && Array.isArray(window.AUDIT_KVG_STROKES)) ? window.AUDIT_KVG_STROKES : [];
    if (rawStrokes.length === 0) return;
    const compiledList = rawStrokes.map((s, idx) => compileStrokePhysics({
      d: s.d,
      type: s.type || "",
      component: s.component || "",
      index: idx + 1
    }, 0, 0, 792, rawStrokes.length));
    const isDark = (document.documentElement.getAttribute("data-theme") || "dark") === "dark";
    const baseTone = isDark ? "dark-sumi" : "sumi";

    const canvases = document.querySelectorAll("canvas.audit-sumi-canvas");
    canvases.forEach(canvas => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const tileMode = canvas.getAttribute("data-tile-mode") || "all";
      if (tileMode === "all") {
        compiledList.forEach(compiled => {
          renderFullCompiledStroke(ctx, compiled, { toneMode: baseTone, opacity: 1.0 });
        });
      } else {
        const activeSet = new Set((canvas.getAttribute("data-active-ids") || "").split(",").filter(Boolean));
        const bgList = [];
        const fgList = [];
        rawStrokes.forEach((s, idx) => {
          const compiled = compiledList[idx];
          const strokeId = s.id || "";
          if (activeSet.has(strokeId)) {
            fgList.push({ compiled, options: { toneMode: "vermilion", opacity: 1.0 } });
          } else {
            bgList.push({ compiled, options: { toneMode: baseTone, opacity: 0.20 } });
          }
        });
        bgList.forEach(s => renderFullCompiledStroke(ctx, s.compiled, s.options));
        fgList.forEach(s => renderFullCompiledStroke(ctx, s.compiled, s.options));
      }
    });
  };
}

/**
 * SVG要素の構築（KanjiVG筆画表示を最優先、明朝体・印刷書体を第2モードとして描画）
 */
function renderSvgInto(targetElement, visual, tree) {
  // 1. バックエンドからの構造化 KanjiVG JSON データ処理（筆画単位ベクター表示 - デフォルト）
  if (state.activeDisplayMode !== "mincho" && visual.has_kanjivg && visual.kanjivg && typeof visual.kanjivg === "object") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 109 109");
    svg.classList.add("kvg-root");

    // 筆画総数を事前カウント（運筆の物理密度計算用）
    const totalStrokes = countKvgStrokes(visual.kanjivg) || 10;
    let strokeCounter = 0;
    const strokeEntries = [];

    // 和紙墨溜まり用SVGフィルター
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    const filter = document.createElementNS("http://www.w3.org/2000/svg", "filter");
    filter.setAttribute("id", "slender-sumi-pool");
    filter.setAttribute("x", "-10%");
    filter.setAttribute("y", "-10%");
    filter.setAttribute("width", "120%");
    filter.setAttribute("height", "120%");
    filter.innerHTML = '<feDropShadow dx="0" dy="0.2" stdDeviation="0.3" flood-color="rgba(24, 18, 12, 0.28)"/>';
    defs.appendChild(filter);
    svg.appendChild(defs);

    function renderKvgGroup(group, parentTreePath = "", ancestorComponents = []) {
      const elem = group.element || group.raw_element || "";
      const currentAncestors = elem ? [...ancestorComponents, elem] : [...ancestorComponents];
      let treePath = group.path || "";
      if (!treePath) {
        if (!parentTreePath) {
          treePath = "0";
        } else {
          const foundPath = elem ? findTreePathForElement(tree, elem, parentTreePath) : null;
          if (foundPath) {
            treePath = foundPath;
          } else {
            treePath = (parentTreePath !== "0") ? parentTreePath : "";
          }
        }
      }

      // 安全ガード: 子グループのパスが親の木構造スコープ (parentTreePath) を逸脱しないことを保証
      if (
        parentTreePath &&
        parentTreePath !== "0" &&
        treePath &&
        treePath !== parentTreePath &&
        !treePath.startsWith(parentTreePath + ".")
      ) {
        treePath = parentTreePath;
      }

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      if (group.id) g.setAttribute("id", group.id);
      g.setAttribute("class", "kvg-group");
      if (treePath) g.setAttribute("data-path", treePath);
      if (elem) g.setAttribute("data-char", elem);
      if (group.position) g.setAttribute("data-role", group.position);
      if (group.raw_element) g.setAttribute("data-raw", group.raw_element);

      const strokes = group.strokes || [];
      const children = group.children || [];
      const effectivePathForChildren = treePath || parentTreePath;

      // 直下の筆画（strokes）を描画：表示用パスと透明太幅ヒット領域パス
      if (strokes.length > 0) {
        strokes.forEach(stroke => {
          const strokeIdx = strokeCounter++;
          const allComps = [...currentAncestors];
          if (stroke.component) allComps.push(stroke.component);
          const special = allComps.reverse().find(c => c === '子' || c === '了' || c === '孑');
          const strokeComp = special || stroke.component || elem || "";
          const calligraphyD = stroke.calligraphy_d || compileSlenderStrokePathD(stroke.d, stroke.type, strokeIdx, totalStrokes, strokeComp);

          const visiblePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
          if (stroke.id) visiblePath.setAttribute("id", stroke.id);
          visiblePath.setAttribute("class", "kvg-stroke calligraphic-stroke");
          visiblePath.setAttribute("d", calligraphyD);
          visiblePath.setAttribute("data-orig-d", stroke.d);
          if (stroke.type) visiblePath.setAttribute("kvg:type", stroke.type);
          g.appendChild(visiblePath);

          strokeEntries.push({
            id: stroke.id || "",
            d: stroke.d,
            type: stroke.type || "",
            component: strokeComp,
            index: strokeIdx + 1,
            pathEl: visiblePath
          });

          const hitPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
          hitPath.setAttribute("class", "kvg-stroke-hit");
          hitPath.setAttribute("d", stroke.d);
          g.appendChild(hitPath);
        });
      }

      // 子グループの再帰描画
      children.forEach(childGroup => {
        g.appendChild(renderKvgGroup(childGroup, effectivePathForChildren, currentAncestors));
      });

      if (treePath && (treePath !== "0" || children.length === 0)) {
        attachInteractiveEventsToNode(g, treePath, elem, group.position || "", group.raw_element || "");
      }
      return g;
    }

    svg.appendChild(renderKvgGroup(visual.kanjivg, ""));
    targetElement.appendChild(svg);
    setupCalligraphySumiCanvas(targetElement, svg, strokeEntries);
    applyHitTestDepth();
    return;
  }

  // 2. 明朝体（印刷書体）インタラクティブベクターSVG
  if (visual.interactive_svg && (visual.interactive_svg.base_path || (visual.interactive_svg.component_layers && visual.interactive_svg.component_layers.length > 0))) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 1024 1024");
    svg.setAttribute("class", "kvg-svg print-style-svg");

    const uid = (targetElement.id ? targetElement.id + "_" : "") + Math.random().toString(36).slice(2, 7);
    const rawLayers = visual.interactive_svg.component_layers || [];
    const layers = rawLayers.filter(l => l && l.path && l.path !== "0");

    // <defs> クリップパス定義
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    layers.forEach(layer => {
      const safePath = String(layer.path).replace(/[^a-zA-Z0-9_-]/g, "_");
      const clipPath = document.createElementNS("http://www.w3.org/2000/svg", "clipPath");
      clipPath.setAttribute("id", `clip-${uid}-${safePath}`);

      const clipRects = (Array.isArray(layer.clip_rects) && layer.clip_rects.length > 0)
        ? layer.clip_rects
        : [layer.bbox || [0, 0, 1, 1]];
      clipRects.forEach(cr => {
        const rx = Math.round(cr[0] * 1024);
        const ry = Math.round(cr[1] * 1024);
        const rw = Math.round(cr[2] * 1024);
        const rh = Math.round(cr[3] * 1024);

        const clipRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        clipRect.setAttribute("x", String(rx));
        clipRect.setAttribute("y", String(ry));
        clipRect.setAttribute("width", String(rw));
        clipRect.setAttribute("height", String(rh));
        clipPath.appendChild(clipRect);
      });

      defs.appendChild(clipPath);
    });
    svg.appendChild(defs);

    const rootG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    rootG.setAttribute("class", "kvg-root");
    rootG.setAttribute("data-path", "0");

    const basePath = visual.interactive_svg.base_path || "";
    // ベース文字全体の明朝体アウトライン（鮮明な単一実線・不透明度1）
    if (basePath) {
      const baseGlyph = document.createElementNS("http://www.w3.org/2000/svg", "path");
      baseGlyph.setAttribute("d", basePath);
      baseGlyph.setAttribute("transform", "translate(0, 880) scale(1, -1)");
      baseGlyph.setAttribute("class", "print-base-glyph");
      rootG.appendChild(baseGlyph);
    }

    // 階層深度昇順ソート（浅い階層ほど先、深い子部品ほどDOM後ろ＝前面に配置されX線ホバーが正確にヒット）
    layers.sort((a, b) => a.path.split(".").length - b.path.split(".").length);

    // 最上位の svg_path 保持層を判定（祖先がすでに svg_path を保持している層を除外）
    const topSvgLayerPaths = new Set();
    layers.forEach(layer => {
      if (!layer.svg_path) return;
      const lPath = layer.path;
      let hasAncestor = false;
      for (const anc of topSvgLayerPaths) {
        if (lPath.startsWith(anc + ".")) {
          hasAncestor = true;
          break;
        }
      }
      if (!hasAncestor) {
        topSvgLayerPaths.add(lPath);
      }
    });

    layers.forEach(layer => {
      const depth = layer.path.split(".").length - 1;
      const safePath = String(layer.path).replace(/[^a-zA-Z0-9_-]/g, "_");
      const bbox = layer.bbox || [0, 0, 1, 1];
      const rx = Math.round(bbox[0] * 1024);
      const ry = Math.round(bbox[1] * 1024);
      const rw = Math.round(bbox[2] * 1024);
      const rh = Math.round(bbox[3] * 1024);

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "component-vector-layer kvg-group");
      g.setAttribute("data-path", layer.path);
      g.setAttribute("data-char", escapeAttr(layer.char || ""));
      g.setAttribute("data-depth", String(depth));
      if (layer.role_label) g.setAttribute("data-role", escapeAttr(layer.role_label));
      if (layer.raw_char) g.setAttribute("data-raw", escapeAttr(layer.raw_char));

      if (basePath) {
        // base_path あり：クリップされた明朝体スライスのみ描画（ホバー時に朱色で発色）
        // 重要: clip-pathをtransformを持つ要素自体にかけるとフォントローカル座標系（上下反転）で評価されてしまうため、
        // 画面座標系 (0..1024) を維持する親 <g> に clip-path を指定し、さらにその外側のラッパーに drop-shadow を適用して光彩の直線切断を防ぐ
        const glowWrapper = document.createElementNS("http://www.w3.org/2000/svg", "g");
        glowWrapper.setAttribute("class", "print-component-glow-wrapper");

        const sliceGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
        const shouldClip = (layer.needs_clip !== false) || !layer.slice_path || (layer.slice_path === basePath);
        if (shouldClip) {
          sliceGroup.setAttribute("clip-path", `url(#clip-${uid}-${safePath})`);
        }
        sliceGroup.setAttribute("class", "print-component-slice-group");

        const slice = document.createElementNS("http://www.w3.org/2000/svg", "path");
        const slicePath = layer.slice_path || basePath;
        slice.setAttribute("d", slicePath);
        slice.setAttribute("transform", "translate(0, 880) scale(1, -1)");
        slice.setAttribute("class", "print-component-slice");

        sliceGroup.appendChild(slice);
        glowWrapper.appendChild(sliceGroup);
        g.appendChild(glowWrapper);
      } else if (layer.svg_path) {
        // base_path なし：最上位のベクター保持層は常時表示、深層はホバー時のみ朱色発色
        const isTop = topSvgLayerPaths.has(layer.path);
        const fallback = document.createElementNS("http://www.w3.org/2000/svg", "path");
        fallback.setAttribute("d", layer.svg_path);
        if (layer.svg_transform) {
          fallback.setAttribute("transform", layer.svg_transform);
        }
        if (isTop) {
          fallback.setAttribute("class", "print-component-fallback");
        } else {
          fallback.setAttribute("class", "print-component-slice-fallback");
        }
        g.appendChild(fallback);
      }

      // インタラクティブヒットボックス & ホバー枠（分割ヒット領域 hit_rects 対応）
      const hitRects = (layer.hit_rects && Array.isArray(layer.hit_rects) && layer.hit_rects.length > 0)
        ? layer.hit_rects
        : [bbox];

      hitRects.forEach(hr => {
        const hrx = Math.round(hr[0] * 1024);
        const hry = Math.round(hr[1] * 1024);
        const hrw = Math.round(hr[2] * 1024);
        const hrh = Math.round(hr[3] * 1024);

        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", String(hrx));
        rect.setAttribute("y", String(hry));
        rect.setAttribute("width", String(hrw));
        rect.setAttribute("height", String(hrh));
        rect.setAttribute("rx", "10");
        rect.setAttribute("ry", "10");
        rect.setAttribute("class", "component-layer-hitbox");
        g.appendChild(rect);
      });

      attachInteractiveEventsToNode(g, layer.path, layer.char || "", layer.role_label || "", layer.raw_char || "");
      rootG.appendChild(g);
    });

    if (!basePath && topSvgLayerPaths.size === 0) {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      const isMulti = Array.from(state.currentChar || "").length > 1;
      text.setAttribute("x", "512");
      text.setAttribute("y", isMulti ? "512" : "720");
      text.setAttribute("font-size", isMulti ? "110" : "700");
      if (isMulti) {
        text.setAttribute("dominant-baseline", "central");
      }
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("fill", "currentColor");
      text.style.fontFamily = "var(--font-kanji)";
      text.textContent = state.currentChar;
      rootG.appendChild(text);
    }

    svg.appendChild(rootG);
    targetElement.appendChild(svg);
    applyHitTestDepth();
    return;
  }

  // 3. 静的SVG文字列フォールバック（デモプリセット等）
  if (visual.has_kanjivg && visual.kanjivg_svg && typeof visual.kanjivg_svg === "string") {
    const parser = new DOMParser();
    const doc = parser.parseFromString(visual.kanjivg_svg, "image/svg+xml");
    const svgElem = doc.querySelector("svg");
    if (svgElem) {
      svgElem.removeAttribute("width");
      svgElem.removeAttribute("height");

      // 和紙墨溜まり用SVGフィルター
      if (!svgElem.querySelector("#slender-sumi-pool")) {
        let defs = svgElem.querySelector("defs");
        if (!defs) {
          defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
          svgElem.insertBefore(defs, svgElem.firstChild);
        }
        const filter = document.createElementNS("http://www.w3.org/2000/svg", "filter");
        filter.setAttribute("id", "slender-sumi-pool");
        filter.setAttribute("x", "-10%");
        filter.setAttribute("y", "-10%");
        filter.setAttribute("width", "120%");
        filter.setAttribute("height", "120%");
        filter.innerHTML = '<feDropShadow dx="0" dy="0.2" stdDeviation="0.3" flood-color="rgba(24, 18, 12, 0.28)"/>';
        defs.appendChild(filter);
      }

      const strokePaths = Array.from(svgElem.querySelectorAll("path.kvg-stroke"));
      const totalStrokes = strokePaths.length || 10;
      const strokeEntries = [];
      strokePaths.forEach((pathEl, strokeIdx) => {
        const origD = pathEl.getAttribute("d") || "";
        const type = pathEl.getAttribute("kvg:type") || "";

        let strokeComp = "";
        const ancestorComps = [];
        let curr = pathEl.parentElement;
        while (curr && curr !== svgElem) {
          const elComp = curr.getAttribute("kvg:element") || curr.getAttribute("data-char") || "";
          if (elComp) {
            ancestorComps.push(elComp);
          }
          curr = curr.parentElement;
        }
        const special = ancestorComps.find(c => c === '子' || c === '了' || c === '孑');
        strokeComp = special || ancestorComps[0] || "";

        const calligraphyD = compileSlenderStrokePathD(origD, type, strokeIdx, totalStrokes, strokeComp);

        pathEl.setAttribute("d", calligraphyD);
        pathEl.setAttribute("data-orig-d", origD);
        pathEl.classList.add("calligraphic-stroke");

        strokeEntries.push({
          id: pathEl.getAttribute("id") || "",
          d: origD,
          type: type,
          component: strokeComp,
          index: strokeIdx + 1,
          pathEl: pathEl
        });

        const hitPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
        hitPath.setAttribute("class", "kvg-stroke-hit");
        hitPath.setAttribute("d", origD);
        if (pathEl.parentNode) {
          pathEl.parentNode.insertBefore(hitPath, pathEl.nextSibling);
        }
      });

      attachSvgInteractiveEvents(svgElem);
      targetElement.appendChild(svgElem);
      setupCalligraphySumiCanvas(targetElement, svgElem, strokeEntries);
      return;
    }
  }

  // 4. フォールバック（文字テキスト描画）
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 1024 1024");
  svg.classList.add("kvg-root");
  const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
  const isMulti = Array.from(state.currentChar || "").length > 1;
  text.setAttribute("x", "512");
  text.setAttribute("y", isMulti ? "512" : "720");
  text.setAttribute("font-size", isMulti ? "110" : "700");
  if (isMulti) {
    text.setAttribute("dominant-baseline", "central");
  }
  text.setAttribute("text-anchor", "middle");
  text.setAttribute("fill", "currentColor");
  text.style.fontFamily = "var(--font-kanji)";
  text.textContent = state.currentChar;
  svg.appendChild(text);
  targetElement.appendChild(svg);
}

/**
 * KanjiVG SVG 内の要素へイベントリスナーを付与
 */
function attachSvgInteractiveEvents(svgElem) {
  const groups = svgElem.querySelectorAll("g[id^='kvg:']");
  groups.forEach(g => {
    g.classList.add("kvg-group");
    const path = g.getAttribute("data-path") || "0";
    const element = g.getAttribute("kvg:element") || "";
    const original = g.getAttribute("kvg:original") || "";
    if (path && (path !== "0" || g.querySelectorAll("g[id^='kvg:']").length === 0)) {
      attachInteractiveEventsToNode(g, path, element, "", original);
    }
  });
}

/**
 * キャンバス部品クリック時の段階的ロック制御
 */
function handleComponentClick(path, char, role = "", raw_char = "") {
  if (!path || path === "0") return;

  const node = findNodeByPath(state.charData?.tree, path);

  // すでにロック済みの末端部品を再度クリックした場合: 単体調査へドリルダウン
  if (state.lockedPath === path) {
    const targetChar = char || node?.char || "";
    if (targetChar && targetChar !== state.currentChar) {
      inspectCharacter(targetChar);
    }
    return;
  }

  // 部品を固定（ロック）
  lockComponentScope(path);
}

/**
 * ノードへのホバーおよびクリックイベントの紐付け（mouseover による入れ子要素の確実な捕捉）
 */
function attachInteractiveEventsToNode(domNode, path, char, role = "", raw_char = "") {
  domNode.addEventListener("mouseover", (e) => {
    e.stopPropagation();
    let effectivePath = path;
    let effectiveChar = char;
    let effectiveRole = role;
    let effectiveRaw = raw_char;
    if (!state.lockedPath) {
      const parts = path.split(".");
      if (parts.length > 2) {
        const l1Path = parts.slice(0, 2).join(".");
        const hasL1Ancestor = !!domNode.closest ? !!domNode.closest(`.kvg-group[data-path="${l1Path}"]`) : false;
        if (!hasL1Ancestor) {
          effectivePath = l1Path;
          const l1Node = findNodeByPath(state.charData?.tree, l1Path);
          if (l1Node) {
            effectiveChar = l1Node.char || "";
            effectiveRole = l1Node.role_label || "";
            effectiveRaw = l1Node.raw_char || "";
          }
        }
      }
    }
    handleComponentHover(effectivePath, effectiveChar, effectiveRole, effectiveRaw);
  });

  domNode.addEventListener("mouseout", (e) => {
    if (e.relatedTarget && domNode.contains(e.relatedTarget)) {
      return;
    }
    const nextTarget = e.relatedTarget?.closest ? e.relatedTarget.closest("[data-path]") : null;
    const nextPath = nextTarget ? nextTarget.getAttribute("data-path") : null;
    if (!nextPath || nextPath === "0") {
      clearComponentHover();
    }
  });

  domNode.addEventListener("click", (e) => {
    e.stopPropagation();
    let effectivePath = path;
    let effectiveChar = char;
    let effectiveRole = role;
    let effectiveRaw = raw_char;
    if (!state.lockedPath) {
      const parts = path.split(".");
      if (parts.length > 2) {
        const l1Path = parts.slice(0, 2).join(".");
        const hasL1Ancestor = !!domNode.closest ? !!domNode.closest(`.kvg-group[data-path="${l1Path}"]`) : false;
        if (!hasL1Ancestor) {
          effectivePath = l1Path;
          const l1Node = findNodeByPath(state.charData?.tree, l1Path);
          if (l1Node) {
            effectiveChar = l1Node.char || "";
            effectiveRole = l1Node.role_label || "";
            effectiveRaw = l1Node.raw_char || "";
          }
        }
      }
    }
    handleComponentClick(effectivePath, effectiveChar, effectiveRole, effectiveRaw);
  });

  // マウスホイールによる階層深度切り替え
  domNode.addEventListener("wheel", (e) => {
    e.preventDefault();
    e.stopPropagation();
    handleWheelHierarchy(e.deltaY);
  }, { passive: false });
}

/**
 * ホバー時の詳細更新および双方向連動ハイライト
 */
function handleComponentHover(path, charOrEntering = "", role = "", raw_char = "") {
  if (charOrEntering === false) {
    clearComponentHover();
    return;
  }

  let targetPath = path || "0";
  let targetChar = typeof charOrEntering === "string" ? charOrEntering : "";
  let targetRole = role || "";
  let targetRaw = raw_char || "";

  state.hoveredPath = targetPath;

  // 対象ノードの詳細メタデータサマリー取得
  const activeNode = findNodeByPath(state.charData?.tree, targetPath);
  if (activeNode) {
    targetChar = targetChar || activeNode.char || "";
    targetRole = targetRole || activeNode.role_label || "";
    targetRaw = targetRaw || activeNode.raw_char || "";
  }
  const metaSummary = activeNode?.meta_summary || null;

  // 1. キャンバス内要素のハイライト
  document.querySelectorAll("[data-path]").forEach(el => {
    const elPath = el.getAttribute("data-path");
    if (!elPath || !targetPath || targetPath === "0") {
      el.classList.remove("hovered", "dimmed");
      return;
    }

    if (el.classList.contains("spatial-box")) {
      // 親の矩形領域が子要素全域を包含するため、完全一致時のみ hovered
      if (elPath === targetPath) {
        el.classList.add("hovered");
        el.classList.remove("dimmed");
      } else {
        el.classList.remove("hovered");
        el.classList.add("dimmed");
      }
    } else if (el.classList.contains("component-vector-layer")) {
      // 印刷書体スライス・破線枠は完全一致時のみ hovered（重複枠線の防止）
      if (elPath === targetPath) {
        el.classList.add("hovered");
      } else {
        el.classList.remove("hovered");
      }
    } else if (el.classList.contains("kvg-group")) {
      if (elPath === targetPath || elPath.startsWith(targetPath + ".")) {
        el.classList.add("hovered");
      } else {
        el.classList.remove("hovered");
      }
    } else if (el.classList.contains("tree-node") || el.classList.contains("tree-node-card")) {
      // ツリーノードは後述の処理で対応
    } else {
      if (elPath === targetPath) {
        el.classList.add("hovered");
      } else {
        el.classList.remove("hovered");
      }
    }
  });

  document.querySelectorAll(".kvg-root").forEach(svg => {
    if (targetPath && targetPath !== "0") {
      svg.classList.add("has-hovered-child");
    } else {
      svg.classList.remove("has-hovered-child");
    }
  });

  // 1.5 KanjiVG筆画レイヤー（layer_strokes）直接同期
  const layerStrokesMap = state.charData?.visual?.layer_strokes || state.charData?.visual?.kanjivg?.layer_strokes;
  if (layerStrokesMap) {
    const activeStrokes = new Set(layerStrokesMap[targetPath] || []);
    document.querySelectorAll(".kvg-stroke").forEach(strokeEl => {
      const sid = strokeEl.getAttribute("id");
      if (sid && activeStrokes.has(sid)) {
        strokeEl.classList.add("active-stroke");
      } else {
        strokeEl.classList.remove("active-stroke");
      }
    });
  }

  // 2. 中央ツリービューの双方向連動ハイライト & 自動スクロール
  document.querySelectorAll(".tree-node, .tree-node-card").forEach(nodeEl => {
    const nodePath = nodeEl.getAttribute("data-path");
    if (!nodePath || !targetPath || targetPath === "0") {
      nodeEl.classList.remove("hovered", "pulse", "hovered-descendant");
      return;
    }
    if (nodePath === targetPath) {
      nodeEl.classList.add("hovered", "pulse");
      nodeEl.classList.remove("hovered-descendant");

      // 親の .column-content のみスクロール（祖先コンテナやウィンドウの意図しないスクロールを完全防止）
      const scrollParent = nodeEl.closest(".column-content");
      if (scrollParent) {
        const parentRect = scrollParent.getBoundingClientRect();
        const nodeRect = nodeEl.getBoundingClientRect();
        if (nodeRect.top < parentRect.top) {
          scrollParent.scrollTop -= (parentRect.top - nodeRect.top) + 8;
        } else if (nodeRect.bottom > parentRect.bottom) {
          scrollParent.scrollTop += (nodeRect.bottom - parentRect.bottom) + 8;
        }
      }
    } else if (nodePath.startsWith(targetPath + ".")) {
      nodeEl.classList.add("hovered-descendant");
      nodeEl.classList.remove("hovered", "pulse");
    } else {
      nodeEl.classList.remove("hovered", "pulse", "hovered-descendant");
    }
  });

  // 3. HUD更新
  updateHud(targetChar || "—", targetPath, targetRole, targetRaw, metaSummary);
  refreshCalligraphySumiCanvas();
}

function clearComponentHover() {
  state.hoveredPath = null;
  document.querySelectorAll("[data-path]").forEach(el => el.classList.remove("hovered", "dimmed"));
  document.querySelectorAll(".kvg-root").forEach(svg => svg.classList.remove("has-hovered-child"));
  document.querySelectorAll(".kvg-stroke").forEach(el => el.classList.remove("active-stroke"));
  document.querySelectorAll(".tree-node, .tree-node-card").forEach(el => el.classList.remove("hovered", "pulse", "hovered-descendant"));

  updateCanvasLockClasses();
  resetHud();
  refreshCalligraphySumiCanvas();
}

/**
 * マウスホイールによる階層切り替え
 */
function handleWheelHierarchy(deltaY) {
  if (!state.hoveredPath) return;
  const parts = state.hoveredPath.split(".");
  let newPath = state.hoveredPath;

  if (deltaY > 0) {
    // 浅い階層へ
    if (parts.length > 1) {
      parts.pop();
      newPath = parts.join(".");
    }
  } else {
    // 深い階層へ
    const currNode = findNodeByPath(state.charData?.tree, state.hoveredPath);
    if (currNode && currNode.children && currNode.children.length > 0) {
      newPath = currNode.children[0].path;
    }
  }

  if (newPath !== state.hoveredPath) {
    const node = findNodeByPath(state.charData?.tree, newPath);
    if (node) {
      handleComponentHover(newPath, node.char, node.role_label, node.raw_char);
    }
  }
}

function setHudContent({ glyph = "", nameHtml = "", codepoint = "", rawChar = "", trail = "", hint = "", isActive = true, opacity = "1" }) {
  const hud = document.getElementById("hoverHud");
  const glyphBox = document.getElementById("hudGlyphBox");
  if (!hud || !glyphBox) return;

  hud.classList.toggle("active", isActive);
  glyphBox.innerHTML = renderGlyphHTML(glyph);
  glyphBox.style.opacity = opacity;
  document.getElementById("hudCharName").innerHTML = nameHtml;
  document.getElementById("hudCodepoint").textContent = codepoint;
  document.getElementById("hudRawOrig").textContent = (rawChar && rawChar !== glyph) ? `(原表記: ${rawChar})` : "";
  document.getElementById("hudTrail").textContent = trail;
  const hintEl = document.getElementById("hudHint");
  if (hintEl && hint) hintEl.textContent = hint;
}

function updateHud(char, path, role, raw_char, metaSummary = null) {
  const parts = [];
  if (metaSummary?.stroke_count) parts.push(`${metaSummary.stroke_count}画`);
  if (metaSummary?.ja_on?.length) parts.push(`音: ${metaSummary.ja_on.join("・")}`);
  if (metaSummary?.ja_kun?.length) parts.push(`訓: ${metaSummary.ja_kun.join("・")}`);
  const extra = parts.length ? ` | ${parts.join(" | ")}` : "";

  setHudContent({
    glyph: char,
    nameHtml: renderGlyphHTML(char),
    codepoint: getCodepointHex(char),
    rawChar: raw_char,
    trail: `階層パス: ${path}${role ? ` [役割: ${role}]` : ""}${extra}`,
    isActive: true
  });
}

function resetHud() {
  if (state.lockedPath) {
    const lockedNode = findNodeByPath(state.charData?.tree, state.lockedPath);
    if (lockedNode) {
      const lockedDepth = state.lockedPath.split(".").length - 1;
      const hasChildren = Array.isArray(lockedNode.children) && lockedNode.children.length > 0;
      const isComposite = !lockedNode.char && !lockedNode.raw_char;
      const dispChar = lockedNode.char || lockedNode.raw_char || (lockedNode.role_label ? `[${lockedNode.role_label}]` : "複合部品");

      setHudContent({
        glyph: dispChar,
        nameHtml: `[固定] ${renderGlyphHTML(dispChar)}`,
        codepoint: isComposite ? "(複合要素)" : getCodepointHex(dispChar),
        rawChar: lockedNode.raw_char,
        trail: `階層パス: ${state.lockedPath} [役割: ${lockedNode.role_label || "固定部品"}] | ${hasChildren ? `内部の第${lockedDepth + 1}階層部品を探索中` : "末端部品固定中"}`,
        hint: hasChildren
          ? `[固定中: ${dispChar}] 内部の第${lockedDepth + 1}階層部品をホバーで確認(クリックでさらに固定 / 「選択解除」で解除)`
          : `クリックで「${dispChar}」を単体調査 ／ 選択解除で復帰`,
        isActive: true
      });
      return;
    }
  }

  // デフォルト状態（未固定時）
  const cur = state.currentChar || "中";
  setHudContent({
    glyph: cur,
    nameHtml: `${renderGlyphHTML(cur)}(全体)`,
    codepoint: getCodepointHex(cur),
    trail: "階層パス: 0 [役割: 全体]",
    hint: "※ 部品ホバーで字形確認 / クリックで選択・逆引き検索",
    isActive: false,
    opacity: "0.75"
  });
}

/**
 * 漢字属性・字書情報カードのレンダリング
 */
function renderAttributeCard() {
  const meta = state.charData?.meta;
  if (!meta) return;

  const char = meta.char || meta.literal || state.currentChar;
  const cpHex = meta.codepoint || getCodepointHex(char);

  document.getElementById("attrCharCodepoint").textContent = cpHex;
  document.getElementById("attrCodepoint").textContent = cpHex;

  const tierBadge = document.getElementById("attrTierBadge");
  tierBadge.textContent = meta.tier || "通常漢字";

  // 部首情報の成形（辞書オブジェクトまたは文字列フォールバック）
  let radText = "—";
  if (meta.radical) {
    if (typeof meta.radical === "object") {
      const rName = meta.radical.name || meta.radical.char || "";
      const rNum = meta.radical.num ? ` [第${meta.radical.num}部]` : "";
      const rChar = meta.radical.char ? `${meta.radical.char}(${rName})` : rName;
      radText = rChar ? `${rChar}${rNum}` : (meta.radical.num ? `第${meta.radical.num}部` : "—");
    } else if (typeof meta.radical === "string") {
      radText = meta.radical;
    }
  }

  const strokeCountText = meta.stroke_count ? `${meta.stroke_count}画` : "画数未詳";
  document.getElementById("attrStrokesRadical").textContent = `${strokeCountText} ／ ${radText}`;

  // 読み（音・訓）
  const onReadings = (Array.isArray(meta.ja_on) && meta.ja_on.length > 0)
    ? meta.ja_on
    : (meta.on_readings || []);
  document.getElementById("attrOnReadings").textContent =
    onReadings.length > 0 ? onReadings.join("、") : "—";

  const kunReadings = (Array.isArray(meta.ja_kun) && meta.ja_kun.length > 0)
    ? meta.ja_kun
    : (meta.kun_readings || []);
  document.getElementById("attrKunReadings").textContent =
    kunReadings.length > 0 ? kunReadings.join("、") : "—";

  // バッジ一覧
  const badgesContainer = document.getElementById("attrBadges");
  badgesContainer.innerHTML = "";
  (meta.badges || []).forEach(b => {
    const span = document.createElement("span");
    span.className = "badge badge-grade";
    span.textContent = b;
    badgesContainer.appendChild(span);
  });

  // 辞書コード
  const daikanwa = meta.daikanwa || "—";
  const fourCorner = meta.four_corner || "—";
  const skip = meta.skip_code || meta.skip || "—";
  const cangjie = meta.cangjie || "—";
  const mojijoho = meta.moji_joho || meta.mojijoho || "—";
  document.getElementById("attrDictCodes").textContent =
    `大漢和: ${daikanwa} | 四角号碼: ${fourCorner} | SKIP: ${skip} | 倉頡: ${cangjie} | MJ文字: ${mojijoho}`;

  // 同等部品・異体字（文字列配列およびオブジェクト配列両対応）
  const equivList = document.getElementById("attrEquivalents");
  equivList.innerHTML = "";
  const equivalents = meta.equivalents || [];
  if (equivalents.length > 0) {
    equivalents.forEach(eq => {
      const chip = document.createElement("button");
      chip.className = "equiv-chip";
      let eqChar = "";
      let eqLabel = "";
      if (typeof eq === "string") {
        eqChar = eq;
        eqLabel = getCodepointHex(eq);
      } else if (typeof eq === "object" && eq) {
        eqChar = eq.char || "";
        eqLabel = eq.label || eq.codepoint || getCodepointHex(eqChar);
      }
      if (eqChar) {
        chip.innerHTML = `${renderGlyphHTML(eqChar)} <span style="font-size:0.68rem;opacity:0.75;">(${eqLabel})</span>`;
        chip.addEventListener("click", () => inspectCharacter(eqChar));
        equivList.appendChild(chip);
      }
    });
  }
  if (equivList.children.length === 0) {
    equivList.innerHTML = `<span style="font-size:0.75rem;color:var(--text-muted);">特になし</span>`;
  }
}

// =============================================================================
// 6. 中央カラム: 構造分解ツリー & IDSシーケンス
// =============================================================================

function renderStructureSelector() {
  const container = document.getElementById("structureSelector");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  const alts = state.charData.alternatives || [];
  alts.forEach((alt, idx) => {
    const btn = document.createElement("button");
    btn.className = `struct-btn ${idx === state.activeStructureIndex ? "active" : ""}`;
    const label = alt.label || alt.source || alt.id || "構造";
    btn.innerHTML = `${escapeAttr(label)}: ${renderIdsHTML(alt.ids)}`;
    btn.addEventListener("click", () => {
      state.activeStructureIndex = idx;
      inspectCharacter(state.currentChar, false, alt.ids);
    });
    container.appendChild(btn);
  });
}

function renderIdsTokens() {
  const container = document.getElementById("idsTokensContainer");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  if (state.charData.unavailable) return;
  const alts = state.charData.alternatives || [];
  const alt = alts[state.activeStructureIndex] || alts[0] || { ids: state.currentChar };
  const idsStr = alt.ids || state.currentChar;

  tokenizeIds(idsStr).forEach(tok => {
    const chip = document.createElement("span");
    chip.className = "ids-token-chip";
    if (tok in IDC_OPERATORS) {
      chip.classList.add("operator");
      chip.title = IDC_OPERATORS[tok].name;
      chip.textContent = tok;
    } else {
      chip.innerHTML = renderGlyphHTML(tok);
      chip.addEventListener("click", () => {
        inspectCharacter(tok);
      });
    }
    container.appendChild(chip);
  });
}

/**
 * 再帰的分解ツリーの描画
 */
function renderRecursiveTree() {
  const container = document.getElementById("treeContainer");
  if (!container || !state.charData) return;
  container.innerHTML = "";

  const tree = state.charData.tree;
  if (!tree) return;

  function buildNodeDOM(node, depth = 0) {
    const wrapper = document.createElement("div");
    wrapper.className = "tree-node-wrapper";

    const card = document.createElement("div");
    card.className = "tree-node-card";
    card.setAttribute("data-path", node.path || "0");

    // 左側: 役割バッジ、グリフ表示、文字名、コードポイント
    const left = document.createElement("div");
    left.className = "tree-node-left";

    const roleBadge = document.createElement("span");
    roleBadge.className = "tree-role-badge";
    roleBadge.textContent = node.role_label ? `[${node.role_label}]` : `[第${depth}階層]`;
    left.appendChild(roleBadge);

    const glyphBox = document.createElement("div");
    glyphBox.className = "tree-glyph-box";
    glyphBox.innerHTML = renderGlyphHTML(node.char || node.op);
    left.appendChild(glyphBox);

    const meta = document.createElement("div");
    meta.className = "tree-node-meta";

    const nameRow = document.createElement("div");
    nameRow.className = "tree-node-name-row";

    const charName = document.createElement("span");
    charName.className = "tree-node-char";
    charName.innerHTML = renderGlyphHTML(node.char || node.op);
    nameRow.appendChild(charName);

    if (node.op && node.op in IDC_OPERATORS) {
      const opBadge = document.createElement("span");
      opBadge.className = "badge badge-tier-basic";
      opBadge.textContent = `${node.op} ${IDC_OPERATORS[node.op].short}`;
      nameRow.appendChild(opBadge);
    }

    if (node.tier) {
      const tierBadge = document.createElement("span");
      tierBadge.className = "badge badge-tier-ext";
      tierBadge.textContent = node.tier;
      nameRow.appendChild(tierBadge);
    }

    // 画数サマリー（meta_summary 由来）
    if (node.meta_summary?.stroke_count) {
      const strokeBadge = document.createElement("span");
      strokeBadge.className = "badge";
      strokeBadge.style.background = "var(--bg-tertiary)";
      strokeBadge.textContent = `${node.meta_summary.stroke_count}画`;
      nameRow.appendChild(strokeBadge);
    }

    // 読み情報（meta_summary 由来）
    const reads = [...(node.meta_summary?.ja_on || []), ...(node.meta_summary?.ja_kun || [])];
    if (reads.length > 0) {
      const readSpan = document.createElement("span");
      readSpan.className = "tree-node-readings";
      readSpan.style.fontSize = "0.72rem";
      readSpan.style.color = "var(--text-muted)";
      readSpan.textContent = reads.slice(0, 3).join("、");
      nameRow.appendChild(readSpan);
    }

    meta.appendChild(nameRow);

    const sub = document.createElement("span");
    sub.className = "tree-node-sub";
    const rawInfo = (node.raw_char && node.raw_char !== node.char) ? ` (原表記: ${escapeAttr(node.raw_char)})` : "";
    const bboxFormatted = (node.bbox || []).map(v => typeof v === "number" ? v.toFixed(2) : v).join(", ");
    sub.textContent = `${getCodepointHex(node.char || "")}${rawInfo} | 領域: [${bboxFormatted}]`;
    meta.appendChild(sub);

    left.appendChild(meta);
    card.appendChild(left);

    // 右側: ドリルダウン & 逆引き追加アクションボタン
    const right = document.createElement("div");
    right.className = "tree-node-right";

    if (node.char && node.char !== state.currentChar) {
      const btnInspect = document.createElement("button");
      btnInspect.className = "btn-tree-action";
      btnInspect.innerHTML = "詳細";
      btnInspect.title = `「${node.char}」を主文字として詳細分解します`;
      btnInspect.addEventListener("click", (e) => {
        e.stopPropagation();
        inspectCharacter(node.char);
      });
      right.appendChild(btnInspect);

      const btnAddFind = document.createElement("button");
      btnAddFind.className = "btn-tree-action add-find";
      btnAddFind.innerHTML = "＋逆引き";
      btnAddFind.title = `「${node.char}」を逆引き検索条件に追加します`;
      btnAddFind.addEventListener("click", (e) => {
        e.stopPropagation();
        addFindChip(node.char);
      });
      right.appendChild(btnAddFind);
    }

    if (state.lockedPath && node.path === state.lockedPath) {
      card.classList.add("locked-node");
    }

    card.appendChild(right);

    // クリックによる段階的ロック連動
    card.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      e.stopPropagation();
      handleComponentClick(node.path, node.char, node.role_label, node.raw_char);
    });

    // 双方向ホバーイベント紐付け
    card.addEventListener("mouseenter", () => {
      handleComponentHover(node.path, node.char, node.role_label, node.raw_char);
    });
    card.addEventListener("mouseleave", () => {
      clearComponentHover();
    });

    wrapper.appendChild(card);

    // 子要素の再帰展開
    if (node.children && node.children.length > 0) {
      const childrenCont = document.createElement("div");
      childrenCont.className = "tree-children";
      node.children.forEach(child => {
        childrenCont.appendChild(buildNodeDOM(child, depth + 1));
      });
      wrapper.appendChild(childrenCont);
    }

    return wrapper;
  }

  container.appendChild(buildNodeDOM(tree, 0));
}

// =============================================================================
// 7. 右カラム: 包含漢字・逆引き探索（ids-find）
// =============================================================================

function addFindChip(char) {
  if (!char) return;
  state.findChips.add(char);
  renderFindChips();
  executeFindSearch();
}

function removeFindChip(char) {
  state.findChips.delete(char);
  renderFindChips();
  executeFindSearch();
}

function clearFindChips() {
  state.findChips.clear();
  renderFindChips();
  executeFindSearch();
}

function renderFindChips() {
  const container = document.getElementById("findChipsContainer");
  const input = document.getElementById("findComponentInput");
  if (!container || !input) return;

  // 既存のチップを削除（input以外）
  const oldChips = container.querySelectorAll(".component-chip");
  oldChips.forEach(c => c.remove());

  state.findChips.forEach(char => {
    const chip = document.createElement("span");
    chip.className = "component-chip";
    chip.innerHTML = `${renderGlyphHTML(char)} <button class="chip-remove-btn" title="条件から削除">×</button>`;
    chip.querySelector(".chip-remove-btn").addEventListener("click", () => removeFindChip(char));
    container.insertBefore(chip, input);
  });
}

/**
 * 逆引き検索の実行（CHISE ids-find）
 */
async function executeFindSearch() {
  const request = findRequests.begin();
  const resultsGrid = document.getElementById("resultsGrid");
  if (!resultsGrid) return;

  const chipsArray = Array.from(state.findChips);
  if (chipsArray.length === 0) {
    resultsGrid.innerHTML = `
      <div class="state-message">
        <p>検索したい部品を追加してください。</p>
        <p style="font-size:0.75rem;">例: 「𭕄」や「虫」を追加すると包含する漢字が一覧表示されます。</p>
      </div>
    `;
    updateResultsSummary(0, 0, 0);
    return;
  }

  // フィルタ設定取得
  const hierarchyFilter = document.getElementById("filterHierarchy")?.value || "all";
  const categoryFilter = document.getElementById("filterCategory")?.value || "all";
  const minStroke = parseInt(document.getElementById("filterStrokeMin")?.value, 10) || 0;
  const maxStroke = parseInt(document.getElementById("filterStrokeMax")?.value, 10) || 999;

  let results = [];
  let totalCount = 0;
  let directCount = 0;
  let indirectCount = 0;

  try {
    const params = new URLSearchParams();
    params.set("components", chipsArray.join(" "));
    // サーバー側は "transitive" で間接検索を処理
    params.set("mode", hierarchyFilter === "indirect" ? "transitive" : hierarchyFilter);
    params.set("tier", categoryFilter);
    if (minStroke > 0) params.set("min_strokes", String(minStroke));
    if (maxStroke < 999) params.set("max_strokes", String(maxStroke));

    const res = await fetch(`/api/ids-find?${params.toString()}`, { signal: request.signal });
    if (!res.ok) throw new Error("逆引き検索の取得失敗");
    if (res.ok) {
      const data = await res.json();
      results = data.results || [];
      totalCount = data.total !== undefined ? data.total : results.length;

      if (data.direct_total !== undefined && data.indirect_total !== undefined) {
        directCount = data.direct_total;
        indirectCount = data.indirect_total;
      } else {
        directCount = results.filter(r =>
          r.is_direct === 1 || r.is_direct === true || chipsArray.some(c => (r.chise_ids || r.ids || "").includes(c))
        ).length;
        indirectCount = Math.max(0, totalCount - directCount);
      }
    }
  } catch (e) {
    if (!request.isCurrent()) return;
    console.warn("逆引き検索結果を取得できませんでした:", e);
    resultsGrid.textContent = "逆引き検索結果を取得できませんでした。再度検索してください。";
    updateResultsSummary("未詳", "未詳", "未詳");
    return;
  }

  if (!request.isCurrent()) return;

  updateResultsSummary(totalCount, directCount, indirectCount);
  renderFindResults(results, chipsArray);
}

/**
 * 逆引き検索結果の描画
 */
function renderFindResults(results, activeKeywords = []) {
  const resultsGrid = document.getElementById("resultsGrid");
  if (!resultsGrid) return;
  resultsGrid.innerHTML = "";

  if (results.length === 0) {
    resultsGrid.innerHTML = `
      <div class="state-message">
        <p>該当する包含漢字が見つかりませんでした。</p>
        <p style="font-size:0.75rem;">フィルタ条件を緩和するか、キャンバスやツリーの部品をクリックして検索してください。</p>
      </div>
    `;
    return;
  }

  results.forEach(res => {
    const card = document.createElement("div");
    card.className = "result-card";

    const char = res.char || res.literal || "";
    const codepoint = res.codepoint || getCodepointHex(char);
    const tier = res.tier || "通常漢字";
    const strokeText = res.stroke_count ? `${res.stroke_count}画` : "画数未詳";
    const idsStr = res.chise_ids || res.ids || "";
    const viaChar = res.via_char || res.via || "";

    const isDirect = (res.is_direct !== undefined)
      ? (res.is_direct === 1 || res.is_direct === true)
      : (activeKeywords.length === 0 || activeKeywords.some(kw => idsStr.includes(kw)));

    // 左側: グリフ、情報、バッジ、IDS表示
    const left = document.createElement("div");
    left.className = "result-card-left";

    const glyphBox = document.createElement("div");
    glyphBox.className = "result-glyph-box";
    glyphBox.innerHTML = renderGlyphHTML(char);
    left.appendChild(glyphBox);

    const info = document.createElement("div");
    info.className = "result-info";

    const header = document.createElement("div");
    header.className = "result-header-row";

    const title = document.createElement("span");
    title.className = "result-char-title";
    title.innerHTML = renderGlyphHTML(char);
    header.appendChild(title);

    const cp = document.createElement("span");
    cp.className = "result-codepoint";
    cp.textContent = getCodepointHex(char) || codepoint;
    header.appendChild(cp);

    info.appendChild(header);

    // バッジ行
    const badgesRow = document.createElement("div");
    badgesRow.className = "result-badges-row";

    // 頻度バッジ
    if (res.freq !== undefined && res.freq !== null && res.freq > 0) {
      const freqBadge = document.createElement("span");
      freqBadge.className = "badge badge-freq";
      freqBadge.textContent = `頻度 #${res.freq}`;
      badgesRow.appendChild(freqBadge);
    }

    // 学年・常用バッジ
    if (res.grade !== undefined && res.grade !== null && res.grade > 0) {
      const gradeBadge = document.createElement("span");
      gradeBadge.className = "badge badge-grade";
      if (res.grade >= 1 && res.grade <= 6) {
        gradeBadge.textContent = `小学${res.grade}年`;
      } else if (res.grade === 8) {
        gradeBadge.textContent = "常用漢字";
      } else if (res.grade === 9 || res.grade === 10) {
        gradeBadge.textContent = "人名用漢字";
      } else {
        gradeBadge.textContent = `学年${res.grade}`;
      }
      badgesRow.appendChild(gradeBadge);
    }

    const tierBadge = document.createElement("span");
    tierBadge.className = "badge badge-tier-basic";
    tierBadge.textContent = tier;
    badgesRow.appendChild(tierBadge);

    const strokeBadge = document.createElement("span");
    strokeBadge.className = "badge";
    strokeBadge.style.background = "var(--bg-tertiary)";
    strokeBadge.textContent = strokeText;
    badgesRow.appendChild(strokeBadge);

    // 階層・直接/間接バッジ
    if (isDirect) {
      const directBadge = document.createElement("span");
      directBadge.className = "badge badge-direct";
      directBadge.textContent = "直接構成";
      badgesRow.appendChild(directBadge);
    } else {
      const indirectBadge = document.createElement("span");
      indirectBadge.className = "badge badge-indirect";
      if (viaChar) {
        indirectBadge.innerHTML = `間接(経由: <a class="via-link" data-via="${escapeAttr(viaChar)}">${renderGlyphHTML(viaChar)}</a>)`;
        const viaLink = indirectBadge.querySelector(".via-link");
        if (viaLink) {
          viaLink.addEventListener("click", (e) => {
            e.stopPropagation();
            inspectCharacter(viaChar);
          });
        }
      } else {
        indirectBadge.textContent = "間接(深層展開)";
      }
      badgesRow.appendChild(indirectBadge);
    }

    info.appendChild(badgesRow);

    // IDS表示（検索部品を強調表示）
    if (idsStr) {
      const idsRow = document.createElement("div");
      idsRow.className = "result-ids-row";
      idsRow.innerHTML = `構造: ${renderIdsHTML(idsStr, activeKeywords)}`;
      info.appendChild(idsRow);
    }

    // 読み表示
    let readingsList = [];
    if (Array.isArray(res.ja_on) || Array.isArray(res.ja_kun)) {
      if (res.ja_on && res.ja_on.length > 0) readingsList.push(res.ja_on.join("・"));
      if (res.ja_kun && res.ja_kun.length > 0) readingsList.push(res.ja_kun.join("・"));
    } else if (res.readings) {
      readingsList.push(res.readings);
    }

    if (readingsList.length > 0) {
      const readRow = document.createElement("div");
      readRow.className = "result-readings-row";
      readRow.textContent = `読み: ${readingsList.join(" / ")}`;
      info.appendChild(readRow);
    }

    left.appendChild(info);
    card.appendChild(left);

    // クリックでこの文字を調査
    card.addEventListener("click", () => inspectCharacter(char));

    resultsGrid.appendChild(card);
  });
}

function updateResultsSummary(total, direct, indirect) {
  document.getElementById("resultsTotalCount").textContent = total;
  document.getElementById("resultsDirectCount").textContent = direct;
  document.getElementById("resultsIndirectCount").textContent = indirect;
}

// =============================================================================
// 7.5 収録熟語・語彙検索（第4カラム）
// =============================================================================

async function loadWordsForCurrentKanji() {
  const wordsGrid = document.getElementById("wordsGrid");
  const wordsTotalBadge = document.getElementById("wordsTotalBadge");
  const wordsTotalCount = document.getElementById("wordsTotalCount");
  const wordsTopCount = document.getElementById("wordsTopCount");
  const wordsHighCount = document.getElementById("wordsHighCount");

  const targetKanji = state.currentChar;
  if (!targetKanji) return;

  const request = wordsRequests.begin();

  if (wordsGrid) {
    wordsGrid.innerHTML = `
      <div class="state-message">
        <div class="state-spinner"></div>
        <p>「${targetKanji}」を含む熟語・語彙を検索中...</p>
      </div>
    `;
  }

  const posFilter = state.wordsFilter.position || "all";
  const tierFilter = state.wordsFilter.tier || "all";
  const keyword = state.wordsFilter.keyword || "";
  const scopeFilter = state.wordsFilter.scope || "auto";

  const url = `/api/words?kanji=${encodeURIComponent(targetKanji)}&scope=${encodeURIComponent(scopeFilter)}&position=${encodeURIComponent(posFilter)}&tier=${encodeURIComponent(tierFilter)}&keyword=${encodeURIComponent(keyword)}&limit=100`;

  try {
    const res = await fetch(url, { signal: request.signal });
    if (!res.ok) {
      throw new Error(`API error: ${res.status}`);
    }
    const data = await res.json();
    if (!request.isCurrent()) return;
    state.wordsData = data;

    const total = data.total || 0;
    const summary = data.summary || {};
    const isComponent = !!data.is_component_search;

    if (wordsTotalBadge) wordsTotalBadge.textContent = `${total}語`;
    if (wordsTotalCount) wordsTotalCount.textContent = total;
    if (wordsTopCount) wordsTopCount.textContent = summary.top || 0;
    if (wordsHighCount) wordsHighCount.textContent = summary.high || 0;

    const wordsModeBadge = document.getElementById("wordsModeBadge");
    if (wordsModeBadge) {
      const dCount = summary.direct !== undefined ? summary.direct : 0;
      const cCount = summary.carrier !== undefined ? summary.carrier : 0;
      if (dCount > 0 && cCount > 0) {
        wordsModeBadge.style.display = "inline-flex";
        wordsModeBadge.innerHTML = `<span style="color:var(--accent-primary);font-weight:700;">漢字(青) ${dCount}語</span><span style="margin:0 4px;opacity:0.5;">/</span><span style="color:#16a34a;font-weight:700;">部品(緑) ${cCount}語</span>`;
        wordsModeBadge.title = `「${targetKanji}」自身を含む熟語(${dCount}語)と、構成要素として含む熟語(${cCount}語)を統合表示中`;
      } else if (cCount > 0) {
        wordsModeBadge.style.display = "inline-flex";
        wordsModeBadge.innerHTML = `<span style="color:#16a34a;font-weight:700;">部品「${targetKanji}」包含(緑) ${cCount}語</span>`;
        wordsModeBadge.title = `「${targetKanji}」を構成要素・部首として含む熟語を表示中`;
      } else if (dCount > 0) {
        wordsModeBadge.style.display = "inline-flex";
        wordsModeBadge.innerHTML = `<span style="color:var(--accent-primary);font-weight:700;">漢字「${targetKanji}」(青) ${dCount}語</span>`;
        wordsModeBadge.title = `「${targetKanji}」自身を含む熟語を表示中`;
      } else {
        wordsModeBadge.style.display = "none";
      }
    }

    renderWordsGrid(data.results || [], targetKanji, isComponent);
  } catch (err) {
    if (!request.isCurrent()) return;
    state.wordsData = null;
    if (wordsTotalBadge) wordsTotalBadge.textContent = "未詳";
    for (const count of [wordsTotalCount, wordsTopCount, wordsHighCount]) {
      if (count) count.textContent = "未詳";
    }
    const modeBadge = document.getElementById("wordsModeBadge");
    if (modeBadge) modeBadge.style.display = "none";
    if (wordsGrid) {
      wordsGrid.innerHTML = `
        <div class="state-message">
          <p>語彙データの読み込みに失敗しました。</p>
          <p style="font-size:0.75rem;">サーバー接続状態をご確認ください。</p>
        </div>
      `;
    }
  }
}

function renderWordsGrid(words, currentKanji, isComponentSearch = false) {
  const wordsGrid = document.getElementById("wordsGrid");
  if (!wordsGrid) return;
  wordsGrid.innerHTML = "";

  if (!words || words.length === 0) {
    wordsGrid.innerHTML = `
      <div class="state-message">
        <p>該当する熟語・語彙が見つかりませんでした。</p>
        <p style="font-size:0.75rem;">フィルタ条件を緩和するか、別の漢字をお試しください。</p>
      </div>
    `;
    return;
  }

  words.forEach(w => {
    const card = document.createElement("div");
    card.className = "word-card";

    // 上部ヘッダー（見出し語、読み、バッジ群）
    const topRow = document.createElement("div");
    topRow.className = "word-card-top";

    const lemmaGroup = document.createElement("div");
    lemmaGroup.className = "word-lemma-group";

    const lemmaSpan = document.createElement("span");
    lemmaSpan.className = "word-lemma";

    // 提示漢字（青）および構成部品漢字（緑）をハイライト
    const matchedKanjiList = (w.matched_kanjis || (w.matched_kanji || "").split(",")).map(k => k.trim()).filter(Boolean);
    const directSymbols = [currentKanji, ...(state.charData?.meta?.equivalents || [])];

    let lemmaHtml = "";
    for (const ch of (w.lemma || "")) {
      if (directSymbols.includes(ch)) {
        lemmaHtml += `<span class="highlight-kanji" title="「${escapeAttr(currentKanji)}」自体を含む漢字">${escapeAttr(ch)}</span>`;
      } else if (matchedKanjiList.includes(ch)) {
        lemmaHtml += `<span class="highlight-carrier" title="「${escapeAttr(currentKanji)}」を構成要素として含む漢字: ${escapeAttr(ch)}">${escapeAttr(ch)}</span>`;
      } else {
        lemmaHtml += escapeAttr(ch);
      }
    }
    lemmaSpan.innerHTML = lemmaHtml;
    lemmaGroup.appendChild(lemmaSpan);

    if (w.reading) {
      const readSpan = document.createElement("span");
      readSpan.className = "word-reading";
      readSpan.textContent = `【${w.reading}】`;
      lemmaGroup.appendChild(readSpan);
    }
    topRow.appendChild(lemmaGroup);

    // バッジ群（頻度、位置、品詞、直接/部品キャリア）
    const badgesRow = document.createElement("div");
    badgesRow.className = "word-badges-row";

    // 頻度バッジ
    const tier = w.frequency_tier || "専門・稀少";
    const freqBadge = document.createElement("span");
    let tierClass = "badge-freq-rare";
    if (tier === "最頻出") tierClass = "badge-freq-top";
    else if (tier === "頻出") tierClass = "badge-freq-high";
    else if (tier === "一般") tierClass = "badge-freq-mid";
    else if (tier === "発展") tierClass = "badge-freq-adv";

    freqBadge.className = `badge ${tierClass}`;
    freqBadge.textContent = (w.frequency_display && w.frequency_display !== "未詳")
      ? `${tier} ${w.frequency_display}`
      : tier;
    badgesRow.appendChild(freqBadge);

    const carriers = (w.carrier_kanjis && w.carrier_kanjis.length > 0)
      ? w.carrier_kanjis
      : matchedKanjiList.filter(k => !directSymbols.includes(k));
    const hasDirect = (w.has_direct_kanji !== undefined)
      ? w.has_direct_kanji
      : (w.lemma && directSymbols.some(s => w.lemma.includes(s)));

    // 漢字直接一致バッジ（青）
    if (hasDirect) {
      const directBadge = document.createElement("span");
      directBadge.className = "badge badge-direct-match";
      directBadge.textContent = `漢字: ${currentKanji}`;
      directBadge.title = `「${currentKanji}」自体を含む漢字熟語`;
      badgesRow.appendChild(directBadge);
    }

    // 部品キャリアバッジ（緑）
    if (carriers.length > 0) {
      const carrierBadge = document.createElement("span");
      carrierBadge.className = "badge badge-carrier";
      carrierBadge.textContent = `部品: ${carriers.join("・")}`;
      carrierBadge.title = `この熟語内の「${carriers.join("・")}」が「${currentKanji}」を構成要素として含みます`;
      badgesRow.appendChild(carrierBadge);
    }

    // 出現位置バッジ
    if (w.position_type) {
      const posMap = {
        head: "語頭",
        middle: "語中",
        tail: "語尾",
        single: "単独",
      };
      const posBadge = document.createElement("span");
      posBadge.className = "badge badge-position";
      posBadge.textContent = posMap[w.position_type] || w.position_type;
      badgesRow.appendChild(posBadge);
    }

    // 品詞バッジ
    if (w.pos) {
      const posBadge = document.createElement("span");
      posBadge.className = "badge badge-pos";
      posBadge.textContent = w.pos;
      badgesRow.appendChild(posBadge);
    }

    topRow.appendChild(badgesRow);
    card.appendChild(topRow);

    // 語釈・意味リスト
    const defCont = document.createElement("div");
    defCont.className = "word-definition";

    const defs = (Array.isArray(w.definitions) && w.definitions.length > 0)
      ? w.definitions
      : (w.definition ? [w.definition] : []);

    if (defs.length > 1) {
      defs.slice(0, 3).forEach((d, idx) => {
        const item = document.createElement("div");
        item.className = "word-def-item";
        const num = ["①", "②", "③"][idx] || `(${idx + 1})`;
        item.innerHTML = `<span class="word-def-num">${num}</span> ${escapeAttr(d)}`;
        defCont.appendChild(item);
      });
    } else if (defs.length === 1) {
      defCont.textContent = defs[0];
    } else {
      defCont.textContent = "語釈未詳";
      defCont.style.color = "var(--text-muted)";
    }
    card.appendChild(defCont);

    // カードフッター: 構成漢字の調査ジャンプボタン
    const otherKanjis = [];
    const kanjiRegex = /[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\u{20000}-\u{2FA1F}\u{30000}-\u{3347F}]/u;
    for (const c of (w.lemma || "")) {
      if (kanjiRegex.test(c) && c !== currentKanji && !otherKanjis.includes(c)) {
        otherKanjis.push(c);
      }
    }

    if (otherKanjis.length > 0) {
      const footer = document.createElement("div");
      footer.className = "word-card-footer";

      const linksWrap = document.createElement("div");
      linksWrap.className = "word-kanji-links";
      linksWrap.innerHTML = `<span>構成漢字:</span>`;

      otherKanjis.slice(0, 3).forEach(ok => {
        const btnJump = document.createElement("button");
        btnJump.type = "button";
        btnJump.className = "word-kanji-jump-btn";
        btnJump.textContent = `「${ok}」を調査 →`;
        btnJump.title = `「${ok}」を主文字として詳細分解します`;
        btnJump.addEventListener("click", (e) => {
          e.stopPropagation();
          inspectCharacter(ok);
        });
        linksWrap.appendChild(btnJump);
      });

      footer.appendChild(linksWrap);

      const srcLabel = document.createElement("span");
      srcLabel.className = "word-source-label";
      srcLabel.textContent = w.source || "国語辞典";
      footer.appendChild(srcLabel);

      card.appendChild(footer);
    }

    wordsGrid.appendChild(card);
  });
}

// =============================================================================
// 8. パンくずリスト & ナビゲーション
// =============================================================================

function updateBreadcrumbsUI() {
  const trail = document.getElementById("breadcrumbsTrail");
  if (!trail) return;

  // ラベル保持
  trail.innerHTML = `<span class="breadcrumb-label">探索履歴:</span>`;

  state.history.forEach((char, idx) => {
    if (idx > 0) {
      const sep = document.createElement("span");
      sep.className = "breadcrumb-sep";
      sep.textContent = "→";
      trail.appendChild(sep);
    }

    const item = document.createElement("button");
    item.className = `breadcrumb-item ${idx === state.historyIndex ? "active" : ""}`;
    item.innerHTML = `${renderGlyphHTML(char, "crumb-glyph")} <span>(${getCodepointHex(char)})</span>`;
    item.addEventListener("click", () => {
      state.historyIndex = idx;
      inspectCharacter(char, false);
    });
    trail.appendChild(item);
  });

  // 進む・戻るボタンの活性化
  const btnBack = document.getElementById("btnHistoryBack");
  const btnForward = document.getElementById("btnHistoryForward");
  if (btnBack) btnBack.disabled = state.historyIndex <= 0;
  if (btnForward) btnForward.disabled = state.historyIndex >= state.history.length - 1;
}

// =============================================================================
// 9. イベントリスナー初期化 & 起動処理
// =============================================================================

function initEventListeners() {
  // 出典・ライセンスモーダル制御
  const btnCreditsModal = document.getElementById("btnCreditsModal");
  const creditsModal = document.getElementById("creditsModal");
  const creditsModalCloseBtn = document.getElementById("creditsModalCloseBtn");
  const creditsModalCloseFooterBtn = document.getElementById("creditsModalCloseFooterBtn");

  function openCreditsModal() {
    if (!creditsModal) return;
    creditsModal.style.display = "flex";
    creditsModal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeCreditsModal() {
    if (!creditsModal) return;
    creditsModal.style.display = "none";
    creditsModal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  if (btnCreditsModal && creditsModal) {
    btnCreditsModal.addEventListener("click", openCreditsModal);
    if (creditsModalCloseBtn) {
      creditsModalCloseBtn.addEventListener("click", closeCreditsModal);
    }
    if (creditsModalCloseFooterBtn) {
      creditsModalCloseFooterBtn.addEventListener("click", closeCreditsModal);
    }
    creditsModal.addEventListener("click", (e) => {
      if (e.target === creditsModal) {
        closeCreditsModal();
      }
    });
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && creditsModal.style.display === "flex") {
        closeCreditsModal();
      }
    });
  }

  // テーマ切替
  const themeBtn = document.getElementById("themeToggleBtn");
  if (themeBtn) {
    document.documentElement.setAttribute("data-theme", state.theme);
    const themeLabel = document.getElementById("themeToggleText");
    if (themeLabel) {
      themeLabel.textContent = state.theme === "dark" ? "外観: 暗色" : "外観: 明色";
    }
    themeBtn.addEventListener("click", () => {
      state.theme = state.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", state.theme);
      if (typeof localStorage !== "undefined") {
        localStorage.setItem("kanji_theme", state.theme);
      }
      if (themeLabel) {
        themeLabel.textContent = state.theme === "dark" ? "外観: 暗色" : "外観: 明色";
      }
      refreshCalligraphySumiCanvas();
    });
  }

  // 表示モード切替（筆画表示 vs 明朝体印刷書体）
  const btnKvg = document.getElementById("btnModeKvg");
  const btnMincho = document.getElementById("btnModeMincho");
  if (btnKvg && btnMincho) {
    btnKvg.addEventListener("click", () => {
      if (state.activeDisplayMode === "kvg") return;
      state.activeDisplayMode = "kvg";
      btnKvg.classList.add("active");
      btnMincho.classList.remove("active");
      renderCanvas();
    });
    btnMincho.addEventListener("click", () => {
      if (state.activeDisplayMode === "mincho") return;
      state.activeDisplayMode = "mincho";
      btnMincho.classList.add("active");
      btnKvg.classList.remove("active");
      renderCanvas();
    });
  }

  // 統合検索バー
  const searchInput = document.getElementById("mainSearchInput");
  const btnInspect = document.getElementById("btnInspect");
  const btnFind = document.getElementById("btnFind");

  if (btnInspect && searchInput) {
    btnInspect.addEventListener("click", () => {
      const val = searchInput.value.trim();
      if (val) inspectCharacter(val);
    });
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = searchInput.value.trim();
        if (val) inspectCharacter(val);
      }
    });
  }

  if (btnFind && searchInput) {
    btnFind.addEventListener("click", () => {
      const val = searchInput.value.trim();
      if (val) addFindChip(val);
    });
  }

  // クイック探索プリセット
  document.querySelectorAll(".preset-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const drilldown = btn.getAttribute("data-drilldown");
      if (drilldown) {
        // 段階的ドリルダウン例 (蛍 -> 𰃮 -> 𭕄)
        const sequence = drilldown.split(",");
        state.history = [];
        sequence.forEach(ch => state.history.push(ch));
        state.historyIndex = 0;
        inspectCharacter(sequence[0], false);
      } else {
        const kanji = btn.getAttribute("data-kanji");
        if (kanji) inspectCharacter(kanji);
      }
    });
  });

  // 履歴進む・戻る・消去
  const btnBack = document.getElementById("btnHistoryBack");
  const btnForward = document.getElementById("btnHistoryForward");
  const btnClear = document.getElementById("btnHistoryClear");

  if (btnBack) {
    btnBack.addEventListener("click", () => {
      if (state.historyIndex > 0) {
        state.historyIndex--;
        inspectCharacter(state.history[state.historyIndex], false);
      }
    });
  }

  if (btnForward) {
    btnForward.addEventListener("click", () => {
      if (state.historyIndex < state.history.length - 1) {
        state.historyIndex++;
        inspectCharacter(state.history[state.historyIndex], false);
      }
    });
  }

  if (btnClear) {
    btnClear.addEventListener("click", () => {
      state.history = [state.currentChar];
      state.historyIndex = 0;
      updateBreadcrumbsUI();
    });
  }

  // キャンバス内空白領域への移動時および領域からの退出時にホバーハイライトを解除
  const canvasContainer = document.getElementById("canvasSvgContainer");
  if (canvasContainer) {
    canvasContainer.addEventListener("mouseover", (e) => {
      const hitNode = e.target?.closest ? e.target.closest("[data-path]") : null;
      const hitPath = hitNode ? hitNode.getAttribute("data-path") : null;
      if ((!hitPath || hitPath === "0") && state.hoveredPath) {
        clearComponentHover();
      }
    });
    canvasContainer.addEventListener("mouseleave", () => {
      clearComponentHover();
    });
  }

  // 段階的ロック階層探索コントローラー
  const btnLockStepUp = document.getElementById("btnLockStepUp");
  if (btnLockStepUp) {
    btnLockStepUp.addEventListener("click", () => {
      stepLockScopeUp();
    });
  }

  const btnResetLock = document.getElementById("btnResetLock");
  if (btnResetLock) {
    btnResetLock.addEventListener("click", () => {
      resetLockedScope();
    });
  }

  // Escキーで選択固定（ロック）解除
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.lockedPath !== null) {
      resetLockedScope();
    }
  });

  // 逆引きチップ入力
  const findInput = document.getElementById("findComponentInput");
  if (findInput) {
    findInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = findInput.value.trim();
        if (val) {
          addFindChip(val);
          findInput.value = "";
        }
      }
    });
  }

  const btnClearFind = document.getElementById("btnClearFindChips");
  if (btnClearFind) {
    btnClearFind.addEventListener("click", clearFindChips);
  }

  // フィルタ変更イベント
  const filterHierarchy = document.getElementById("filterHierarchy");
  const filterCategory = document.getElementById("filterCategory");
  const btnApplyFind = document.getElementById("btnApplyFind");

  if (filterHierarchy) filterHierarchy.addEventListener("change", executeFindSearch);
  if (filterCategory) filterCategory.addEventListener("change", executeFindSearch);
  if (btnApplyFind) btnApplyFind.addEventListener("click", executeFindSearch);

  // 熟語検索・フィルタイベント（第4カラム）
  const wordsInput = document.getElementById("wordsKeywordInput");
  let wordsDebounceTimer = null;
  if (wordsInput) {
    wordsInput.addEventListener("input", (e) => {
      clearTimeout(wordsDebounceTimer);
      wordsDebounceTimer = setTimeout(() => {
        state.wordsFilter.keyword = e.target.value.trim();
        loadWordsForCurrentKanji();
      }, 250);
    });
  }

  const filterWordScope = document.getElementById("filterWordScope");
  if (filterWordScope) {
    filterWordScope.addEventListener("change", (e) => {
      state.wordsFilter.scope = e.target.value;
      loadWordsForCurrentKanji();
    });
  }

  const filterWordPos = document.getElementById("filterWordPosition");
  if (filterWordPos) {
    filterWordPos.addEventListener("change", (e) => {
      state.wordsFilter.position = e.target.value;
      loadWordsForCurrentKanji();
    });
  }

  const filterWordTier = document.getElementById("filterWordTier");
  if (filterWordTier) {
    filterWordTier.addEventListener("change", (e) => {
      state.wordsFilter.tier = e.target.value;
      loadWordsForCurrentKanji();
    });
  }

  const btnClearWords = document.getElementById("btnClearWordsFilter");
  if (btnClearWords) {
    btnClearWords.addEventListener("click", () => {
      state.wordsFilter = { position: "all", tier: "all", keyword: "", scope: "all" };
      if (wordsInput) wordsInput.value = "";
      if (filterWordScope) filterWordScope.value = "all";
      if (filterWordPos) filterWordPos.value = "all";
      if (filterWordTier) filterWordTier.value = "all";
      loadWordsForCurrentKanji();
    });
  }

  initInkPhysicsSettingsPanel();
}

const INK_PHYSICS_PARAM_KEYS = [
  "paperGrainIntensity",
  "coffeeRingIntensity",
  "nijimiIntensity",
  "bristleStriationIntensity",
  "dwellPoolingIntensity",
  "kmTransmittanceContrast",
  "glueChromaticWarmth",
  "coreMantleContrast",
  "cefengObliqueIntensity",
  "tuftPlasticityElasticity",
  "reservoirCompressionSqueeze",
  "kasureAmount"
];

function detectMatchingInkPhysicsPreset() {
  for (const [presetKey, presetObj] of Object.entries(INK_PHYSICS_PRESETS)) {
    const presetVals = presetObj.values || presetObj;
    const allMatch = INK_PHYSICS_PARAM_KEYS.every((k) => {
      return Math.abs((SLENDER_PHYSICS[k] ?? 0) - (presetVals[k] ?? 0)) < 1e-3;
    });
    if (allMatch) return presetKey;
  }
  return null;
}

function syncInkPhysicsSettingsUI(activePresetKey = undefined) {
  const resolvedPreset = activePresetKey !== undefined ? activePresetKey : detectMatchingInkPhysicsPreset();
  document.querySelectorAll(".ink-physics-slider").forEach((slider) => {
    const param = slider.getAttribute("data-param");
    if (param && SLENDER_PHYSICS[param] !== undefined) {
      slider.value = String(SLENDER_PHYSICS[param]);
    }
  });
  document.querySelectorAll(".ink-slider-val").forEach((badge) => {
    const param = badge.getAttribute("data-val-for");
    if (param && SLENDER_PHYSICS[param] !== undefined) {
      badge.textContent = Number(SLENDER_PHYSICS[param]).toFixed(2);
    }
  });
  document.querySelectorAll(".btn-ink-preset").forEach((btn) => {
    const pKey = btn.getAttribute("data-preset");
    btn.classList.toggle("active", Boolean(resolvedPreset && pKey === resolvedPreset));
  });
}

function redrawAllInkPhysicsCanvasesNow() {
  if (document.getElementById("canvasSvgContainer")) {
    refreshCalligraphySumiCanvas();
  }
  if (typeof window !== "undefined" && typeof window.renderAllAuditCanvases === "function") {
    window.renderAllAuditCanvases();
  }
}

let inkRedrawFrameHandle = null;

// Coalesce rapid slider `input` events into at most one expensive redraw per animation frame
function redrawAllInkPhysicsCanvases() {
  if (typeof requestAnimationFrame !== "function") {
    redrawAllInkPhysicsCanvasesNow();
    return;
  }
  if (inkRedrawFrameHandle !== null) return;
  inkRedrawFrameHandle = requestAnimationFrame(() => {
    inkRedrawFrameHandle = null;
    redrawAllInkPhysicsCanvasesNow();
  });
}

function applyInkPhysicsPreset(presetKey) {
  const presetObj = INK_PHYSICS_PRESETS[presetKey];
  if (!presetObj) return false;
  const preset = presetObj.values || presetObj;
  INK_PHYSICS_PARAM_KEYS.forEach((k) => {
    if (preset[k] !== undefined) {
      SLENDER_PHYSICS[k] = Number(preset[k]);
    }
  });
  try {
    localStorage.setItem("kanji_ink_physics", JSON.stringify(preset));
  } catch (_e) {
    // Ignore storage quota / privacy mode errors
  }
  syncInkPhysicsSettingsUI(presetKey);
  redrawAllInkPhysicsCanvases();
  return true;
}

function updateInkPhysicsParameter(paramKey, rawVal) {
  if (!INK_PHYSICS_PARAM_KEYS.includes(paramKey)) return false;
  const num = Number(rawVal);
  if (!Number.isFinite(num)) return false;
  SLENDER_PHYSICS[paramKey] = Math.max(0.0, Math.min(2.5, num));
  try {
    const saved = {};
    INK_PHYSICS_PARAM_KEYS.forEach((k) => {
      saved[k] = SLENDER_PHYSICS[k];
    });
    localStorage.setItem("kanji_ink_physics", JSON.stringify(saved));
  } catch (_e) {
    // Ignore storage quota / privacy mode errors
  }
  syncInkPhysicsSettingsUI();
  redrawAllInkPhysicsCanvases();
  return true;
}

function resetInkPhysicsSettings() {
  INK_PHYSICS_PARAM_KEYS.forEach((k) => {
    SLENDER_PHYSICS[k] = DEFAULT_SLENDER_PHYSICS[k];
  });
  try {
    localStorage.removeItem("kanji_ink_physics");
  } catch (_e) {
    // Ignore storage errors
  }
  syncInkPhysicsSettingsUI("standard");
  redrawAllInkPhysicsCanvases();
}

function initInkPhysicsSettingsPanel() {
  try {
    const savedRaw = localStorage.getItem("kanji_ink_physics");
    if (savedRaw) {
      const parsed = JSON.parse(savedRaw);
      if (parsed && typeof parsed === "object") {
        INK_PHYSICS_PARAM_KEYS.forEach((k) => {
          const v = Number(parsed[k]);
          if (Number.isFinite(v)) {
            SLENDER_PHYSICS[k] = Math.max(0.0, Math.min(2.5, v));
          }
        });
      }
    }
  } catch (_e) {
    // Ignore corrupt localStorage state
  }

  const toggleBtn = document.getElementById("btnInkSettingsToggle");
  const panel = document.getElementById("inkPhysicsSettingsPanel");
  if (toggleBtn && panel) {
    toggleBtn.addEventListener("click", () => {
      const nextHidden = !panel.hidden;
      panel.hidden = nextHidden;
      toggleBtn.setAttribute("aria-expanded", nextHidden ? "false" : "true");
    });
  }

  document.querySelectorAll(".btn-ink-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      const presetKey = btn.getAttribute("data-preset");
      if (presetKey) applyInkPhysicsPreset(presetKey);
    });
  });

  document.querySelectorAll(".ink-physics-slider").forEach((slider) => {
    slider.addEventListener("input", (e) => {
      const paramKey = slider.getAttribute("data-param");
      if (paramKey) {
        updateInkPhysicsParameter(paramKey, e.target.value);
      }
    });
  });

  const resetBtn = document.getElementById("btnResetInkPhysics");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      resetInkPhysicsSettings();
    });
  }

  syncInkPhysicsSettingsUI();
}

if (typeof window !== "undefined") {
  window.INK_PHYSICS_PRESETS = INK_PHYSICS_PRESETS;
  window.applyInkPhysicsPreset = applyInkPhysicsPreset;
  window.updateInkPhysicsParameter = updateInkPhysicsParameter;
  window.resetInkPhysicsSettings = resetInkPhysicsSettings;
}

// 起動初期化
document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  renderFindChips();

  const urlParams = new URLSearchParams(window.location.search);
  const themeParam = urlParams.get("theme");
  if (themeParam === "dark" || themeParam === "light") {
    state.theme = themeParam;
    document.documentElement.setAttribute("data-theme", state.theme);
    const themeLabel = document.getElementById("themeToggleText");
    if (themeLabel) {
      themeLabel.textContent = state.theme === "dark" ? "外観: 暗色" : "外観: 明色";
    }
  }

  if (!document.getElementById("canvasSvgContainer")) {
    if (window.renderAllAuditCanvases) window.renderAllAuditCanvases();
    return;
  }

  const initialChar = urlParams.get("char") || urlParams.get("c") || urlParams.get("q") || "中";
  const initialHover = urlParams.get("hover") || urlParams.get("path");
  const initialLock = urlParams.get("lock");

  inspectCharacter(initialChar).then(() => {
    if (initialLock) {
      lockComponentScope(initialLock);
    } else if (initialHover) {
      handleComponentHover(initialHover);
    }
  });
});
