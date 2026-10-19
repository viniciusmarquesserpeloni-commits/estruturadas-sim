/* Núcleo: formatação, estado (com persistência local), dados e orquestração dos cálculos.
   Os cálculos pesados rodam num Web Worker (assets/js/worker.js); sem Worker, rodam aqui mesmo. */
(function () {
  "use strict";
  const E = window.Estr;
  const App = (window.App = window.App || {});
  App.E = E;

  /* ---------------- Formatação (mesmo padrão do painel de fundos) ---------------- */
  const NF = {};
  const nf = (d) => NF[d] || (NF[d] = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  App.esc = esc;
  App.fmt = {
    pct(v, d = 2, sign = true) {
      if (v == null || !isFinite(v)) return "—";
      const x = Math.abs(v * 100) < 0.5 * Math.pow(10, -d) ? 0 : v * 100;
      return (sign && x > 0 ? "+" : "") + nf(d).format(x) + "%";
    },
    lvl(v, d = 2) { return v == null || !isFinite(v) ? "—" : nf(d).format(v * 100) + "%"; },
    num(v, d = 2) { return v == null || !isFinite(v) ? "—" : nf(d).format(v); },
    int(v) { return v == null || !isFinite(v) ? "—" : nf(0).format(v); },
    brl(v, d = 2) { return v == null || !isFinite(v) ? "—" : (v < 0 ? "-R$ " : "R$ ") + nf(d).format(Math.abs(v)); },
    date(iso) { if (!iso) return "—"; const [y, m, d] = iso.slice(0, 10).split("-"); return `${d}/${m}/${y}`; },
  };
  /* Valor com cor de sinal (classe pos/neg do tema). */
  App.signed = (v, d = 2) => `<span class="num ${v > 1e-12 ? "pos" : v < -1e-12 ? "neg" : ""}">${App.fmt.pct(v, d)}</span>`;
  /* Lê número digitado em formato brasileiro ("1.234,56") ou internacional. */
  App.parseNum = function (txt) {
    if (txt == null) return null;
    let t = String(txt).trim().replace(/\s|R\$|%/g, "");
    if (!t) return null;
    if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
    const v = Number(t);
    return isFinite(v) ? v : null;
  };

  /* ---------------- Estado ---------------- */
  const store = {
    get(k, d) { try { const v = localStorage.getItem("es:" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("es:" + k, JSON.stringify(v)); } catch (e) { /* armazenamento indisponível */ } },
  };
  App.store = store;
  const DEFAULT_ADV = {
    start: "2010-01-01", adjusted: true, monitoring: "close", extra: 0,
    vol: null, rate: null, q: 0, pricingPaths: 50000, pricingSeed: 42,
    mcMethod: "bootstrap", mcDrift: "historico", mcPaths: 10000, mcBlock: 20, mcSeed: 42,
  };
  function defaults() {
    const s = E.PRESETS.protecao_total.build();
    return {
      ticker: "BBDC4", presetKey: "protecao_total", structure: s,
      term: { mode: "datas", months: 12, du: 252, trade: s.trade_date, expiry: s.expiry_date },
      invested: 30000, costMode: "informado", costInformed: 0,
      expost: { trade: s.trade_date, expiry: s.expiry_date },
      variations: null, adv: Object.assign({}, DEFAULT_ADV), advOpen: false,
    };
  }
  function loadState() {
    const d = defaults(), saved = store.get("state", null);
    if (!saved) return d;
    try {
      const st = Object.assign(d, saved);
      st.adv = Object.assign({}, DEFAULT_ADV, saved.adv || {});
      st.term = Object.assign(defaults().term, saved.term || {});
      st.expost = Object.assign(defaults().expost, saved.expost || {});
      st.structure = E.structure(saved.structure.name, saved.structure.legs, saved.structure);
      return st;
    } catch (e) { return defaults(); }
  }
  App.state = loadState();
  App.csv = null; // série enviada pelo usuário (só na memória)
  const listeners = {};
  App.on = (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); };
  App.emit = (ev, p) => { (listeners[ev] || []).forEach((fn) => fn(p)); };

  /* Atualiza o estado, salva e agenda o recálculo. structural = a tabela de pernas foi substituída. */
  App.update = function (patch, opts = {}) {
    Object.assign(App.state, patch);
    store.set("state", App.state);
    if (opts.structural) App.emit("structure");
    App.recompute();
  };
  /* Substitui a estrutura (preset, JSON importado, solver). */
  App.setStructure = function (s, presetKey, resetMeta = true) {
    const patch = { structure: s, presetKey: presetKey ?? App.state.presetKey, variations: null };
    if (resetMeta) {
      if (s.ticker && !App.csv) patch.ticker = s.ticker;
      patch.costInformed = s.option_cost || 0;
      if (s.trade_date && s.expiry_date) {
        patch.term = Object.assign({}, App.state.term, { mode: "datas", trade: s.trade_date, expiry: s.expiry_date });
        patch.expost = { trade: s.trade_date, expiry: s.expiry_date };
      }
    }
    App.update(patch, { structural: true });
    if (resetMeta) App.emit("params");
  };
  App.reset = () => { store.set("state", null); App.state = defaults(); App.emit("params"); App.emit("structure"); App.recompute(); };

  /* ---------------- Dados ---------------- */
  const getJSON = (url) => fetch(url, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`); return r.json(); });
  App.data = { index: null, cdi: null, prices: {}, error: null };
  App.loadIndex = async function () {
    const [idx, cdi] = await Promise.all([getJSON("data/index.json"), getJSON("data/cdi.json").catch(() => null)]);
    App.data.index = idx;
    App.data.cdi = cdi;
    App.data.byTicker = Object.fromEntries(idx.acoes.map((a) => [a.t, a]));
    return idx;
  };
  App.loadPrices = function (t) {
    const p = App.data.prices;
    if (!p[t]) p[t] = getJSON(`data/precos/${encodeURIComponent(t)}.json`).catch((e) => { delete p[t]; throw e; });
    return p[t];
  };
  /* CSV com Date, Close[, High, Low] (aceita ";" e vírgula decimal, datas DD/MM/AAAA ou AAAA-MM-DD). */
  App.parseCsv = function (text) {
    const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());
    if (lines.length < 3) throw new Error("CSV vazio ou muito curto.");
    const sep = (lines[0].match(/;/g) || []).length > (lines[0].match(/,/g) || []).length ? ";" : ",";
    const head = lines[0].split(sep).map((h) => h.trim().toLowerCase().replace(/"/g, ""));
    const find = (names) => head.findIndex((h) => names.includes(h));
    const iD = find(["date", "data"]), iC = find(["close", "fechamento", "adj close", "preco", "preço"]);
    const iH = find(["high", "maxima", "máxima"]), iL = find(["low", "minima", "mínima"]);
    if (iD < 0 || iC < 0) throw new Error("O CSV precisa das colunas Date e Close (ou Data e Fechamento).");
    const num = (s) => { let t = String(s || "").trim().replace(/"/g, ""); if (sep === ";" || /,\d+$/.test(t)) t = t.replace(/\./g, "").replace(",", "."); return Number(t); };
    const date = (s) => { const t = String(s).trim().replace(/"/g, ""); const m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/); return m ? `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}` : t.slice(0, 10); };
    const rows = lines.slice(1).map((l) => l.split(sep)).map((c) => ({ d: date(c[iD]), c: num(c[iC]), h: iH >= 0 ? num(c[iH]) : NaN, l: iL >= 0 ? num(c[iL]) : NaN }))
      .filter((r) => /^\d{4}-\d{2}-\d{2}$/.test(r.d) && r.c > 0).sort((a, b) => (a.d < b.d ? -1 : a.d > b.d ? 1 : 0));
    const uniq = rows.filter((r, i) => i === rows.length - 1 || rows[i + 1].d !== r.d);
    if (uniq.length < 30) throw new Error("Histórico muito curto (menos de 30 pregões).");
    return { ticker: "CSV", d: uniq.map((r) => r.d), c: uniq.map((r) => r.c), ca: null,
      h: uniq.map((r) => Math.max(r.h > 0 ? r.h : r.c, r.c)), l: uniq.map((r) => Math.min(r.l > 0 ? r.l : r.c, r.c)), hasHL: iH >= 0 && iL >= 0 };
  };

  App.download = function (name, content, mime) {
    const blob = new Blob([content], { type: mime });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  App.toast = function (msg) {
    let t = document.getElementById("toast");
    if (!t) {
      t = document.createElement("div"); t.id = "toast";
      t.style.cssText = "position:fixed;top:16px;left:50%;transform:translateX(-50%);background:#0e2a33;color:#fff;padding:9px 16px;border-radius:8px;font-size:13px;z-index:100;box-shadow:0 6px 20px rgba(0,0,0,.2);transition:opacity .2s";
      t.setAttribute("role", "status"); document.body.appendChild(t);
    }
    t.textContent = msg; t.style.opacity = "1";
    clearTimeout(t._h); t._h = setTimeout(() => { t.style.opacity = "0"; }, 2600);
  };

  /* ---------------- Worker ---------------- */
  let worker = null, seq = 0;
  const pending = new Map();
  const LOCAL = {
    price: (a) => E.priceStructure(a.s, a.sigma, a.r, a.q, a.n, a.paths, a.seed, a.monitoring),
    solve: (a) => E.solveZeroCost(a.s, a.legs, a.param, a.sigma, a.r, a.q, a.n, a.paths, a.seed, a.monitoring, a.bounds, a.target),
    hist: (a) => E.runHistorical(a.s, a.P, a.n, a.cost, a.monitoring, a.extra, a.cdiF),
    mc: (a) => E.runMonteCarlo(a.s, a.P, a.n, a.cost, a.o),
  };
  try {
    const ver = ((document.querySelector('script[src*="core.js"]') || {}).src || "").split("?")[1] || "";
    worker = new Worker("assets/js/worker.js" + (ver ? "?" + ver : ""));
    worker.onmessage = (ev) => { const p = pending.get(ev.data.id); if (!p) return; pending.delete(ev.data.id); ev.data.ok ? p.ok(ev.data.result) : p.fail(new Error(ev.data.error)); };
    worker.onerror = () => { worker = null; pending.forEach((p) => p.retry()); pending.clear(); };
  } catch (e) { worker = null; }
  App.call = function (type, args) {
    const local = () => new Promise((ok, fail) => setTimeout(() => { try { ok(LOCAL[type](args)); } catch (e) { fail(e); } }, 20));
    if (!worker) return local();
    return new Promise((ok, fail) => {
      const id = ++seq;
      pending.set(id, { ok, fail, retry: () => local().then(ok, fail) });
      worker.postMessage({ id, type, args });
    });
  };

  /* ---------------- Orquestração dos cálculos ---------------- */
  const cache = new Map();
  const memo = (key, fn) => {
    if (cache.has(key)) return cache.get(key);
    const p = fn().catch((e) => { cache.delete(key); throw e; });
    cache.set(key, p);
    if (cache.size > 40) cache.delete(cache.keys().next().value);
    return p;
  };
  App.ctx = {};
  let gen = 0, timer = null;
  App.recompute = function (delay = 120) { clearTimeout(timer); timer = setTimeout(run, delay); };

  /* Prazo em pregões conforme o modo escolhido. */
  App.termDays = function (st, dates) {
    const t = st.term;
    if (t.mode === "meses") return { n: Math.max(1, Math.round(t.months * 21)), obs: null };
    if (t.mode === "du") return { n: Math.max(1, Math.round(t.du)), obs: null };
    if (!t.trade || !t.expiry || t.expiry <= t.trade) return { n: 1, obs: null, error: "O vencimento deve ser posterior à contratação." };
    const r = E.termFromDates(t.trade, t.expiry, dates);
    return { n: Math.max(1, r.n), obs: r.obs };
  };

  async function run() {
    const g = ++gen, st = App.state, ctx = (App.ctx = { gen: g, loading: true });
    const live = () => g === gen;
    const push = () => { if (live()) App.emit("results", ctx); };
    try {
      if (!App.data.index) await App.loadIndex();
    } catch (e) { ctx.dataError = "Não foi possível carregar os dados do site (" + e.message + ")."; }
    // Preços
    let raw = null;
    try {
      raw = App.csv || (st.ticker ? await App.loadPrices(st.ticker) : null);
      if (!raw) throw new Error("Escolha uma ação.");
    } catch (e) { ctx.priceError = App.data.byTicker && !App.data.byTicker[st.ticker] ? `Ação ${st.ticker} não está na base do site. Escolha outra na lista ou envie um CSV (Mais opções).` : e.message; }
    if (!live()) return;
    const P = raw ? E.preparePrices(raw, st.adv.adjusted, st.adv.start) : null;
    if (P && P.c.length < 30) { ctx.priceError = "Histórico muito curto no período escolhido."; }
    ctx.raw = raw; ctx.P = P && P.c.length >= 30 ? P : null;
    ctx.ticker = App.csv ? "CSV" : st.ticker;
    const term = App.termDays(st, ctx.P ? ctx.P.d : null);
    ctx.n = term.n; ctx.obs = term.obs; ctx.termError = term.error;
    ctx.histVol = ctx.P ? E.histVol(ctx.P.c) : NaN;
    ctx.sigma = st.adv.vol ?? (isFinite(ctx.histVol) ? ctx.histVol : 0.3);
    const selic = App.data.index ? App.data.index.selic_meta : null;
    ctx.rateAnnual = st.adv.rate ?? (selic ?? 0.10);
    ctx.r = E.annualToContinuous(ctx.rateAnnual);
    const s = st.structure, extra = st.adv.extra || 0;
    ctx.extra = extra;
    const informed = st.costMode === "informado";
    ctx.issues = E.validate(s, informed ? st.costInformed : null);
    push();

    // Custo teórico (sempre que houver opções, para comparação)
    if (!E.hasErrors(ctx.issues) && E.optionLegs(s).length) {
      const a = { s, sigma: ctx.sigma, r: ctx.r, q: st.adv.q, n: ctx.n, paths: st.adv.pricingPaths, seed: st.adv.pricingSeed, monitoring: st.adv.monitoring };
      ctx.theoPending = true; push();
      try { ctx.theo = await memo("price:" + JSON.stringify([s.legs, a.sigma, a.r, a.q, a.n, a.paths, a.seed, a.monitoring]), () => App.call("price", a)); }
      catch (e) { ctx.theoError = e.message; }
      ctx.theoPending = false;
      if (!live()) return;
    }
    ctx.cost = !E.optionLegs(s).length ? 0 : informed ? st.costInformed : ctx.theo ? ctx.theo.net : null;
    ctx.issues = ctx.cost == null ? ctx.issues : E.validate(s, ctx.cost);
    ctx.ok = ctx.cost != null && !E.hasErrors(ctx.issues);
    push();
    if (!ctx.ok || !ctx.P) { ctx.loading = false; push(); return; }

    // Backtests
    const key = JSON.stringify([s.legs, ctx.cost, ctx.ticker, st.adv.adjusted, st.adv.start, ctx.n, st.adv.monitoring, extra, ctx.rateAnnual, App.csv ? App.csv.d.length : 0]);
    ctx.cdiF = E.cdiFactor(ctx.P.d, App.data.cdi && App.data.cdi.d.length ? App.data.cdi : null, ctx.rateAnnual);
    ctx.histPending = true; push();
    try {
      if (ctx.n >= ctx.P.c.length) throw new Error(`Histórico insuficiente (${ctx.P.c.length} pregões) para janelas de ${ctx.n} pregões.`);
      ctx.hist = await memo("hist:" + key, () => App.call("hist", { s, P: ctx.P, n: ctx.n, cost: ctx.cost, monitoring: st.adv.monitoring, extra, cdiF: ctx.cdiF }));
    } catch (e) { ctx.histError = e.message; }
    ctx.histPending = false;
    if (!live()) return;
    ctx.mcPending = true; push();
    const o = { method: st.adv.mcMethod, nPaths: st.adv.mcPaths, block: st.adv.mcBlock, drift: st.adv.mcDrift, cdiAnnual: ctx.rateAnnual, seed: st.adv.mcSeed, monitoring: st.adv.monitoring, extra };
    try { ctx.mc = await memo("mc:" + key + JSON.stringify(o), () => App.call("mc", { s, P: ctx.P, n: ctx.n, cost: ctx.cost, o })); }
    catch (e) { ctx.mcError = e.message; }
    ctx.mcPending = false; ctx.loading = false;
    push();
  }

  /* Rótulos de prazo/estrutura para textos. */
  App.termText = (ctx) => `${App.fmt.int(ctx.n)} pregões (≈ ${App.fmt.num(ctx.n / 21, 1)} meses)` + (ctx.obs ? ` · apuração em ${App.fmt.date(ctx.obs)}` : "");
})();
