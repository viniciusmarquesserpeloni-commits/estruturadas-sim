/* Página "Comparar": até 4 estruturas lado a lado, com a mesma ação, prazo e premissas da barra de parâmetros.
   É o uso que o próprio simulador recomenda: as probabilidades servem mais para comparar estruturas e dimensionar
   barreiras do que para prever a direção da ação. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc, CH = () => App.charts;
  App.views = App.views || {};
  let root = null, formPreset = "collar", formCost = "0,00";
  const alive = () => root && document.body.contains(root) && App.route === "comparar";
  const MAX = 4;
  const results = new Map(); // chave (item + contexto) -> { hist, mc, error }

  const items = () => (App.state.compare || []).map((x) => Object.assign({}, x, { s: E.structure(x.structure.name, x.structure.legs, x.structure) }));

  /* Adiciona uma estrutura (com o custo que ela usa) à comparação; devolve uma mensagem para o usuário. */
  App.addToCompare = function (s, cost, label) {
    const list = (App.state.compare || []).slice();
    if (cost == null || !isFinite(cost)) return "Defina o custo das opções antes de comparar.";
    if (E.hasErrors(E.validate(s, cost))) return "A estrutura tem erros: corrija antes de comparar.";
    if (list.length >= MAX) return `A comparação já tem ${MAX} estruturas: remova uma antes.`;
    let name = label || s.name;
    if (list.some((x) => x.name === name)) { let k = 2; while (list.some((x) => x.name === `${name} (${k})`)) k++; name = `${name} (${k})`; }
    list.push({ id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), name, cost, structure: JSON.parse(JSON.stringify(s)) });
    App.update({ compare: list });
    return `“${name}” adicionada à comparação (${list.length} de ${MAX}).`;
  };

  function keyOf(it, ctx) {
    const a = App.state.adv;
    return JSON.stringify([it.structure.legs, it.cost, ctx.ticker, a.adjusted, a.start, ctx.n, a.monitoring, ctx.extra, ctx.rateAnnual,
      ctx.regimeAdjust, a.mcMethod, a.volModel, a.mcDrift, a.mcPremium, a.mcCustom, a.mcBlock, a.mcSeed, App.csv ? App.csv.d.length : 0, ctx.P ? ctx.P.c.length : 0]);
  }

  async function compute(ctx) {
    const a = App.state.adv;
    for (const it of items()) {
      const k = keyOf(it, ctx);
      if (results.has(k)) continue;
      const r = { pending: true };
      results.set(k, r);
      try {
        r.hist = await App.call("hist", { s: it.s, P: ctx.P, n: ctx.n, cost: it.cost, monitoring: a.monitoring, extra: ctx.extra, cdiF: ctx.cdiF, cdiRef: ctx.rateAnnual, regimeAdjust: ctx.regimeAdjust });
        const o = { method: a.mcMethod, volModel: a.volModel, nPaths: 6000, block: a.mcBlock, drift: a.mcDrift, premium: a.mcPremium, custom: a.mcCustom, cdiAnnual: ctx.rateAnnual, seed: a.mcSeed, monitoring: a.monitoring, extra: ctx.extra, keep: 0 };
        r.mc = await App.call("mc", { s: it.s, P: ctx.P, n: ctx.n, cost: it.cost, o });
      } catch (e) { r.error = e.message; }
      r.pending = false;
      if (results.size > 60) results.delete(results.keys().next().value);
      update(App.ctx);
    }
  }

  function render(el) { root = el; update(App.ctx); }

  function addForm() {
    const opts = Object.entries(E.PRESETS).map(([k, p]) => `<option value="${k}"${k === formPreset ? " selected" : ""}>${esc(p.name)}</option>`).join("");
    return `<div class="toolbar" style="align-items:flex-end;flex-wrap:wrap;gap:10px">
      <button class="btn primary" type="button" id="c-add-cur">Adicionar a estrutura atual</button>
      <span class="small muted">ou um preset:</span>
      <label class="pfield"><span class="f-label">Preset</span><select class="select" id="c-preset">${opts}</select></label>
      <label class="pfield" style="width:150px"><span class="f-label">Custo (% do valor inicial)</span><input class="input num" id="c-cost" value="${esc(formCost)}" inputmode="decimal"></label>
      <button class="btn" type="button" id="c-add-preset">Adicionar preset</button>
    </div>`;
  }

  function update(ctx) {
    if (!alive() || !ctx) return;
    const list = items();
    const head = `<div class="page-head"><div><h2>Comparar estruturas</h2><p>Até ${MAX} estruturas lado a lado, com a mesma ação, prazo e premissas da barra de parâmetros; cada uma com o seu custo. É o melhor uso das probabilidades: comparar estruturas e dimensionar barreiras.</p></div></div>`;
    const blocked = App.ui.blocked(ctx);
    CH().disposeIn(root);
    if (blocked && !list.length) { root.innerHTML = head + blocked; return; }
    if (!list.length) {
      root.innerHTML = head + `<div class="card"><div class="card-b"><p style="margin-top:0">Nenhuma estrutura na comparação ainda. Monte uma estrutura na aba <a href="#/estrutura">Estrutura</a> e clique em <b>Adicionar à comparação</b>, ou adicione aqui a estrutura atual ou um preset.</p>${addForm()}</div></div>`;
      bind();
      return;
    }
    const ready = !!(ctx.P && ctx.cdiF && ctx.n && !ctx.priceError && !ctx.dataError);
    if (ready) compute(ctx);
    const warn = ctx.dataError || ctx.priceError ? `<div class="err-note">${esc(ctx.dataError || ctx.priceError)}</div>` : !ready ? `<div class="loading">Carregando os preços…</div>` : "";
    const res = list.map((it) => (ready ? results.get(keyOf(it, ctx)) : null));
    const sums = res.map((r) => (r && r.hist && r.mc ? { h: E.summarize(r.hist), m: E.summarize(r.mc) } : null));
    const prof = list.map((it) => { try { return E.profileSummary(it.s, it.cost); } catch (e) { return null; } });
    const cell = (i, fn) => (res[i] && res[i].error ? `<span class="neg small">${esc(res[i].error)}</span>` : sums[i] ? fn(sums[i]) : `<span class="muted small">calculando…</span>`);
    const pct = (v, d = 1) => (isFinite(v) ? F.pct(v, d, false) : "—");
    const ci = (s, k) => (s.ci && s.ci[k] ? ` <span class="muted small">(${F.num(s.ci[k][0] * 100, 0)}–${F.num(s.ci[k][1] * 100, 0)}%)</span>` : "");
    /* índices com o melhor valor (empates em negrito juntos; nada em negrito se todos forem iguais) */
    const best = (vals, higher = true) => {
      const ok = vals.filter((x) => isFinite(x));
      if (ok.length < 2) return [];
      const t = higher ? Math.max(...ok) : Math.min(...ok), idx = vals.map((x, i) => (isFinite(x) && Math.abs(x - t) < 1e-9 ? i : -1)).filter((i) => i >= 0);
      return idx.length === ok.length ? [] : idx;
    };
    const rows = [
      ["section", "Estrutura"],
      ["Custo das opções", list.map((it) => F.pct(it.cost, 2, false))],
      ["Retorno máximo no vencimento", prof.map((p) => (p ? (p.gain_unlimited ? "ilimitado" : pct(p.return_max, 2)) : "—"))],
      ["Pior retorno no vencimento", prof.map((p) => (p ? (p.loss_unlimited ? "ilimitado" : pct(p.return_min, 2)) : "—"))],
      ["section", "Backtest histórico (com IC 95%)"],
      ["P(lucro > 0)", "h", "p_lucro", true],
      ["P(retorno > CDI de hoje)", "h", "p_cdi", true],
      ["P(barreira acionada)", "h", "p_barreira", null],
      ["Retorno mediano", "h", "mediana", true, 2],
      ["Retorno médio − CDI de hoje", "h", "excesso_cdi", true, 2],
      ["CVaR 5% (média dos 5% piores)", "h", "cvar5", true, 2],
      ["section", `Monte Carlo — ${esc((E.MC_METHOD_LABELS[App.state.adv.mcMethod] || "").replace(/ \(recomendado\)$/, ""))}`],
      ["P(lucro > 0)", "m", "p_lucro", true],
      ["P(retorno > CDI de hoje)", "m", "p_cdi", true],
      ["P(barreira acionada)", "m", "p_barreira", null],
      ["Retorno médio − CDI de hoje", "m", "excesso_cdi", true, 2],
      ["CVaR 5% (média dos 5% piores)", "m", "cvar5", true, 2],
    ];
    const body = rows.map((r) => {
      if (r[0] === "section") return `<tr><td colspan="${list.length + 1}" style="font-weight:700;padding-top:12px">${r[1]}</td></tr>`;
      if (Array.isArray(r[1])) return `<tr><td>${r[0]}</td>${r[1].map((v) => `<td>${v}</td>`).join("")}</tr>`;
      const [label, src, k, higher, d = 1] = r;
      const vals = sums.map((s) => (s ? s[src][k] : NaN)), b = higher == null ? [] : best(vals, higher);
      return `<tr><td>${label}</td>${list.map((it, i) => `<td${b.includes(i) ? ' style="font-weight:700"' : ""}>${cell(i, (s) => {
        const v = s[src][k], txt = k === "p_barreira" && !isFinite(v) ? "sem barreira" : !isFinite(v) ? "—" : d === 2 ? App.signed(v) : pct(v);
        return txt + (src === "h" && isFinite(v) ? ci(s.h, k) : "");
      })}</td>`).join("")}</tr>`;
    }).join("");
    const headRow = `<tr><th>Indicador</th>${list.map((it, i) => `<th style="white-space:normal">${esc(it.name)} <button class="btn ghost sm" type="button" data-rm="${it.id}" title="Remover da comparação" aria-label="Remover ${esc(it.name)}" style="padding:0 4px">×</button></th>`).join("")}</tr>`;
    root.innerHTML = head + `
      <div class="card"><div class="card-b">${addForm()}</div></div>${warn}
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Indicadores lado a lado</h3><span class="sub">${esc(ctx.ticker || "")} · ${App.termText(ctx)}</span></div>
        <div class="card-b" style="overflow-x:auto"><table class="compact">${headRow}${body}</table></div>
        <div class="card-note">Em negrito, o melhor valor de cada linha (P(barreira) não é marcada: tocar a barreira é bom em umas estruturas e ruim em outras). Quando os intervalos de confiança se sobrepõem, a diferença entre as estruturas pode ser só ruído da amostra. "Retorno médio − CDI" no Monte Carlo com retorno esperado = CDI mede o custo embutido de cada estrutura. Monte Carlo com 6.000 caminhos por estrutura.</div></div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Retorno no vencimento × variação da ação</h3><span class="sub">linha cheia: barreira não tocada · tracejada: barreira tocada</span></div>
        <div class="card-b"><div class="chart tall" id="c-payoff"></div></div></div>`;
    CH().payoffCompare(root.querySelector("#c-payoff"), list, ctx.extra || 0);
    bind();
  }

  function bind() {
    const $ = (id) => root.querySelector("#" + id);
    $("c-preset").addEventListener("change", (e) => { formPreset = e.target.value; });
    $("c-cost").addEventListener("input", (e) => { formCost = e.target.value; });
    $("c-add-cur").addEventListener("click", () => {
      const ctx = App.ctx, s = App.state.structure;
      App.toast(App.addToCompare(s, ctx.cost, s.name + (App.state.costMode === "teorico" ? " (custo teórico)" : "")));
      update(App.ctx);
    });
    $("c-add-preset").addEventListener("click", () => {
      const k = $("c-preset").value, s = E.PRESETS[k].build(), cost = (App.parseNum($("c-cost").value) || 0) / 100;
      App.toast(App.addToCompare(s, cost, s.name));
      update(App.ctx);
    });
    root.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => {
      App.update({ compare: (App.state.compare || []).filter((x) => x.id !== b.dataset.rm) });
      update(App.ctx);
    }));
  }

  App.on("results", update);
  App.views.comparar = { render };
})();
