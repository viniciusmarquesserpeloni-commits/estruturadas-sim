/* Página "Ex-post": a estrutura aplicada ao caminho realizado de uma operação real. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc, CH = () => App.charts;
  App.views = App.views || {};
  let root = null;
  const alive = () => root && document.body.contains(root);

  function render(el) {
    root = el;
    const ex = App.state.expost;
    el.innerHTML = `
      <div class="page-head"><div><h2>Ex-post</h2><p>Aplica a estrutura no caminho de preços <b>realmente observado</b> entre a contratação e a apuração (fechamento de D−1 do vencimento).</p></div></div>
      <div class="card"><div class="card-b"><div class="toolbar">
        <label class="pfield"><span class="f-label">Data de contratação</span><input class="input" type="date" id="x-trade" value="${ex.trade || ""}"></label>
        <label class="pfield"><span class="f-label">Data de vencimento</span><input class="input" type="date" id="x-expiry" value="${ex.expiry || ""}"></label>
        <button class="btn ghost sm" type="button" id="x-from-term" title="Usar as datas do prazo (barra de parâmetros)">Usar datas do prazo</button>
      </div></div></div>
      <div id="x-body" style="margin-top:16px"></div>`;
    const set = () => App.update({ expost: { trade: el.querySelector("#x-trade").value, expiry: el.querySelector("#x-expiry").value } });
    el.querySelector("#x-trade").addEventListener("change", set);
    el.querySelector("#x-expiry").addEventListener("change", set);
    el.querySelector("#x-from-term").addEventListener("click", () => {
      const t = App.state.term;
      if (!t.trade || !t.expiry) { App.toast("Defina o prazo por datas na barra de parâmetros."); return; }
      el.querySelector("#x-trade").value = t.trade; el.querySelector("#x-expiry").value = t.expiry; set();
    });
    update(App.ctx);
  }

  function update(ctx) {
    if (!alive() || !ctx) return;
    const body = root.querySelector("#x-body"), st = App.state, s = st.structure;
    CH().disposeIn(body);
    const blocked = App.ui.blocked(ctx);
    if (blocked) { body.innerHTML = blocked; return; }
    if (ctx.cost == null) { body.innerHTML = `<div class="card"><div class="loading">Calculando o custo teórico…</div></div>`; return; }
    if (!ctx.P) { body.innerHTML = `<div class="card"><div class="loading">Carregando preços…</div></div>`; return; }
    let ex;
    try { ex = E.runExPost(s, ctx.P, st.expost.trade, st.expost.expiry, ctx.cost, st.adv.monitoring, ctx.extra); }
    catch (e) { body.innerHTML = `<div class="warn-note">${esc(e.message)}</div>`; return; }
    const note = ex.finished
      ? `<div class="disclaimer" style="margin-bottom:16px">Operação encerrada: apuração em <b>${F.date(ex.obsDate)}</b> (D−1 do vencimento ${F.date(ex.expiry)}).</div>`
      : `<div class="warn-note">Vencimento ainda não chegou (apuração prevista em <b>${F.date(ex.obsDate)}</b>). Situação <b>até ${F.date(ex.lastDate)}</b>: marcação <b>intrínseca</b> — o payoff como se a apuração fosse hoje, com o status das barreiras até agora. <b>Não</b> é o valor de mercado da estrutura (que inclui o valor temporal das opções).</div>`;
    const K = App.ui.kpi;
    body.innerHTML = note + `
      <div class="card kpi-strip">
        ${K(ex.finished ? "Retorno da estrutura" : "Retorno intrínseco até hoje", App.signed(ex.ret), "bruto de IR")}
        ${K("Resultado (R$)", F.brl(st.invested * ex.ret), `sobre ${F.brl(st.invested, 0)}`)}
        ${K("Retorno só da ação", App.signed(ex.stockRet), "mesmo período")}
        ${K("Valor inicial", F.brl(ex.s0), `fechamento de ${F.date(ex.tradeDate)}`)}
        ${K("Pregões decorridos", F.int(ex.nElapsed), ex.finished ? "operação encerrada" : `até ${F.date(ex.lastDate)}`)}
        ${K("Barreiras", ex.hits.length ? ex.hits.filter((h) => h.hit).length + " de " + ex.hits.length + " tocada(s)" : "—", ex.hits.length ? "" : "estrutura sem barreira")}
      </div>
      ${ex.hits.length ? `<div class="card" style="margin-top:16px"><div class="card-b"><ul class="insight">${ex.hits.map((h) => `<li>${h.hit ? `Barreira <b>${esc(h.label)}</b> tocada em <b>${F.date(h.date)}</b>.` : `Barreira <b>${esc(h.label)}</b> <b>não tocada</b> ${ex.finished ? "durante a operação" : "até agora"}.`}</li>`).join("")}</ul></div></div>` : ""}
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>${esc(ctx.ticker)}: caminho realizado desde a contratação</h3><span class="sub">strikes e barreiras em R$ (nível × valor inicial)</span></div>
        <div class="card-b"><div class="chart tall" id="x-chart"></div></div>
        <div class="card-note">Preço ${st.adv.adjusted ? "ajustado por proventos" : "bruto"}${st.adv.adjusted ? ": os valores em R$ podem diferir dos da lâmina, mas as variações percentuais são comparáveis" : ""}. Monitoramento: ${E.MONITORING_LABELS[st.adv.monitoring].toLowerCase()}.</div></div>`;
    CH().expost(body.querySelector("#x-chart"), ex, s, ctx.ticker);
  }

  App.on("results", update);
  App.views["ex-post"] = { render };
})();
