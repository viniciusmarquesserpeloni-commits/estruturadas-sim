// Testes do motor JS (node --test tests/js). Compara com resultados do motor Python
// (tests/js/fixtures.json, gerado por scripts/make_js_fixtures.py) e repete os casos das lâminas.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
for (const f of ["legs", "presets", "pricing", "backtest", "early"]) require(`../../site/assets/js/engine/${f}.js`);
const E = globalThis.Estr;
const FX = JSON.parse(readFileSync(new URL("./fixtures.json", import.meta.url), "utf-8"));

const close = (a, b, tol = 1e-10, msg = "") => {
  if (a == null || b == null || Number.isNaN(a) || Number.isNaN(b)) {
    assert.ok((a == null || Number.isNaN(a)) && (b == null || Number.isNaN(b)), `${msg}: ${a} vs ${b}`);
    return;
  }
  assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), `${msg}: ${a} vs ${b}`);
};
const closeArr = (a, b, tol, msg) => { assert.equal(a.length, b.length, msg + " (tamanho)"); for (let i = 0; i < b.length; i++) close(a[i], b[i], tol, `${msg}[${i}]`); };
const linear = (finals, n = 5) => finals.map((f) => Array.from({ length: n }, (_, j) => 1 + (f - 1) * (j + 1) / n));
const ret = (s, rows, cost = 0, hi, lo, mon = "close") => Array.from(E.returnsFromPayoff(E.evaluatePaths(s, rows, hi, lo, mon).payoff, cost, E.hasStock(s)));

test("casos das lâminas (mesmos do pytest)", () => {
  closeArr(ret(E.PRESETS.booster.build(), linear([1.10, 1.30, 0.90])), [0.20, 0.25, -0.10], 1e-12, "booster");
  closeArr(ret(E.PRESETS.collar.build(), linear([0.80, 1.10, 1.30])), [0, 0.10, 0.15], 1e-12, "collar");
  const cki = E.PRESETS.collar_ki.build();
  closeArr(ret(cki, [[1.10, 1.43, 1.30, 1.50], [1.10, 1.42, 1.30, 1.40], [0.95, 1.20, 0.90, 0.80]]), [0.13, 0.40, 0], 1e-12, "collar KI");
  const fko = E.PRESETS.fko.build();
  closeArr(ret(fko, linear([0.75, 0.95, 1.10, 1.25, 1.60])), [0.1, 0.1, 0.1, 0.1, 0.1], 1e-12, "FKO sem toque");
  closeArr(ret(fko, [0.75, 0.95, 1.6].map((f) => [0.65, f])), [-0.25, -0.05, 0.6], 1e-12, "FKO com toque");
  const pt = E.PRESETS.protecao_total.build();
  closeArr(ret(pt, linear([0.80, 1.00, 1.04, 1.28, 1.38])), [0.041, 0.041, 0.061, 0.42, 0.57], 1e-12, "Proteção Total");
  closeArr(ret(pt, [0.8, 1.0, 1.28].map((f) => [1.40, f])), [0.041, 0.041, 0.041], 1e-12, "Proteção Total com toque");
});

test("monitoramento intradiário usa máxima/mínima", () => {
  const s = E.PRESETS.collar_ki.build();
  const c = [[1.10, 1.40, 1.35]], h = [[1.12, 1.45, 1.37]], l = [[1.08, 1.38, 1.33]];
  assert.equal(E.evaluatePaths(s, c, h, l, "close").anyHit[0], 0);
  assert.equal(E.evaluatePaths(s, c, h, l, "intraday").anyHit[0], 1);
  close(ret(s, c, 0, h, l, "intraday")[0], 0.13, 1e-12, "intradiário");
});

