/* Web Worker: cálculos pesados (Monte Carlo de precificação, solver, backtests) fora da thread da página. */
const V = self.location.search || "";
importScripts(...["legs", "presets", "pricing", "backtest"].map((f) => `engine/${f}.js${V}`));
const E = self.Estr;

const TASKS = {
  price: (a) => E.priceStructure(a.s, a.sigma, a.r, a.q, a.n, a.paths, a.seed, a.monitoring),
  solve: (a) => E.solveZeroCost(a.s, a.legs, a.param, a.sigma, a.r, a.q, a.n, a.paths, a.seed, a.monitoring, a.bounds, a.target),
  hist: (a) => E.runHistorical(a.s, a.P, a.n, a.cost, a.monitoring, a.extra, a.cdiF),
  mc: (a) => E.runMonteCarlo(a.s, a.P, a.n, a.cost, a.o),
};

self.onmessage = (ev) => {
  const { id, type, args } = ev.data;
  try {
    self.postMessage({ id, ok: true, result: TASKS[type](args) });
  } catch (e) {
    self.postMessage({ id, ok: false, error: e.message || String(e) });
  }
};
