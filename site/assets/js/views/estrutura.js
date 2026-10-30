/* Página "Estrutura": composição (editor de pernas), payoff, quadro de rentabilidade, custo teórico e solver. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc, CH = () => App.charts;
  App.views = App.views || {};
  let root = null, solverRes = null;
  const alive = () => root && document.body.contains(root) && App.route === "estrutura";

  function render(el) {
    root = el; solverRes = null;
    el.innerHTML = `
      <div class="page-head">
        <div><h2 id="s-name"></h2><p id="s-notes"></p></div>
        <div class="toolbar no-print">
          <button class="btn" type="button" id="s-export" title="Salvar a estrutura (lâmina) em JSON para importar depois">Exportar JSON</button>
        </div>
      </div>
      <div class="issues" id="s-issues"></div>
      <div class="card"><div class="card-h"><h3>Composição da estratégia</h3><span class="sub">Strikes e barreiras em % do valor inicial · proporção = opções por ação</span></div>
        <div class="card-b" style="overflow-x:auto"><div id="s-editor"></div></div></div>
      <div class="card kpi-strip" id="s-kpis" style="margin-top:16px"></div>
      <div class="grid g-main" style="margin-top:16px">
        <div class="card"><div class="card-h"><h3>Retorno no vencimento × variação da ação</h3><span class="sub" id="s-payoff-sub"></span></div>
          <div class="card-b"><div class="chart tall" id="s-payoff"></div></div>
          <div class="card-note">Retornos brutos de IR sobre o valor investido. Com barreira, as linhas mostram os dois cenários: barreira nunca tocada e barreira tocada em algum momento.</div></div>
        <div class="card"><div class="card-h"><h3>Resumo em linguagem simples</h3></div><div class="card-b"><ul class="insight" id="s-summary"></ul></div></div>
      </div>
      <div class="grid g-2" style="margin-top:16px">
        <div class="card"><div class="card-h"><h3>Quadro de rentabilidade no vencimento</h3><span class="sub">formato das lâminas</span></div>
          <div class="card-b">
            <label class="small muted" for="s-vars">Variações da ação (%), separadas por ponto e vírgula</label>
            <div class="toolbar" style="margin:6px 0 12px"><input class="input" id="s-vars" style="flex:1"><button class="btn ghost sm" type="button" id="s-vars-reset">Padrão</button></div>
            <div id="s-quadro"></div>
          </div></div>
        <div class="card"><div class="card-h"><h3>Custo teórico das opções</h3><span class="sub" id="s-theo-sub"></span></div>
          <div class="card-b" id="s-theo"></div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Solver de custo zero</h3><span class="sub">encontra o parâmetro que zera o custo líquido teórico (ou atinge um custo alvo)</span></div>
        <div class="card-b" id="s-solver"></div></div>`;
    el.querySelector("#s-export").addEventListener("click", () => {
      const s = App.state.structure;
      App.download(`${s.name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_")}.json`, JSON.stringify(E.toJSON(s), null, 2), "application/json");
    });
    const vars = el.querySelector("#s-vars");
    vars.addEventListener("change", () => {
      const vs = vars.value.split(";").map((x) => App.parseNum(x)).filter((x) => x != null).map((x) => x / 100);
      App.update({ variations: vs.length ? vs : null });
    });
    el.querySelector("#s-vars-reset").addEventListener("click", () => App.update({ variations: null }));
    buildEditor(); buildSolver(); update(App.ctx);
  }

  /* ---------------- Editor de pernas ---------------- */
  const KIND_OPTS = Object.entries(E.KIND_LABELS), BAR_OPTS = Object.entries(E.BARRIER_LABELS);
  function buildEditor() {
    const s = App.state.structure, box = root.querySelector("#s-editor");
    root.querySelector("#s-name").textContent = s.name;
    root.querySelector("#s-notes").textContent = s.notes || "Edite a tabela livremente: os presets apenas preenchem as pernas.";
    const opt = (list, cur) => list.map(([v, l]) => `<option value="${v}" ${String(v) === String(cur) ? "selected" : ""}>${l}</option>`).join("");
    box.innerHTML = `<table class="legs"><thead><tr><th>#</th><th>Tipo</th><th>Posição</th><th>Preço de exercício (%)</th><th>Tipo de barreira</th><th>Valor da barreira (%)</th><th>Proporção</th><th></th></tr></thead><tbody>
      ${s.legs.map((l, i) => {
        const stock = l.kind === "stock", nob = stock || l.barrier === "none";
        return `<tr data-i="${i}">
          <td class="n">${i + 1}</td>
          <td><select class="select" data-f="kind">${opt(KIND_OPTS, l.kind)}</select></td>
          <td><select class="select" data-f="position">${opt([[1, "Comprada"], [-1, "Vendida"]], l.position)}</select></td>
          <td><input class="input num" data-f="strike" value="${stock || l.strike == null ? "" : F.num(l.strike * 100, 2)}" ${stock ? "disabled placeholder='—'" : ""} inputmode="decimal"></td>
          <td><select class="select" data-f="barrier" ${stock ? "disabled" : ""}>${opt(BAR_OPTS, l.barrier)}</select></td>
          <td><input class="input num" data-f="level" value="${nob || l.level == null ? "" : F.num(l.level * 100, 2)}" ${nob ? "disabled placeholder='—'" : ""} inputmode="decimal"></td>
          <td><input class="input num" data-f="ratio" value="${F.num(l.ratio, 4)}" inputmode="decimal"></td>
          <td class="x"><button type="button" data-rm="${i}" title="Remover perna" aria-label="Remover perna ${i + 1}">×</button></td>
        </tr>`;
      }).join("")}</tbody></table>
      <div class="toolbar" style="margin-top:10px"><button class="btn sm" type="button" id="s-add">+ Adicionar perna</button>
      <span class="small muted">Ex.: Proteção Total BBDC4 = ação comprada; put comprada 104,10%; call vendida 104,10% Knock Up and In 138,10%; call comprada 100% Knock Up and Out 138,10% × 0,5.</span></div>`;
    box.querySelectorAll("tr[data-i]").forEach((tr) => tr.addEventListener("change", (e) => {
      const i = +tr.dataset.i, f = e.target.dataset.f, legs = App.state.structure.legs.map((l) => Object.assign({}, l));
      const l = legs[i], v = e.target.value;
      if (f === "kind") { l.kind = v; if (v !== "stock" && l.strike == null) l.strike = 1; }
      else if (f === "position") l.position = +v;
      else if (f === "barrier") { l.barrier = v; if (v !== "none" && l.level == null) l.level = v.startsWith("up") ? 1.3 : 0.7; }
      else if (f === "strike" || f === "level") { const n = App.parseNum(v); l[f] = n == null ? null : n / 100; }
      else if (f === "ratio") { const n = App.parseNum(v); l.ratio = n == null ? 0 : n; }
      const s = E.structure(App.state.structure.name, legs, Object.assign({}, App.state.structure, { legs: undefined }));
      App.update({ structure: s }, { structural: f === "kind" || f === "barrier" });
    }));
    box.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => {
      const legs = App.state.structure.legs.filter((_, k) => k !== +b.dataset.rm);
      App.update({ structure: E.structure(App.state.structure.name, legs, Object.assign({}, App.state.structure, { legs: undefined })) }, { structural: true });
    }));
    box.querySelector("#s-add").addEventListener("click", () => {
      const legs = App.state.structure.legs.concat([E.leg("call", 1, 1)]);
      App.update({ structure: E.structure(App.state.structure.name, legs, Object.assign({}, App.state.structure, { legs: undefined })) }, { structural: true });
    });
  }

  /* ---------------- Solver ---------------- */
  function buildSolver() {
    const s = App.state.structure, box = root.querySelector("#s-solver");
    const opts = s.legs.map((l, i) => [i, l]).filter(([, l]) => E.isOption(l));
    if (!opts.length) { box.innerHTML = `<p class="muted small">A estrutura não tem opções.</p>`; return; }
    const last = opts[opts.length - 1][0];
    box.innerHTML = `
      <div class="toolbar" style="align-items:flex-end">
        <div class="pfield" style="flex:2 1 320px"><span class="f-label">Perna(s) — várias recebem o mesmo valor (ex.: put e call do FKO)</span>
          <div class="chips">${opts.map(([i, l]) => `<label class="chip" style="cursor:pointer"><input type="checkbox" data-leg="${i}" ${i === last ? "checked" : ""} style="accent-color:var(--ink);margin-right:4px">${i + 1}: ${esc(E.legLabel(l))}</label>`).join("")}</div></div>
        <div class="pfield"><span class="f-label">Parâmetro</span><select class="select" id="sv-param">${Object.entries(E.PARAM_LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
        <div class="pfield" style="width:110px"><span class="f-label">Mín.</span><input class="input num" id="sv-lo"></div>
        <div class="pfield" style="width:110px"><span class="f-label">Máx.</span><input class="input num" id="sv-hi"></div>
        <div class="pfield" style="width:120px"><span class="f-label">Custo alvo (%)</span><input class="input num" id="sv-target" value="0,00"></div>
        <button class="btn primary" type="button" id="sv-run">Resolver</button>
      </div>
      <div id="sv-out" style="margin-top:12px"></div>`;
    const param = box.querySelector("#sv-param"), lo = box.querySelector("#sv-lo"), hi = box.querySelector("#sv-hi");
    const selected = () => [...box.querySelectorAll("[data-leg]:checked")].map((c) => +c.dataset.leg);
    const fillBounds = () => {
      const legs = selected(), l = App.state.structure.legs[legs[0] ?? last], [a, b] = E.defaultBounds(l, param.value);
      const sc = param.value === "ratio" ? 1 : 100;
      lo.value = F.num(a * sc, param.value === "ratio" ? 4 : 2); hi.value = F.num(b * sc, param.value === "ratio" ? 4 : 2);
    };
    fillBounds();
    param.addEventListener("change", fillBounds);
    box.querySelector("#sv-run").addEventListener("click", async () => {
      const legs = selected(), ctx = App.ctx, out = box.querySelector("#sv-out");
      if (!legs.length) { out.innerHTML = `<div class="warn-note">Escolha ao menos uma perna.</div>`; return; }
      const sc = param.value === "ratio" ? 1 : 100;
      const bounds = [App.parseNum(lo.value) / sc, App.parseNum(hi.value) / sc];
      out.innerHTML = `<div class="loading">Resolvendo (Monte Carlo com ${F.int(App.state.adv.pricingPaths)} caminhos)…</div>`;
      const s = App.state.structure;
      try {
        const res = await App.call("solve", { s, legs, param: param.value, sigma: ctx.sigma, r: ctx.r, q: App.state.adv.q, n: ctx.n,
          paths: App.state.adv.pricingPaths, seed: App.state.adv.pricingSeed, monitoring: App.state.adv.monitoring, bounds, target: (App.parseNum(box.querySelector("#sv-target").value) || 0) / 100 });
        solverRes = { res, legs, param: param.value, s };
        showSolver();
      } catch (e) { out.innerHTML = `<div class="err-note">${esc(e.message)}</div>`; }
    });
  }
  function showSolver() {
    const out = root.querySelector("#sv-out");
    if (!solverRes || !out) return;
    const { res, legs, param, s } = solverRes;
    if (!res.converged) { out.innerHTML = `<div class="warn-note">${esc(res.message)}</div>`; return; }
    const shown = param === "ratio" ? F.num(res.value, 4) : F.lvl(res.value, 4);
    out.innerHTML = `<div class="toolbar"><span><b>${E.PARAM_LABELS[param]} = ${shown}</b> → custo ${F.pct(res.cost, 4)}${res.se ? ` (± ${F.pct(res.se, 3, false)} de erro padrão)` : ""}</span>
      <button class="btn" type="button" id="sv-apply">Aplicar à tabela</button>
      ${App.state.costMode === "informado" ? `<span class="small muted">Dica: use o custo “Teórico” (ou informe o custo alvo) para levar o custo resolvido aos backtests.</span>` : ""}</div>`;
    out.querySelector("#sv-apply").addEventListener("click", () => { App.setStructure(E.withParam(s, legs, param, res.value), App.state.presetKey, false); App.toast("Parâmetro aplicado à tabela"); });
  }

  /* ---------------- Resultados ---------------- */
  function kpi(label, value, hint, small) {
    return `<div class="kpi"><div class="label">${label}</div><div class="value ${small ? "sm" : ""}">${value}</div>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  }
  function update(ctx) {
    if (!alive() || !ctx) return;
    const st = App.state, s = st.structure, $ = (id) => root.querySelector("#" + id);
    $("s-issues").innerHTML = (ctx.issues || []).map((x) => `<div class="${x.level === "erro" ? "err-note" : "warn-note"}" style="margin:0">${esc(x.msg)}</div>`).join("")
      + (st.costMode === "teorico" && ctx.theoPending ? `<div class="loading" style="padding:4px 0;text-align:left">Calculando o custo teórico…</div>` : "");
    const cost = ctx.cost;
    const theoTxt = ctx.theo ? F.pct(ctx.theo.net) + (ctx.theo.netSe ? ` <span class="small muted">± ${F.pct(ctx.theo.netSe, 3, false)}</span>` : "") : ctx.theoPending ? "…" : E.optionLegs(s).length ? "—" : "0,00%";
    let prof = null;
    if (ctx.ok) prof = E.profileSummary(s, cost);
    $("s-kpis").innerHTML = [
      kpi("Custo das opções usado", cost == null ? "—" : F.pct(cost), st.costMode === "informado" ? "informado (mesa)" : "teórico"),
      kpi("Custo teórico", theoTxt, "BS + Monte Carlo"),
      kpi("Retorno máximo", !prof ? "—" : prof.gain_unlimited ? "Ilimitado" : F.pct(prof.return_max - ctx.extra), "no vencimento"),
      kpi("Pior retorno", !prof ? "—" : prof.loss_unlimited ? "Ilimitado" : F.pct(prof.return_min - ctx.extra), "no vencimento"),
      kpi("Prazo", `${F.int(ctx.n)} pregões`, ctx.obs ? `apuração em ${F.date(ctx.obs)}` : `≈ ${F.num(ctx.n / 21, 1)} meses`),
      kpi("Valor investido", F.brl(st.invested, 0), "referência: mínimo de R$ 30 mil nas lâminas", true),
    ].join("");

    if (ctx.ok) {
      CH().payoff($("s-payoff"), s, cost, ctx.extra);
      $("s-payoff-sub").textContent = `custo ${F.pct(cost, 2, false)}${ctx.extra ? ` · custos adicionais ${F.pct(ctx.extra, 2, false)}` : ""}`;
      $("s-summary").innerHTML = E.describe(s, cost).map((t) => `<li>${t}</li>`).join("") +
        `<li class="small">Retornos no vencimento, <b>brutos de IR</b>, sobre o valor investido ${E.hasStock(s) ? "(ação + custo das opções)" : "(prêmio pago)"}${ctx.extra ? `, já descontados ${F.pct(ctx.extra, 2, false)} de custos adicionais` : ""}.</li>`;
      const vars = st.variations || E.defaultVariations(s);
      const vin = $("s-vars");
      if (document.activeElement !== vin) vin.value = vars.map((v) => F.num(v * 100, Math.abs(v * 100 - Math.round(v * 100)) < 1e-9 ? 0 : 2)).join("; ");
      const t = E.profitabilityTable(s, cost, vars, ctx.extra);
      $("s-quadro").innerHTML = `<div style="overflow-x:auto"><table class="compact"><thead><tr><th>Variação da ação</th>${t.columns.map((c) => `<th>${c}</th>`).join("")}${t.columns.map((c) => `<th>${c.replace("Barreira ", "")} (R$)</th>`).join("")}</tr></thead><tbody>
        ${t.rows.map((r) => `<tr><td>${F.pct(r.v, r.v * 100 % 1 ? 2 : 0)}</td>${r.values.map((x) => `<td>${x == null ? '<span class="muted" title="Cenário impossível com monitoramento no fechamento">—</span>' : App.signed(x)}</td>`).join("")}${r.values.map((x) => `<td class="num">${x == null ? "—" : F.brl(st.invested * x)}</td>`).join("")}</tr>`).join("")}
        </tbody></table></div>${E.events(s).length ? `<div class="small muted" style="margin-top:8px">“—” = cenário impossível (ex.: terminar acima de uma barreira de alta sem tê-la tocado).</div>` : ""}`;
    } else {
      CH().disposeIn($("s-payoff").parentElement); $("s-payoff").innerHTML = `<div class="loading">${ctx.theoPending ? "Calculando o custo teórico…" : "Corrija a estrutura para ver o payoff."}</div>`;
      $("s-summary").innerHTML = ""; $("s-quadro").innerHTML = "";
    }

    // Custo teórico por perna
    const th = $("s-theo");
    $("s-theo-sub").textContent = `vol ${F.pct(ctx.sigma, 1, false)} · taxa ${F.pct(ctx.rateAnnual, 2, false)} a.a. · ${F.int(ctx.n)} pregões`;
    if (!E.optionLegs(s).length) th.innerHTML = `<p class="muted small">Sem opções na estrutura.</p>`;
    else if (ctx.theoPending) th.innerHTML = `<div class="loading">Calculando (Monte Carlo com ${F.int(st.adv.pricingPaths)} caminhos para as barreiras)…</div>`;
    else if (ctx.theoError) th.innerHTML = `<div class="err-note">${esc(ctx.theoError)}</div>`;
    else if (ctx.theo) {
      const diff = st.costMode === "informado" ? st.costInformed - ctx.theo.net : null;
      th.innerHTML = `<div style="overflow-x:auto"><table class="compact"><thead><tr><th>Perna</th><th>Método</th><th>Preço unitário</th><th>Contribuição</th><th>Erro padrão</th></tr></thead><tbody>
        ${ctx.theo.legs.map((x) => `<tr><td style="white-space:normal">${esc(E.legLabel(x.leg))}</td><td>${x.method}</td><td>${F.pct(x.unit, 3, false)}</td><td>${F.pct(x.signed, 3)}</td><td>${x.se ? F.pct(x.se, 3, false) : "—"}</td></tr>`).join("")}
        <tr><td><b>Custo líquido</b></td><td></td><td></td><td><b>${F.pct(ctx.theo.net, 3)}</b></td><td>${ctx.theo.netSe ? F.pct(ctx.theo.netSe, 3, false) : "—"}</td></tr></tbody></table></div>
        ${diff != null ? `<p class="small" style="margin:10px 0 0">Custo informado <b>${F.pct(st.costInformed)}</b> × teórico <b>${F.pct(ctx.theo.net)}</b>: diferença de <b>${F.pct(diff)}</b> do valor inicial (≈ remuneração da estrutura + diferenças de vol/taxa em relação à mesa).</p>` : ""}
        <p class="small muted" style="margin:8px 0 0">Black-Scholes para vanilla; Monte Carlo neutro ao risco (antitéticas, seed fixa, ${F.int(ctx.theo.nPaths || st.adv.pricingPaths)} caminhos) para barreiras. Referência teórica: pode divergir do preço da mesa.</p>`;
    } else th.innerHTML = `<p class="muted small">Corrija a estrutura para calcular.</p>`;
  }

  App.on("structure", () => { if (alive()) { solverRes = null; buildEditor(); buildSolver(); } });
  App.on("results", update);
  App.views.estrutura = { render };
})();