test("presets: payoff, perfil e quadro iguais ao Python", () => {
  for (const [key, fx] of Object.entries(FX.presets)) {
    const s = E.fromJSON(fx.json);
    closeArr(E.evaluatePaths(s, fx.close, fx.high, fx.low, "close").payoff, fx.payoff_close, 1e-10, key + " close");
    closeArr(E.evaluatePaths(s, fx.close, fx.high, fx.low, "intraday").payoff, fx.payoff_intra, 1e-10, key + " intra");
    closeArr(Array.from(E.evaluatePaths(s, fx.close, fx.high, fx.low, "close").anyHit), fx.hit_close, 0, key + " hit");
    closeArr(Array.from(E.evaluatePaths(s, fx.close, fx.high, fx.low, "intraday").anyHit), fx.hit_intra, 0, key + " hit intra");
    closeArr(E.expiryPayoff(s, fx.grid, "none"), fx.exp_none, 1e-10, key + " exp none");
    closeArr(E.expiryPayoff(s, fx.grid, "all"), fx.exp_all, 1e-10, key + " exp all");
    const prof = E.profileSummary(s, fx.cost);
    close(prof.return_max, fx.profile.return_max, 1e-8, key + " ret max"); // supremo na borda da barreira (grade)
    close(prof.return_min, fx.profile.return_min, 1e-9, key + " ret min");
    assert.equal(prof.gain_unlimited, fx.profile.gain_unlimited, key);
    assert.equal(prof.loss_unlimited, fx.profile.loss_unlimited, key);
    closeArr(E.defaultVariations(s), fx.variations, 1e-12, key + " variações");
    const t = E.profitabilityTable(s, fx.cost, fx.variations);
    t.rows.forEach((row, i) => closeArr(row.values, fx.table[i], 1e-10, `${key} quadro ${i}`));
    assert.ok(E.describe(s, fx.cost).length >= 2, key + " descrição");
  }
});

test("Black-Scholes igual ao scipy e paridade put-call", () => {
  for (const [kind, K, T, sig, v] of FX.bs) close(E.bsPrice(kind, 1, K, T, 0.12, 0.02, sig), v, 1e-12, `BS ${kind} ${K} ${T} ${sig}`);
  for (const K of [0.8, 1, 1.2]) close(E.bsPrice("call", 1, K, 1, 0.12, 0.02, 0.3) - E.bsPrice("put", 1, K, 1, 0.12, 0.02, 0.3), Math.exp(-0.02) - K * Math.exp(-0.12), 1e-12, "paridade");
});

test("Monte Carlo: in + out = vanilla e vanilla ≈ BS (3 erros padrão)", () => {
  const r = Math.log1p(0.12), ctx = E.mcContext(252, 0.3, r, 0, 50000, 7);
  const [pin] = E.mcPriceLeg(E.leg("call", 1, 1.05, "up_in", 1.35), ctx);
  const [pout] = E.mcPriceLeg(E.leg("call", 1, 1.05, "up_out", 1.35), ctx);
  const [pv, se] = E.mcPriceLeg(E.leg("call", 1, 1.05), ctx);
  close(pin + pout, pv, 1e-12, "in+out");
  assert.ok(Math.abs(pv - E.bsPrice("call", 1, 1.05, 1, r, 0, 0.3)) < 3 * se, "vanilla MC vs BS");
  const pc = E.mcPriceLeg(E.leg("call", 1, 1.05, "up_in", 1.3), E.mcContext(252, 0.3, r, 0, 20000, 1, "close"))[0];
  const pi = E.mcPriceLeg(E.leg("call", 1, 1.05, "up_in", 1.3), E.mcContext(252, 0.3, r, 0, 20000, 1, "intraday"))[0];
  assert.ok(pi > pc, "BGK aumenta knock-in");
});

test("solver de custo zero", () => {
  const r = Math.log1p(0.12);
  for (const [s, idx, bounds] of [[E.PRESETS.collar.build(), 2, null], [E.PRESETS.fko.build(), [1, 2], [0.8, 1.6]], [E.PRESETS.protecao_total.build(), 3, null]]) {
    const param = Array.isArray(idx) || s.preset === "collar" ? "strike" : "ratio";
    const res = E.solveZeroCost(s, idx, param, 0.3, r, 0, 252, 20000, 42, "close", bounds);
    assert.ok(res.converged, res.message);
    assert.ok(Math.abs(res.cost) < 1e-6, `custo ${res.cost}`);
  }
  const no = E.solveZeroCost(E.PRESETS.straddle.build(), 0, "strike", 0.3, r);
  assert.ok(!no.converged && no.message.includes("Não há solução"));
});

test("backtest histórico igual ao Python", () => {
  const P = { d: FX.prices.d, c: Float64Array.from(FX.prices.c), h: Float64Array.from(FX.prices.h), l: Float64Array.from(FX.prices.l) };
  const cf = E.cdiFactor(P.d, null, 0.10);
  for (const fx of FX.historico) {
    const s = E.PRESETS[fx.preset].build();
    const res = E.runHistorical(s, P, fx.N, 0, fx.monitoring, fx.extra, cf);
    closeArr(res.ret, fx.ret, 1e-10, fx.preset + " ret");
    closeArr(Array.from(res.anyHit), fx.hit, 0, fx.preset + " hit");
    closeArr(res.cdi, fx.cdi, 1e-10, fx.preset + " cdi");
    assert.equal(res.nEff, fx.n_effective);
    const sm = E.summarize(res);
    for (const [k, v] of Object.entries(fx.summary)) close(sm[k === "n_effective" ? "nEff" : k], v, 1e-9, `${fx.preset} ${k}`);
  }
});

