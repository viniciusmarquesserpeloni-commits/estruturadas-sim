/* Backtest, calendário e métricas — porta de estruturadas/backtest.py, data.py e metrics.py.
   Séries de preços: { d: ["AAAA-MM-DD", ...], c: Float64Array, h, l } (datas ISO comparam como texto). */
(function (root) {
  "use strict";
  const E = root.Estr;
  const TD = 252, TOL = 1e-9;
  E.DRIFT_LABELS = { historico: "Histórico", zero: "Zero", cdi: "CDI" };
  E.MC_METHOD_LABELS = { bootstrap: "Bootstrap em blocos", gbm: "GBM (log-normal)" };
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

  /* Para cada data inicial t com N pregões à frente: caminho = P[t+1 : t+N] / P[t]. */
  E.runHistorical = function (s, P, N, cost, monitoring = "close", extra = 0, cdiF = null) {
    if (!(N >= 1)) throw new Error("O prazo deve ter pelo menos 1 pregão.");
    const n = P.c.length - N;
    if (n <= 0) throw new Error(`Histórico insuficiente: ${P.c.length} pregões para um prazo de ${N}.`);
    const intra = monitoring === "intraday";
    const sT = new Float64Array(n), runMax = new Float64Array(n), runMin = new Float64Array(n);
    for (let t = 0; t < n; t++) {
      const base = P.c[t];
      let mx = -Infinity, mn = Infinity;
      for (let j = t + 1; j <= t + N; j++) {
        const c = P.c[j], up = intra ? Math.max(P.h[j], c) : c, dn = intra ? Math.min(P.l[j], c) : c;
        if (up > mx) mx = up; if (dn < mn) mn = dn;
      }
      sT[t] = P.c[t + N] / base; runMax[t] = mx / base; runMin[t] = mn / base;
    }
    const r = resultFrom(s, { sT, runMax, runMin }, cost, extra, 0);
    r.start = P.d.slice(0, n); r.end = P.d.slice(N, N + n);
    if (cdiF) { r.cdi = new Float64Array(n); for (let t = 0; t < n; t++) r.cdi[t] = cdiF[t + N] / cdiF[t] - 1; }
    return Object.assign(r, { kind: "historico", N, n, nEff: Math.ceil(n / N), monitoring });
  };

  /* ---------------- Monte Carlo ---------------- */
  E.logReturns = function (P) {
    const out = [];
    for (let i = 1; i < P.c.length; i++) { const v = Math.log(P.c[i] / P.c[i - 1]); if (isFinite(v)) out.push(v); }
    return Float64Array.from(out);
  };
  /* Bootstrap circular em blocos dos log-retornos diários (resumo + amostra de caminhos). */
  E.blockBootstrapSummary = function (lr, nPaths, N, block = 20, seed = 42, keep = 0) {
    if (lr.length < 2) throw new Error("Histórico insuficiente para o bootstrap.");
    block = Math.max(1, Math.min(block, lr.length));
    const rng = E.rng(seed), L = lr.length;
    const sT = new Float64Array(nPaths), runMax = new Float64Array(nPaths), runMin = new Float64Array(nPaths), sample = [];
    for (let i = 0; i < nPaths; i++) {
      let x = 0, mx = -Infinity, mn = Infinity, j = 0, pos = 0;
      const row = sample.length < keep ? new Float64Array(N) : null;
      while (j < N) {
        if (j % block === 0) pos = rng.int(L);
        x += lr[(pos + (j % block)) % L];
        if (x > mx) mx = x; if (x < mn) mn = x;
        if (row) row[j] = Math.exp(x);
        j++;
      }
      sT[i] = Math.exp(x); runMax[i] = Math.exp(mx); runMin[i] = Math.exp(mn);
      if (row) sample.push(row);
    }
    return { sT, runMax, runMin, sample };
  };
  E.gbmDriftDaily = function (lr, sigma, drift, cdiAnnual) {
    const dt = 1 / TD;
    if (drift === "historico") return lr.reduce((a, b) => a + b, 0) / lr.length;
    if (drift === "zero") return -0.5 * sigma * sigma * dt;
    if (drift === "cdi") return (Math.log1p(cdiAnnual) - 0.5 * sigma * sigma) * dt;
    throw new Error("Drift inválido: " + drift);
  };
  E.runMonteCarlo = function (s, P, N, cost, o = {}) {
    const method = o.method || "bootstrap", nPaths = o.nPaths || 10000, block = o.block || 20, drift = o.drift || "historico";
    const cdiAnnual = o.cdiAnnual ?? 0.10, seed = o.seed ?? 42, monitoring = o.monitoring || "close", extra = o.extra || 0;
    const lr = E.logReturns(P);
    const m = lr.reduce((a, b) => a + b, 0) / lr.length;
    const sigma = Math.sqrt(lr.reduce((a, b) => a + (b - m) * (b - m), 0) / (lr.length - 1) * TD);
    const sum = method === "bootstrap" ? E.blockBootstrapSummary(lr, nPaths, N, block, seed, E.EXIT_PATHS)
      : E.gbmSummary(nPaths, N, sigma, E.gbmDriftDaily(lr, sigma, drift, cdiAnnual), seed, true, E.EXIT_PATHS);
    const shift = monitoring === "intraday" ? E.BGK_BETA * sigma * Math.sqrt(1 / TD) : 0;
    const r = resultFrom(s, sum, cost, extra, shift);
    const n = sum.sT.length;
    r.cdi = new Float64Array(n).fill(Math.pow(1 + cdiAnnual, N / TD) - 1);
    return Object.assign(r, { kind: "mc", N, n, nEff: n, sample: sum.sample, sigma, method, drift, block, seed, monitoring });
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
    out.media_anual = E.annualize(out.media, res.N);
    out.mediana_anual = E.annualize(out.mediana, res.N);
    out.acao_media_anual = E.annualize(out.acao_media, res.N);
    if (res.cdi) {
      out.p_cdi = frac(r, (v, i) => v > res.cdi[i] + TOL);
      out.cdi_medio = mean(res.cdi);
      out.cdi_medio_anual = E.annualize(out.cdi_medio, res.N);
    } else out.p_cdi = out.cdi_medio = out.cdi_medio_anual = NaN;
    return out;
  };

  E.METRIC_ROWS = [
    ["n", "Nº de janelas / caminhos", "int"], ["nEff", "Amostra efetiva (janelas não sobrepostas)", "int"],
    ["p_lucro", "P(lucro > 0)", "pct"], ["p_cdi", "P(retorno > CDI do período)", "pct"], ["p_perda", "P(perda)", "pct"],
    ["p_zero", "P(retorno = 0)", "pct"], ["p_max", "P(atingir o retorno máximo)", "pct"], ["@barreiras", "", ""],
    ["media", "Retorno médio", "pct"], ["media_anual", "Retorno médio anualizado (base 252)", "pct"], ["mediana", "Mediana", "pct"],
    ["p5", "Percentil 5", "pct"], ["p25", "Percentil 25", "pct"], ["p75", "Percentil 75", "pct"], ["p95", "Percentil 95", "pct"],
    ["pior", "Pior", "pct"], ["melhor", "Melhor", "pct"],
    ["acao_media", "Só a ação: retorno médio", "pct"], ["acao_media_anual", "Só a ação: retorno médio anualizado", "pct"],
    ["acao_mediana", "Só a ação: mediana", "pct"], ["acao_p_lucro", "Só a ação: P(lucro > 0)", "pct"],
    ["p_bate_acao", "P(estrutura > só a ação)", "pct"], ["cdi_medio", "CDI médio do período", "pct"], ["cdi_medio_anual", "CDI médio anualizado", "pct"],
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
