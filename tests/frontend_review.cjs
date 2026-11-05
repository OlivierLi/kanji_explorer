const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() { this.children = []; this.handlers = {}; this.value = ''; this.style = {}; this.classList = {add(){}, remove(){}}; }
  set innerHTML(v) { this.html = v; this.children = []; }
  get innerHTML() { return this.html; }
  appendChild(v) { this.children.push(v); }
  addEventListener(type, fn) { this.handlers[type] = fn; }
  setAttribute() {}
}
const elements = new Map();
for (const id of ['breadcrumbsTrail','btnHistoryBack','btnHistoryForward','resultsGrid', 'filterHierarchy','filterCategory', 'attrCharCodepoint','attrCodepoint','attrTierBadge','attrStrokesRadical','attrOnReadings','attrKunReadings','attrBadges','attrDictCodes','attrEquivalents']) elements.set(id,new Element());
const context = vm.createContext({console:{warn(){}}, URLSearchParams, AbortController, setTimeout, clearTimeout, document:{getElementById:id=>elements.get(id)||null, createElement:()=>new Element(),querySelectorAll:()=>[], addEventListener(){}}, window:{}, localStorage:{getItem:()=>null}});
const run = code => vm.runInContext(code, context);
run(fs.readFileSync('static/app.js','utf8'));
run(`globalThis.actualWords=loadWordsForCurrentKanji;
for (const name of ['renderFindChips','updateLockControllerUI','resetHud','renderCanvas','renderStructureSelector','renderIdsTokens','renderRecursiveTree','loadWordsForCurrentKanji']) globalThis[name]=()=>{};
globalThis.actualFind=executeFindSearch; executeFindSearch=()=>{};
globalThis.rendered=null; renderFindResults=(results, keywords)=>{rendered={results,keywords}};
globalThis.summary=null; updateResultsSummary=(...counts)=>{summary=counts};`);
let queue=[];
context.fetch = (url, options) => new Promise((resolve,reject)=>queue.push({resolve,reject,url,signal:options?.signal}));
const data = char => ({meta:{char}, alternatives:[], visual:{}});
const ok = value => ({ok:true,json:async()=>value});
const flush = async()=>{await Promise.resolve();await Promise.resolve();};
(async()=>{
  const slower=run(`inspectCharacter('日')`);const slowerResponse=queue.shift();
  const faster=run(`inspectCharacter('月')`);queue.shift().resolve(ok(data('月')));await faster;
  slowerResponse.resolve(ok(data('日')));await slower;assert.equal(run('state.currentChar'),'月');
  // The newer fetch wins, even when older JSON resolves last.
  let resolveJson;
  const old=run(`inspectCharacter('日')`);
  queue.shift().resolve({ok:true,json:()=>new Promise(resolve=>resolveJson=resolve)});await flush();
  const latest=run(`inspectCharacter('月')`);queue.shift().resolve(ok(data('月')));await latest;
  resolveJson(data('日'));await old;assert.equal(run('state.currentChar'),'月');
  // Alternative requests and stale failures must not replace a newer selection.
  const alt=run(`inspectCharacter('月',false,'⿴冂二')`);
  const next=run(`inspectCharacter('木')`);const stale=queue.shift();queue.shift().resolve(ok(data('木')));await next;stale.reject(Error('offline'));await alt;assert.equal(run('state.currentChar'),'木');
  // Back/Forward/breadcrumb handlers keep the controls and active entry in sync.
  run(`state.history=['中','日'];state.historyIndex=1;initEventListeners();updateBreadcrumbsUI()`);
  elements.get('btnHistoryBack').handlers.click();assert.equal(elements.get('btnHistoryForward').disabled,false);assert.equal(elements.get('btnHistoryBack').disabled,true);queue.shift().resolve(ok(data('中')));await flush();
  elements.get('btnHistoryForward').handlers.click();assert.equal(elements.get('btnHistoryForward').disabled,true);queue.shift().resolve(ok(data('日')));await flush();
  elements.get('breadcrumbsTrail').children[0].handlers.click();assert.equal(run('state.historyIndex'),0);assert.match(elements.get('breadcrumbsTrail').children[0].className,/active/);queue.shift().resolve(ok(data('中')));await flush();
  for (const [history, word, index] of [[['中','日'],'中国',2],[['日','中'],'中国',1],[['日'],'日日国',0]]) {
    context.historyFixture=history;context.wordFixture=word;
    const p=run(`state.history=historyFixture;state.historyIndex=historyFixture.length-1;inspectCharacter(wordFixture)`);
    assert.equal(run('state.historyIndex'),index);assert.equal(run('state.history[state.historyIndex+1]'),'国');queue.shift().resolve(ok(data(Array.from(word)[0])));await p;
  }
  // Both ordinary and formerly embedded-preset failures show unknown facts.
  for (const char of ['一','蛍','𭕄']) {
    const p=run(`inspectCharacter('${char}')`);queue.shift().resolve({ok:false});await p;
    assert.equal(run('state.charData.meta.stroke_count'),null);assert.equal(elements.get('attrTierBadge').textContent,'情報取得不可');assert.match(elements.get('attrStrokesRadical').textContent,/画数未詳/);assert.equal(run('state.charData.alternatives.length'),0);
  }
  for (const query of ['U+4E00','4E00','&CDP-895F;','CDP-8BD9','⿰木木']) {
    context.failedQuery=query;
    const p=run('inspectCharacter(failedQuery)');queue.shift().resolve({ok:false});await p;
    assert.equal(elements.get('attrCodepoint').textContent,'未詳');
  }
  for (const query of ['U+41','u2d544','U+110000','U+ZZZZ','0x110000','&U-i003+2D928;','&U+4E06;',"&M-12345';",'&A-IWDSU+201A2;']) {
    context.notation=query;
    const p=run('inspectCharacter(notation)');const response=queue.shift();
    assert.equal(new URLSearchParams(response.url.split('?')[1]).get('q'),query);
    response.resolve({ok:false});await p;
  }
  // Entity/codepoint helpers and history normalization after canonical resolution.
  assert.equal(run(`getCodepointHex('u2d544')`),'U+2D544');
  assert.equal(run(`getCodepointHex('4E00')`),'U+4E00');
  assert.equal(run(`getCodepointHex('CDP-8BD9')`),'CDP-8BD9');
  assert.equal(run(`getCodepointHex('&U-i003+2D928;')`),'U-i003+2D928');
  assert.match(run(`renderGlyphHTML('CDP-8BD9')`),/\/api\/glyph\?c=%26CDP-8BD9%3B/);
  run(`state.history=['中'];state.historyIndex=0`);
  const cpResolve=run(`inspectCharacter('U+86CD')`);queue.shift().resolve(ok(data('蛍')));await cpResolve;
  assert.deepEqual(Array.from(run('state.history')),['中','蛍']);assert.equal(run('state.historyIndex'),1);
  const cpDedup=run(`inspectCharacter('U+86CD')`);queue.shift().resolve(ok(data('蛍')));await cpDedup;
  assert.deepEqual(Array.from(run('state.history')),['中','蛍']);assert.equal(run('state.historyIndex'),1);
  // Failed /api/char requests must not overwrite findChips or cascade find/words searches.
  run(`state.findChips=new Set(['蛍']);globalThis.findCalls=0;globalThis.wordsCalls=0;executeFindSearch=()=>{globalThis.findCalls++};loadWordsForCurrentKanji=()=>{globalThis.wordsCalls++}`);
  const failedNotation=run(`inspectCharacter('U+110000')`);queue.shift().resolve({ok:false});await failedNotation;
  assert.deepEqual(Array.from(run('state.findChips')),['蛍']);assert.equal(run('globalThis.findCalls'),0);assert.equal(run('globalThis.wordsCalls'),0);
  run(`executeFindSearch=()=>{};loadWordsForCurrentKanji=()=>{}`);
  const failed=run(`inspectCharacter('月')`);queue.shift().reject(Error('offline'));await failed;assert.equal(run('state.charData.unavailable'),true);
  // Reverse lookup owns an independent generation, including delayed JSON and clear.
  run(`state.findChips=new Set(['木'])`);const first=run('actualFind()');let resolveFindJson;queue.shift().resolve({ok:true,json:()=>new Promise(r=>resolveFindJson=r)});await flush();
  run(`state.findChips=new Set(['水'])`);elements.get('filterHierarchy').value='direct';const second=run('actualFind()');queue.shift().resolve(ok({results:[{char:'河'}],total:1,direct_total:1,indirect_total:0}));await second;
  resolveFindJson({results:[{char:'林'}],total:4});await first;assert.equal(run('rendered.keywords[0]'),'水');assert.equal(run('rendered.results[0].char'),'河');assert.equal(run('summary[0]'),1);
  // A filter-only change supersedes pending work; stale HTTP failures stay silent.
  const obsoleteFilter=run('actualFind()');const obsoleteResponse=queue.shift();
  elements.get('filterCategory').value='common';const filtered=run('actualFind()');queue.shift().resolve(ok({results:[{char:'海'}],total:2,direct_total:1,indirect_total:1}));await filtered;
  obsoleteResponse.resolve({ok:false});await obsoleteFilter;assert.equal(run('rendered.results[0].char'),'海');assert.equal(run('summary[0]'),2);
  const pending=run('actualFind()');run(`executeFindSearch=actualFind;clearFindChips()`);queue.shift().reject(Error('offline'));await pending;assert.match(elements.get('resultsGrid').innerHTML,/部品を追加/);assert.equal(run('summary[0]'),0);
  // Current failures explicitly report unavailable results and unknown counts.
  for (const networkFailure of [false, true]) {
    run(`state.findChips=new Set(['木'])`);
    const unavailable=run('actualFind()');const response=queue.shift();
    if (networkFailure) response.reject(Error('offline'));else response.resolve({ok:false});
    await unavailable;
    assert.match(elements.get('resultsGrid').textContent,/取得できませんでした/);
    assert.deepEqual(Array.from(run('summary')),['未詳','未詳','未詳']);
  }
  // Words share the same request-ownership contract as character and find panels.
  for (const id of ['wordsGrid','wordsTotalBadge','wordsTotalCount','wordsTopCount','wordsHighCount','wordsModeBadge']) elements.set(id,new Element());
  run(`globalThis.wordRender=null;renderWordsGrid=(results,char)=>{wordRender={results,char}}`);
  const words = (char,total) => ({results:[{lemma:char}],total,summary:{top:total,high:0,direct:total}});
  for (const change of ['character','filter']) {
    run(`state.currentChar='日'`);
    const oldWords=run('actualWords()');let resolveOldJson;
    const oldResponse=queue.shift();oldResponse.resolve({ok:true,json:()=>new Promise(r=>resolveOldJson=r)});await flush();
    if (change==='character') run(`state.currentChar='月'`);
    else run(`state.wordsFilter.keyword='新'`);
    const newWords=run('actualWords()');assert.equal(oldResponse.signal.aborted,true);queue.shift().resolve(ok(words('新',2)));await newWords;
    resolveOldJson(words('旧',9));await oldWords;
    assert.equal(run('wordRender.results[0].lemma'),'新');
    assert.equal(elements.get('wordsTotalCount').textContent,2);
  }
  const obsoleteWords=run('actualWords()');const obsoleteWordResponse=queue.shift();
  const currentWords=run('actualWords()');queue.shift().resolve(ok(words('新',3)));await currentWords;
  obsoleteWordResponse.reject(Error('offline'));await obsoleteWords;
  assert.equal(elements.get('wordsTotalCount').textContent,3);
  assert.equal(run('state.wordsData.total'),3);
  // Independent panel scopes must not cancel one another.
  const concurrentFind=run('actualFind()');const findResponse=queue.shift();
  const concurrentWords=run('actualWords()');const wordsResponse=queue.shift();
  assert.equal(findResponse.signal.aborted,false);
  wordsResponse.resolve(ok(words('同時',4)));await concurrentWords;
  findResponse.resolve(ok({results:[{char:'林'}],total:1,direct_total:1,indirect_total:0}));await concurrentFind;
  assert.equal(run('rendered.results[0].char'),'林');
  const unavailableWords=run('actualWords()');queue.shift().resolve({ok:false});await unavailableWords;
  assert.equal(run('state.wordsData'),null);
  assert.equal(elements.get('wordsTotalCount').textContent,'未詳');
  assert.equal(elements.get('wordsModeBadge').style.display,'none');
  assert.match(elements.get('wordsGrid').innerHTML,/失敗/);
  console.log('Frontend review regressions passed');
})().catch(error=>{console.error(error);process.exitCode=1});