test("ex-post igual ao Python", () => {
  const P = { d: FX.prices.d, c: Float64Array.from(FX.prices.c), h: Float64Array.from(FX.prices.h), l: Float64Array.from(FX.prices.l) };
  for (const fx of FX.expost) {
    const r = E.runExPost(E.PRESETS[fx.preset].build(), P, fx.trade, fx.expiry, 0, fx.monitoring);
    assert.equal(r.obsDate, fx.obs); assert.equal(r.lastDate, fx.last); assert.equal(r.finished, fx.finished);
    assert.equal(r.nElapsed, fx.n); close(r.ret, fx.ret, 1e-10, fx.preset);
    fx.hits.forEach(([lbl, hit, when], i) => { assert.equal(r.hits[i].label, lbl); assert.equal(r.hits[i].hit, hit); assert.equal(r.hits[i].date, when); });
  }
});

test("calendário de pregões igual ao Python", () => {
  for (const [y, list] of Object.entries(FX.calendario.feriados)) assert.deepEqual([...E.b3Holidays(+y)].sort(), list);
  for (const [d, exp] of FX.calendario.anterior) assert.equal(E.previousBusinessDay(d), exp);
  for (const [a, b, n] of FX.calendario.contagem) assert.equal(E.countTradingDays(a, b), n, `${a}→${b}`);
  for (const [a, b, n, obs] of FX.calendario.termo_com_serie) assert.deepEqual(E.termFromDates(a, b, FX.prices.d), { n, obs });
});

test("JSON: ida e volta mantém o payoff", () => {
  const s = E.PRESETS.protecao_total.build();
  const s2 = E.fromJSON(JSON.stringify(E.toJSON(s)));
  const rows = linear([0.7, 1.0, 1.2, 1.5]);
  assert.deepEqual(Array.from(E.evaluatePaths(s, rows).payoff), Array.from(E.evaluatePaths(s2, rows).payoff));
  const fromFile = E.fromJSON(readFileSync(new URL("../../presets/protecao_total_bbdc4.json", import.meta.url), "utf-8"));
  assert.deepEqual(fromFile.legs, s.legs);
});

/* ---------------- Saída antecipada ---------------- */
const jsCfg = (c) => ({ trigger: c.trigger, exitSpread: c.exit_spread, delay: c.delay, minDays: c.min_days, volMode: c.vol_mode,
  volWindow: c.vol_window, volAdd: c.vol_add, mcPaths: c.mc_paths, calibrate: c.calibrate });

test("saída antecipada: fórmulas de barreira, marcação e séries iguais ao Python", () => {
  const S = FX.saida;
  for (const [kind, barrier, s, K, H, v] of S.barreira) close(E.barrierPrice(kind, barrier, s, K, H, 0.6, 0.11, 0.01, 0.35), v, 1e-10, `${kind} ${barrier} S=${s} K=${K}`);
  const pt = E.PRESETS.protecao_total.build();
  for (const [s, mx, mn, T, mon, v] of S.valor) close(E.structureValue(pt, s, mx, mn, T, 0.12, 0.3, mon), v, 1e-10, `valor S=${s}`);
  closeArr(E.rollingVol(Float64Array.from(FX.prices.c), 63), S.rolling_vol, 1e-9, "vol móvel");
  closeArr(E.cdiRateSeries(Float64Array.from(S.cdiF)), S.cdi_rate, 1e-10, "taxa CDI");
});

