/* Página "Monte Carlo": caminhos simulados a partir do histórico (bootstrap em blocos ou GBM). */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc, CH = () => App.charts;
  App.views = App.views || {};
  let root = null;
  const alive = () => root && document.body.contains(root);
  function render(el) { root = el; update(App.ctx); }

  function update(ctx) {
    if (!alive() || !ctx) return;
    const st = App.state, s = st.structure, UI = App.ui;
    const head = `<div class="page-head"><div><h2>Monte Carlo</h2><p>Complemento ao backtest: milhares de caminhos simulados a partir dos retornos diários históricos da ação, com a mesma estrutura e o mesmo prazo.</p></div>
      <div class="toolbar no-print">${ctx.mc ? '<button class="btn" type="button" id="m-csv">Baixar caminhos (CSV)</button>' : ""}</div></div>`;
    const blocked = UI.blocked(ctx);
    if (blocked) { CH().disposeIn(root); root.innerHTML = head + blocked; return; }
    if (ctx.mcError) { CH().disposeIn(root); root.innerHTML = head + `<div class="card empty"><h3>Não foi possível rodar o Monte Carlo</h3><p>${esc(ctx.mcError)}</p></div>`; return; }
    if (!ctx.mc) { CH().disposeIn(root); root.innerHTML = head + `<div class="card"><div class="loading">Simulando ${F.int(st.adv.mcPaths)} caminhos…</div></div>`; return; }
    const res = ctx.mc, sm = E.summarize(res);
    const desc = (res.method === "bootstrap" ? `bootstrap em blocos de ${res.block} dias (fechamento, máxima e mínima juntos)` : `GBM com σ de ${F.pct(res.sigma, 1, false)} a.a.`)
      + ` · retorno esperado da ação: ${E.DRIFT_LABELS[res.drift].toLowerCase()}${res.mu != null ? ` (${F.pct(res.mu, 2, false)} a.a.)` : ""}`;
    const cdi = Math.pow(1 + ctx.rateAnnual, res.N / 252) - 1;
    CH().disposeIn(root);
    root.innerHTML = head + `
      <p class="small muted" style="margin:-8px 0 12px"><b>${F.int(sm.n)} caminhos</b> de ${F.int(res.N)} pregões · ${desc} · seed ${res.seed}${res.monitoring === "intraday" ? " · barreira com correção de Broadie-Glasserman-Kou (intradiário)" : ""}</p>
      <div class="card"><div class="kpi-strip">${UI.kpis(sm, st.invested, "caminhos", ctx.scen)}</div>
        <div class="card-note">O erro de sorteio é desprezível; a incerteza que importa é de premissa. As faixas mostram o mínimo e o máximo entre 9 cenários de retorno esperado × volatilidade (tabela abaixo).</div></div>
      ${UI.scenarioCard(ctx, res)}
      <div class="grid g-2" style="margin-top:16px">
        <div class="card"><div class="card-h"><h3>Distribuição dos retornos</h3><span class="sub">Monte Carlo</span></div>
          <div class="card-b"><div class="chart" id="m-hist"></div></div>
          <div class="card-note">CDI do período: ${F.pct(ctx.rateAnnual, 2, false)} a.a. composto por ${F.int(res.N)} pregões (${F.pct(cdi, 2, false)}).</div></div>
        <div class="card"><div class="card-h"><h3>Amostra de 100 caminhos simulados</h3><span class="sub">nível em % do valor inicial</span></div>
          <div class="card-b"><div class="chart" id="m-paths"></div></div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Métricas: histórico × Monte Carlo</h3></div><div class="card-b">${UI.sideBySide(ctx)}</div>
        <div class="card-note">No Monte Carlo cada caminho é independente (amostra efetiva = nº de caminhos), mas ele herda as premissas do método: o bootstrap reamostra o passado; o GBM supõe retornos normais com vol constante.</div></div>
      ${UI.exitBlock(ctx, "mc")}`;
    CH().histogram(root.querySelector("#m-hist"), [{ name: "Monte Carlo", color: CH().COLORS.ORANGE, values: res.ret }], cdi);
    CH().paths(root.querySelector("#m-paths"), res, s);
    UI.mountExit(root, ctx, "mc");
    root.querySelector("#m-csv").addEventListener("click", () => App.download(`monte_carlo_${ctx.ticker}.csv`, UI.csv(res, st.invested), "text/csv;charset=utf-8"));
  }

  App.on("results", update);
  App.views["monte-carlo"] = { render };
})();
