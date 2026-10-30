/* Vol condicional (GARCH(1,1) / GJR-GARCH) e Monte Carlo FHS — porta de estruturadas/garch.py.
   h[t+1] = ω + (α + γ·1[ε_t<0])·ε_t² + β·h[t], por quase-máxima verossimilhança gaussiana (Nelder-Mead
   determinístico, igual ao do Python). FHS (Barone-Adesi, Giannopoulos & Vosper, 1999): choques
   padronizados reais z = ε/√h sorteados a partir da vol de hoje, com a vol de cada caminho evoluindo. */
(function (root) {
  "use strict";
  const E = root.Estr;
  const TD = 252, P_MAX = 0.999;
  E.VOL_MODEL_LABELS = { gjr: "GJR-GARCH (assimétrico)", garch: "GARCH(1,1)" };
  E.GARCH_MIN_OBS = 250;
  E.GARCH_RESTARTS = 5;
  const logistic = (x) => 1 / (1 + Math.exp(-x)), logit = (p) => Math.log(p / (1 - p));
  const seqsum = (a) => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i]; return s; };

  /* Parâmetros irrestritos -> [ω, α, γ, β] (ver unpack_params no Python). */
  E.garchUnpack = function (x, model, s2) {
    const vLong = s2 * Math.exp(x[0]), p = P_MAX * logistic(x[1]), a = logistic(x[2]);
    const shock = a * p, beta = (1 - a) * p;
    let gamma = 0, alpha = shock;
    if (model === "gjr") { const g = logistic(x[3]); gamma = 2 * g * shock; alpha = (1 - g) * shock; }
    return [vLong * (1 - p), alpha, gamma, beta];
  };
  /* Pontos iniciais (persistência, choques, fração assimétrica no GJR) e passo do simplex: iguais ao Python. */
  const START_POINTS = [[0.97, 0.08, 0.625], [0.90, 0.12, 0.5]], NM_STEP = 0.25;
  const startParams = (model, k = 0) => { const [p, shock, g] = START_POINTS[k], x = [0, logit(p / P_MAX), logit(shock / p)]; if (model === "gjr") x.push(logit(g)); return x; };

  /* Variância condicional (n+1): h[0] = h0; h[n] = previsão para o próximo pregão. */
  E.garchFilter = function (eps, omega, alpha, gamma, beta, h0) {
    const n = eps.length, h = new Float64Array(n + 1);
    h[0] = h0;
    for (let t = 0; t < n; t++) { const e = eps[t]; h[t + 1] = omega + (alpha + (e < 0 ? gamma : 0)) * (e * e) + beta * h[t]; }
    return h;
  };

  /* Nelder-Mead padrão (1 / 2 / 0,5 / 0,5), escrito igual ao do Python. */
  E.nelderMead = function (f, x0, step = NM_STEP, maxIter = 2000, xtol = 1e-7, ftol = 1e-11) {
    const n = x0.length;
    let S = [x0.slice()];
    for (let i = 0; i < n; i++) { const v = x0.slice(); v[i] += step; S.push(v); }
    let fs = S.map((v) => f(v)), it = 0;
    while (it < maxIter) {
      const order = [...Array(n + 1).keys()].sort((a, b) => fs[a] - fs[b]);
      S = order.map((i) => S[i]); fs = order.map((i) => fs[i]);
      let spread = 0;
      for (let i = 1; i <= n; i++) for (let j = 0; j < n; j++) spread = Math.max(spread, Math.abs(S[i][j] - S[0][j]));
      if (fs[n] - fs[0] <= ftol && spread <= xtol) break;
      it++;
      const c = new Array(n).fill(0);
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) c[j] += S[i][j];
      for (let j = 0; j < n; j++) c[j] /= n;
      const w = S[n], xr = c.map((cj, j) => cj + (cj - w[j])), fr = f(xr);
      if (fr < fs[0]) {
        const xe = c.map((cj, j) => cj + 2 * (cj - w[j])), fe = f(xe);
        if (fe < fr) { S[n] = xe; fs[n] = fe; } else { S[n] = xr; fs[n] = fr; }
        continue;
      }
      if (fr < fs[n - 1]) { S[n] = xr; fs[n] = fr; continue; }
      let xc, fc, ok;
      if (fr < fs[n]) { xc = c.map((cj, j) => cj + 0.5 * (xr[j] - cj)); fc = f(xc); ok = fc <= fr; }
      else { xc = c.map((cj, j) => cj + 0.5 * (w[j] - cj)); fc = f(xc); ok = fc < fs[n]; }
      if (ok) { S[n] = xc; fs[n] = fc; continue; }
      const b = S[0];
      for (let i = 1; i <= n; i++) { S[i] = S[i].map((v, j) => b[j] + 0.5 * (v - b[j])); fs[i] = f(S[i]); }
    }
    let best = 0;
    for (let i = 1; i <= n; i++) if (fs[i] < fs[best]) best = i;
    return { x: S[best], f: fs[best], it };
  };

  /* Parâmetros já estimados aplicados a uma série: resíduos padronizados, variância e previsão de hoje. */
  E.garchFiltered = function (lr, omega, alpha, gamma, beta, model = "gjr", up = null, dn = null, iterations = 0) {
    const n = lr.length, m = seqsum(lr) / n, eps = new Float64Array(n);
    for (let i = 0; i < n; i++) eps[i] = lr[i] - m;
    let s2 = 0; for (let i = 0; i < n; i++) s2 += eps[i] * eps[i]; s2 /= n;
    const h = E.garchFilter(eps, omega, alpha, gamma, beta, s2), z = new Float64Array(n), u = new Float64Array(n), d = new Float64Array(n);
    let ll = 0;
    for (let i = 0; i < n; i++) { const sh = Math.sqrt(h[i]); z[i] = eps[i] / sh; u[i] = up ? up[i] / sh : 0; d[i] = dn ? dn[i] / sh : 0; ll += Math.log(2 * Math.PI) + Math.log(h[i]) + eps[i] * eps[i] / h[i]; }
    const zm = seqsum(z) / n;
    let zv = 0; for (let i = 0; i < n; i++) zv += (z[i] - zm) * (z[i] - zm);
    const zs = Math.sqrt(zv / n);
    let kappa = 0;
    for (let i = 0; i < n; i++) { z[i] = (z[i] - zm) / zs; if (z[i] < 0) kappa += z[i] * z[i]; }
    kappa /= n;
    return E.garchSummary({ model, omega, alpha, gamma, beta, mean: m, s2, loglik: -0.5 * ll, n, h, z, up: u, dn: d, kappa, iterations });
  };
  /* Acrescenta as grandezas derivadas (persistência, variância de longo prazo, meia-vida, BIC). */
  E.garchSummary = function (g) {
    g.persistence = Math.min(g.alpha + g.gamma * g.kappa + g.beta, 0.9999);
    g.hNext = g.h[g.h.length - 1];
    g.longRunVar = g.omega / (1 - g.persistence);
    g.halfLife = Math.log(0.5) / Math.log(g.persistence);
    g.nParams = g.model === "gjr" ? 4 : 3;
    g.bic = -2 * g.loglik + g.nParams * Math.log(g.n);
    return g;
  };

  E.garchFit = function (lr, model = "gjr", up = null, dn = null) {
    if (!E.VOL_MODEL_LABELS[model]) throw new Error("Modelo de vol inválido: " + model);
    const n = lr.length;
    if (n < E.GARCH_MIN_OBS) throw new Error(`Histórico insuficiente para o GARCH: ${n} retornos (mínimo ${E.GARCH_MIN_OBS}).`);
    const m = seqsum(lr) / n, eps = new Float64Array(n), e2 = new Float64Array(n);
    for (let i = 0; i < n; i++) { eps[i] = lr[i] - m; e2[i] = eps[i] * eps[i]; }
    const s2 = seqsum(e2) / n;
    const nll = (x) => {
      const [omega, alpha, gamma, beta] = E.garchUnpack(x, model, s2);
      let h = s2, s = 0;
      for (let t = 0; t < n; t++) { s += Math.log(h) + e2[t] / h; h = omega + (alpha + (eps[t] < 0 ? gamma : 0)) * e2[t] + beta * h; }
      return 0.5 * s / n;
    };
    // dois pontos iniciais e, em cada um, reinícios a partir do melhor ponto até não haver melhora (igual ao Python)
    let best = null, it = 0;
    for (let k = 0; k < START_POINTS.length; k++) {
      let r = E.nelderMead(nll, startParams(model, k));
      it += r.it;
      for (let j = 0; j < E.GARCH_RESTARTS; j++) {
        const r2 = E.nelderMead(nll, r.x);
        it += r2.it;
        const improved = r.f - r2.f > 1e-10;
        if (r2.f < r.f) r = r2;
        if (!improved) break;
      }
      if (!best || r.f < best.f) best = r;
    }
    const [omega, alpha, gamma, beta] = E.garchUnpack(best.x, model, s2);
    return E.garchFiltered(lr, omega, alpha, gamma, beta, model, up, dn, it);
  };

  /* Variância diária média esperada nos próximos m pregões, dado h_{T+1} = h1. */
  E.termVar = (g, h1, m) => { m = Math.max(m, 1); const p = g.persistence, vl = g.longRunVar; return vl + (h1 - vl) * (1 - Math.pow(p, m)) / (m * (1 - p)); };
  E.termVol = (g, h1, m) => Math.sqrt(E.termVar(g, h1, m) * TD);
  /* E[h_{T+k}] dado h_{T+1} = h1. */
  E.expectedVar = (g, h1, k) => g.longRunVar + Math.pow(g.persistence, k - 1) * (h1 - g.longRunVar);

  /* Resumo para o painel de volatilidade (anualizado). */
  E.volPanel = function (g, lr, N, window = 63) {
    const tail = lr.slice(Math.max(0, lr.length - window));
    let m = 0; for (let i = 0; i < tail.length; i++) m += tail[i]; m /= tail.length;
    let v = 0; for (let i = 0; i < tail.length; i++) v += (tail[i] - m) * (tail[i] - m);
    return { modelo: E.VOL_MODEL_LABELS[g.model], vol_hoje: Math.sqrt(g.hNext * TD), vol_longo_prazo: Math.sqrt(g.longRunVar * TD),
      vol_prazo: E.termVol(g, g.hNext, N), vol_realizada: tail.length > 1 ? Math.sqrt(v / (tail.length - 1) * TD) : NaN,
      meia_vida: g.halfLife, persistencia: g.persistence, alpha: g.alpha, gamma: g.gamma, beta: g.beta, omega: g.omega, n: g.n, bic: g.bic };
  };

  /* Drift diário do FHS (ver fhs_drift_daily no Python). */
  E.fhsDriftDaily = function (lr, mu, scale = 1) {
    if (mu != null) return Math.log1p(mu) / TD;
    const n = lr.length, m = seqsum(lr) / n;
    let v = 0; for (let i = 0; i < n; i++) v += (lr[i] - m) * (lr[i] - m);
    return m + 0.5 * scale * scale * v / (n - 1);
  };

  /* Monte Carlo FHS resumido (S_T, máximo, mínimo) + `keep` caminhos completos (fechamento, máxima,
     mínima e variância prevista para o dia seguinte). Mesma ordem de sorteios do Python. */
  E.fhsSummary = function (g, nPaths, N, seed = 42, drift = 0, scale = 1, keep = 0, intraday = true) {
    const rng = E.rng(seed), L = g.z.length, z = g.z, u = g.up, d = g.dn, s2 = scale * scale;
    const { omega, alpha, gamma, beta } = g;
    const sT = new Float64Array(nPaths), runMax = new Float64Array(nPaths), runMin = new Float64Array(nPaths);
    const sample = [], sampleH = [], sampleL = [], sampleV = [];
    for (let i = 0; i < nPaths; i++) {
      let x = 0, h = g.hNext, mx = -Infinity, mn = Infinity;
      const keepIt = sample.length < keep;
      const row = keepIt ? new Float64Array(N) : null, rowH = keepIt && intraday ? new Float64Array(N) : null;
      const rowL = keepIt && intraday ? new Float64Array(N) : null, rowV = keepIt ? new Float64Array(N) : null;
      for (let j = 0; j < N; j++) {
        const q = rng.int(L), sh = Math.sqrt(h), e = sh * z[q];
        x += drift - 0.5 * s2 * h + scale * e;
        const xu = intraday ? x + scale * sh * u[q] : x, xd = intraday ? x + scale * sh * d[q] : x;
        if (xu > mx) mx = xu; if (xd < mn) mn = xd;
        h = omega + (alpha + (e < 0 ? gamma : 0)) * (e * e) + beta * h;
        if (row) { row[j] = Math.exp(x); rowV[j] = h; if (rowH) { rowH[j] = Math.exp(xu); rowL[j] = Math.exp(xd); } }
      }
      sT[i] = Math.exp(x); runMax[i] = Math.exp(mx); runMin[i] = Math.exp(mn);
      if (row) { sample.push(row); sampleV.push(rowV); if (rowH) { sampleH.push(rowH); sampleL.push(rowL); } }
    }
    return { sT, runMax, runMin, sample, sampleH: intraday ? sampleH : null, sampleL: intraday ? sampleL : null, sampleV };
  };

  /* Série da vol condicional anualizada por data (h[i] = prevista no fechamento do pregão i) e a vol realizada
     de 63 pregões, para o gráfico do painel. */
  E.volHistory = function (P, g, window = 63) {
    const n = Math.min(P.c.length, g.h.length), cond = new Float64Array(n);
    for (let i = 0; i < n; i++) cond[i] = Math.sqrt(g.h[i] * TD);
    return { d: P.d.slice(0, n), cond, realized: E.rollingVol ? E.rollingVol(P.c.slice(0, n), window) : null };
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