test("saída antecipada: backtest histórico e ex-post iguais ao Python", () => {
  const P = { d: FX.prices.d, c: Float64Array.from(FX.prices.c), h: Float64Array.from(FX.prices.h), l: Float64Array.from(FX.prices.l) };
  const F = Float64Array.from(FX.saida.cdiF);
  for (const fx of FX.saida.historico) {
    const s = E.PRESETS[fx.preset].build();
    const h = E.runHistorical(s, P, fx.N, 0, fx.monitoring, 0, F);
    const x = E.runHistoricalExit(s, P, fx.N, 0, jsCfg(fx.cfg), F, h.ret, fx.monitoring);
    const tag = `${fx.preset} N=${fx.N}`;
    closeArr(Array.from(x.triggered), fx.gatilho, 0, tag + " gatilho");
    closeArr(Array.from(x.triggerDay), fx.dia_gatilho, 0, tag + " dia gatilho");
    closeArr(Array.from(x.early), fx.saida, 0, tag + " saída");
    closeArr(Array.from(x.exitDay), fx.dia_saida, 0, tag + " dia saída");
    closeArr(x.retFinal, fx.retorno_final, 1e-9, tag + " retorno");
    closeArr(x.cdiPeriod, fx.cdi_periodo, 1e-10, tag + " cdi");
    closeArr(x.cdiStart, fx.cdi_inicio, 1e-10, tag + " cdi início");
    const sm = E.summarizeExit(x);
    assert.ok(sm.p_saida >= 0 && sm.p_saida <= 1);
  }
  for (const fx of FX.saida.expost) {
    const r = E.runExPostExit(E.PRESETS[fx.preset].build(), P, fx.trade, fx.N, 0, jsCfg(fx.cfg), F);
    assert.deepEqual(r.dates, fx.dates);
    closeArr(r.ret, fx.ret, 1e-9, fx.preset + " ret ex-post");
    closeArr(r.threshold, fx.threshold, 1e-10, fx.preset + " gatilho ex-post");
    assert.equal(r.triggerDate, fx.trigger); assert.equal(r.exitDate, fx.exit);
    close(r.exitReturn, fx.exit_return, 1e-9, fx.preset + " retorno de saída");
  }
});

test("saída antecipada: regras (delay, carência, vencimento) e Monte Carlo", () => {
  const s = E.structure("ação", [E.leg("stock")]);
  const N = 20, P = { d: Array.from({ length: N + 1 }, (_, i) => "2024-01-" + String(i + 1).padStart(2, "0")), c: Float64Array.from({ length: N + 1 }, (_, i) => Math.pow(1.01, i)) };
  P.h = P.c; P.l = P.c;
  const F = Float64Array.from({ length: N + 1 }, (_, i) => Math.pow(1.1, i / 252));
  const hold = [Math.pow(1.01, N) - 1];
  const run = (cfg) => E.runHistoricalExit(s, P, N, 0, Object.assign({ exitSpread: 0 }, cfg), F, hold);
  let x = run({});
  assert.equal(x.triggerDay[0], 1); assert.equal(x.exitDay[0], 2); close(x.retFinal[0], 1.01 ** 2 - 1, 1e-12, "delay 1");
  x = run({ delay: 0 }); assert.equal(x.exitDay[0], 1);
  x = run({ minDays: 5 }); assert.equal(x.triggerDay[0], 5); assert.equal(x.exitDay[0], 6);
  x = run({ exitSpread: 0.03 }); assert.equal(x.triggerDay[0], 4);
  x = run({ minDays: 19, delay: 1 }); assert.equal(x.triggered[0], 1); assert.equal(x.early[0], 0); assert.equal(x.exitDay[0], N);
  // Monte Carlo: caminhos completos guardados + saída nos 2.000 primeiros
  const Pf = { d: FX.prices.d, c: Float64Array.from(FX.prices.c), h: Float64Array.from(FX.prices.h), l: Float64Array.from(FX.prices.l) };
  const pt = E.PRESETS.protecao_total.build();
  const mc = E.runMonteCarlo(pt, Pf, 60, 0, { nPaths: 3000, cdiAnnual: 0.1 });
  assert.equal(mc.sample.length, 2000);
  const em = E.runMcExit(pt, mc.sample, 60, 0, {}, mc.ret, mc.sigma, 0.1);
  assert.equal(em.n, 2000);
  for (let i = 0; i < em.n; i++) if (!em.early[i]) assert.equal(em.retFinal[i], mc.ret[i]);
});

/* ---------------- Fase 1 da revisão metodológica ---------------- */
test("fase 1: gerador mulberry32, IC por block bootstrap e CVaR iguais ao Python", () => {
  const F1 = FX.fase1;
  const g = E.rng(2026);
  closeArr(F1.rng.map(() => g.uni()), F1.rng, 1e-15, "mulberry32");
  const g2 = E.rng(77);
  assert.deepEqual(F1.rng_int.map(() => g2.int(13)), F1.rng_int);
  for (const c of F1.ci) closeArr(E.blockBootstrapCi(Float64Array.from(c.ind), c.block), c.ci, 1e-12, `IC bloco ${c.block}`);
  for (const [r, q, v] of F1.cvar) close(E.cvar(r, q), v, 1e-12, "CVaR");
});

