/* Precificação teórica — porta de estruturadas/pricing.py.
   Vanilla: Black-Scholes-Merton. Barreiras: Monte Carlo neutro ao risco (GBM, passos diários,
   antitéticas, seed fixa). Solver de custo zero: método de Brent.
   r e q são taxas contínuas ao ano; preços em fração de S0. */
(function (root) {
  "use strict";
  const E = root.Estr;
  const TD = (E.TRADING_DAYS = 252);
  E.BGK_BETA = 0.5826;
  E.annualToContinuous = (a) => Math.log1p(a);

  /* Normal acumulada com precisão dupla (algoritmo de Hart, implementação de G. West). */
  E.cnd = function (x) {
    const a = Math.abs(x);
    let c;
    if (a > 37) c = 0;
    else {
      const e = Math.exp(-a * a / 2);
      if (a < 7.07106781186547) {
        let b = 3.52624965998911e-2 * a + 0.700383064443688;
        b = b * a + 6.37396220353165; b = b * a + 33.912866078383; b = b * a + 112.079291497871;
        b = b * a + 221.213596169931; b = b * a + 220.206867912376;
        c = e * b;
        b = 8.83883476483184e-2 * a + 1.75566716318264;
        b = b * a + 16.064177579207; b = b * a + 86.7807322029461; b = b * a + 296.564248779674;
        b = b * a + 637.333633378831; b = b * a + 793.826512519948; b = b * a + 440.413735824752;
        c = c / b;
      } else {
        let b = a + 0.65;
        b = a + 4 / b; b = a + 3 / b; b = a + 2 / b; b = a + 1 / b;
        c = e / b / 2.506628274631;
      }
    }
    return x > 0 ? 1 - c : c;
  };

  E.bsPrice = function (kind, S, K, T, r, q, sigma) {
    const dfr = Math.exp(-r * T), dfq = Math.exp(-q * T);
    if (!(sigma > 0) || !(T > 0)) {
      const fwd = (S * dfq) / dfr;
      return dfr * (kind === "call" ? Math.max(fwd - K, 0) : Math.max(K - fwd, 0));
    }
    const sq = Math.sqrt(T);
    const d1 = (Math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sq), d2 = d1 - sigma * sq;
    if (kind === "call") return S * dfq * E.cnd(d1) - K * dfr * E.cnd(d2);
    return K * dfr * E.cnd(-d2) - S * dfq * E.cnd(-d1);
  };

  /* Gerador pseudoaleatório com seed (mulberry32) + normais por Box-Muller. */
  E.rng = function (seed) {
    let a = (seed >>> 0) || 0x9e3779b9;
    let spare = null;
    const uni = () => {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const normal = () => {
      if (spare !== null) { const s = spare; spare = null; return s; }
      let u = 0; while (u === 0) u = uni();
      const v = uni(), m = Math.sqrt(-2 * Math.log(u));
      spare = m * Math.sin(2 * Math.PI * v);
      return m * Math.cos(2 * Math.PI * v);
    };
    const int = (n) => Math.floor(uni() * n);
    return { uni, normal, int };
  };

  /* Caminhos GBM resumidos (S_T, máximo, mínimo). Com antitéticas, o caminho i da 1ª metade usa +Z
     e o caminho i + n/2 usa −Z. keep = nº de caminhos completos guardados para gráficos. */
  E.gbmSummary = function (nPaths, nDays, sigma, logDriftDaily, seed = 42, antithetic = true, keep = 0) {
    const rng = E.rng(seed), vol = sigma * Math.sqrt(1 / TD);
    const nBase = antithetic ? Math.ceil(nPaths / 2) : nPaths, n = antithetic ? 2 * nBase : nPaths;
    const sT = new Float64Array(n), runMax = new Float64Array(n), runMin = new Float64Array(n);
    const sample = [];
    for (let i = 0; i < nBase; i++) {
      let x1 = 0, x2 = 0, mx1 = -Infinity, mn1 = Infinity, mx2 = -Infinity, mn2 = Infinity;
      const keepIt = sample.length < keep, row = keepIt ? new Float64Array(nDays) : null;
      for (let j = 0; j < nDays; j++) {
        const z = rng.normal();
        x1 += logDriftDaily + vol * z;
        if (x1 > mx1) mx1 = x1; if (x1 < mn1) mn1 = x1;
        if (antithetic) { x2 += logDriftDaily - vol * z; if (x2 > mx2) mx2 = x2; if (x2 < mn2) mn2 = x2; }
        if (row) row[j] = Math.exp(x1);
      }
      sT[i] = Math.exp(x1); runMax[i] = Math.exp(mx1); runMin[i] = Math.exp(mn1);
      if (antithetic) { sT[nBase + i] = Math.exp(x2); runMax[nBase + i] = Math.exp(mx2); runMin[nBase + i] = Math.exp(mn2); }
      if (row) sample.push(row);
    }
    return { sT, runMax, runMin, sample };
  };

  E.mcContext = function (nDays, sigma, r, q = 0, nPaths = 50000, seed = 42, monitoring = "close", antithetic = true) {
    const dt = 1 / TD;
    const sum = E.gbmSummary(nPaths, nDays, sigma, (r - q - 0.5 * sigma * sigma) * dt, seed, antithetic);
    return { sum, nPaths: sum.sT.length, nDays, sigma, r, q, antithetic, T: nDays / TD,
      shift: monitoring === "intraday" ? E.BGK_BETA * sigma * Math.sqrt(dt) : 0 };
  };

  const pairAverage = (x, anti) => {
    if (!anti) return x;
    const h = Math.floor(x.length / 2), out = new Float64Array(h);
    for (let i = 0; i < h; i++) out[i] = 0.5 * (x[i] + x[h + i]);
    return out;
  };
  const meanSe = (x) => {
    const n = x.length; let m = 0;
    for (let i = 0; i < n; i++) m += x[i];
    m /= n;
    let v = 0;
    for (let i = 0; i < n; i++) v += (x[i] - m) * (x[i] - m);
    return [m, n > 1 ? Math.sqrt(v / (n - 1) / n) : 0];
  };

  /* Payoff descontado de UMA opção (sem posição/proporção) em cada caminho. */
  function legSamples(l, ctx, hits) {
    const n = ctx.sum.sT.length, out = new Float64Array(n), df = Math.exp(-ctx.r * ctx.T);
    const key = E.legEventKey(l), h = key ? hits[key] : null, knockIn = E.knock(l) === "in";
    for (let i = 0; i < n; i++) {
      const S = ctx.sum.sT[i];
      const raw = l.kind === "call" ? Math.max(S - l.strike, 0) : Math.max(l.strike - S, 0);
      const act = !h ? 1 : knockIn ? h[i] : 1 - h[i];
      out[i] = df * raw * act;
    }
    return out;
  }
  E.mcPriceLeg = function (l, ctx) {
    const ev = E.events({ legs: [l] });
    const hits = E.eventHits(ctx.sum, ev, ctx.shift);
    return meanSe(pairAverage(legSamples(l, ctx, hits), ctx.antithetic));
  };

  E.priceStructureCtx = function (s, ctx) {
    const hits = ctx.sum ? E.eventHits(ctx.sum, E.events(s), ctx.shift) : {};
    const legs = [];
    let mcTotal = null;
    E.optionLegs(s).forEach((l) => {
      let price, se = 0, method;
      if (E.hasBarrier(l)) {
        const smp = legSamples(l, ctx, hits);
        [price, se] = meanSe(pairAverage(smp, ctx.antithetic));
        mcTotal = mcTotal || new Float64Array(smp.length);
        const w = l.position * l.ratio;
        for (let i = 0; i < smp.length; i++) mcTotal[i] += w * smp[i];
        method = "MC";
      } else {
        price = E.bsPrice(l.kind, 1, l.strike, ctx.T, ctx.r, ctx.q, ctx.sigma);
        method = "BS";
      }
      legs.push({ leg: l, unit: price, signed: l.position * l.ratio * price, method, se });
    });
    const net = legs.reduce((a, x) => a + x.signed, 0);
    const netSe = mcTotal ? meanSe(pairAverage(mcTotal, ctx.antithetic))[1] : 0;
    return { legs, net, netSe, nPaths: ctx.nPaths };
  };

  const needsMc = (s) => E.optionLegs(s).some(E.hasBarrier);
  const plainCtx = (nDays, sigma, r, q) => ({ sum: null, nPaths: 0, nDays, sigma, r, q, antithetic: false, T: nDays / TD, shift: 0 });

  E.priceStructure = function (s, sigma, r, q = 0, nDays = 252, nPaths = 50000, seed = 42, monitoring = "close") {
    const ctx = needsMc(s) ? E.mcContext(nDays, sigma, r, q, nPaths, seed, monitoring) : plainCtx(nDays, sigma, r, q);
    return E.priceStructureCtx(s, ctx);
  };

  /* ---------------- Solver de custo zero ---------------- */
  E.PARAM_LABELS = { strike: "Preço de exercício", barrier: "Valor da barreira", ratio: "Proporção" };
  E.withParam = function (s, indices, param, x) {
    const out = E.copyStructure(s);
    [].concat(indices).forEach((i) => {
      const l = out.legs[i];
      if (param === "strike") l.strike = x; else if (param === "barrier") l.level = x; else if (param === "ratio") l.ratio = x;
      else throw new Error(param);
    });
    return out;
  };
  E.defaultBounds = (l, param) => (param === "strike" ? [0.3, 3.0] : param === "barrier" ? (E.barrierDir(l) === "up" ? [1.0001, 3.0] : [0.05, 0.9999]) : [1e-4, 10]);

  /* Método de Brent (zeroin) para f(x) = 0 em [a, b] com f(a)·f(b) < 0. */
  E.brent = function (f, a, b, tol = 1e-7, maxIter = 200) {
    let fa = f(a), fb = f(b);
    if (fa * fb > 0) throw new Error("Sem mudança de sinal no intervalo");
    let c = a, fc = fa, d = b - a, e = d;
    for (let it = 0; it < maxIter; it++) {
      if (fb * fc > 0) { c = a; fc = fa; d = e = b - a; }
      if (Math.abs(fc) < Math.abs(fb)) { a = b; b = c; c = a; fa = fb; fb = fc; fc = fa; }
      const tol1 = 2 * Number.EPSILON * Math.abs(b) + 0.5 * tol, xm = 0.5 * (c - b);
      if (Math.abs(xm) <= tol1 || fb === 0) return b;
      if (Math.abs(e) >= tol1 && Math.abs(fa) > Math.abs(fb)) {
        let p, q, rr, s = fb / fa;
        if (a === c) { p = 2 * xm * s; q = 1 - s; }
        else { q = fa / fc; rr = fb / fc; p = s * (2 * xm * q * (q - rr) - (b - a) * (rr - 1)); q = (q - 1) * (rr - 1) * (s - 1); }
        if (p > 0) q = -q; else p = -p;
        if (2 * p < Math.min(3 * xm * q - Math.abs(tol1 * q), Math.abs(e * q))) { e = d; d = p / q; }
        else { d = xm; e = d; }
      } else { d = xm; e = d; }
      a = b; fa = fb;
      b += Math.abs(d) > tol1 ? d : xm > 0 ? tol1 : -tol1;
      fb = f(b);
    }
    return b;
  };

  E.solveZeroCost = function (s, indices, param, sigma, r, q = 0, nDays = 252, nPaths = 50000, seed = 42,
    monitoring = "close", bounds = null, target = 0) {
    const idx = [].concat(indices);
    const fail = (message) => ({ converged: false, value: null, cost: null, se: null, message });
    if (!idx.length || idx.some((i) => i < 0 || i >= s.legs.length)) return fail("Perna inválida.");
    for (const i of idx) {
      if (!E.isOption(s.legs[i])) return fail("Escolha apenas pernas de opção (não a ação).");
      if (param === "barrier" && !E.hasBarrier(s.legs[i])) return fail(`A perna ${i + 1} não tem barreira.`);
    }
    const [lo, hi] = bounds || E.defaultBounds(s.legs[idx[0]], param);
    const ctx = needsMc(s) ? E.mcContext(nDays, sigma, r, q, nPaths, seed, monitoring) : plainCtx(nDays, sigma, r, q);
    const f = (x) => E.priceStructureCtx(E.withParam(s, idx, param, x), ctx).net - target;
    const flo = f(lo), fhi = f(hi);
    if (!isFinite(flo) || !isFinite(fhi) || flo * fhi > 0)
      return fail(`Não há solução no intervalo informado: o custo líquido tem o mesmo sinal nos dois extremos (${E.fmtPct(flo + target, 4, true)} em ${E.fmtNum(lo, 4)} e ${E.fmtPct(fhi + target, 4, true)} em ${E.fmtNum(hi, 4)}). Tente outro parâmetro, outra perna ou outro intervalo.`);
    const x = E.brent(f, lo, hi);
    const res = E.priceStructureCtx(E.withParam(s, idx, param, x), ctx);
    return { converged: true, value: x, cost: res.net, se: res.netSe, message: "Solução encontrada." };
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
