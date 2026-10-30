/* Painel de calibração walk-forward — porta de estruturadas/calibration.py.
   A cada `step` pregões, só com dados até a data t: P(lucro), P(> CDI) e P(barreira) pelo método do Monte Carlo
   (GARCH reestimado a cada `refit` pregões), comparadas com o que aconteceu na janela [t, t+N] (caminho real,
   CDI da época). Régua: chute fixo = frequência nas janelas já encerradas até t. Brier = média de (p − 0/1)². */
(function (root) {
  "use strict";
  const E = root.Estr;
  const TD = 252, TOL = 1e-9;
  E.CALIB_EVENTS = [["lucro", "P(lucro > 0)"], ["cdi", "P(retorno > CDI)"], ["barreira", "P(barreira acionada)"]];

  E.walkForward = function (s, P, N, cost, o = {}, progress = null) {
    const method = o.method || "fhs_garch", step = o.step || 10, nPaths = o.nPaths || 1000, refit = o.refit || 252;
    const volModel = o.volModel || "gjr", cdiAnnual = o.cdiAnnual ?? 0.10, cdiF = o.cdiF || null;
    const n = P.c.length, start = Math.max(o.start || 504, N + 252), dates = [];
    for (let t = start; t < n - N; t += step) dates.push(t);
    if (!dates.length) throw new Error(`Histórico insuficiente para a calibração: são necessários mais de ${start + N} pregões.`);
    const hist = E.runHistorical(s, P, N, cost, o.monitoring || "close", o.extra || 0, cdiF, null, false);
    const hasBar = E.events(s).length > 0, nh = hist.n, real = { lucro: new Float64Array(nh), cdi: new Float64Array(nh) };
    if (hasBar) real.barreira = new Float64Array(nh);
    const fixedCdi = Math.pow(1 + cdiAnnual, N / TD) - 1;
    for (let i = 0; i < nh; i++) {
      real.lucro[i] = hist.ret[i] > TOL ? 1 : 0;
      real.cdi[i] = hist.ret[i] > (hist.cdi ? hist.cdi[i] : fixedCdi) + TOL ? 1 : 0;
      if (hasBar) real.barreira[i] = hist.anyHit[i] ? 1 : 0;
    }
    const csum = {};
    for (const k in real) { const c = new Float64Array(nh + 1); for (let i = 0; i < nh; i++) c[i + 1] = c[i] + real[k][i]; csum[k] = c; }
    const all = E.ohlcLogReturns(P);
    let fit = null, fitT = -1e9;
    const rows = [];
    dates.forEach((t, j) => {
      const sub = { d: P.d.slice(0, t + 1), c: P.c.subarray(0, t + 1), h: P.h.subarray(0, t + 1), l: P.l.subarray(0, t + 1) };
      const rate = cdiF ? Math.pow(cdiF[t] / cdiF[t - 1], TD) - 1 : cdiAnnual;
      let g = null;
      if (method === "fhs_garch") {
        const lr = all.lr.subarray(0, t), up = all.up.subarray(0, t), dn = all.dn.subarray(0, t);
        if (!fit || t - fitT >= refit) { fit = E.garchFit(lr, volModel, up, dn); fitT = t; g = fit; }
        else g = E.garchFiltered(lr, fit.omega, fit.alpha, fit.gamma, fit.beta, volModel, up, dn);
      }
      const r = E.runMonteCarlo(s, sub, N, cost, { method, nPaths, block: o.block || 20, drift: o.drift || "cdi", premium: o.premium ?? 0.05,
        custom: o.custom ?? null, cdiAnnual: rate, seed: o.seed ?? 42, monitoring: o.monitoring || "close", extra: o.extra || 0, volModel, garch: g, keep: 0 });
      let luc = 0, cdi = 0, bar = 0;
      for (let i = 0; i < r.n; i++) { if (r.ret[i] > TOL) luc++; if (r.ret[i] > r.cdiHoje + TOL) cdi++; if (r.anyHit[i]) bar++; }
      const closed = t - N + 1;
      const row = { data: P.d[t], cdi_ref: rate, vol: r.sigma, prev_lucro: luc / r.n, prev_cdi: cdi / r.n };
      if (hasBar) row.prev_barreira = bar / r.n;
      for (const k in real) { row["clim_" + k] = csum[k][closed] / closed; row["real_" + k] = real[k][t]; }
      rows.push(row);
      if (progress) progress((j + 1) / dates.length);
    });
    return { rows, N, step, method, nPaths, start, refit, volModel, drift: o.drift || "cdi" };
  };

  const eventsOf = (res) => E.CALIB_EVENTS.filter(([k]) => res.rows.length && ("prev_" + k) in res.rows[0]);
  /* Brier do modelo × do chute fixo e ganho relativo (1 − modelo/chute). */
  E.calibBrier = function (res) {
    return eventsOf(res).map(([k, label]) => {
      let bm = 0, bc = 0, pm = 0, cm = 0, y = 0;
      for (const r of res.rows) {
        const yy = r["real_" + k], p = r["prev_" + k], c = r["clim_" + k];
        bm += (p - yy) * (p - yy); bc += (c - yy) * (c - yy); pm += p; cm += c; y += yy;
      }
      const n = res.rows.length;
      return { indicador: label, chave: k, brier_modelo: bm / n, brier_chute: bc / n, ganho: bc > 0 ? 1 - bm / bc : NaN,
        prev_media: pm / n, chute_medio: cm / n, real: y / n, n };
    });
  };
  /* Diagrama de confiabilidade: previsões em faixas de 10 p.p. × frequência realizada. */
  E.calibReliability = function (res, key, bins = 10) {
    const acc = Array.from({ length: bins }, () => ({ p: 0, y: 0, n: 0 }));
    for (const r of res.rows) {
      const p = r["prev_" + key], b = Math.min(Math.floor(p * bins), bins - 1);
      acc[b].p += p; acc[b].y += r["real_" + key]; acc[b].n++;
    }
    return acc.map((a, i) => (a.n ? { faixa: `${(i * 100) / bins}–${((i + 1) * 100) / bins}%`, prev_media: a.p / a.n, real: a.y / a.n, n: a.n } : null)).filter(Boolean);
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
