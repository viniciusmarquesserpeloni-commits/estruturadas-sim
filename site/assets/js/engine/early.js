/* Saída antecipada — porta de estruturadas/early_exit.py (+ métricas de metrics.py).
   Quando o retorno acumulado da estrutura (líquido do spread de saída) atinge o gatilho (150% do CDI
   acumulado), o investidor é orientado a desmontar; com o OK dele, a desmontagem ocorre `delay` pregões
   depois, pelo valor daquele dia. Marcação a modelo: Black-Scholes para vanilla e Reiner-Rubinstein para
   barreiras (com BGK para monitoramento diário), vol realizada móvel + adicional, calibrada ao preço pago. */
(function (root) {
  "use strict";
  const E = root.Estr;
  const TD = 252, TOL = 1e-9;
  const N_ = (x) => E.cnd(x);
  E.VOL_MODE_LABELS = { garch: "Vol GARCH do prazo restante + adicional", rolling: "Vol realizada móvel + adicional", fixed: "Vol da contratação + adicional (fixa)" };
  E.EXIT_DEFAULTS = { trigger: 1.5, exitSpread: 0.01, delay: 1, minDays: 0, volMode: "garch", volModel: "gjr", volWindow: 63, volAdd: 0.03, mcPaths: 2000, calibrate: true };

  /* Ajuste GARCH sobre os fechamentos (h[i] = variância prevista no fechamento do pregão i para o dia seguinte);
     null se o histórico for curto (a marcação volta para a vol móvel). */
  E.garchVariance = function (c, model = "gjr", g = null) {
    const lr = new Float64Array(c.length - 1);
    for (let i = 1; i < c.length; i++) lr[i - 1] = Math.log(c[i] / c[i - 1]);
    try { g = g || E.garchFit(lr, model); } catch (e) { return null; }
    return g.h.length === lr.length + 1 ? g : null;
  };

  /* Opção com barreira de monitoramento contínuo, sem rebate (Reiner-Rubinstein / Haug). */
  E.barrierPrice = function (kind, barrier, S, K, H, T, r, q, sig) {
    const b = r - q, sT = sig * Math.sqrt(T), mu = (b - 0.5 * sig * sig) / (sig * sig);
    const x1 = Math.log(S / K) / sT + (1 + mu) * sT, x2 = Math.log(S / H) / sT + (1 + mu) * sT;
    const y1 = Math.log((H * H) / (S * K)) / sT + (1 + mu) * sT, y2 = Math.log(H / S) / sT + (1 + mu) * sT;
    const eq = Math.exp((b - r) * T), er = Math.exp(-r * T);
    const eta = barrier.startsWith("up") ? -1 : 1, phi = kind === "call" ? 1 : -1;
    const hs1 = Math.pow(H / S, 2 * (mu + 1)), hs2 = Math.pow(H / S, 2 * mu);
    const A = phi * S * eq * N_(phi * x1) - phi * K * er * N_(phi * x1 - phi * sT);
    const B = phi * S * eq * N_(phi * x2) - phi * K * er * N_(phi * x2 - phi * sT);
    const C = phi * S * eq * hs1 * N_(eta * y1) - phi * K * er * hs2 * N_(eta * y1 - eta * sT);
    const D = phi * S * eq * hs1 * N_(eta * y2) - phi * K * er * hs2 * N_(eta * y2 - eta * sT);
    const above = K > H;
    switch (kind + ":" + barrier) {
      case "call:up_in": return above ? A : B - C + D;
      case "call:up_out": return above ? 0 : A - B + C - D;
      case "call:down_in": return above ? C : A - B + D;
      case "call:down_out": return above ? A - C : B - D;
      case "put:up_in": return above ? A - B + D : C;
      case "put:up_out": return above ? B - D : A - C;
      case "put:down_in": return above ? B - C + D : A;
      case "put:down_out": return above ? A - B + C - D : 0;
    }
    throw new Error("Barreira inválida: " + barrier);
  };

  /* Valor da estrutura (S0 = 1) com prazo restante T > 0. monitoring "close" afasta a barreira (BGK). */
  E.structureValue = function (s, S, runMax, runMin, T, r, sig, monitoring = "close", q = 0) {
    sig = Math.min(2, Math.max(0.05, sig));
    const shift = monitoring === "close" ? E.BGK_BETA * sig * Math.sqrt(1 / TD) : 0;
    let total = 0;
    for (const l of s.legs) {
      let v;
      if (l.kind === "stock") v = S;
      else {
        const van = E.bsPrice(l.kind, S, l.strike, T, r, q, sig);
        if (!E.hasBarrier(l)) v = van;
        else {
          const B = l.level, up = E.barrierDir(l) === "up";
          const hit = up ? runMax >= B - 1e-12 : runMin <= B + 1e-12;
          const ifHit = E.knock(l) === "in" ? van : 0;
          const H = up ? B * Math.exp(shift) : B * Math.exp(-shift);
          const beyond = up ? S >= H : S <= H;
          v = hit || beyond ? ifHit : E.barrierPrice(l.kind, l.barrier, S, l.strike, H, T, r, q, sig);
        }
      }
      total += l.position * l.ratio * v;
    }
    return total;
  };

  /* Vol realizada anualizada com os `window` log-retornos até cada dia; início sem janela completa
     recebe a primeira vol disponível (igual ao pandas rolling().std() + bfill). */
  E.rollingVol = function (c, window = 63) {
    const n = c.length, out = new Float64Array(n), lr = new Float64Array(n);
    for (let i = 1; i < n; i++) lr[i] = Math.log(c[i] / c[i - 1]);
    let first = -1;
    for (let i = window; i < n; i++) {
      let m = 0;
      for (let j = i - window + 1; j <= i; j++) m += lr[j];
      m /= window;
      let v = 0;
      for (let j = i - window + 1; j <= i; j++) v += (lr[j] - m) * (lr[j] - m);
      out[i] = Math.sqrt(v / (window - 1) * TD);
      if (first < 0) first = i;
    }
    const fill = first >= 0 ? out[first] : 0.30;
    for (let i = 0; i < (first >= 0 ? first : n); i++) out[i] = fill;
    return out;
  };
  /* Taxa contínua anual do CDI em cada pregão: 252·ln(1 + CDI do dia). */
  E.cdiRateSeries = function (F) {
    const n = F.length, out = new Float64Array(n);
    if (n < 2) return out;
    for (let i = 1; i < n; i++) out[i] = TD * Math.log1p(Math.max(F[i] / F[i - 1] - 1, 0));
    out[0] = out[1];
    return out;
  };

  const paidValue = (s, cost) => (E.hasStock(s) ? 1 + cost : cost);
  const offsetOf = (s, cost, cfg, N, r0, sig0, monitoring) => (cfg.calibrate ? paidValue(s, cost) - E.structureValue(s, 1, 1, 1, N / TD, r0, sig0, monitoring) : 0);

  /* Regra de saída num caminho de N pregões. get(k) devolve {S, up, down, r, sig, cdi} do dia k (1..N). */
  function exitPath(s, N, get, cost, cfg, retHold, monitoring, extra, r0, sig0) {
    const off = offsetOf(s, cost, cfg, N, r0, sig0, monitoring), hasStock = E.hasStock(s);
    let runMax = -Infinity, runMin = Infinity, trig = 0, exitDay = 0, retExit = null;
    for (let k = 1; k < N; k++) {
      const d = get(k);
      if (d.up > runMax) runMax = d.up;
      if (d.down < runMin) runMin = d.down;
      if (trig && k < exitDay) continue;
      const v = E.structureValue(s, d.S, runMax, runMin, (N - k) / TD, d.r, d.sig, monitoring) + off * (N - k) / N;
      const ret = E.returnsFromPayoff(v, cost, hasStock, extra) - cfg.exitSpread;
      if (trig && k === exitDay) { retExit = ret; break; }
      if (!trig && ret >= cfg.trigger * d.cdi && ret > 0 && k >= Math.max(cfg.minDays, 1)) {
        trig = k; exitDay = k + cfg.delay;
        if (exitDay === k) { retExit = ret; break; }
        if (exitDay >= N) break;
      }
    }
    const early = trig > 0 && exitDay < N && retExit != null;
    const day = early ? exitDay : N;
    return { triggered: trig > 0, triggerDay: trig, early, exitDay: day, retFinal: early ? retExit : retHold, cdi: get(day, true).cdi };
  }

  function pack(rows, retHold, N, extraCols = {}) {
    const n = rows.length;
    const out = { N, n, triggered: new Uint8Array(n), triggerDay: new Int32Array(n), early: new Uint8Array(n), exitDay: new Int32Array(n),
      retFinal: new Float64Array(n), retHold: Float64Array.from(retHold.slice(0, n)), cdiPeriod: new Float64Array(n) };
    rows.forEach((x, i) => { out.triggered[i] = x.triggered ? 1 : 0; out.triggerDay[i] = x.triggerDay; out.early[i] = x.early ? 1 : 0;
      out.exitDay[i] = x.exitDay; out.retFinal[i] = x.retFinal; out.cdiPeriod[i] = x.cdi; });
    return Object.assign(out, extraCols);
  }

  /* Saída antecipada em todas as janelas históricas (mesmas janelas de runHistorical). */
  /* Com regimeAdjust (e cdiRef): caminhos re-ancorados no CDI de hoje e CDI de hoje no gatilho e na marcação
     (retHold deve vir do runHistorical com o mesmo ajuste). */
  E.runHistoricalExit = function (s, P, N, cost, cfg, cdiF, retHold, monitoring = "close", extra = 0, cdiRef = null, regimeAdjust = false, garch = null) {
    cfg = Object.assign({}, E.EXIT_DEFAULTS, cfg);
    const n = P.c.length - N, rates = E.cdiRateSeries(cdiF), rv = E.rollingVol(P.c, cfg.volWindow).map((v) => v + cfg.volAdd);
    const g = cfg.volMode === "garch" ? E.garchVariance(P.c, cfg.volModel, garch) : null;
    const sigAt = (t, i, k) => (g ? E.termVol(g, g.h[i], N - k) + cfg.volAdd : cfg.volMode === "fixed" ? rv[t] : rv[i]);
    const intra = monitoring === "intraday", rows = [], cdiStart = new Float64Array(n), adj = !!(regimeAdjust && cdiRef != null);
    const rRef = adj ? Math.log1p(cdiRef) : 0;
    for (let t = 0; t < n; t++) {
      const base = P.c[t];
      const get = (k) => {
        const i = t + k, f = adj ? Math.pow(1 + cdiRef, k / TD) / (cdiF[i] / cdiF[t]) : 1, S = (P.c[i] / base) * f;
        return { S, up: intra ? Math.max((P.h[i] / base) * f, S) : S, down: intra ? Math.min((P.l[i] / base) * f, S) : S,
          r: adj ? rRef : rates[i], sig: sigAt(t, i, k), cdi: adj ? Math.pow(1 + cdiRef, k / TD) - 1 : cdiF[i] / cdiF[t] - 1 };
      };
      rows.push(exitPath(s, N, get, cost, cfg, retHold[t], monitoring, extra, adj ? rRef : rates[t], g ? E.termVol(g, g.h[t], N) + cfg.volAdd : rv[t]));
      cdiStart[t] = Math.expm1(rates[t]);
    }
    return pack(rows, retHold, N, { cdiStart, start: P.d.slice(0, n), kind: "historico", cfg });
  };

  /* Saída antecipada nos caminhos completos guardados pelo Monte Carlo (CDI constante).
     high/low: máximas e mínimas sorteadas (bootstrap, FHS; intradiário sem BGK); sem elas, toques pela barreira
     deslocada. varPaths + garch (FHS): marcação com a vol GARCH do prazo restante de cada caminho. */
  E.runMcExit = function (s, paths, N, cost, cfg, retHold, sigmaHist, cdiAnnual, monitoring = "close", extra = 0, high = null, low = null, varPaths = null, garch = null, volScale = 1) {
    cfg = Object.assign({}, E.EXIT_DEFAULTS, cfg);
    const m = Math.min(cfg.mcPaths, paths.length), r = Math.log1p(cdiAnnual), sig = sigmaHist + cfg.volAdd;
    const gv = varPaths && garch && cfg.volMode !== "fixed";
    const hl = monitoring === "intraday" && high && low;
    const hs = monitoring === "intraday" && !hl ? E.BGK_BETA * sigmaHist * Math.sqrt(1 / TD) : 0, eu = Math.exp(hs), ed = Math.exp(-hs);
    const mon = monitoring === "intraday" ? "continuous" : "close", rows = [];
    for (let p = 0; p < m; p++) {
      const row = paths[p], rh = hl ? high[p] : null, rl = hl ? low[p] : null, rv = gv ? varPaths[p] : null;
      const get = (k) => { const S = row[k - 1]; return { S, up: rh ? rh[k - 1] : S * eu, down: rl ? rl[k - 1] : S * ed, r,
        sig: rv ? volScale * E.termVol(garch, rv[k - 1], N - k) + cfg.volAdd : sig, cdi: Math.pow(1 + cdiAnnual, k / TD) - 1 }; };
      rows.push(exitPath(s, N, get, cost, cfg, retHold[p], mon, extra, r, sig));
    }
    return pack(rows, retHold, N, { kind: "mc", cfg });
  };

  /* Marcação diária e gatilho no caminho realizado de uma operação (nTotal = pregões até a apuração). */
  E.runExPostExit = function (s, P, trade, nTotal, cost, cfg, cdiF, monitoring = "close", extra = 0) {
    cfg = Object.assign({}, E.EXIT_DEFAULTS, cfg);
    const i0 = E.lastIndexOnOrBefore(P.d, trade);
    if (i0 < 0) return null;
    const m = Math.min(nTotal, P.c.length - 1 - i0);
    if (m < 1) return null;
    const s0 = P.c[i0], rates = E.cdiRateSeries(cdiF), rv = E.rollingVol(P.c, cfg.volWindow).map((v) => v + cfg.volAdd);
    const g = cfg.volMode === "garch" ? E.garchVariance(P.c, cfg.volModel) : null;
    const sigAt = (i, k) => (g ? E.termVol(g, g.h[i], nTotal - k) + cfg.volAdd : cfg.volMode === "fixed" ? rv[i0] : rv[i]);
    const off = offsetOf(s, cost, cfg, nTotal, rates[i0], g ? E.termVol(g, g.h[i0], nTotal) + cfg.volAdd : rv[i0], monitoring), intra = monitoring === "intraday";
    const dates = [], ret = new Float64Array(m), threshold = new Float64Array(m);
    let runMax = -Infinity, runMin = Infinity, trig = -1;
    for (let j = 0; j < m; j++) {
      const k = j + 1, i = i0 + k, S = P.c[i] / s0;
      runMax = Math.max(runMax, intra ? Math.max(P.h[i] / s0, S) : S);
      runMin = Math.min(runMin, intra ? Math.min(P.l[i] / s0, S) : S);
      dates.push(P.d[i]);
      threshold[j] = cfg.trigger * (cdiF[i] / cdiF[i0] - 1);
      if (k < nTotal) {
        const v = E.structureValue(s, S, runMax, runMin, (nTotal - k) / TD, rates[i], sigAt(i, k), monitoring) + off * (nTotal - k) / nTotal;
        ret[j] = E.returnsFromPayoff(v, cost, E.hasStock(s), extra) - cfg.exitSpread;
      } else ret[j] = NaN;
      if (trig < 0 && ret[j] >= threshold[j] && ret[j] > 0 && k >= Math.max(cfg.minDays, 1)) trig = j;
    }
    let exitDate = null, exitReturn = null;
    if (trig >= 0) { const e = trig + cfg.delay; if (e < m && e + 1 < nTotal) { exitDate = dates[e]; exitReturn = ret[e]; } }
    return { dates, ret, threshold, triggerDate: trig >= 0 ? dates[trig] : null, exitDate, exitReturn };
  };

  /* ---------------- Métricas ---------------- */
  const pct = (sorted, p) => { const h = (sorted.length - 1) * p / 100, lo = Math.floor(h), hi = Math.ceil(h); return sorted[lo] + (sorted[hi] - sorted[lo]) * (h - lo); };
  const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
  E.summarizeExit = function (x) {
    const n = x.n, r = Array.from(x.retFinal), days = Array.from(x.exitDay), ex = [];
    for (let i = 0; i < n; i++) if (x.early[i]) ex.push(x.exitDay[i]);
    ex.sort((a, b) => a - b);
    const ann = r.map((v, i) => Math.pow(1 + v, TD / days[i]) - 1).sort((a, b) => a - b);
    const pcdi = r.map((v, i) => (x.cdiPeriod[i] > 0 ? v / x.cdiPeriod[i] : NaN)).filter((v) => isFinite(v)).sort((a, b) => a - b);
    const rs = r.slice().sort((a, b) => a - b);
    let trig = 0, early = 0, lucro = 0, perda = 0, cdi = 0, exitRet = 0;
    for (let i = 0; i < n; i++) {
      trig += x.triggered[i]; early += x.early[i]; if (x.early[i]) exitRet += r[i];
      if (r[i] > TOL) lucro++; if (r[i] < -TOL) perda++; if (r[i] > x.cdiPeriod[i] + TOL) cdi++;
    }
    return {
      ci: x.kind === "historico" ? { p_saida: E.blockBootstrapCi(Float64Array.from(x.early), x.N) } : {}, cvar5: E.cvar(r, 0.05),
      n, p_gatilho: trig / n, p_saida: early / n,
      dias_p25: ex.length ? pct(ex, 25) : NaN, dias_mediana: ex.length ? pct(ex, 50) : NaN, dias_p75: ex.length ? pct(ex, 75) : NaN,
      ret_saida_media: early ? exitRet / early : NaN, media: mean(r), mediana: pct(rs, 50), media_venc: mean(Array.from(x.retHold)),
      p_lucro: lucro / n, p_perda: perda / n, p_cdi: cdi / n, pct_cdi_mediana: pcdi.length ? pct(pcdi, 50) : NaN,
      anual_mediana: pct(ann, 50), dias_medio: mean(days),
    };
  };
  E.EXIT_ROWS = [
    ["p_gatilho", "P(gatilho atingido)", "pct"], ["p_saida", "P(saída antes do vencimento)", "pct"],
    ["dias_mediana", "Dia mediano da saída (pregões)", "int"], ["dias_medio", "Prazo médio investido (pregões)", "int"],
    ["ret_saida_media", "Retorno médio nas saídas antecipadas", "pct"], ["media", "Retorno médio (com saída)", "pct"],
    ["media_venc", "Retorno médio levando ao vencimento", "pct"], ["mediana", "Retorno mediano (com saída)", "pct"],
    ["anual_mediana", "Retorno anualizado mediano (com saída)", "pct"], ["p_lucro", "P(lucro > 0) com saída", "pct"],
    ["p_perda", "P(perda) com saída", "pct"], ["p_cdi", "P(retorno > CDI do período investido)", "pct"],
    ["pct_cdi_mediana", "% do CDI mediano (período investido)", "pct"],
  ];
  E.CDI_REGIMES = [[0, 0.08, "CDI até 8% a.a."], [0.08, 0.12, "CDI entre 8% e 12% a.a."], [0.12, 1, "CDI acima de 12% a.a."]];
  /* Janelas históricas agrupadas pelo CDI no início: o nível de juros muda o valor da estrutura e a régua. */
  E.exitByCdiRegime = function (x) {
    return E.CDI_REGIMES.map(([lo, hi, label]) => {
      const idx = [];
      for (let i = 0; i < x.n; i++) if (x.cdiStart[i] > lo && x.cdiStart[i] <= hi) idx.push(i);
      if (!idx.length) return null;
      const ex = idx.filter((i) => x.early[i]).map((i) => x.exitDay[i]).sort((a, b) => a - b);
      return { label, n: idx.length, pSaida: ex.length / idx.length, diaMediano: ex.length ? pct(ex, 50) : NaN,
        pCdi: idx.filter((i) => x.retFinal[i] > x.cdiPeriod[i] + TOL).length / idx.length,
        media: mean(idx.map((i) => x.retFinal[i])), mediaVenc: mean(idx.map((i) => x.retHold[i])) };
    }).filter(Boolean);
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
