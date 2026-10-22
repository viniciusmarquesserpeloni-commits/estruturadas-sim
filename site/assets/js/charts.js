/* Gráficos (Apache ECharts) no mesmo estilo do painel de fundos: grade discreta, linhas de 2px,
   referência tracejada em cinza, tooltip sempre ativo. Rótulos e números em pt-BR. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt;
  const C = (App.charts = {});
  const instances = new Map();
  const INK = "#0e2a33", TEXT2 = "#4b5f66", MUTED = "#7d8f95", GRID = "#e9ece7", AXIS = "#cfd6cf";
  const BLUE = "#2a78d6", ORANGE = "#eb6834", RED = "#e34948", AQUA = "#1baf7a", GRAY = "#7d8f95";
  C.COLORS = { BLUE, ORANGE, RED, AQUA, GRAY };
  const FONT = getComputedStyle(document.body).fontFamily;

  C.mount = function (el, option) {
    if (!el) return null;
    let ch = instances.get(el);
    if (ch && ch.isDisposed()) ch = null;
    if (!ch) { ch = echarts.init(el, null, { renderer: "canvas" }); instances.set(el, ch); }
    ch.setOption(Object.assign({ textStyle: { fontFamily: FONT, color: TEXT2 }, animationDuration: 300 }, option), true);
    return ch;
  };
  C.disposeIn = function (root) {
    for (const [el, ch] of instances) if (!document.body.contains(el) || (root && root.contains(el))) { ch.dispose(); instances.delete(el); }
  };
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => instances.forEach((ch) => !ch.isDisposed() && ch.resize()), 120); });

  const pct = (v, d = 0) => F.pct(v, d, false);
  const axis = { axisLine: { lineStyle: { color: AXIS } }, axisTick: { show: false }, axisLabel: { color: MUTED, fontSize: 11 }, splitLine: { lineStyle: { color: GRID } } };
  const tooltipBase = {
    backgroundColor: "#fff", borderColor: "#e2e6e0", borderWidth: 1, padding: [8, 10], confine: true,
    textStyle: { color: INK, fontSize: 12, fontFamily: FONT }, extraCssText: "box-shadow:0 6px 18px rgba(14,42,51,.12);border-radius:8px;",
  };
  const dot = (c, dashed) => dashed
    ? `<i style="display:inline-block;width:12px;border-top:2px dashed ${c};margin-right:6px;vertical-align:3px"></i>`
    : `<i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};margin-right:6px"></i>`;
  const row = (label, value, color, dashed) => `<div class="row"><span>${color ? dot(color, dashed) : ""}${App.esc(label)}</span><b>${value}</b></div>`;
  const legend = { top: 0, left: 0, icon: "roundRect", itemWidth: 12, itemHeight: 4, textStyle: { color: TEXT2, fontSize: 12 } };
  const vline = (x, label, color, type, pos = "insideEndTop") => ({ xAxis: x, lineStyle: { color, type, width: type === "dashed" ? 1.5 : 1 }, label: { formatter: label, color, fontSize: 11, position: pos } });
  const hline = (y, label, color, type, pos = "insideEndTop") => ({ yAxis: y, lineStyle: { color, type, width: type === "dashed" ? 1.5 : 1 }, label: { formatter: label, color, fontSize: 11, position: pos } });

  /* 1. Retorno no vencimento × variação da ação (ramos com e sem toque na barreira). */
  C.payoff = function (el, s, cost, extra) {
    const levels = [1].concat(E.strikes(s), E.events(s).map((e) => e.level));
    const hi = Math.max(1.5, Math.max(...levels) + 0.25), lo = Math.max(0, Math.min(0.5, Math.min(...levels) - 0.25));
    const xs = [];
    for (let i = 0; i <= 600; i++) xs.push(lo + ((hi - lo) * i) / 600);
    levels.forEach((l) => { xs.push(l); xs.push(l - 1e-6); });
    xs.sort((a, b) => a - b);
    const hasEv = E.events(s).length > 0;
    const branches = hasEv ? [["none", "Barreira não tocada", BLUE], ["all", "Barreira tocada", ORANGE]] : [["none", "Estrutura", BLUE]];
    const series = [{ name: "Só a ação", type: "line", showSymbol: false, data: xs.map((x) => [x - 1, x - 1]), lineStyle: { color: GRAY, width: 1.5, type: "dashed" }, itemStyle: { color: GRAY }, z: 1 }];
    branches.forEach(([b, name, color], k) => {
      const p = E.expiryPayoff(s, xs, b);
      series.push({ name, type: "line", showSymbol: false, connectNulls: false, lineStyle: { color, width: 2.5 }, itemStyle: { color }, z: 3 + k,
        data: xs.map((x, i) => [x - 1, isFinite(p[i]) ? E.returnsFromPayoff(p[i], cost, E.hasStock(s), extra) : null]) });
    });
    const marks = E.strikes(s).map((k, i) => vline(k - 1, `K ${F.lvl(k)}`, GRAY, "dotted", i % 2 ? "insideStartTop" : "insideEndTop"))
      .concat(E.events(s).map((e) => vline(e.level - 1, `Barreira ${F.lvl(e.level)}`, ORANGE, "dashed", "insideEndBottom")));
    series[1].markLine = { symbol: "none", silent: true, data: marks };
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 40, bottom: 28, containLabel: true },
      legend,
      tooltip: Object.assign({}, tooltipBase, { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: AXIS } },
        formatter: (ps) => `<div class="tt"><div class="tt-h">Ação ${F.pct(ps[0].data[0], 1)}</div>${ps.filter((p) => p.data[1] != null).map((p) => row(p.seriesName, F.pct(p.data[1]), p.color, p.seriesName === "Só a ação")).join("")}</div>` }),
      xAxis: Object.assign({ type: "value", min: lo - 1, max: hi - 1, name: "Variação da ação no vencimento", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: TEXT2, fontSize: 11.5 } }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) }, splitLine: { show: false } }),
      yAxis: Object.assign({ type: "value", scale: true }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) } }),
      series,
    });
  };

  /* 2. Histograma de retornos (frequência relativa), com linhas em 0% e no CDI. */
  C.histogram = function (el, sets, cdi) {
    const all = [];
    sets.forEach((st) => all.push(...st.values));
    const sorted = Float64Array.from(all).sort();
    const q = (p) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * (sorted.length - 1))))];
    let lo = q(0.005), hi = q(0.995);
    if (hi - lo < 1e-3) { lo -= 0.01; hi += 0.01; }
    const nb = 50, w = (hi - lo) / nb, centers = Array.from({ length: nb }, (_, i) => lo + w * (i + 0.5));
    const series = sets.map((st) => {
      const counts = new Array(nb).fill(0);
      st.values.forEach((v) => { const i = Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / w))); counts[i]++; });
      return { name: st.name, type: "bar", barGap: "-100%", barCategoryGap: "8%", data: counts.map((c, i) => [centers[i], c / st.values.length]),
        itemStyle: { color: st.color, opacity: sets.length > 1 ? 0.6 : 0.85, borderRadius: [3, 3, 0, 0] } };
    });
    const marks = [vline(0, "0%", GRAY, "solid", "insideEndTop")];
    if (cdi != null && isFinite(cdi)) marks.push(vline(cdi, `CDI ${F.pct(cdi, 1, false)}`, AQUA, "dashed", "insideEndTop"));
    series[0].markLine = { symbol: "none", silent: true, data: marks };
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 40, bottom: 28, containLabel: true },
      legend: Object.assign({}, legend, { icon: "circle", itemWidth: 8, itemHeight: 8 }),
      tooltip: Object.assign({}, tooltipBase, { trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(14,42,51,.04)" } },
        formatter: (ps) => `<div class="tt"><div class="tt-h">Retorno ≈ ${F.pct(ps[0].data[0], 1)}</div>${ps.map((p) => row(p.seriesName, F.pct(p.data[1], 1, false), p.color)).join("")}</div>` }),
      xAxis: Object.assign({ type: "value", min: lo, max: hi, name: "Retorno da estrutura no período", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: TEXT2, fontSize: 11.5 } }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) }, splitLine: { show: false } }),
      yAxis: Object.assign({ type: "value" }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) } }),
      series,
    });
  };

  /* 4. Retorno de cada janela pela data de início: cor = lucro/sem lucro, símbolo = barreira acionada. */
  C.windows = function (el, res) {
    const groups = [["Lucro", BLUE, "circle", true, false], ["Sem lucro", RED, "circle", false, false],
      ["Lucro (barreira acionada)", BLUE, "triangle", true, true], ["Sem lucro (barreira acionada)", RED, "triangle", false, true]];
    const series = groups.map(([name, color, symbol, prof, hit]) => {
      const data = [];
      for (let i = 0; i < res.ret.length; i++) if ((res.ret[i] > 1e-9) === prof && !!res.anyHit[i] === hit) data.push([res.start[i], res.ret[i], i]);
      return { name, type: "scatter", symbol, symbolSize: symbol === "circle" ? 5 : 7, large: data.length > 3000, data,
        itemStyle: { color, opacity: 0.75 } };
    }).filter((s) => s.data.length);
    if (series.length) series[0].markLine = { symbol: "none", silent: true, data: [{ yAxis: 0, lineStyle: { color: AXIS, type: "solid" }, label: { show: false } }] };
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
      legend: Object.assign({}, legend, { icon: undefined, itemWidth: 10, itemHeight: 10 }),
      tooltip: Object.assign({}, tooltipBase, { trigger: "item",
        formatter: (p) => { const i = p.data[2]; return `<div class="tt"><div class="tt-h">${F.date(res.start[i])} → ${F.date(res.end[i])}</div>${row("Estrutura", F.pct(res.ret[i]))}${row("Só a ação", F.pct(res.stock[i]))}${res.cdi ? row("CDI", F.pct(res.cdi[i])) : ""}${row("Barreira", res.anyHit[i] ? "acionada" : "não acionada")}</div>`; } }),
      xAxis: Object.assign({ type: "time" }, axis, { splitLine: { show: false }, axisLabel: { color: MUTED, fontSize: 11, hideOverlap: true, formatter: { year: "{yyyy}", month: "{MM}/{yy}", day: "{dd}/{MM}" } } }),
      yAxis: Object.assign({ type: "value", scale: true }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) } }),
      series,
    });
  };

  /* 5. Preço da ação no período, com destaque de uma janela e seus níveis (strikes/barreiras). */
  C.price = function (el, P, ticker, s, win) {
    const data = P.d.map((d, i) => [d, P.c[i]]);
    const series = [{ name: "Fechamento", type: "line", showSymbol: false, data, lineStyle: { color: BLUE, width: 1.5 }, itemStyle: { color: BLUE }, sampling: "lttb" }];
    if (win) {
      const [i0, i1] = win, s0 = P.c[i0];
      series[0].markArea = { silent: true, itemStyle: { color: "rgba(235,104,52,.10)" }, data: [[{ xAxis: P.d[i0] }, { xAxis: P.d[i1] }]] };
      E.strikes(s).forEach((k) => series.push({ name: `K ${F.lvl(k)}`, type: "line", showSymbol: false, data: [[P.d[i0], k * s0], [P.d[i1], k * s0]], lineStyle: { color: GRAY, type: "dotted", width: 1 }, itemStyle: { color: GRAY } }));
      E.events(s).forEach((e) => series.push({ name: `Barreira ${F.lvl(e.level)}`, type: "line", showSymbol: false, data: [[P.d[i0], e.level * s0], [P.d[i1], e.level * s0]], lineStyle: { color: ORANGE, type: "dashed", width: 1.5 }, itemStyle: { color: ORANGE } }));
    }
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 16, bottom: 56, containLabel: true },
      tooltip: Object.assign({}, tooltipBase, { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: AXIS } },
        formatter: (ps) => `<div class="tt"><div class="tt-h">${F.date(ps[0].data[0])}</div>${ps.map((p) => row(p.seriesName, F.brl(p.data[1]), p.color)).join("")}</div>` }),
      xAxis: Object.assign({ type: "time" }, axis, { splitLine: { show: false }, axisLabel: { color: MUTED, fontSize: 11, hideOverlap: true, formatter: { year: "{yyyy}", month: "{MM}/{yy}", day: "{dd}/{MM}" } } }),
      yAxis: Object.assign({ type: "value", scale: true }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => F.brl(v, 0) } }),
      dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8, borderColor: "transparent", backgroundColor: "#f4f5f2", fillerColor: "rgba(14,42,51,.08)", handleSize: 14, showDetail: false, dataBackground: { lineStyle: { color: AXIS }, areaStyle: { color: "#eef0ec" } } }],
      series,
    });
  };

  /* Ex-post: caminho realizado com strikes e barreiras em R$, marcos da operação e toque na barreira. */
  C.expost = function (el, ex, s, ticker) {
    const xEnd = ex.obsDate > ex.lastDate ? ex.obsDate : ex.lastDate;
    const lvl = (name, v, color, type) => ({ name, type: "line", showSymbol: false, data: [[ex.tradeDate, v], [xEnd, v]], lineStyle: { color, type, width: type === "dashed" ? 1.5 : 1 }, itemStyle: { color },
      endLabel: { show: true, formatter: name, color, fontSize: 11, distance: -4, offset: [-4, -10], align: "right" } });
    const intra = ex.highs.some((h, i) => Math.abs(h - ex.prices[i]) > 1e-9);
    const series = [{ name: "Fechamento", type: "line", showSymbol: false, data: ex.dates.map((d, i) => [d, ex.prices[i]]), lineStyle: { color: BLUE, width: 2 }, itemStyle: { color: BLUE }, z: 5 }];
    if (intra) {
      series.push({ name: "Máxima", type: "line", showSymbol: false, data: ex.dates.map((d, i) => [d, ex.highs[i]]), lineStyle: { color: BLUE, width: 1, type: "dotted", opacity: 0.5 }, itemStyle: { color: BLUE } });
      series.push({ name: "Mínima", type: "line", showSymbol: false, data: ex.dates.map((d, i) => [d, ex.lows[i]]), lineStyle: { color: BLUE, width: 1, type: "dotted", opacity: 0.5 }, itemStyle: { color: BLUE } });
    }
    const atS0 = E.strikes(s).some((k) => Math.abs(k - 1) < 1e-9);
    series.push(lvl(`Valor inicial ${F.brl(ex.s0)}${atS0 ? " = K 100,00%" : ""}`, ex.s0, GRAY, "solid"));
    E.strikes(s).filter((k) => Math.abs(k - 1) >= 1e-9).forEach((k) => series.push(lvl(`K ${F.lvl(k)}`, k * ex.s0, GRAY, "dotted")));
    E.events(s).forEach((e) => series.push(lvl(`Barreira ${F.lvl(e.level)}`, e.level * ex.s0, ORANGE, "dashed")));
    const touched = ex.hits.filter((h) => h.hit);
    if (touched.length) series.push({ name: "Toque na barreira", type: "scatter", symbol: "diamond", symbolSize: 12, itemStyle: { color: ORANGE, borderColor: "#fff", borderWidth: 2 },
      data: touched.map((h) => [h.date, ex.prices[ex.dates.indexOf(h.date)]]), z: 6 });
    series[0].markLine = { symbol: "none", silent: true, data: [{ xAxis: ex.obsDate, lineStyle: { color: GRAY, type: "dashed" }, label: { formatter: "Apuração (D−1)", color: GRAY, fontSize: 11, position: "insideEndBottom" } }] };
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
      legend: Object.assign({}, legend, { data: ["Fechamento"].concat(intra ? ["Máxima", "Mínima"] : [], touched.length ? ["Toque na barreira"] : []) }),
      tooltip: Object.assign({}, tooltipBase, { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: AXIS } },
        formatter: (ps) => { const p0 = ps.find((p) => p.seriesName === "Fechamento"); if (!p0) return ""; const i = p0.dataIndex; return `<div class="tt"><div class="tt-h">${F.date(p0.data[0])}</div>${row("Fechamento", F.brl(ex.prices[i]), BLUE)}${row("Nível", F.lvl(ex.prices[i] / ex.s0))}${intra ? row("Máxima", F.brl(ex.highs[i])) + row("Mínima", F.brl(ex.lows[i])) : ""}</div>`; } }),
      xAxis: Object.assign({ type: "time", max: xEnd }, axis, { splitLine: { show: false }, axisLabel: { color: MUTED, fontSize: 11, hideOverlap: true, formatter: { year: "{yyyy}", month: "{MM}/{yy}", day: "{dd}/{MM}" } } }),
      yAxis: Object.assign({ type: "value", scale: true }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => F.brl(v, 0) } }),
      series,
    });
  };

  /* Saída antecipada: em que mês da operação as janelas/caminhos são desmontados (fração do total). */
  C.exitDays = function (el, sets, N) {
    const bin = 21, nb = Math.ceil(N / bin);
    const labels = Array.from({ length: nb }, (_, i) => `${i + 1}º mês`);
    const series = sets.map((st) => {
      const counts = new Array(nb).fill(0);
      for (let i = 0; i < st.res.n; i++) if (st.res.early[i]) counts[Math.min(nb - 1, Math.floor((st.res.exitDay[i] - 1) / bin))]++;
      return { name: st.name, type: "bar", data: counts.map((c) => c / st.res.n), barGap: "10%", barMaxWidth: 18,
        itemStyle: { color: st.color, borderRadius: [3, 3, 0, 0] } };
    });
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
      legend: Object.assign({}, legend, { icon: "circle", itemWidth: 8, itemHeight: 8 }),
      tooltip: Object.assign({}, tooltipBase, { trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(14,42,51,.04)" } },
        formatter: (ps) => `<div class="tt"><div class="tt-h">Saída no ${App.esc(ps[0].axisValue)} (pregões ${(ps[0].dataIndex) * bin + 1}–${Math.min(N, (ps[0].dataIndex + 1) * bin)})</div>${ps.map((p) => row(p.seriesName, F.pct(p.value, 1, false), p.color)).join("")}</div>` }),
      xAxis: Object.assign({ type: "category", data: labels }, axis, { axisLabel: { color: MUTED, fontSize: 11, hideOverlap: true }, splitLine: { show: false } }),
      yAxis: Object.assign({ type: "value" }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) } }),
      series,
    });
  };

  /* Ex-post: retorno de saída (marcação diária, líquido do spread) × gatilho de % do CDI. */
  C.expostExit = function (el, x, cfg) {
    const ret = x.dates.map((d, i) => [d, isFinite(x.ret[i]) ? x.ret[i] : null]);
    const thr = x.dates.map((d, i) => [d, x.threshold[i]]);
    const series = [
      { name: "Retorno de saída (marcação)", type: "line", showSymbol: false, data: ret, lineStyle: { color: BLUE, width: 2 }, itemStyle: { color: BLUE }, z: 3 },
      { name: `Gatilho (${F.num(cfg.trigger * 100, 0)}% do CDI)`, type: "line", showSymbol: false, data: thr, lineStyle: { color: AQUA, width: 1.5, type: "dashed" }, itemStyle: { color: AQUA }, z: 2 },
    ];
    const marks = [];
    if (x.triggerDate) marks.push({ name: "Gatilho atingido", coord: [x.triggerDate, x.ret[x.dates.indexOf(x.triggerDate)]], color: ORANGE });
    if (x.exitDate) marks.push({ name: "Desmontagem", coord: [x.exitDate, x.exitReturn], color: RED });
    marks.forEach((m) => series.push({ name: m.name, type: "scatter", symbol: "diamond", symbolSize: 12, data: [m.coord], itemStyle: { color: m.color, borderColor: "#fff", borderWidth: 2 }, z: 5 }));
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
      legend,
      tooltip: Object.assign({}, tooltipBase, { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: AXIS } },
        formatter: (ps) => `<div class="tt"><div class="tt-h">${F.date(ps[0].data[0])}</div>${ps.filter((p) => p.data[1] != null).map((p) => row(p.seriesName, F.pct(p.data[1]), p.color)).join("")}</div>` }),
      xAxis: Object.assign({ type: "time" }, axis, { splitLine: { show: false }, axisLabel: { color: MUTED, fontSize: 11, hideOverlap: true, formatter: { year: "{yyyy}", month: "{MM}/{yy}", day: "{dd}/{MM}" } } }),
      yAxis: Object.assign({ type: "value", scale: true }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) } }),
      series,
    });
  };

  /* Amostra de caminhos simulados (nível em % do valor inicial) com strikes e barreiras. */
  C.paths = function (el, res, s) {
    const sample = (res.sample || []).slice(0, 100);
    const series = sample.map((row, k) => ({ type: "line", showSymbol: false, silent: true, data: [[0, 1]].concat(Array.from(row, (v, j) => [j + 1, v])),
      lineStyle: { color: BLUE, width: 1, opacity: 0.16 }, z: 1, animation: false, name: "c" + k }));
    const marks = E.strikes(s).map((k, i) => hline(k, `K ${F.lvl(k)}`, GRAY, "dotted", i % 2 ? "insideStartTop" : "insideEndTop"))
      .concat(E.events(s).map((e) => hline(e.level, `Barreira ${F.lvl(e.level)}`, ORANGE, "dashed")));
    if (series.length) series[0].markLine = { symbol: "none", silent: true, data: marks };
    return C.mount(el, {
      grid: { left: 8, right: 16, top: 16, bottom: 28, containLabel: true },
      tooltip: { show: false },
      xAxis: Object.assign({ type: "value", min: 0, max: res.N, name: "Pregões desde a contratação", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: TEXT2, fontSize: 11.5 } }, axis, { splitLine: { show: false } }),
      yAxis: Object.assign({ type: "value", scale: true }, axis, { axisLabel: { color: MUTED, fontSize: 11, formatter: (v) => pct(v) } }),
      series,
    });
  };
})();
