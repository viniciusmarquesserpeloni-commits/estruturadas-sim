/* Web Worker: cálculos pesados (Monte Carlo de precificação, solver, backtests) fora da thread da página. */
const V = self.location.search || "";
importScripts(...["legs", "presets", "pricing", "garch", "backtest", "early", "calib"].map((f) => `engine/${f}.js${V}`));
const E = self.Estr;

const TASKS = {
  price: (a) => E.priceStructure(a.s, a.sigma, a.r, a.q, a.n, a.paths, a.seed, a.monitoring),
  solve: (a) => E.solveZeroCost(a.s, a.legs, a.param, a.sigma, a.r, a.q, a.n, a.paths, a.seed, a.monitoring, a.bounds, a.target),
  hist: (a) => E.runHistorical(a.s, a.P, a.n, a.cost, a.monitoring, a.extra, a.cdiF, a.cdiRef, a.regimeAdjust),
  mc: (a) => E.runMonteCarlo(a.s, a.P, a.n, a.cost, a.o),
  hexit: (a) => E.runHistoricalExit(a.s, a.P, a.n, a.cost, a.cfg, a.cdiF, a.retHold, a.monitoring, a.extra, a.cdiRef, a.regimeAdjust),
  mcexit: (a) => E.runMcExitParts(a.s, a.parts, a.n, a.cost, a.cfg, a.cdiAnnual, a.monitoring, a.extra),
  volp: (a) => E.termVolForecast(a.P, a.n, a.volModel),
  scen: (a) => E.runScenarios(a.s, a.P, a.n, a.cost, a.o),
  calib: (a, progress) => E.walkForward(a.s, a.P, a.n, a.cost, a.o, progress),
};

self.onmessage = (ev) => {
  const { id, type, args } = ev.data;
  let last = 0;
  const progress = (p) => { if (p - last >= 0.01 || p >= 1) { last = p; self.postMessage({ id, progress: p }); } };
  try {
    self.postMessage({ id, ok: true, result: TASKS[type](args, progress) });
  } catch (e) {
    self.postMessage({ id, ok: false, error: e.message || String(e) });
  }
};
