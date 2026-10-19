/* Página "Backtest histórico" (janelas móveis) + utilitários compartilhados com a página de Monte Carlo. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc, CH = () => App.charts;
  App.views = App.views || {};

  /* ---------------- Utilitários compartilhados ---------------- */
  const UI = (App.ui = {});
  UI.kpi = (label, value, hint) => `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  UI.kpis = function (sm, invested, what) {
    const bar = sm.barreiras.length ? sm.barreiras.map((b) => F.pct(b.p, 1, false)).join(" / ") : "—";
    return [
      UI.kpi("P(lucro > 0)", F.pct(sm.p_lucro, 1, false), `${what}: ${F.int(sm.n)}`),
      UI.kpi("P(retorno > CDI)", F.pct(sm.p_cdi, 1, false), `CDI médio ${F.pct(sm.cdi_medio, 2, false)}`),
      UI.kpi("P(perda)", F.pct(sm.p_perda, 1, false), `pior: ${F.pct(sm.pior)}`),
      UI.kpi("Retorno mediano", App.signed(sm.mediana), F.brl(invested * sm.mediana)),
      UI.kpi("Retorno médio", App.signed(sm.media), `${F.pct(sm.media_anual, 2)} a.a. · ${F.brl(invested * sm.media)}`),
      UI.kpi("Barreira acionada", bar, sm.barreiras.length ? sm.barreiras.map((b) => esc(b.label)).join(" / ") : "estrutura sem barreira"),
    ].join("");
  };
  /* Tabela de métricas lado a lado (histórico × Monte Carlo). */
  UI.metricsTable = function (cols) {
    const names = Object.keys(cols), sums = Object.values(cols);
    const labels = [...new Set(sums.flatMap((s) => s.barreiras.map((b) => b.label)))];
    const cell = (v, kind) => (v == null || !isFinite(v) ? "—" : kind === "int" ? F.int(v) : F.pct(v, 2, false));
    const rows = [];
    E.METRIC_ROWS.forEach(([k, label, kind]) => {
      if (k === "@barreiras") { labels.forEach((lbl) => rows.push(`<tr><td style="white-space:normal">Barreira acionada (${esc(lbl)})</td>${sums.map((s) => { const b = s.barreiras.find((x) => x.label === lbl); return `<td>${b ? F.pct(b.p, 2, false) : "—"}</td>`; }).join("")}</tr>`)); return; }
      const signedRow = kind === "pct" && !k.startsWith("p_") && !k.startsWith("acao_p") && !k.startsWith("cdi");
      rows.push(`<tr><td style="white-space:normal">${label}</td>${sums.map((s) => `<td>${signedRow && isFinite(s[k]) ? App.signed(s[k]) : cell(s[k], kind)}</td>`).join("")}</tr>`);
    });
    return `<div style="overflow-x:auto"><table class="compact"><thead><tr><th>Métrica</th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  };
  UI.csv = function (res, invested) {
    const head = ["data_inicio", "data_fim", "acao_final", "retorno", "retorno_acao", "retorno_cdi", "barreira_acionada", "resultado_rs"];
    const n = res.ret.length, num = (v, d = 6) => (v == null || !isFinite(v) ? "" : v.toFixed(d).replace(".", ","));
    const lines = [head.join(";")];
    for (let i = 0; i < n; i++) lines.push([res.start ? F.date(res.start[i]) : "", res.end ? F.date(res.end[i]) : "", num(res.sT[i]), num(res.ret[i]), num(res.stock[i]),
      res.cdi ? num(res.cdi[i]) : "", res.anyHit[i] ? "sim" : "nao", num(invested * res.ret[i], 2)].join(";"));
    return "﻿" + lines.join("\r\n");
  };
  UI.sideBySide = (ctx) => {
    const cols = {};
    if (ctx.hist) cols["Histórico"] = E.summarize(ctx.hist);
    if (ctx.mc) cols["Monte Carlo"] = E.summarize(ctx.mc);
    return UI.metricsTable(cols);
  };
  UI.blocked = function (ctx) {
    if (ctx.dataError || ctx.priceError) return `<div class="card empty"><h3>Sem dados de preço</h3><p>${esc(ctx.dataError || ctx.priceError)}</p></div>`;
    if (ctx.issues && E.hasErrors(ctx.issues)) return `<div class="card empty"><h3>Estrutura com erro</h3><p>${ctx.issues.filter((x) => x.level === "erro").map((x) => esc(x.msg)).join("<br>")}</p><p><a href="#/estrutura">Corrigir na aba Estrutura</a></p></div>`;
    return null;
  };

  /* ---------------- Página ---------------- */
  let root = null, winIdx = null;
  const alive = () => root && document.body.contains(root);
  function render(el) { root = el; winIdx = null; update(App.ctx); }

  function update(ctx) {
    if (!alive() || !ctx) return;
    const st = App.state, s = st.structure;
    const blocked = UI.blocked(ctx);
    const head = `<div class="page-head"><div><h2>Backtest histórico</h2><p>A estrutura, com os mesmos parâmetros em %, aplicada em todas as datas de início possíveis do histórico: “se eu tivesse contratado num dia qualquer do passado, quantas vezes teria ganhado?”</p></div>
      <div class="toolbar no-print">${ctx.hist ? '<button class="btn" type="button" id="b-csv">Baixar janelas (CSV)</button>' : ""}</div></div>`;
    if (blocked) { CH().disposeIn(root); root.innerHTML = head + blocked; return; }
    if (ctx.histError) { CH().disposeIn(root); root.innerHTML = head + `<div class="card empty"><h3>Não foi possível rodar o backtest</h3><p>${esc(ctx.histError)}</p></div>`; return; }
    if (!ctx.hist) { CH().disposeIn(root); root.innerHTML = head + `<div class="card"><div class="loading">Rodando o backtest nas janelas históricas…</div></div>`; return; }
    const res = ctx.hist, sm = E.summarize(res);
    if (winIdx == null || winIdx >= res.ret.length) { winIdx = 0; for (let i = 1; i < res.ret.length; i++) if (res.ret[i] < res.ret[winIdx]) winIdx = i; }
    CH().disposeIn(root);
    root.innerHTML = head + `
      <p class="small muted" style="margin:-8px 0 12px"><b>${esc(ctx.ticker)}</b> · ${F.int(sm.n)} janelas de ${F.int(res.N)} pregões entre ${F.date(ctx.P.d[0])} e ${F.date(ctx.P.d[ctx.P.d.length - 1])} · amostra efetiva (não sobrepostas): <b>${F.int(sm.nEff)}</b> · monitoramento: ${E.MONITORING_LABELS[res.monitoring].toLowerCase()} · custo ${F.pct(ctx.cost, 2, false)}</p>
      <div class="card kpi-strip">${UI.kpis(sm, st.invested, "janelas")}</div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Retorno de cada janela pela data de início</h3><span class="sub">cor = lucro / sem lucro · triângulo = barreira acionada</span></div>
        <div class="card-b"><div class="chart tall" id="b-ts"></div></div>
        <div class="card-note">Janelas vizinhas compartilham quase todo o caminho de preços: os pontos não são observações independentes.</div></div>
      <div class="grid g-2" style="margin-top:16px">
        <div class="card"><div class="card-h"><h3>Distribuição dos retornos</h3><span class="sub">histórico × Monte Carlo</span></div>
          <div class="card-b"><div class="chart" id="b-hist"></div></div>
          <div class="card-note">${ctx.mc ? "" : "Monte Carlo ainda em cálculo. "}Linha do CDI = CDI médio das janelas históricas.</div></div>
        <div class="card"><div class="card-h"><h3>Métricas: histórico × Monte Carlo</h3></div><div class="card-b">${UI.sideBySide(ctx)}</div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Preço da ação e janela em destaque</h3><span class="sub">padrão: a pior janela</span></div>
        <div class="card-b">
          <div class="range-row"><input type="range" id="b-win" min="0" max="${res.ret.length - 1}" value="${winIdx}" aria-label="Janela (data de início)"><span id="b-win-txt" class="small"></span></div>
          <div class="chart" id="b-price" style="margin-top:8px"></div>
        </div></div>`;
    CH().windows(root.querySelector("#b-ts"), res);
    const sets = [{ name: "Janelas históricas", color: CH().COLORS.BLUE, values: res.ret }];
    if (ctx.mc) sets.push({ name: "Monte Carlo", color: CH().COLORS.ORANGE, values: ctx.mc.ret });
    CH().histogram(root.querySelector("#b-hist"), sets, sm.cdi_medio);
    const showWin = () => {
      const i = winIdx;
      root.querySelector("#b-win-txt").innerHTML = `${F.date(res.start[i])} → ${F.date(res.end[i])}: estrutura ${App.signed(res.ret[i])} (${F.brl(st.invested * res.ret[i])}) · ação ${F.pct(res.stock[i])} · barreira ${res.anyHit[i] ? "acionada" : "não acionada"}`;
      CH().price(root.querySelector("#b-price"), ctx.P, ctx.ticker, s, [i, i + res.N]);
    };
    showWin();
    root.querySelector("#b-win").addEventListener("input", (e) => { winIdx = +e.target.value; showWin(); });
    root.querySelector("#b-csv").addEventListener("click", () => App.download(`janelas_${ctx.ticker}.csv`, UI.csv(res, st.invested), "text/csv;charset=utf-8"));
  }

  App.on("results", update);
  App.views.backtest = { render };
})();
