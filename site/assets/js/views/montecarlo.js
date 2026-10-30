/* Página "Monte Carlo": caminhos simulados a partir do histórico (FHS-GARCH, bootstrap em blocos ou GBM),
   painel de volatilidade e teste de calibração walk-forward. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc, CH = () => App.charts;
  App.views = App.views || {};
  let root = null, calibKey = "lucro";
  const alive = () => root && document.body.contains(root) && App.route === "monte-carlo";
  function render(el) { root = el; update(App.ctx); }

  /* Painel de volatilidade (só no FHS-GARCH). */
  function volCard(ctx, res) {
    if (res.method !== "fhs_garch" || !res.garch) return "";
    const g = res.garch, vp = E.volPanel(g, E.ohlcLogReturns(ctx.P).lr, res.N), UI = App.ui;
    const params = `α ${F.num(g.alpha, 3)} · γ ${F.num(g.gamma, 3)} · β ${F.num(g.beta, 3)}`;
    return `<div class="section-title">Volatilidade de hoje — ${esc(vp.modelo)}</div>
      <div class="card kpi-strip">
        ${UI.kpi("Vol de hoje", F.pct(vp.vol_hoje, 1, false), "prevista para o próximo pregão")}
        ${UI.kpi("Vol prevista para o prazo", F.pct(vp.vol_prazo, 1, false), `média dos próximos ${F.int(res.N)} pregões (usada no MC)`)}
        ${UI.kpi("Vol de longo prazo", F.pct(vp.vol_longo_prazo, 1, false), "para onde a vol converge")}
        ${UI.kpi("Vol realizada", F.pct(vp.vol_realizada, 1, false), "últimos 63 pregões")}
        ${UI.kpi("Meia-vida", `${F.num(vp.meia_vida, 0)} pregões`, "para a distância até o longo prazo cair à metade")}
        ${UI.kpi("Persistência", F.num(vp.persistencia, 3), params)}
      </div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Vol condicional × realizada</h3><span class="sub">últimos 3 anos + previsão para o prazo (tracejada)</span></div>
        <div class="card-b"><div class="chart" id="m-vol"></div></div>
        <div class="card-note">O GARCH estima a vol de cada dia a partir dos choques recentes (quedas pesam mais no GJR). O Monte Carlo parte da vol de hoje e a deixa voltar para a média de longo prazo no ritmo da meia-vida; cada caminho reage aos próprios choques. Parâmetros estimados com ${F.int(g.n)} retornos diários.</div></div>`;
  }
  function mountVol(ctx, res) {
    const el = root.querySelector("#m-vol");
    if (!el) return;
    const g = res.garch, vh = E.volHistory(ctx.P, g), fc = [];
    let d = ctx.P.d[ctx.P.d.length - 1];
    fc.push([d, Math.sqrt(g.hNext * 252)]);
    for (let k = 1; k <= res.N; k++) {
      do d = E.addDaysISO(d, 1); while (!E.isBusinessDay(d));
      fc.push([d, Math.sqrt(E.expectedVar(g, g.hNext, k) * 252)]);
    }
    CH().vol(el, vh, fc, Math.sqrt(g.longRunVar * 252));
  }

  /* Calibração walk-forward sob demanda. */
  function calibCard(ctx) {
    const c = App.calib, st = App.state, fresh = c.key === App.calibKey(ctx);
    const head = `<div class="section-title">Calibração — o modelo teria acertado no passado?</div><div class="card" id="m-calib-card">`;
    const intro = `<p class="small" style="margin:0 0 10px">A cada 10 pregões do histórico (depois de 2 anos de dados), o simulador estima as probabilidades
      <b>só com os dados até aquela data</b> — com o método e as premissas escolhidos — e confere o que aconteceu de fato nos ${F.int(ctx.n)} pregões seguintes.
      A régua é o <b>chute fixo</b>: a frequência histórica do evento até a data. Brier = média de (probabilidade − resultado)²; menor é melhor.</p>`;
    if (c.running && fresh) {
      return head + `<div class="card-b">${intro}<div class="small muted" style="margin-bottom:6px">Testando… ${F.pct(c.progress, 0, false)}</div>
        <div style="height:8px;background:var(--surface-2);border-radius:6px;overflow:hidden"><div style="height:100%;width:${(c.progress * 100).toFixed(1)}%;background:var(--accent, #2a78d6);transition:width .2s"></div></div></div></div>`;
    }
    if (!c.res || !fresh) {
      return head + `<div class="card-b">${intro}${c.error && fresh ? `<div class="err-note">${esc(c.error)}</div>` : ""}
        <button class="btn" type="button" id="m-calib">Testar calibração</button>
        <span class="small muted" style="margin-left:8px">≈ 1.000 caminhos por data; leva alguns segundos.</span></div></div>`;
    }
    const res = c.res, br = E.calibBrier(res), evs = br.map((b) => b.chave);
    if (!evs.includes(calibKey)) calibKey = evs[0];
    const label = br.find((b) => b.chave === calibKey).indicador;
    const span = res.rows.length ? `${F.date(res.rows[0].data)} a ${F.date(res.rows[res.rows.length - 1].data)}` : "";
    const nEff = Math.max(1, Math.round((res.rows.length * res.step) / res.N));
    const table = `<table class="compact"><thead><tr><th>Indicador</th><th title="Brier do modelo">Modelo</th><th title="Brier do chute fixo">Chute fixo</th><th>Ganho</th><th title="Probabilidade média prevista">Previsto</th><th title="Frequência realizada">Real</th></tr></thead><tbody>
      ${br.map((b) => `<tr><td>${esc(b.indicador)}</td><td>${F.num(b.brier_modelo, 4)}</td><td>${F.num(b.brier_chute, 4)}</td><td>${App.signed(b.ganho, 1)}</td><td>${F.pct(b.prev_media, 1, false)}</td><td>${F.pct(b.real, 1, false)}</td></tr>`).join("")}
      </tbody></table>`;
    const verdict = br.map((b) => (b.ganho > 0.02 ? `${esc(b.indicador)}: o modelo foi melhor que o chute fixo` : b.ganho > 0 ? `${esc(b.indicador)}: praticamente empatado com o chute fixo` : `${esc(b.indicador)}: não superou o chute fixo`)).join(" · ");
    return head + `<div class="card-h"><h3>Resultado do teste</h3><span class="sub">${F.int(res.rows.length)} datas de ${span} · ${esc(E.MC_METHOD_LABELS[res.method])}</span></div>
      <div class="card-b"><div class="grid g-2">
        <div><div class="small muted" style="margin-bottom:6px">Brier score (menor é melhor) e ganho sobre o chute fixo</div><div style="overflow-x:auto">${table}</div><p class="small" style="margin:10px 0 0">${verdict}.</p>
          <button class="btn ghost sm" type="button" id="m-calib" style="padding-left:0;margin-top:8px">Testar de novo</button></div>
        <div><div class="seg" role="group" aria-label="Indicador do diagrama">${br.map((b) => `<button type="button" data-ck="${b.chave}" aria-pressed="${b.chave === calibKey}">${esc(b.indicador)}</button>`).join("")}</div>
          <div class="chart" id="m-rel" style="height:260px"></div></div>
      </div></div>
      <div class="card-note">Se o Brier do modelo não for menor que o do chute fixo, trate a probabilidade como ordem de grandeza, não como previsão. Diagrama: cada ponto agrupa as datas com previsão na mesma faixa de 10 p.p.; sobre a diagonal = bem calibrado. Janelas vizinhas se sobrepõem (≈ ${F.int(nEff)} períodos independentes), então diferenças pequenas de Brier são ruído. GARCH reestimado a cada ${F.int(res.refit)} pregões; CDI de cada data como régua.</div></div>`;
  }
  function mountCalib(ctx) {
    const btn = root.querySelector("#m-calib");
    if (btn) btn.addEventListener("click", () => App.runCalibration(onCalib));
    root.querySelectorAll("[data-ck]").forEach((b) => b.addEventListener("click", () => { calibKey = b.dataset.ck; refreshCalib(); }));
    const el = root.querySelector("#m-rel"), c = App.calib;
    if (el && c.res) {
      const label = E.calibBrier(c.res).find((b) => b.chave === calibKey).indicador;
      CH().reliability(el, E.calibReliability(c.res, calibKey), label);
    }
  }
  function refreshCalib() {
    if (!alive()) return;
    const card = root.querySelector("#m-calib-card"), ctx = App.ctx;
    if (!card || !ctx) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = calibCard(ctx);
    const sec = card.previousElementSibling;
    CH().disposeIn(card);
    card.replaceWith(tmp.querySelector("#m-calib-card"));
    if (sec && sec.classList.contains("section-title")) sec.replaceWith(tmp.querySelector(".section-title"));
    mountCalib(ctx);
  }
  let calibTimer = null;
  const onCalib = (fromProgress) => { if (fromProgress) { if (!calibTimer) calibTimer = setTimeout(() => { calibTimer = null; refreshCalib(); }, 150); } else refreshCalib(); };

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
    const method = res.method === "fhs_garch" ? `FHS-${res.volModel === "gjr" ? "GJR" : "GARCH"}: vol de hoje do modelo e choques reais padronizados (vol média prevista ${F.pct(res.sigma, 1, false)} a.a.)`
      : res.method === "bootstrap" ? `bootstrap em blocos de ${res.block} dias (fechamento, máxima e mínima juntos)` : `GBM com σ de ${F.pct(res.sigma, 1, false)} a.a.`;
    const desc = method + ` · retorno esperado da ação: ${E.DRIFT_LABELS[res.drift].toLowerCase()}${res.mu != null ? ` (${F.pct(res.mu, 2, false)} a.a.)` : ""}`;
    const intra = res.monitoring === "intraday" ? (res.method === "gbm" ? " · barreira com correção de Broadie-Glasserman-Kou (intradiário)" : " · barreira pela máxima/mínima sorteadas (intradiário)") : "";
    const cdi = Math.pow(1 + ctx.rateAnnual, res.N / 252) - 1;
    const assume = res.method === "fhs_garch" ? "o FHS reamostra os choques do passado, mas parte da vol de hoje e a deixa evoluir" : res.method === "bootstrap" ? "o bootstrap reamostra o passado com a vol média do período" : "o GBM supõe retornos normais com vol constante";
    CH().disposeIn(root);
    root.innerHTML = head + `
      <p class="small muted" style="margin:-8px 0 12px"><b>${F.int(sm.n)} caminhos</b> de ${F.int(res.N)} pregões · ${desc} · seed ${res.seed}${intra}</p>
      <div class="card"><div class="kpi-strip">${UI.kpis(sm, st.invested, "caminhos", ctx.scen)}</div>
        <div class="card-note">O erro de sorteio é desprezível; a incerteza que importa é de premissa. As faixas mostram o mínimo e o máximo entre 9 cenários de retorno esperado × volatilidade (tabela abaixo).</div></div>
      ${volCard(ctx, res)}
      ${UI.scenarioCard(ctx, res)}
      <div class="grid g-2" style="margin-top:16px">
        <div class="card"><div class="card-h"><h3>Distribuição dos retornos</h3><span class="sub">Monte Carlo</span></div>
          <div class="card-b"><div class="chart" id="m-hist"></div></div>
          <div class="card-note">CDI do período: ${F.pct(ctx.rateAnnual, 2, false)} a.a. composto por ${F.int(res.N)} pregões (${F.pct(cdi, 2, false)}).</div></div>
        <div class="card"><div class="card-h"><h3>Amostra de 100 caminhos simulados</h3><span class="sub">nível em % do valor inicial</span></div>
          <div class="card-b"><div class="chart" id="m-paths"></div></div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Métricas: histórico × Monte Carlo</h3></div><div class="card-b">${UI.sideBySide(ctx)}</div>
        <div class="card-note">No Monte Carlo cada caminho é independente (amostra efetiva = nº de caminhos), mas ele herda as premissas do método: ${assume}.</div></div>
      ${calibCard(ctx)}
      ${UI.exitBlock(ctx, "mc")}`;
    CH().histogram(root.querySelector("#m-hist"), [{ name: "Monte Carlo", color: CH().COLORS.ORANGE, values: res.ret }], cdi);
    CH().paths(root.querySelector("#m-paths"), res, s);
    mountVol(ctx, res);
    mountCalib(ctx);
    UI.mountExit(root, ctx, "mc");
    root.querySelector("#m-csv").addEventListener("click", () => App.download(`monte_carlo_${ctx.ticker}.csv`, UI.csv(res, st.invested), "text/csv;charset=utf-8"));
  }

  App.on("results", update);
  App.views["monte-carlo"] = { render };
})();
