/* Backtest, calendário e métricas — porta de estruturadas/backtest.py, data.py e metrics.py.
   Séries de preços: { d: ["AAAA-MM-DD", ...], c: Float64Array, h, l } (datas ISO comparam como texto). */
(function (root) {
  "use strict";
  const E = root.Estr;
  const TD = 252, TOL = 1e-9;
  E.DRIFT_LABELS = { cdi: "CDI", cdi_premio: "CDI + prêmio", zero: "Zero", historico: "Histórico (média do período)", personalizado: "Personalizado" };
  E.MC_METHOD_LABELS = { media: "Média dos 3 métodos (recomendado)", fhs_garch: "FHS-GARCH (vol condicional)", bootstrap: "Bootstrap em blocos", gbm: "GBM (log-normal)" };
  E.ENSEMBLE = ["fhs_garch", "bootstrap", "gbm"]; // métodos combinados em "media"
  E.EXIT_PATHS = 2000; // caminhos completos guardados (gráfico usa 100; saída antecipada usa todos)

  /* ---------------- Datas e calendário ---------------- */
  const toUTC = (iso) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return Date.UTC(y, m - 1, d); };
  const toISO = (t) => new Date(t).toISOString().slice(0, 10);
  const DAY = 86400000;
  E.addDaysISO = (iso, n) => toISO(toUTC(iso) + n * DAY);

  function easter(y) {
    const a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4;
    const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
    const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
    const month = Math.floor((h + l - 7 * m + 114) / 31), day = ((h + l - 7 * m + 114) % 31) + 1;
    return Date.UTC(y, month - 1, day);
  }
  const holCache = {};
  /* Aproximação dos feriados da B3: nacionais, Carnaval, Sexta-feira Santa, Corpus Christi,
     Consciência Negra (desde 2024), 24/12 e 31/12. */
  E.b3Holidays = function (y) {
    if (holCache[y]) return holCache[y];
    const fixed = [[1, 1], [4, 21], [5, 1], [9, 7], [10, 12], [11, 2], [11, 15], [12, 24], [12, 25], [12, 31]];
    if (y >= 2024) fixed.push([11, 20]);
    const set = new Set(fixed.map(([m, d]) => toISO(Date.UTC(y, m - 1, d))));
    const e = easter(y);
    [-48, -47, -2, 60].forEach((k) => set.add(toISO(e + k * DAY)));
    return (holCache[y] = set);
  };
  E.isBusinessDay = (iso) => { const wd = new Date(toUTC(iso)).getUTCDay(); return wd !== 0 && wd !== 6 && !E.b3Holidays(+iso.slice(0, 4)).has(iso); };

  const lastIndexBefore = (dates, iso) => { // maior i com dates[i] < iso
    let lo = 0, hi = dates.length - 1, ans = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (dates[m] < iso) { ans = m; lo = m + 1; } else hi = m - 1; }
    return ans;
  };
  const lastIndexOnOrBefore = (dates, iso) => {
    let lo = 0, hi = dates.length - 1, ans = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (dates[m] <= iso) { ans = m; lo = m + 1; } else hi = m - 1; }
    return ans;
  };
  E.lastIndexOnOrBefore = lastIndexOnOrBefore;

  /* Pregão anterior a iso (D−1): pela série quando ela cobre a data; senão pelo calendário. */
  E.previousBusinessDay = function (iso, dates) {
    if (dates && dates.length && iso <= E.addDaysISO(dates[dates.length - 1], 1)) {
      const i = lastIndexBefore(dates, iso);
      if (i >= 0) return dates[i];
    }
    let t = E.addDaysISO(iso, -1);
    while (!E.isBusinessDay(t)) t = E.addDaysISO(t, -1);
    return t;
  };
  /* Nº de pregões em (t0, t1]: datas da série onde houver dados + calendário para o trecho futuro. */
  E.countTradingDays = function (t0, t1, dates) {
    if (t1 <= t0) return 0;
    let n = 0, last = t0;
    if (dates && dates.length) {
      const a = lastIndexOnOrBefore(dates, t0), b = lastIndexOnOrBefore(dates, t1);
      n += Math.max(0, b - a);
      const end = dates[dates.length - 1];
      last = t0 > (t1 < end ? t1 : end) ? t0 : (t1 < end ? t1 : end);
    }
    for (let t = E.addDaysISO(last, 1); t <= t1; t = E.addDaysISO(t, 1)) if (E.isBusinessDay(t)) n++;
    return n;
  };
  /* Prazo em pregões entre a contratação e a apuração (fechamento de D−1 do vencimento). */
  E.termFromDates = function (trade, expiry, dates) {
    const obs = E.previousBusinessDay(expiry, dates);
    return { n: E.countTradingDays(trade, obs, dates), obs };
  };

  /* ---------------- Séries ---------------- */
  /* Converte o JSON de preços (c bruto, ca ajustado, h/l brutos) na série usada pelo motor. */
  E.preparePrices = function (raw, adjusted = true, start = null, end = null) {
    const n = raw.d.length;
    let i0 = 0, i1 = n - 1;
    if (start) while (i0 < n && raw.d[i0] < start) i0++;
    if (end) while (i1 >= 0 && raw.d[i1] > end) i1--;
    const m = Math.max(0, i1 - i0 + 1);
    const out = { d: raw.d.slice(i0, i1 + 1), c: new Float64Array(m), h: new Float64Array(m), l: new Float64Array(m) };
    for (let k = 0; k < m; k++) {
      const i = i0 + k, c = raw.c[i], f = adjusted && raw.ca ? raw.ca[i] / c : 1;
      out.c[k] = c * f;
      out.h[k] = (raw.h ? raw.h[i] ?? c : c) * f;
      out.l[k] = (raw.l ? raw.l[i] ?? c : c) * f;
    }
    return out;
  };
  E.histVol = function (c, window = TD) {
    const lr = [];
    for (let i = Math.max(1, c.length - window); i < c.length; i++) lr.push(Math.log(c[i] / c[i - 1]));
    if (lr.length < 2) return NaN;
    const m = lr.reduce((a, b) => a + b, 0) / lr.length;
    return Math.sqrt(lr.reduce((a, b) => a + (b - m) * (b - m), 0) / (lr.length - 1) * TD);
  };
  /* Fator acumulado do CDI em cada data da série (começa em 1); dias sem dado usam a última taxa
     conhecida ou a taxa anual de fallback. cdi = { d: [...], r: [frações ao dia] }. */
  E.cdiFactor = function (dates, cdi, fallbackAnnual) {
    const fb = Math.pow(1 + fallbackAnnual, 1 / TD) - 1, out = new Float64Array(dates.length);
    let j = -1, lastRate = null, acc = 1;
    const cd = cdi && cdi.d ? cdi.d : [];
    for (let i = 0; i < dates.length; i++) {
      while (j + 1 < cd.length && cd[j + 1] <= dates[i]) { j++; lastRate = cdi.r[j]; }
      const rate = i === 0 ? 0 : lastRate == null ? fb : lastRate;
      acc *= 1 + rate;
      out[i] = acc;
    }
    return out;
  };

  /* ---------------- Janelas históricas ---------------- */
  const eventKeys = (s) => E.events(s);
  function resultFrom(s, sum, cost, extra, shift) {
    const ev = E.evaluateSummary(s, sum, shift);
    const ret = E.returnsFromPayoff(ev.payoff, cost, E.hasStock(s), extra);
    const stock = new Float64Array(sum.sT.length);
    for (let i = 0; i < stock.length; i++) stock[i] = sum.sT[i] - 1;
    let retMax = null;
    try { const m = E.profileSummary(s, cost).return_max; retMax = m == null ? null : m - extra; } catch (e) { retMax = null; }
    return { ret, stock, payoff: ev.payoff, sT: sum.sT, hits: ev.hits, anyHit: ev.anyHit, events: ev.events, retMax };
  }

  /* Para cada data inicial t com N pregões à frente: caminho = P[t+1 : t+N] / P[t].
     Com regimeAdjust (exige cdiF e cdiRef), o caminho é multiplicado por
     f[t,k] = (1 + cdiRef)^(k/252) / (CDI acumulado de t a t+k na época): preserva o excesso de retorno
     sobre o CDI de cada época e re-ancora no CDI de hoje ("e se eu contratasse agora?"). */
  E.runHistorical = function (s, P, N, cost, monitoring = "close", extra = 0, cdiF = null, cdiRef = null, regimeAdjust = false) {
    if (!(N >= 1)) throw new Error("O prazo deve ter pelo menos 1 pregão.");
    const n = P.c.length - N;
    if (n <= 0) throw new Error(`Histórico insuficiente: ${P.c.length} pregões para um prazo de ${N}.`);
    const intra = monitoring === "intraday", adjust = !!(regimeAdjust && cdiF && cdiRef != null);
    const sT = new Float64Array(n), runMax = new Float64Array(n), runMin = new Float64Array(n);
    const sT0 = adjust ? new Float64Array(n) : null, mx0 = adjust ? new Float64Array(n) : null, mn0 = adjust ? new Float64Array(n) : null;
    for (let t = 0; t < n; t++) {
      const base = P.c[t];
      let mx = -Infinity, mn = Infinity, mxr = -Infinity, mnr = Infinity;
      for (let j = t + 1; j <= t + N; j++) {
        const c = P.c[j], up = intra ? Math.max(P.h[j], c) : c, dn = intra ? Math.min(P.l[j], c) : c;
        const f = adjust ? Math.pow(1 + cdiRef, (j - t) / TD) / (cdiF[j] / cdiF[t]) : 1;
        if (up * f > mx) mx = up * f; if (dn * f < mn) mn = dn * f;
        if (adjust) { if (up > mxr) mxr = up; if (dn < mnr) mnr = dn; }
      }
      const fN = adjust ? Math.pow(1 + cdiRef, N / TD) / (cdiF[t + N] / cdiF[t]) : 1;
      sT[t] = (P.c[t + N] * fN) / base; runMax[t] = mx / base; runMin[t] = mn / base;
      if (adjust) { sT0[t] = P.c[t + N] / base; mx0[t] = mxr / base; mn0[t] = mnr / base; }
    }
    const r = resultFrom(s, { sT, runMax, runMin }, cost, extra, 0);
    if (adjust) r.retRaw = E.returnsFromPayoff(E.evaluateSummary(s, { sT: sT0, runMax: mx0, runMin: mn0 }, 0).payoff, cost, E.hasStock(s), extra);
    r.start = P.d.slice(0, n); r.end = P.d.slice(N, N + n);
    if (cdiF) { r.cdi = new Float64Array(n); for (let t = 0; t < n; t++) r.cdi[t] = cdiF[t + N] / cdiF[t] - 1; }
    if (cdiRef != null) r.cdiHoje = Math.pow(1 + cdiRef, N / TD) - 1;
    return Object.assign(r, { kind: "historico", N, n, nEff: Math.ceil(n / N), monitoring, regimeAdjust: adjust, cdiRef });
  };

  /* ---------------- Monte Carlo ---------------- */
  E.logReturns = function (P) {
    const out = [];
    for (let i = 1; i < P.c.length; i++) { const v = Math.log(P.c[i] / P.c[i - 1]); if (isFinite(v)) out.push(v); }
    return Float64Array.from(out);
  };
  /* Log-retornos de fechamento e distância da máxima/mínima ao fechamento de cada dia (sorteados juntos). */
  E.ohlcLogReturns = function (P) {
    const lr = [], up = [], dn = [];
    for (let i = 1; i < P.c.length; i++) {
      const v = Math.log(P.c[i] / P.c[i - 1]), u = Math.max(Math.log(P.h[i] / P.c[i]), 0), d = Math.min(Math.log(P.l[i] / P.c[i]), 0);
      if (isFinite(v) && isFinite(u) && isFinite(d)) { lr.push(v); up.push(u); dn.push(d); }
    }
    return { lr: Float64Array.from(lr), up: Float64Array.from(up), dn: Float64Array.from(dn) };
  };
  const meanOf = (a) => { let m = 0; for (let i = 0; i < a.length; i++) m += a[i]; return m / a.length; };
  const varOf = (a) => { const m = meanOf(a); let v = 0; for (let i = 0; i < a.length; i++) v += (a[i] - m) * (a[i] - m); return v / (a.length - 1); };
  /* Retorno esperado anual da ação (null = média histórica do período). */
  E.driftAnnual = function (drift, cdiAnnual, premium = 0.05, custom = null) {
    if (drift === "cdi") return cdiAnnual;
    if (drift === "cdi_premio") return cdiAnnual + premium;
    if (drift === "zero") return 0;
    if (drift === "personalizado") return custom == null ? cdiAnnual : custom;
    if (drift === "historico") return null;
    throw new Error("Drift inválido: " + drift);
  };
  /* Drift diário do bootstrap para que E[S_T] ≈ (1 + mu)^(N/252): ln(1+mu)/252 − ½·scale²·var(lr). */
  E.bootstrapDriftDaily = (lr, mu, scale = 1) => (mu == null ? null : Math.log1p(mu) / TD - 0.5 * scale * scale * varOf(lr));
  /* Bootstrap circular em blocos (resumo + amostra de caminhos). o.driftDaily troca a média e o.scale escala os
     desvios: lr* = drift + scale·(lr − média). Com o.up/o.dn, sorteia junto a máxima/mínima do dia; o.intraday
     faz o resumo (máximo/mínimo) usar esses extremos em vez do fechamento. */
  /* Correção martingal empírica (Duan e Simonato, 1998), ver martingale_factors no Python: fator de cada dia que faz
     a média dos caminhos bater com (1 + mu)^(j/252). pass(cb) roda a simulação chamando cb(j, S) para cada fechamento;
     a soma segue a mesma ordem do Python (caminho a caminho). */
  E.martingaleFactors = function (nPaths, N, mu, pass) {
    const sums = new Float64Array(N), f = new Float64Array(N);
    pass((j, v) => { sums[j] += v; });
    for (let j = 0; j < N; j++) f[j] = Math.pow(1 + mu, (j + 1) / TD) / (sums[j] / nPaths);
    return f;
  };
  /* o.mu (retorno esperado anual) liga a correção martingal (duas passadas com os mesmos sorteios). */
  E.blockBootstrapSummary = function (lr, nPaths, N, block = 20, seed = 42, keep = 0, o = {}) {
    if (lr.length < 2) throw new Error("Histórico insuficiente para o bootstrap.");
    block = Math.max(1, Math.min(block, lr.length));
    const L = lr.length, scale = o.scale ?? 1, hl = !!(o.up && o.dn);
    const raw = o.driftDaily == null && scale === 1, m = raw ? 0 : meanOf(lr), d = o.driftDaily == null ? m : o.driftDaily;
    const core = (f, cb, keepN) => {
      const rng = E.rng(seed), sT = new Float64Array(nPaths), runMax = new Float64Array(nPaths), runMin = new Float64Array(nPaths);
      const sample = [], sampleH = [], sampleL = [];
      for (let i = 0; i < nPaths; i++) {
        let x = 0, mx = -Infinity, mn = Infinity, j = 0, pos = 0, last = 0;
        const keepIt = sample.length < keepN;
        const row = keepIt ? new Float64Array(N) : null, rowH = keepIt && hl ? new Float64Array(N) : null, rowL = keepIt && hl ? new Float64Array(N) : null;
        while (j < N) {
          if (j % block === 0) pos = rng.int(L);
          const q = (pos + (j % block)) % L;
          x += raw ? lr[q] : d + scale * (lr[q] - m);
          const fj = f ? f[j] : 1, c = Math.exp(x) * fj;
          if (cb) { cb(j, Math.exp(x)); j++; continue; }
          const cu = hl ? Math.exp(x + scale * o.up[q]) * fj : c, cd = hl ? Math.exp(x + scale * o.dn[q]) * fj : c;
          const a = o.intraday && hl ? cu : c, b = o.intraday && hl ? cd : c;
          if (a > mx) mx = a; if (b < mn) mn = b;
          if (row) { row[j] = c; if (rowH) { rowH[j] = cu; rowL[j] = cd; } }
          last = c; j++;
        }
        if (cb) continue;
        sT[i] = last; runMax[i] = mx; runMin[i] = mn;
        if (row) { sample.push(row); if (rowH) { sampleH.push(rowH); sampleL.push(rowL); } }
      }
      return { sT, runMax, runMin, sample, sampleH: hl ? sampleH : null, sampleL: hl ? sampleL : null };
    };
    const f = o.mu != null ? E.martingaleFactors(nPaths, N, o.mu, (cb) => core(null, cb, 0)) : null;
    return core(f, null, keep);
  };
  /* Drift logarítmico diário do GBM: (ln(1 + mu) − σ²/2)·Δt, ou a média histórica. */
  E.gbmDriftDaily = function (lr, sigma, drift, cdiAnnual, premium = 0.05, custom = null) {
    const mu = E.driftAnnual(drift, cdiAnnual, premium, custom);
    return mu == null ? meanOf(lr) : (Math.log1p(mu) - 0.5 * sigma * sigma) / TD;
  };
  /* FHS-GARCH (padrão): parte da vol de hoje do GARCH/GJR e sorteia choques padronizados reais (com máxima e
     mínima do dia); o.garch reaproveita um ajuste já feito (cenários, calibração). */
  /* Média dos 3 métodos (padrão): FHS, bootstrap e GBM com nPaths/3 caminhos cada, juntos (média das probabilidades).
     Com o.volBlend (padrão), a vol do prazo do FHS é combinada com a realizada de 252 pregões (E.blendScale). */
  E.runMonteCarlo = function (s, P, N, cost, o = {}) {
    const method = o.method || "media", nPaths = o.nPaths || 10000, block = o.block || 20, drift = o.drift || "cdi";
    if (method === "media") return runEnsemble(s, P, N, cost, o, nPaths);
    const cdiAnnual = o.cdiAnnual ?? 0.10, seed = o.seed ?? 42, monitoring = o.monitoring || "close", extra = o.extra || 0;
    const premium = o.premium ?? 0.05, custom = o.custom ?? null, volScale = o.volScale ?? 1, keep = o.keep ?? E.EXIT_PATHS;
    const volModel = o.volModel || "gjr";
    const { lr, up, dn } = E.ohlcLogReturns(P);
    const g = method === "fhs_garch" ? o.garch || E.garchFit(lr, volModel, up, dn) : null;
    const blend = g && o.volBlend !== false ? E.blendScale(g, lr, N) : 1, volScaleEff = volScale * blend;
    const sigmaBase = g ? E.termVol(g, g.hNext, N) * blend : Math.sqrt(varOf(lr) * TD), sigma = sigmaBase * volScale, mu = E.driftAnnual(drift, cdiAnnual, premium, custom);
    let sum, shift = 0;
    if (method === "fhs_garch") {
      sum = E.fhsSummary(g, nPaths, N, seed, E.fhsDriftDaily(lr, mu, volScaleEff), volScaleEff, keep, monitoring === "intraday", o.martingale !== false ? mu : null);
    } else if (method === "bootstrap") {
      sum = E.blockBootstrapSummary(lr, nPaths, N, block, seed, keep, { driftDaily: E.bootstrapDriftDaily(lr, mu, volScale), scale: volScale, up, dn, intraday: monitoring === "intraday", mu: o.martingale !== false ? mu : null });
    } else if (method === "gbm") {
      sum = E.gbmSummary(nPaths, N, sigma, E.gbmDriftDaily(lr, sigma, drift, cdiAnnual, premium, custom), seed, true, keep);
      shift = monitoring === "intraday" ? E.BGK_BETA * sigma * Math.sqrt(1 / TD) : 0;
    } else throw new Error("Método inválido: " + method);
    const r = resultFrom(s, sum, cost, extra, shift);
    const n = sum.sT.length;
    r.cdi = new Float64Array(n).fill(Math.pow(1 + cdiAnnual, N / TD) - 1);
    r.cdiHoje = r.cdi[0];
    return Object.assign(r, { kind: "mc", N, n, nEff: n, sample: sum.sample, sampleH: sum.sampleH || null, sampleL: sum.sampleL || null,
      sampleV: sum.sampleV || null, garch: g, volModel, sigma, sigmaBase, volScale, volScaleEff, mu, premium, method, drift, block, seed, monitoring });
  };

  const probs = (r) => {
    let luc = 0, cdi = 0, bar = 0, sum = 0;
    for (let i = 0; i < r.n; i++) { const v = r.ret[i]; if (v > TOL) luc++; if (v > r.cdiHoje + TOL) cdi++; if (r.anyHit[i]) bar++; sum += v; }
    return { p_lucro: luc / r.n, p_cdi: cdi / r.n, p_barreira: r.events.length ? bar / r.n : NaN, media: sum / r.n };
  };
  const concat = (arrs) => { const out = new arrs[0].constructor(arrs.reduce((a, x) => a + x.length, 0)); let k = 0; for (const x of arrs) { out.set(x, k); k += x.length; } return out; };
  function runEnsemble(s, P, N, cost, o, nPaths) {
    let g = o.garch;
    if (!g) { const x = E.ohlcLogReturns(P); g = E.garchFit(x.lr, o.volModel || "gjr", x.up, x.dn); }
    const per = Math.ceil(nPaths / E.ENSEMBLE.length), keep = Math.ceil((o.keep ?? E.EXIT_PATHS) / E.ENSEMBLE.length);
    const parts = E.ENSEMBLE.map((m) => E.runMonteCarlo(s, P, N, cost, Object.assign({}, o, { method: m, nPaths: per, keep, garch: m === "fhs_garch" ? g : null })));
    const f = parts[0], cat = (k) => concat(parts.map((p) => p[k])), hits = {};
    for (const e of f.events) hits[e.key] = concat(parts.map((p) => p.hits[e.key]));
    const sample = [], k = Math.min(...parts.map((p) => p.sample.length));
    for (let i = 0; i < k; i++) for (const p of parts) sample.push(p.sample[i]); // intercalados: o gráfico mistura os três
    const r = { ret: cat("ret"), stock: cat("stock"), payoff: cat("payoff"), sT: cat("sT"), anyHit: cat("anyHit"), cdi: cat("cdi"), hits, events: f.events, retMax: f.retMax };
    const n = r.ret.length;
    return Object.assign(r, { kind: "mc", N, n, nEff: n, cdiHoje: f.cdiHoje, sample, sampleH: null, sampleL: null, sampleV: null, garch: g,
      volModel: f.volModel, sigma: f.sigma, sigmaBase: f.sigmaBase, volScale: f.volScale, volScaleEff: f.volScaleEff, mu: f.mu, premium: f.premium,
      method: "media", drift: f.drift, block: f.block, seed: f.seed, monitoring: f.monitoring,
      parts, partsSummary: parts.map((p) => Object.assign({ method: p.method, sigma: p.sigma }, probs(p))) });
  }

  E.SCENARIO_DRIFTS = ["zero", "cdi", "cdi_premio"];
  E.SCENARIO_VOLS = [0.6, 1.0, 1.3]; // ≈ percentis 10 e 90 do erro histórico da previsão de vol em 3 meses
  /* Grade de premissas do Monte Carlo (incerteza de premissa, não de sorteio): drift × vol, mesmos sorteios. */
  E.runScenarios = function (s, P, N, cost, o = {}) {
    const rows = [];
    if (["fhs_garch", "media"].includes(o.method || "media") && !o.garch) { const x = E.ohlcLogReturns(P); o = Object.assign({}, o, { garch: E.garchFit(x.lr, o.volModel || "gjr", x.up, x.dn) }); }
    for (const drift of E.SCENARIO_DRIFTS) for (const vs of E.SCENARIO_VOLS) {
      const r = E.runMonteCarlo(s, P, N, cost, Object.assign({}, o, { drift, volScale: vs, nPaths: o.nPaths || 5000, keep: 0 }));
      rows.push(Object.assign({ drift, mu: r.mu, volScale: vs, sigma: r.sigma }, probs(r)));
    }
    return rows;
  };

  /* ---------------- Ex-post ---------------- */
  E.runExPost = function (s, P, trade, expiry, cost, monitoring = "close", extra = 0) {
    if (expiry <= trade) throw new Error("O vencimento deve ser posterior à data de contratação.");
    const i0 = lastIndexOnOrBefore(P.d, trade);
    if (i0 < 0) throw new Error("Não há preço na data de contratação (ou antes dela) no histórico carregado.");
    const obs = E.previousBusinessDay(expiry, P.d);
    const iEnd = lastIndexOnOrBefore(P.d, obs);
    if (iEnd <= i0) throw new Error("Ainda não há pregões após a data de contratação no histórico carregado.");
    const s0 = P.c[i0], m = iEnd - i0;
    const close = new Float64Array(m), high = new Float64Array(m), low = new Float64Array(m);
    for (let k = 0; k < m; k++) { close[k] = P.c[i0 + 1 + k] / s0; high[k] = P.h[i0 + 1 + k] / s0; low[k] = P.l[i0 + 1 + k] / s0; }
    const ev = E.evaluatePaths(s, [close], [high], [low], monitoring);
    const payoff = ev.payoff[0];
    const hits = E.events(s).map((e) => { const j = E.firstHitIndex(close, e, high, low, monitoring); return { event: e, label: E.eventLabel(e), hit: j >= 0, date: j >= 0 ? P.d[i0 + 1 + j] : null }; });
    return {
      tradeDate: P.d[i0], obsDate: obs, expiry, lastDate: P.d[iEnd], finished: P.d[iEnd] >= obs, s0, nElapsed: m,
      dates: P.d.slice(i0, iEnd + 1), prices: Array.from(P.c.slice(i0, iEnd + 1)),
      highs: [s0].concat(Array.from(high, (v) => v * s0)), lows: [s0].concat(Array.from(low, (v) => v * s0)),
      payoff, ret: E.returnsFromPayoff(payoff, cost, E.hasStock(s), extra), stockRet: close[m - 1] - 1, hits,
    };
  };

  /* ---------------- Métricas ---------------- */
  const sorted = (a) => Float64Array.from(a).sort();
  const pctile = (s, p) => { // interpolação linear (igual ao numpy.percentile padrão)
    const h = (s.length - 1) * p / 100, lo = Math.floor(h), hi = Math.ceil(h);
    return s[lo] + (s[hi] - s[lo]) * (h - lo);
  };
  const mean = (a) => { let m = 0; for (let i = 0; i < a.length; i++) m += a[i]; return m / a.length; };
  const frac = (a, fn) => { let k = 0; for (let i = 0; i < a.length; i++) if (fn(a[i], i)) k++; return k / a.length; };
  E.annualize = (r, N) => (r == null || !isFinite(r) || r <= -1 ? NaN : Math.pow(1 + r, TD / N) - 1);

  E.Z95 = 1.959963984540054; E.EFFECTIVE_FACTOR = 1.5;
  /* Amostra efetiva de n janelas sobrepostas de N pregões para o IC: 1,5 × janelas não sobrepostas (fator
     calibrado por simulação: o intervalo de Wilson cobre 94%–97%; o block bootstrap anterior cobria 82%–90%). */
  E.effectiveSample = (n, N) => Math.max(1, E.EFFECTIVE_FACTOR * n / Math.max(1, N));
  /* Intervalo de Wilson para uma proporção p em nEff observações independentes: fica em [0, 1] e não degenera
     quando p = 0 ou 1 (com p = 0, o limite superior é z²/(n + z²)). */
  E.wilsonCi = function (p, nEff, z = E.Z95) {
    if (!(nEff > 0) || p !== p) return [NaN, NaN];
    const den = 1 + z * z / nEff, center = (p + z * z / (2 * nEff)) / den;
    const half = z * Math.sqrt(p * (1 - p) / nEff + z * z / (4 * nEff * nEff)) / den;
    return [Math.max(0, center - half), Math.min(1, center + half)];
  };
  /* CVaR (expected shortfall): média dos q piores resultados (pelo menos um). */
  E.cvar = function (r, q = 0.05) { const s = sorted(r), k = Math.max(1, Math.ceil(q * s.length)); let m = 0; for (let i = 0; i < k; i++) m += s[i]; return m / k; };

  E.summarize = function (res) {
    const r = res.ret, st = res.stock, sr = sorted(r), ss = sorted(st);
    const out = {
      n: r.length, nEff: res.nEff,
      p_lucro: frac(r, (v) => v > TOL), p_perda: frac(r, (v) => v < -TOL), p_zero: frac(r, (v) => Math.abs(v) <= TOL),
      p_max: res.retMax == null ? NaN : frac(r, (v) => v >= res.retMax - 1e-6),
      media: mean(r), mediana: pctile(sr, 50), p5: pctile(sr, 5), p25: pctile(sr, 25), p75: pctile(sr, 75), p95: pctile(sr, 95),
      pior: sr[0], melhor: sr[sr.length - 1],
      acao_media: mean(st), acao_mediana: pctile(ss, 50), acao_p_lucro: frac(st, (v) => v > TOL),
      p_bate_acao: frac(r, (v, i) => v > st[i] + TOL),
      barreiras: res.events.map((e) => ({ label: E.eventLabel(e), p: mean(res.hits[e.key]) })),
    };
    out.cvar5 = E.cvar(r, 0.05);
    out.p_barreira = res.events.length ? mean(res.anyHit) : NaN;
    out.media_anual = E.annualize(out.media, res.N);
    out.mediana_anual = E.annualize(out.mediana, res.N);
    out.acao_media_anual = E.annualize(out.acao_media, res.N);
    // régua do CDI: de hoje (padrão) e da época de cada janela (secundária, só no histórico)
    const hoje = res.cdiHoje != null, ref = (i) => (hoje ? res.cdiHoje : res.cdi[i]);
    out.p_cdi = hoje || res.cdi ? frac(r, (v, i) => v > ref(i) + TOL) : NaN;
    out.cdi_hoje = hoje ? res.cdiHoje : NaN;
    // retorno médio − CDI de hoje no prazo: no Monte Carlo neutro (retorno esperado = CDI), o custo embutido da estrutura
    out.excesso_cdi = hoje ? out.media - res.cdiHoje : NaN;
    if (res.cdi && res.kind === "historico") {
      const base = res.retRaw || r;
      out.p_cdi_epoca = frac(base, (v, i) => v > res.cdi[i] + TOL);
      out.cdi_medio = mean(res.cdi);
      out.cdi_medio_anual = E.annualize(out.cdi_medio, res.N);
    } else out.p_cdi_epoca = out.cdi_medio = out.cdi_medio_anual = NaN;
    out.ci = {};
    if (res.kind === "historico") {
      const nEff = E.effectiveSample(r.length, res.N), ci = (p) => E.wilsonCi(p, nEff);
      out.n_ef_ic = nEff;
      out.ci.p_lucro = ci(out.p_lucro);
      out.ci.p_perda = ci(out.p_perda);
      if (hoje || res.cdi) out.ci.p_cdi = ci(out.p_cdi);
      if (res.events.length) out.ci.p_barreira = ci(out.p_barreira);
    }
    return out;
  };

  E.METRIC_ROWS = [
    ["n", "Nº de janelas / caminhos", "int"], ["nEff", "Amostra efetiva (janelas não sobrepostas)", "int"],
    ["p_lucro", "P(lucro > 0)", "pct"], ["p_cdi", "P(retorno > CDI de hoje)", "pct"], ["p_barreira", "P(barreira acionada)", "pct"],
    ["p_perda", "P(perda)", "pct"], ["p_cdi_epoca", "P(retorno > CDI da época)", "pct"], ["p_zero", "P(retorno = 0)", "pct"], ["p_max", "P(atingir o retorno máximo)", "pct"], ["@barreiras", "", ""],
    ["media", "Retorno médio", "pct"], ["media_anual", "Retorno médio anualizado (base 252)", "pct"], ["excesso_cdi", "Retorno médio − CDI de hoje (no prazo)", "pct"], ["mediana", "Mediana", "pct"],
    ["p5", "Percentil 5", "pct"], ["cvar5", "CVaR 5% (média dos 5% piores)", "pct"], ["p25", "Percentil 25", "pct"], ["p75", "Percentil 75", "pct"], ["p95", "Percentil 95", "pct"],
    ["pior", "Pior", "pct"], ["melhor", "Melhor", "pct"],
    ["acao_media", "Só a ação: retorno médio", "pct"], ["acao_media_anual", "Só a ação: retorno médio anualizado", "pct"],
    ["acao_mediana", "Só a ação: mediana", "pct"], ["acao_p_lucro", "Só a ação: P(lucro > 0)", "pct"],
    ["p_bate_acao", "P(estrutura > só a ação)", "pct"], ["cdi_hoje", "CDI de hoje no prazo", "pct"],
    ["cdi_medio", "CDI médio da época (janelas)", "pct"], ["cdi_medio_anual", "CDI médio da época, anualizado", "pct"],
  ];

  /* ---------------- Quadro de rentabilidade (formato das lâminas) ---------------- */
  E.defaultVariations = function (s) {
    const vs = new Set([-0.30, -0.20, -0.10, 0, 0.10, 0.20, 0.30]);
    const r2 = (x) => Math.round(x * 1e6) / 1e6;
    E.strikes(s).forEach((k) => vs.add(Math.floor(r2(100 * (k - 1))) / 100));
    E.events(s).forEach((e) => {
      if (e.dir === "up") { const edge = Math.floor(r2(100 * (e.level - 1))) / 100; vs.add(edge); vs.add(edge + 0.10); }
      else { const edge = Math.ceil(r2(100 * (e.level - 1))) / 100; vs.add(edge); vs.add(edge - 0.10); }
    });
    return [...new Set([...vs].map((v) => Math.round(v * 1e4) / 1e4))].filter((v) => v >= -0.95 && v <= 3).sort((a, b) => a - b);
  };
  /* Linhas: variação da ação; colunas: retorno sem toque / com toque (null = cenário impossível). */
  E.profitabilityTable = function (s, cost, variations, extra = 0) {
    const vs = variations.slice().sort((a, b) => a - b), hasEv = E.events(s).length > 0;
    const branches = hasEv ? ["none", "all"] : ["none"];
    return {
      columns: hasEv ? ["Barreira não atingida", "Barreira atingida"] : ["Retorno da estrutura"],
      rows: vs.map((v) => ({ v, values: branches.map((b) => { const p = E.payoffAt(s, 1 + v, b); return isFinite(p) ? E.returnsFromPayoff(p, cost, E.hasStock(s), extra) : null; }) })),
    };
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
