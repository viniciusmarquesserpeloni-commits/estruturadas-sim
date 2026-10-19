/* Motor de payoff — porta de estruturadas/legs.py.
   Convenções: valor inicial S0 = 1; strikes e barreiras em fração de S0 (1.041 = 104,10%).
   Barreira de alta é tocada quando o preço monitorado fica >= barreira; de baixa, <= barreira.
   Funciona no navegador (window.Estr) e no Node (globalThis.Estr), para os testes. */
(function (root) {
  "use strict";
  const E = (root.Estr = root.Estr || {});
  const EPS = 1e-12;

  E.KINDS = ["stock", "call", "put"];
  E.BARRIERS = ["none", "up_in", "up_out", "down_in", "down_out"];
  E.KIND_LABELS = { stock: "Ação", call: "Call", put: "Put" };
  E.BARRIER_LABELS = {
    none: "Não se aplica", up_in: "Knock Up and In", up_out: "Knock Up and Out",
    down_in: "Knock Down and In", down_out: "Knock Down and Out",
  };
  E.MONITORING_LABELS = { close: "Fechamento diário", intraday: "Intradiário" };

  /* ---------------- Formatação pt-BR (usada nos textos do motor) ---------------- */
  const NF = {};
  const nf = (d) => NF[d] || (NF[d] = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }));
  E.fmtNum = (x, d = 2) => (x == null || !isFinite(x) ? "—" : nf(d).format(x));
  E.fmtPct = (x, d = 2, sign = false) => {
    if (x == null || !isFinite(x)) return "—";
    const v = Math.abs(x * 100) < 0.5 * Math.pow(10, -d) ? 0 : x * 100;
    return (sign && v > 0 ? "+" : "") + nf(d).format(v) + "%";
  };
  E.fmtBrl = (x, d = 2) => (x == null || !isFinite(x) ? "—" : (x < 0 ? "-R$ " : "R$ ") + nf(d).format(Math.abs(x)));

  /* ---------------- Pernas e estruturas ---------------- */
  const num = (v) => (v === null || v === undefined || v === "" || !isFinite(+v) ? null : +v);

  E.leg = function (kind, position = 1, strike = null, barrier = "none", level = null, ratio = 1) {
    return E.normalizeLeg({ kind, position, strike, barrier, level, ratio });
  };
  E.normalizeLeg = function (l) {
    const kind = String(l.kind || "").toLowerCase();
    if (!E.KINDS.includes(kind)) throw new Error(`Tipo de perna inválido: ${l.kind}`);
    let barrier = String(l.barrier || "none").toLowerCase();
    if (!E.BARRIERS.includes(barrier)) throw new Error(`Tipo de barreira inválido: ${l.barrier}`);
    const out = { kind, position: +l.position < 0 ? -1 : 1, strike: num(l.strike), barrier, level: num(l.level), ratio: num(l.ratio) ?? 1 };
    if (kind === "stock") { out.strike = null; out.barrier = "none"; out.level = null; }
    if (out.barrier === "none") out.level = null;
    return out;
  };
  E.structure = function (name, legs, extra = {}) {
    const out = Object.assign({ ticker: null, trade_date: null, expiry_date: null, option_cost: 0, preset: null, notes: "" }, extra);
    out.name = name;
    out.legs = legs.map(E.normalizeLeg);
    return out;
  };
  E.copyStructure = (s, changes = {}) => Object.assign({}, s, { legs: s.legs.map((l) => Object.assign({}, l)) }, changes);

  E.isOption = (l) => l.kind !== "stock";
  E.hasBarrier = (l) => l.barrier !== "none";
  E.barrierDir = (l) => (E.hasBarrier(l) ? l.barrier.split("_")[0] : null);
  E.knock = (l) => (E.hasBarrier(l) ? l.barrier.split("_")[1] : null);
  E.hasStock = (s) => s.legs.some((l) => l.kind === "stock");
  E.optionLegs = (s) => s.legs.filter(E.isOption);

  const roundLevel = (x) => Math.round(x * 1e10) / 1e10;
  E.legEventKey = (l) => (E.hasBarrier(l) && l.level != null ? `${E.barrierDir(l)}:${roundLevel(l.level)}` : null);
  /* Eventos de barreira distintos (direção, nível), ordenados como no Python. */
  E.events = function (s) {
    const seen = new Map();
    s.legs.forEach((l) => { const k = E.legEventKey(l); if (k && !seen.has(k)) seen.set(k, { key: k, dir: E.barrierDir(l), level: roundLevel(l.level) }); });
    return [...seen.values()].sort((a, b) => (a.dir < b.dir ? -1 : a.dir > b.dir ? 1 : a.level - b.level));
  };
  E.strikes = (s) => [...new Set(E.optionLegs(s).filter((l) => l.strike != null).map((l) => l.strike))].sort((a, b) => a - b);
  E.eventLabel = (ev) => `${ev.dir === "up" ? "Alta" : "Baixa"} ${E.fmtPct(ev.level)}`;

  E.legLabel = function (l) {
    const pos = l.position > 0 ? "comprada" : "vendida";
    if (l.kind === "stock") return `Ação ${pos}`;
    let t = `${E.KIND_LABELS[l.kind]} ${pos} K=${E.fmtPct(l.strike)}`;
    if (E.hasBarrier(l)) t += ` (${E.BARRIER_LABELS[l.barrier]} ${E.fmtPct(l.level)})`;
    if (Math.abs(l.ratio - 1) > 1e-12) t += ` ×${E.fmtNum(l.ratio, 2)}`;
    return t;
  };

  /* ---------------- Avaliação em caminhos ---------------- */
  E.shiftedLevel = (ev, shift) => (ev.dir === "up" ? ev.level * Math.exp(-shift) : ev.level * Math.exp(shift));

  /* Resumo suficiente de cada caminho: S_T, máximo monitorado (alta) e mínimo monitorado (baixa).
     rows: array de caminhos (cada um um array de N preços relativos a S0). */
  E.summarizePaths = function (rows, highRows, lowRows, monitoring = "close") {
    const n = rows.length;
    const sT = new Float64Array(n), runMax = new Float64Array(n), runMin = new Float64Array(n);
    const intra = monitoring === "intraday";
    for (let i = 0; i < n; i++) {
      const c = rows[i], h = intra && highRows ? highRows[i] : null, lo = intra && lowRows ? lowRows[i] : null;
      let mx = -Infinity, mn = Infinity;
      for (let j = 0; j < c.length; j++) {
        const up = h ? Math.max(h[j], c[j]) : c[j];
        const dn = lo ? Math.min(lo[j], c[j]) : c[j];
        if (up > mx) mx = up;
        if (dn < mn) mn = dn;
      }
      sT[i] = c[c.length - 1]; runMax[i] = mx; runMin[i] = mn;
    }
    return { sT, runMax, runMin };
  };

  E.eventHits = function (sum, events, shift = 0) {
    const n = sum.sT.length, hits = {};
    events.forEach((ev) => {
      const lvl = E.shiftedLevel(ev, shift), a = new Uint8Array(n);
      if (ev.dir === "up") for (let i = 0; i < n; i++) a[i] = sum.runMax[i] >= lvl - EPS ? 1 : 0;
      else for (let i = 0; i < n; i++) a[i] = sum.runMin[i] <= lvl + EPS ? 1 : 0;
      hits[ev.key] = a;
    });
    return hits;
  };

  const rawPayoff = (l, S) => (l.kind === "stock" ? S : l.kind === "call" ? Math.max(S - l.strike, 0) : Math.max(l.strike - S, 0));
  E.rawPayoff = rawPayoff;
  const isActive = (l, hit) => (!E.hasBarrier(l) ? 1 : E.knock(l) === "in" ? hit : 1 - hit);

  E.evaluateSummary = function (s, sum, shift = 0) {
    const evs = E.events(s), hits = E.eventHits(sum, evs, shift), n = sum.sT.length;
    const payoff = new Float64Array(n), anyHit = new Uint8Array(n);
    s.legs.forEach((l) => {
      const k = E.legEventKey(l), h = k ? hits[k] : null, w = l.position * l.ratio;
      for (let i = 0; i < n; i++) payoff[i] += w * rawPayoff(l, sum.sT[i]) * isActive(l, h ? h[i] : 0);
    });
    evs.forEach((ev) => { const h = hits[ev.key]; for (let i = 0; i < n; i++) if (h[i]) anyHit[i] = 1; });
    return { payoff, sT: sum.sT, hits, events: evs, anyHit };
  };
  E.evaluatePaths = (s, rows, highRows, lowRows, monitoring = "close", shift = 0) =>
    E.evaluateSummary(s, E.summarizePaths(rows, highRows, lowRows, monitoring), shift);

  /* Índice do primeiro dia em que o evento foi tocado num único caminho; -1 se nunca. */
  E.firstHitIndex = function (close, ev, high, low, monitoring = "close") {
    for (let j = 0; j < close.length; j++) {
      if (ev.dir === "up") {
        const v = monitoring === "intraday" && high ? Math.max(high[j], close[j]) : close[j];
        if (v >= ev.level - EPS) return j;
      } else {
        const v = monitoring === "intraday" && low ? Math.min(low[j], close[j]) : close[j];
        if (v <= ev.level + EPS) return j;
      }
    }
    return -1;
  };

  /* ---------------- Retornos ---------------- */
  E.returnBase = function (cost, hasStock) {
    if (hasStock) { if (1 + cost <= 0) throw new Error("Custo das opções implica investimento não positivo."); return 1 + cost; }
    if (!(cost > 0)) throw new Error("Estruturas só com opções exigem custo líquido positivo.");
    return cost;
  };
  /* Retorno sobre o capital investido: com ação, base = 1 + c; só opções, base = c. */
  E.returnsFromPayoff = function (payoff, cost, hasStock, extra = 0) {
    const base = E.returnBase(cost, hasStock);
    if (typeof payoff === "number") return payoff / base - 1 - extra;
    const out = new Float64Array(payoff.length);
    for (let i = 0; i < payoff.length; i++) out[i] = payoff[i] / base - 1 - extra;
    return out;
  };

  /* ---------------- Perfil no vencimento ---------------- */
  /* branch "none": nenhuma barreira tocada (S_T precisa estar do lado de dentro; senão NaN);
     branch "all": todas tocadas em algum momento. */
  E.expiryPayoff = function (s, sTs, branch = "none") {
    const evs = E.events(s), hit = branch === "all" ? 1 : 0;
    const out = new Float64Array(sTs.length);
    for (let i = 0; i < sTs.length; i++) {
      const S = sTs[i];
      let feasible = true;
      if (branch === "none") evs.forEach((ev) => { if (ev.dir === "up" ? !(S < ev.level) : !(S > ev.level)) feasible = false; });
      if (!feasible) { out[i] = NaN; continue; }
      let p = 0;
      s.legs.forEach((l) => { p += l.position * l.ratio * rawPayoff(l, S) * isActive(l, hit); });
      out[i] = p;
    }
    return out;
  };
  E.payoffAt = (s, S, branch = "none") => E.expiryPayoff(s, [S], branch)[0];

  E.profileSummary = function (s, cost = 0) {
    const levels = [1].concat(E.strikes(s), E.events(s).map((e) => e.level));
    const top = 3 * Math.max(...levels);
    const grid = [];
    for (let i = 0; i <= 6000; i++) grid.push((top * i) / 6000);
    levels.forEach((l) => { grid.push(l); if (l - 1e-9 >= 0) grid.push(l - 1e-9); });
    const branches = E.events(s).length ? ["none", "all"] : ["none"];
    let gainUnl = false, lossUnl = false, pmax = -Infinity, pmin = Infinity;
    branches.forEach((b) => {
      const p = E.expiryPayoff(s, grid, b);
      p.forEach((v) => { if (isFinite(v)) { if (v > pmax) pmax = v; if (v < pmin) pmin = v; } });
      const far = E.expiryPayoff(s, [top * 10, top * 20], b);
      if (isFinite(far[0]) && isFinite(far[1])) {
        const slope = far[1] - far[0];
        if (slope > 1e-9) gainUnl = true;
        if (slope < -1e-9) lossUnl = true;
      }
    });
    const out = { payoff_max: gainUnl ? null : pmax, payoff_min: lossUnl ? null : pmin, gain_unlimited: gainUnl, loss_unlimited: lossUnl, return_max: null, return_min: null };
    try {
      if (E.hasStock(s) || cost > 0) {
        if (!gainUnl) out.return_max = E.returnsFromPayoff(pmax, cost, E.hasStock(s));
        if (!lossUnl) out.return_min = E.returnsFromPayoff(pmin, cost, E.hasStock(s));
      }
    } catch (e) { /* custo inválido: retornos ficam null */ }
    return out;
  };

  /* ---------------- Validação ---------------- */
  E.validate = function (s, cost) {
    const issues = [];
    if (!s.legs.length) return [{ level: "erro", msg: "A estrutura não tem nenhuma perna." }];
    s.legs.forEach((l, k) => {
      const i = k + 1;
      if (!(l.ratio > 0)) issues.push({ level: "erro", msg: `Perna ${i}: a proporção deve ser maior que zero.` });
      if (E.isOption(l)) {
        if (l.strike == null || !(l.strike > 0)) issues.push({ level: "erro", msg: `Perna ${i}: informe um preço de exercício válido.` });
        if (E.hasBarrier(l)) {
          const b = l.level;
          if (b == null || !(b > 0)) issues.push({ level: "erro", msg: `Perna ${i}: informe o valor da barreira.` });
          else if (E.barrierDir(l) === "up" && b <= 1) issues.push({ level: "erro", msg: `Perna ${i}: barreira de alta deve ser maior que 100% do valor inicial.` });
          else if (E.barrierDir(l) === "down" && b >= 1) issues.push({ level: "erro", msg: `Perna ${i}: barreira de baixa deve ser menor que 100% do valor inicial.` });
        }
      }
    });
    const stockRatio = s.legs.filter((l) => l.kind === "stock").reduce((a, l) => a + l.ratio * l.position, 0);
    if (stockRatio < 0) issues.push({ level: "aviso", msg: "Ação vendida a descoberto: o simulador trata o retorno sobre o valor inicial da ação." });
    if (!E.hasStock(s) && cost != null && !(cost > 0))
      issues.push({ level: "erro", msg: "Estruturas só com opções exigem custo líquido positivo (débito) para calcular o retorno." });
    if (!issues.some((x) => x.level === "erro") && E.profileSummary(s).loss_unlimited)
      issues.push({ level: "aviso", msg: "Perda máxima ILIMITADA na alta (há calls vendidas sem cobertura)." });
    return issues;
  };
  E.hasErrors = (issues) => issues.some((x) => x.level === "erro");

  /* ---------------- JSON (mesmo formato do estruturadas/io.py) ---------------- */
  const KIND_ALIASES = { stock: "stock", call: "call", put: "put", "ação": "stock", acao: "stock" };
  const BARRIER_ALIASES = Object.assign({}, ...E.BARRIERS.map((b) => ({ [b]: b })),
    ...Object.entries(E.BARRIER_LABELS).map(([k, v]) => ({ [v.toLowerCase()]: k })));
  const position = (v) => {
    if (typeof v === "string") {
      const t = v.trim().toLowerCase();
      if (["comprada", "compra", "long", "+1", "1"].includes(t)) return 1;
      if (["vendida", "venda", "short", "-1"].includes(t)) return -1;
      throw new Error(`Posição inválida: ${v}`);
    }
    return +v >= 0 ? 1 : -1;
  };
  E.toJSON = function (s) {
    return {
      formato: "estruturadas-sim/v1", nome: s.name, ticker: s.ticker, data_contratacao: s.trade_date,
      data_vencimento: s.expiry_date, custo_opcoes: s.option_cost, preset: s.preset, observacoes: s.notes,
      pernas: s.legs.map((l) => (l.kind === "stock"
        ? { tipo: l.kind, posicao: l.position > 0 ? "comprada" : "vendida", proporcao: l.ratio }
        : { tipo: l.kind, posicao: l.position > 0 ? "comprada" : "vendida", proporcao: l.ratio, strike: l.strike, barreira_tipo: l.barrier, barreira: l.level })),
    };
  };
  E.fromJSON = function (d) {
    if (typeof d === "string") d = JSON.parse(d);
    if (!d || !Array.isArray(d.pernas)) throw new Error("JSON inválido: campo 'pernas' ausente.");
    const legs = d.pernas.map((p) => {
      const kind = KIND_ALIASES[String(p.tipo ?? p.kind ?? "").trim().toLowerCase()];
      if (!kind) throw new Error(`Tipo de perna inválido: ${p.tipo}`);
      const barrier = BARRIER_ALIASES[String(p.barreira_tipo ?? p.barrier ?? "none").trim().toLowerCase()];
      if (!barrier) throw new Error(`Tipo de barreira inválido: ${p.barreira_tipo}`);
      return { kind, position: position(p.posicao ?? p.position ?? 1), strike: p.strike, barrier, level: p.barreira ?? p.barrier_level, ratio: p.proporcao ?? p.ratio ?? 1 };
    });
    return E.structure(d.nome || "Estrutura importada", legs, {
      ticker: d.ticker || null, trade_date: d.data_contratacao || null, expiry_date: d.data_vencimento || null,
      option_cost: +(d.custo_opcoes || 0), preset: d.preset || null, notes: d.observacoes || "",
    });
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
