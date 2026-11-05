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

const SLENDER_PHYSICS = {
  thickness: 0.86,
  tonStrength: 1.08,
  waistRatio: 0.80,
  nibAngleDeg: -40,
  kasureAmount: 0.30,
  minTaperRatio: 0.10
};

/**
 * 永字八法・筆画種別分類
 */
function classifyStrokeBehavior(stroke) {
  const rawT = stroke.type || '';
  const primary = rawT.split('/')[0].trim();
  const t = primary;
  const name = (stroke.stroke_name || '').toLowerCase();
  const comp = (stroke.component || '').trim();

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
  const isRightNa = (t.includes('㇏') || name.includes('nà') || name.includes('捺')) && !t.includes('㇔');
  const isCrownDot = t === '㇑a' && (comp === '宀' || comp === '亠' || comp === '广' || comp === '疒' || comp === '穴');
  const isDot = (t.includes('㇔') || isCrownDot || name.includes('diǎn') || name.includes('点')) && !isRightNa && !isRisingTi;

  // isSweepEnd covers free-air left sweeps and folds that sweep
  const isSweepEnd = !isHook && !isDot && !isRightNa && !isRisingTi && !isVerticalTi && (
    t.includes('㇒') || t.includes('㇇') || t.includes('㇋') || isVerticalSweep || isZiHengPie || isRoofHook ||
    name.includes('piě') || name.includes('撇')
  );

  const isFold = t.includes('㇕') || t.includes('㇄') || t.includes('㇅') || t.includes('㇆') ||
    t.includes('㇈') || t.includes('㇉') || t.includes('㇊') || t.includes('㇋') ||
    t.includes('㇌') || t.includes('㇍') || t.includes('㇎') || t.includes('㇇') ||
    t.includes('㇖') || t.includes('㇗') || t.includes('㇘') || t.includes('㇙') ||
    t.includes('㇛') || t.includes('㇜') || t.includes('㇞') || t.includes('㇟') ||
    t.includes('㇠') || t.includes('㇡') || isZiHengPie || isRoofHook ||
    name.includes('zhé') || name.includes('折');

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
    isDot,
    isHook,
    isFold,
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

  const behavior = classifyStrokeBehavior(stroke);

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
  if (!behavior.isDot && rawPts.length > 8 && origLen > 8) {
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
  const minCornerS = 5.0;
  const maxCornerS = hookFeature ? hookFeature.s - 6.5 : origLen - 4.5;
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
  const curveWeightBoost = (behavior.isSweepEnd || behavior.isHook || behavior.isRightNa) ? 1.15 : 1.05;
  const shaftRadius = (boxSize * 0.024) * SLENDER_PHYSICS.thickness * densityScale * curveWeightBoost;
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

    if (behavior.isDot) {
      // 点 (diǎn) - natural softly rounded 45° entry tip swelling down-right into broad, plush heel
      const arch = Math.sin(Math.pow(u, 0.82) * (Math.PI * 0.72));
      wL = 0.28 + (1.05 * tonMult) * arch;
      wR = 0.26 + (0.90 * tonMult) * arch;
      poolWeight = 0.40 + 0.55 * arch;
    } else if (behavior.isRisingTi) {
      // 提 (tí) - rising stroke with steady calligraphic slope attack to sharp point
      const headZone = Math.min(totalLen * 0.26, 4.5);
      if (s < headZone) {
        const t = s / headZone;
        const blend = 0.5 * (1 + Math.cos(t * Math.PI));
        wL = 0.88 + (0.32 * tonMult) * blend;
        wR = 0.92 + (0.42 * tonMult) * blend;
        poolWeight = 0.85;
      } else {
        const t = (s - headZone) / Math.max(0.1, totalLen - headZone);
        const taper = 1.0 - 0.90 * Math.pow(t, 1.05);
        wL = 0.88 * taper;
        wR = 0.92 * taper;
        poolWeight = 0.35 * (1 - t);
      }
    } else if (behavior.isRightNa) {
      // 捺 (nà / 磔) - clean gradual press to wave foot at u=0.72 without mid-stroke bulge, then crisp taper to point
      const footU = 0.72;
      if (u <= footU) {
        const t = u / footU;
        const swell = Math.pow(t, 1.15);
        wL = 0.58 + (0.90 - 0.58) * swell;
        wR = 0.58 + (1.06 - 0.58) * swell;
        poolWeight = 0.30 + 0.65 * swell;
      } else {
        const tFoot = (u - footU) / (1.0 - footU);
        const decay = 1.0 - 0.90 * Math.pow(tFoot, 1.05);
        wL = 0.90 * decay;
        wR = 1.06 * decay;
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
          wL += (0.38 * tonMult) * blend;
          wR += (0.16 * tonMult) * blend;
        } else if (isRightToLeftSweep) {
          wR += (0.36 * tonMult) * blend;
          wL += (0.20 * tonMult) * blend;
        } else {
          wL = shaftTension * (1.0 + 0.08 * blend);
          wR = shaftTension * (1.0 + 0.14 * blend);
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

          if (cf.turnSign >= 0) {
            wR += (0.28 * tonMult) * bell;
            wL = Math.max(0.68, wL - 0.12 * bell);
          } else {
            wL += (0.28 * tonMult) * bell;
            wR = Math.max(0.68, wR - 0.12 * bell);
          }
        }
      }

      // Hook Resting Heel & Flick
      if (hookFeature) {
        const hs = hookFeature.s;
        if (s < hs) {
          const dHeel = hs - s;
          const heelRange = (behavior.isCurvedBowHook || (stroke.type || "").includes("㇈") || (stroke.type || "").includes("㇃") || (stroke.type || "").includes("㇆")) ? 16.0 : 7.0;
          if (dHeel < heelRange) {
            const tHeel = dHeel / heelRange;
            const heelBell = 0.5 * (1 + Math.cos(tHeel * Math.PI));
            const outerIsL = (hookFeature.flickUx < 0 && p.tx < 0.3) || (hookFeature.flickUy < -0.5 && p.turnSign < 0);
            if (outerIsL) {
              wL += (0.22 * tonMult) * heelBell;
            } else {
              wR += (0.22 * tonMult) * heelBell;
            }
            poolWeight = Math.max(poolWeight, 0.95 * heelBell);
          }
        } else {
          const tFlick = (s - hs) / Math.max(0.1, totalLen - hs);
          const flickTaper = 1.0 - 0.90 * Math.pow(tFlick, 0.88);
          wL *= flickTaper;
          wR *= flickTaper;
          poolWeight = Math.max(0.1, 0.8 * (1.0 - tFlick));
        }
      } else if (behavior.isRoofHook) {
        const cornerU = cornerFeatures[0] ? cornerFeatures[0].u : 0.78;
        if (u > cornerU) {
          const tHook = (u - cornerU) / (1 - cornerU);
          const taper = 1.0 - 0.90 * Math.pow(tHook, 1.05);
          wL *= taper;
          wR *= taper;
        }
      } else if (behavior.isVerticalTi) {
        const lastCf = cornerFeatures[cornerFeatures.length - 1];
        const cornerU = lastCf ? lastCf.u : 0.75;
        if (u > cornerU) {
          const tTi = (u - cornerU) / (1 - cornerU);
          const taper = 1.0 - 0.90 * Math.pow(tTi, 1.05);
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
          const sweepStart = (lastCf && lastCf.u > 0.42) ? lastCf.u : (isRightToLeftSweep ? 0.30 : 0.34);
          if (u > sweepStart) {
            const tSweep = (u - sweepStart) / (1 - sweepStart);
            const taper = 1.0 - 0.90 * Math.pow(tSweep, 1.05);
            wL *= taper;
            wR *= taper;
          }
        }
      } else if (behavior.isVertical && !behavior.isFold) {
        const endDist = totalLen - s;
        const tomeZone = Math.min(5.5, totalLen * 0.28);
        if (endDist < tomeZone) {
          const t = 1 - (endDist / tomeZone);
          const smoothT = 0.5 * (1 - Math.cos(t * Math.PI));
          if (behavior.isConnectingVertical) {
            wL += (0.15 * tonMult) * smoothT;
            wR += (0.15 * tonMult) * smoothT;
          } else {
            wL += (0.30 * tonMult) * smoothT;
            wR += (0.30 * tonMult) * smoothT;
            poolWeight = Math.max(poolWeight, 0.85 * smoothT);
          }
        }
      } else {
        const endDist = totalLen - s;
        const tomeZone = Math.min(5.5, totalLen * 0.28);
        if (endDist < tomeZone) {
          const t = 1 - (endDist / tomeZone);
          const smoothT = 0.5 * (1 - Math.cos(t * Math.PI));
          wL += (0.30 * tonMult) * smoothT;
          wR += (0.42 * tonMult) * smoothT;
          poolWeight = Math.max(poolWeight, 0.88 * smoothT);
        }
      }
    }

    rawWL[i] = wL;
    rawWR[i] = wR;
    rawPoolWeight[i] = poolWeight;
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
      const maxR = Math.max(shaftRadius * 0.70, 0.90 / kappa);
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

  // Forward-progression enforcement pass on (lx, ly) and (rx, ry)
  for (let iter = 0; iter < 6; iter++) {
    for (let i = 0; i < numSamples; i++) {
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
    while (iterations < 6) {
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
            for (let k = a + 1; k < b; k++) {
              const t = (k - a) / (b - a);
              setP(k, pa.x + t * (pb.x - pa.x), pa.y + t * (pb.y - pa.y));
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

  collapsePolylineLoops(rawPts, true);
  collapsePolylineLoops(rawPts, false);

  for (let i = 0; i < numSamples; i++) {
    const dLx = rawPts[i + 1].lx - rawPts[i].lx;
    const dLy = rawPts[i + 1].ly - rawPts[i].ly;
    const dotL = dLx * rawPts[i].tx + dLy * rawPts[i].ty;
    if (dotL < -0.15) {
      rawPts[i + 1].lx += rawPts[i].tx * (-0.10 - dotL);
      rawPts[i + 1].ly += rawPts[i].ty * (-0.10 - dotL);
    }
    const dRx = rawPts[i + 1].rx - rawPts[i].rx;
    const dRy = rawPts[i + 1].ry - rawPts[i].ry;
    const dotR = dRx * rawPts[i].tx + dRy * rawPts[i].ty;
    if (dotR < -0.15) {
      rawPts[i + 1].rx += rawPts[i].tx * (-0.10 - dotR);
      rawPts[i + 1].ry += rawPts[i].ty * (-0.10 - dotR);
    }
  }

  // Expanded corner features for geometry and evaluation
  const evalCornerFeatures = [...cornerFeatures];
  // Also detect short-stroke flick corner like 心 s3 (origLen < 25)
  if (cornerFeatures.length === 0) {
    let bestA = 0;
    let bestI = -1;
    for (let i = 2; i < numSamples - 2; i++) {
      if (rawPts[i].turnAngle > bestA && rawPts[i].turnAngle > 0.45) {
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
    boxSize
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
  } else if (compiled.behavior.isDot) {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * 0.48;
    d += " Q " + numFmt(endMidX + endPt.tx * capSpan) + " " + numFmt(endMidY + endPt.ty * capSpan) + " " + numFmt(lastR.x) + " " + numFmt(lastR.y);
  } else {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * 0.35;
    d += " Q " + numFmt(endMidX + endPt.tx * capSpan) + " " + numFmt(endMidY + endPt.ty * capSpan) + " " + numFmt(lastR.x) + " " + numFmt(lastR.y);
  }

  for (let i = smoothR.length - 2; i >= 0; i--) {
    d += " L " + numFmt(smoothR[i].x) + " " + numFmt(smoothR[i].y);
  }

  const firstL = smoothL[0];
  const firstR = smoothR[0];
  const p0 = pts[0];
  const entryRatio = compiled.behavior.isDot ? 0.32 : 0.25;
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

  const kScale = (SLENDER_PHYSICS.kasureAmount || 0.30) / 0.30;
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

      const bx = p1.lx + (p1.rx - p1.lx) * ch.lat;
      const by = p1.ly + (p1.ry - p1.ly) * ch.lat;

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

let cloudySumiTextureCanvas = null;

function getCloudySumiTextureCanvas() {
  if (typeof document === "undefined") return null;
  if (!cloudySumiTextureCanvas) {
    const size = 512;
    cloudySumiTextureCanvas = document.createElement("canvas");
    cloudySumiTextureCanvas.width = size;
    cloudySumiTextureCanvas.height = size;
    const tCtx = cloudySumiTextureCanvas.getContext("2d");

    tCtx.fillStyle = "rgba(28, 24, 20, 0.30)";
    tCtx.fillRect(0, 0, size, size);

    let seed = 12345;
    function rnd() {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    }

    // Multi-scale soft cloudy blotches with subtle tonal contrast
    for (let i = 0; i < 95; i++) {
      const cx = rnd() * size;
      const cy = rnd() * size;
      const rad = 14 + rnd() * 24;
      const grad = tCtx.createRadialGradient(cx, cy, 0, cx, cy, rad);
      const isDark = rnd() > 0.42;
      grad.addColorStop(0, isDark ? "rgba(18, 15, 12, 0.14)" : "rgba(45, 38, 32, 0.08)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      tCtx.fillStyle = grad;
      tCtx.beginPath();
      tCtx.arc(cx, cy, rad, 0, Math.PI * 2);
      tCtx.fill();
    }

    // Random short 4px paper fibers at random angles
    tCtx.lineWidth = 0.8;
    tCtx.lineCap = "round";
    for (let i = 0; i < 260; i++) {
      const fx = rnd() * size;
      const fy = rnd() * size;
      const len = 2.5 + rnd() * 4.5;
      const ang = rnd() * Math.PI * 2;
      tCtx.strokeStyle = rnd() > 0.5 ? "rgba(18, 15, 12, 0.08)" : "rgba(38, 32, 28, 0.05)";
      tCtx.beginPath();
      tCtx.moveTo(fx, fy);
      tCtx.lineTo(fx + Math.cos(ang) * len, fy + Math.sin(ang) * len);
      tCtx.stroke();
    }
  }
  return cloudySumiTextureCanvas;
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
  } else if (compiled.behavior.isDot) {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * 0.48;
    ctx.quadraticCurveTo(
      endMidX + endPt.tx * capSpan,
      endMidY + endPt.ty * capSpan,
      lastR.x,
      lastR.y
    );
  } else {
    const endMidX = (lastL.x + lastR.x) * 0.5;
    const endMidY = (lastL.y + lastR.y) * 0.5;
    const capSpan = Math.hypot(lastL.x - lastR.x, lastL.y - lastR.y) * 0.35;
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
  const entryRatio = compiled.behavior.isDot ? 0.32 : 0.25;
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

  const kScale = (SLENDER_PHYSICS.kasureAmount || 0.30) / 0.30;
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

      const b1x = p1.lx + (p1.rx - p1.lx) * ch.lat;
      const b1y = p1.ly + (p1.ry - p1.ly) * ch.lat;
      const b2x = p2.lx + (p2.rx - p2.lx) * ch.lat;
      const b2y = p2.ly + (p2.ry - p2.ly) * ch.lat;

      ctx.beginPath();
      ctx.moveTo(b1x, b1y);
      ctx.lineTo(b2x, b2y);
      ctx.stroke();
    }
  }

  ctx.restore();
}

function renderInternalSumiToneAndPooling(ctx, compiled, limitIdx, toneMode = "sumi") {
  const pts = compiled.samples;
  const r = compiled.shaftRadius;

  ctx.save();
  ctx.globalCompositeOperation = "source-atop";

  // 1. Procedural 2D cloudy sumi wash & fibrous paper grain
  const W = ctx.canvas.width;
  const H = ctx.canvas.height;
  const tex = getCloudySumiTextureCanvas();
  if (tex) {
    ctx.save();
    ctx.globalAlpha = (toneMode === "dark-sumi") ? 0.08 : 0.12;
    const pat = ctx.createPattern(tex, "repeat");
    if (pat) {
      ctx.fillStyle = pat;
      ctx.fillRect(0, 0, W, H);
    }
    ctx.restore();
  }

  // Tone color definitions
  let heavyC0, heavyC1, heavyC2;
  let lightC0, lightC1, lightC2;
  let poolC0, poolC1, poolC2;

  if (toneMode === "vermilion") {
    heavyC0 = "rgba(115, 14, 12, 0.45)";
    heavyC1 = "rgba(115, 14, 12, 0.20)";
    heavyC2 = "rgba(115, 14, 12, 0)";
    lightC0 = "rgba(145, 24, 20, 0.20)";
    lightC1 = "rgba(145, 24, 20, 0.08)";
    lightC2 = "rgba(145, 24, 20, 0)";
    poolC0  = "rgba(115, 14, 12, 0.14)";
    poolC1  = "rgba(115, 14, 12, 0.06)";
    poolC2  = "rgba(115, 14, 12, 0)";
  } else if (toneMode === "dark-sumi") {
    heavyC0 = "rgba(255, 255, 255, 0.25)";
    heavyC1 = "rgba(255, 255, 255, 0.10)";
    heavyC2 = "rgba(255, 255, 255, 0)";
    lightC0 = "rgba(255, 255, 255, 0.12)";
    lightC1 = "rgba(255, 255, 255, 0.05)";
    lightC2 = "rgba(255, 255, 255, 0)";
    poolC0  = "rgba(255, 255, 255, 0.14)";
    poolC1  = "rgba(255, 255, 255, 0.06)";
    poolC2  = "rgba(255, 255, 255, 0)";
  } else {
    heavyC0 = "rgba(6, 5, 4, 0.45)";
    heavyC1 = "rgba(10, 8, 7, 0.20)";
    heavyC2 = "rgba(10, 8, 7, 0)";
    lightC0 = "rgba(42, 36, 31, 0.20)";
    lightC1 = "rgba(35, 30, 26, 0.08)";
    lightC2 = "rgba(35, 30, 26, 0)";
    poolC0  = "rgba(4, 3, 2, 0.06)";
    poolC1  = "rgba(4, 3, 2, 0.02)";
    poolC2  = "rgba(4, 3, 2, 0)";
  }

  // 2. Soft continuous centerline wash along the stroke spine
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i <= limitIdx; i++) {
    ctx.lineTo(pts[i].x, pts[i].y);
  }
  ctx.lineWidth = r * 1.35;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = lightC1;
  ctx.stroke();

  // 3. Soft radial pause pooling
  // Entry press belly
  const entryIdx = Math.min(limitIdx, Math.floor(pts.length * 0.08));
  const pEntry = pts[entryIdx];
  const p0 = pts[0];
  const entryMidX = (p0.x + pEntry.x) * 0.5;
  const entryMidY = (p0.y + pEntry.y) * 0.5;
  const entryGrad = ctx.createRadialGradient(entryMidX, entryMidY, 0, entryMidX, entryMidY, r * 2.2);
  entryGrad.addColorStop(0, poolC0);
  entryGrad.addColorStop(0.60, poolC1);
  entryGrad.addColorStop(1, poolC2);
  ctx.fillStyle = entryGrad;
  ctx.beginPath();
  ctx.arc(entryMidX, entryMidY, r * 2.2, 0, Math.PI * 2);
  ctx.fill();

  // Corner shoulders
  for (const cf of compiled.cornerFeatures) {
    if (limitIdx >= cf.index) {
      const cp = pts[cf.index];
      const shiftSign = cf.turnSign >= 0 ? 1 : -1;
      const sx = cp.x + cp.nx * shiftSign * (r * 0.25);
      const sy = cp.y + cp.ny * shiftSign * (r * 0.25);
      const cornerGrad = ctx.createRadialGradient(sx, sy, 0, sx, sy, r * 2.2);
      cornerGrad.addColorStop(0, poolC0);
      cornerGrad.addColorStop(0.65, poolC1);
      cornerGrad.addColorStop(1, poolC2);
      ctx.fillStyle = cornerGrad;
      ctx.beginPath();
      ctx.arc(sx, sy, r * 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Hook resting heel
  if (compiled.hookFeature && limitIdx >= compiled.hookFeature.index) {
    const hp = pts[compiled.hookFeature.index];
    const hookGrad = ctx.createRadialGradient(hp.x, hp.y, 0, hp.x, hp.y, r * 2.2);
    hookGrad.addColorStop(0, poolC0);
    hookGrad.addColorStop(0.65, poolC1);
    hookGrad.addColorStop(1, poolC2);
    ctx.fillStyle = hookGrad;
    ctx.beginPath();
    ctx.arc(hp.x, hp.y, r * 2.2, 0, Math.PI * 2);
    ctx.fill();
  }

  // Na wave foot
  if (compiled.behavior.isRightNa) {
    const naIdx = Math.floor(pts.length * 0.68);
    if (limitIdx >= naIdx) {
      const np = pts[naIdx];
      const naGrad = ctx.createRadialGradient(np.x, np.y, 0, np.x, np.y, r * 2.2);
      naGrad.addColorStop(0, poolC0);
      naGrad.addColorStop(0.65, poolC1);
      naGrad.addColorStop(1, poolC2);
      ctx.fillStyle = naGrad;
      ctx.beginPath();
      ctx.arc(np.x, np.y, r * 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.restore();
}

function renderPartialCompiledStroke(targetCtx, compiled, endIdx, options = {}) {
  const pts = compiled.samples;
  if (!pts || endIdx < 1) return;
  const limit = Math.min(pts.length - 1, endIdx);

  const W = targetCtx.canvas.width;
  const H = targetCtx.canvas.height;
  const { bufferCanvas, bufferCtx } = getStrokeBufferCanvas(W, H);
  if (!bufferCanvas || !bufferCtx) return;

  bufferCtx.clearRect(0, 0, W, H);

  // 1. Establish unified binary/alpha stroke silhouette in solid black with micro-bleed shadow
  bufferCtx.save();
  bufferCtx.fillStyle = "#000000";
  bufferCtx.shadowColor = "rgba(20, 16, 13, 0.38)";
  bufferCtx.shadowBlur = 1.8;

  bufferCtx.beginPath();
  traceSmoothStrokeContour(bufferCtx, compiled, limit, false);
  bufferCtx.fill();

  // If long falling sweep, carve kasure and draw feathery bristle hairs
  renderKasureAndFrayedBristles(bufferCtx, compiled, limit);
  bufferCtx.restore();

  const toneMode = options.toneMode || "sumi";
  let fillStyle = "rgba(38, 33, 29, 0.82)";
  let compositeOp = "multiply";

  if (toneMode === "vermilion") {
    fillStyle = "rgba(208, 46, 42, 0.90)";
    compositeOp = "source-over";
  } else if (toneMode === "dark-sumi") {
    fillStyle = "rgba(226, 234, 244, 0.88)";
    compositeOp = "source-over";
  }

  // 2. Fill unified silhouette with base tone via source-in
  bufferCtx.save();
  bufferCtx.globalCompositeOperation = "source-in";
  bufferCtx.fillStyle = fillStyle;
  bufferCtx.fillRect(0, 0, W, H);
  bufferCtx.restore();

  // 3. Layer 2D cloudy wash, paper mottling, and soft radial pooling via source-atop
  renderInternalSumiToneAndPooling(bufferCtx, compiled, limit, toneMode);

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