test("fase 1: histórico com ajuste de regime e saída antecipada no CDI de hoje iguais ao Python", () => {
  const F1 = FX.fase1;
  const P = { d: FX.prices.d, c: Float64Array.from(FX.prices.c), h: Float64Array.from(FX.prices.h), l: Float64Array.from(FX.prices.l) };
  const F = Float64Array.from(FX.saida.cdiF);
  for (const fx of F1.regime) {
    const s = E.PRESETS[fx.preset].build();
    const res = E.runHistorical(s, P, fx.N, 0, fx.monitoring, fx.extra, F, F1.cdi_ref, true);
    closeArr(res.ret, fx.ret, 1e-10, fx.preset + " ret ajustado");
    closeArr(res.retRaw, fx.ret_raw, 1e-10, fx.preset + " ret sem ajuste");
    closeArr(Array.from(res.anyHit), fx.hit, 0, fx.preset + " barreira");
    const sm = E.summarize(res);
    for (const [k, v] of Object.entries(fx.summary)) close(sm[k === "n_effective" ? "nEff" : k], v, 1e-9, `${fx.preset} ${k}`);
    for (const [k, v] of Object.entries(fx.ci)) closeArr(sm.ci[k], v, 1e-12, `${fx.preset} IC ${k}`);
    const sx = F1.saida_regime.find((x) => x.preset === fx.preset);
    if (!sx) continue;
    const ee = E.runHistoricalExit(s, P, fx.N, 0, {}, F, res.ret, fx.monitoring, fx.extra, F1.cdi_ref, true);
    closeArr(Array.from(ee.exitDay), sx.dia_saida, 0, fx.preset + " dia saída (ajustado)");
    closeArr(ee.retFinal, sx.retorno_final, 1e-9, fx.preset + " retorno final (ajustado)");
    closeArr(ee.cdiPeriod, sx.cdi_periodo, 1e-12, fx.preset + " CDI do período (ajustado)");
    const se = E.summarizeExit(ee);
    for (const [k, v] of Object.entries(sx.summary)) close(se[k], v, 1e-9, `${fx.preset} saída ${k}`);
    closeArr(se.ci.p_saida, sx.ci.p_saida, 1e-12, fx.preset + " IC saída");
  }
});

test("fase 1: drift no bootstrap, máxima/mínima sorteadas e grade de cenários", () => {
  const P = { d: FX.prices.d, c: Float64Array.from(FX.prices.c), h: Float64Array.from(FX.prices.h), l: Float64Array.from(FX.prices.l) };
  const { lr, up, dn } = E.ohlcLogReturns(P);
  const N = 63, mu = 0.13;
  const sum = E.blockBootstrapSummary(lr, 20000, N, 20, 5, 50, { driftDaily: E.bootstrapDriftDaily(lr, mu), scale: 1, up, dn });
  let m = 0, v = 0;
  for (const x of sum.sT) m += x; m /= sum.sT.length;
  for (const x of sum.sT) v += (x - m) ** 2; const se = Math.sqrt(v / (sum.sT.length - 1) / sum.sT.length);
  assert.ok(Math.abs(m - (1 + mu) ** (N / 252)) < 4 * se, `E[S_T] ${m}`);
  for (let i = 0; i < 50; i++) for (let j = 0; j < N; j++) assert.ok(sum.sampleH[i][j] >= sum.sample[i][j] - 1e-12 && sum.sampleL[i][j] <= sum.sample[i][j] + 1e-12);
  const s = E.PRESETS.collar_ki.build(1.0, 1.06, 1.12);
  const a = E.runMonteCarlo(s, P, N, 0, { nPaths: 4000, cdiAnnual: 0.12, monitoring: "close" });
  const b = E.runMonteCarlo(s, P, N, 0, { nPaths: 4000, cdiAnnual: 0.12, monitoring: "intraday" });
  assert.ok(E.summarize(b).p_barreira >= E.summarize(a).p_barreira);
  assert.equal(a.drift, "cdi");
  const g = E.runScenarios(s, P, N, 0, { cdiAnnual: 0.12, nPaths: 3000 });
  assert.equal(g.length, 9);
  for (const d of E.SCENARIO_DRIFTS) { const r = g.filter((x) => x.drift === d); assert.ok(r[0].p_barreira <= r[1].p_barreira && r[1].p_barreira <= r[2].p_barreira, d); }
  for (const vs of E.SCENARIO_VOLS) { const r = E.SCENARIO_DRIFTS.map((d) => g.find((x) => x.drift === d && x.volScale === vs)); assert.ok(r[0].p_lucro <= r[1].p_lucro && r[1].p_lucro <= r[2].p_lucro, String(vs)); }
});
