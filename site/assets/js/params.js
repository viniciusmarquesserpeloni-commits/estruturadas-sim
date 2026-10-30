/* Barra de parâmetros (topo de todas as páginas): ação, estrutura, prazo, valor, custo e opções avançadas. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc;
  const root = document.getElementById("params");
  const pctIn = (v, d = 2) => (v == null || !isFinite(v) ? "" : F.num(v * 100, d));
  const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  function render() {
    const st = App.state, adv = st.adv, t = st.term;
    const presetOpts = Object.entries(E.PRESETS).map(([k, p]) => `<option value="${k}" ${st.presetKey === k ? "selected" : ""}>${esc(p.name)}</option>`).join("");
    const tickerLabel = App.csv ? "CSV enviado" : st.ticker;
    root.innerHTML = `
      <div class="card"><div class="card-b" style="padding-top:16px">
        <div class="pbar">
          <div class="pfield"><span class="f-label">Ação</span>
            <div class="ac" id="p-ac" style="max-width:none"><input class="input" id="p-ticker" type="search" value="${esc(tickerLabel)}" placeholder="Código ou nome (ex.: PETR4)" autocomplete="off" aria-label="Ação"><div class="ac-list hidden" id="p-ac-list" role="listbox"></div></div>
          </div>
          <div class="pfield"><span class="f-label">Estrutura</span>
            <select class="select" id="p-preset" aria-label="Estrutura">${presetOpts}<option value="custom" ${st.presetKey === "custom" ? "selected" : ""}>Customizada</option><option value="__import">Importar lâmina (JSON)…</option></select>
            <input type="file" id="p-json" accept=".json,application/json" class="hidden">
          </div>
          <div class="pfield"><span class="f-label">Prazo</span>
            <div class="row">
              <div class="seg" role="group" aria-label="Definir prazo por">
                ${[["meses", "Meses"], ["du", "Dias úteis"], ["datas", "Datas"]].map(([k, l]) => `<button type="button" data-term="${k}" aria-pressed="${t.mode === k}">${l}</button>`).join("")}
              </div>
              ${t.mode === "meses" ? `<div class="seg" role="group" aria-label="Vértices">${[3, 6, 9, 12].map((m) => `<button type="button" data-months="${m}" aria-pressed="${t.months === m}">${m}m</button>`).join("")}</div><input class="input num" id="p-months" value="${t.months}" inputmode="numeric" aria-label="Meses" title="Outro prazo, em meses (× 21 pregões)" style="max-width:56px">`
                : t.mode === "du" ? `<input class="input num" id="p-du" value="${t.du}" inputmode="numeric" aria-label="Dias úteis" style="max-width:90px">`
                : `<input class="input" type="date" id="p-trade" value="${t.trade || ""}" aria-label="Contratação" title="Contratação"><input class="input" type="date" id="p-expiry" value="${t.expiry || ""}" aria-label="Vencimento" title="Vencimento">`}
            </div>
          </div>
          <div class="pfield"><span class="f-label">Valor investido (R$)</span>
            <input class="input num" id="p-invested" value="${F.num(st.invested, 2)}" inputmode="decimal" aria-label="Valor investido">
          </div>
          <div class="pfield"><span class="f-label">Custo das opções (% do valor inicial)</span>
            <div class="row">
              <div class="seg" role="group" aria-label="Modo de custo">
                <button type="button" data-cost="informado" aria-pressed="${st.costMode === "informado"}" title="Custo cotado pela mesa (0 = estrutura sem custo)">Informado</button>
                <button type="button" data-cost="teorico" aria-pressed="${st.costMode === "teorico"}" title="Calculado pelo app (Black-Scholes / Monte Carlo)">Teórico</button>
              </div>
              <input class="input num" id="p-cost" value="${pctIn(st.costInformed, 2)}" inputmode="decimal" aria-label="Custo líquido das opções" ${st.costMode === "teorico" ? "disabled" : ""} style="max-width:90px">
            </div>
          </div>
          <div class="pfield"><button class="btn" type="button" id="p-adv" aria-expanded="${st.advOpen}">${st.advOpen ? "Menos opções ▴" : "Mais opções ▾"}</button></div>
        </div>
        ${st.advOpen ? advHtml(st, adv) : ""}
        <div class="pstatus" id="p-status"></div>
      </div></div>`;
    bind();
    status(App.ctx);
  }

  function advHtml(st, adv) {
    const sel = (id, opts, cur) => `<select class="select" id="${id}">${opts.map(([v, l]) => `<option value="${v}" ${String(cur) === String(v) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
    const ctx = App.ctx || {};
    return `<div class="adv">
      <div class="f-group"><span class="f-label">Histórico de preços</span>
        <label class="fl">Desde <input class="input" type="date" id="a-start" value="${adv.start}"></label>
        <label class="fl">Preço ${sel("a-adj", [["1", "Ajustado por proventos"], ["0", "Bruto (sem ajuste)"]], adv.adjusted ? 1 : 0)}</label>
        <label class="fl">Ajustar ao CDI de hoje ${sel("a-reg", [["1", "Sim (recomendado)"], ["0", "Não (CDI da época)"]], adv.regimeAdjust ? 1 : 0)}</label>
        <div class="hint">Re-ancora cada janela no CDI de hoje, preservando o excesso de retorno da ação sobre o CDI da época: responde “e se eu contratasse agora?”.</div>
        <div class="hint">As lâminas ajustam strikes e barreiras em eventos corporativos; o preço ajustado é a aproximação padrão.</div>
        <label class="fl">Arquivo CSV <input type="file" id="a-csv" accept=".csv,.txt" class="input" style="padding:4px"></label>
        ${App.csv ? `<div class="hint">Usando CSV enviado (${F.int(App.csv.d.length)} pregões). <a href="#" id="a-csv-rm">Voltar às ações da base</a></div>` : `<div class="hint">Colunas Date, Close[, High, Low] — para ações fora da lista.</div>`}
      </div>
      <div class="f-group"><span class="f-label">Barreiras e custos</span>
        <label class="fl">Monitoramento ${sel("a-mon", [["close", "Fechamento diário"], ["intraday", "Intradiário"]], adv.monitoring)}</label>
        <div class="hint">Intradiário: máxima (barreiras de alta) e mínima (de baixa) do dia; no Monte Carlo, máxima/mínima sorteadas junto com o dia (FHS, bootstrap) ou correção de Broadie-Glasserman-Kou (GBM).</div>
        <label class="fl">Custos adicionais (% do investido) <input class="input num" id="a-extra" value="${pctIn(adv.extra)}" inputmode="decimal"></label>
      </div>
      <div class="f-group"><span class="f-label">Precificação (modo Teórico)</span>
        <label class="fl">Volatilidade (% a.a.) <input class="input num" id="a-vol" value="${pctIn(adv.vol)}" placeholder="${isFinite(ctx.histVol) ? F.num(ctx.histVol * 100, 2) + " (hist.)" : "automática"}" inputmode="decimal"></label>
        <label class="fl">CDI de referência (% a.a.) <input class="input num" id="a-rate" value="${pctIn(adv.rate)}" placeholder="${App.cdiAtual() != null ? F.num(App.cdiAtual() * 100, 2) + " (atual)" : "10,00"}" inputmode="decimal" title="Use o DI futuro do vencimento, se souber"></label>
        <label class="fl">Dividend yield (% a.a.) <input class="input num" id="a-q" value="${pctIn(adv.q)}" inputmode="decimal"></label>
        <label class="fl">Caminhos do MC (barreiras) ${sel("a-pp", [[20000, "20.000"], [50000, "50.000"], [100000, "100.000"], [200000, "200.000"]], adv.pricingPaths)}</label>
        <div class="hint">Em branco = automático: vol histórica de 252 pregões e Selic meta (BCB).</div>
      </div>
      <div class="f-group"><span class="f-label">Monte Carlo (backtest)</span>
        <label class="fl">Método ${sel("a-mcm", Object.entries(E.MC_METHOD_LABELS), adv.mcMethod)}</label>
        ${adv.mcMethod === "fhs_garch" ? `<label class="fl">Modelo de vol ${sel("a-vm", Object.entries(E.VOL_MODEL_LABELS), adv.volModel || "gjr")}</label>
        <div class="hint">Parte da vol de hoje e sorteia choques reais padronizados; a vol de cada caminho reage aos próprios choques e volta à média de longo prazo.</div>` : ""}
        <label class="fl">Retorno esperado da ação ${sel("a-drift", Object.entries(E.DRIFT_LABELS), adv.mcDrift)}</label>
        ${adv.mcDrift === "cdi_premio" ? `<label class="fl">Prêmio sobre o CDI (p.p. a.a.) <input class="input num" id="a-prem" value="${pctIn(adv.mcPremium)}" inputmode="decimal"></label>` : ""}
        ${adv.mcDrift === "personalizado" ? `<label class="fl">Retorno esperado (% a.a.) <input class="input num" id="a-custom" value="${pctIn(adv.mcCustom)}" inputmode="decimal"></label>` : ""}
        ${adv.mcDrift === "historico" ? `<div class="hint">Média do período: estatisticamente pouco confiável (erro padrão ≈ σ/√anos, cerca de ±8 p.p. a.a.).</div>` : ""}
        ${adv.mcMethod === "bootstrap" ? `<label class="fl">Bloco (dias) <input class="input num" id="a-block" value="${adv.mcBlock}" inputmode="numeric"></label>` : ""}
        <label class="fl">Nº de caminhos ${sel("a-mcp", [[1000, "1.000"], [5000, "5.000"], [10000, "10.000"], [20000, "20.000"], [50000, "50.000"]], adv.mcPaths)}</label>
        <label class="fl">Seed <input class="input num" id="a-seed" value="${adv.mcSeed}" inputmode="numeric"></label>
        <button class="btn ghost sm" type="button" id="a-reset" style="padding-left:0">Restaurar todos os padrões</button>
      </div>
      <div class="f-group"><span class="f-label">Saída antecipada</span>
        <label class="fl">Simular ${sel("x-on", [["1", "Sim"], ["0", "Não"]], adv.exitOn ? 1 : 0)}</label>
        <label class="fl">Gatilho (% do CDI) <input class="input num" id="x-trig" value="${F.num(adv.exitTrigger * 100, 0)}" inputmode="decimal"></label>
        <label class="fl">Spread de saída (% do valor inicial) <input class="input num" id="x-spread" value="${pctIn(adv.exitSpread)}" inputmode="decimal"></label>
        <label class="fl">Pregões até desmontar (OK do investidor) <input class="input num" id="x-delay" value="${adv.exitDelay}" inputmode="numeric"></label>
        <label class="fl">Carência (pregões) <input class="input num" id="x-min" value="${adv.exitMinDays}" inputmode="numeric"></label>
        <label class="fl">Vol da marcação ${sel("x-vol", [["garch", "GARCH do prazo restante + adicional"], ["rolling", "Móvel 63d + adicional"], ["fixed", "Da contratação (fixa)"]], adv.exitVolMode)}</label>
        <label class="fl">Adicional de vol (pontos) <input class="input num" id="x-voladd" value="${F.num(adv.exitVolAdd * 100, 1)}" inputmode="decimal"></label>
        <label class="fl">Calibrar ao preço pago ${sel("x-cal", [["1", "Sim"], ["0", "Não (modelo puro)"]], adv.exitCalibrate ? 1 : 0)}</label>
        <div class="hint">Desmonta quando o retorno acumulado, já descontado o spread, passa do gatilho; a marcação usa Black-Scholes e fórmulas de barreira.</div>
      </div>
    </div>`;
  }

  const setAdv = (patch) => App.update({ adv: Object.assign({}, App.state.adv, patch) });
  const optPct = (txt) => { const v = App.parseNum(txt); return v == null ? null : v / 100; };

  function bind() {
    const $ = (id) => root.querySelector("#" + id);
    // Ação (autocompletar com a lista da base)
    const inp = $("p-ticker"), list = $("p-ac-list");
    let hl = 0, items = [];
    const show = () => {
      const idx = App.data.index ? App.data.index.acoes : [];
      const q = norm(inp.value);
      items = idx.filter((a) => !q || norm(a.t).startsWith(q) || norm(a.n).includes(q)).slice(0, 40);
      list.innerHTML = items.length ? items.map((a, i) => `<button type="button" role="option" class="${i === hl ? "hl" : ""}" data-t="${a.t}"><b>${a.t}</b> · ${esc(a.n)}<small>Histórico desde ${F.date(a.ini)} · vol. 252d ${F.pct(a.vol, 1, false)}</small></button>`).join("")
        : `<div class="small muted" style="padding:10px 12px">Nenhuma ação encontrada. Para outras ações, envie um CSV em “Mais opções”.</div>`;
      list.classList.remove("hidden");
    };
    const pick = (t) => { App.csv = null; list.classList.add("hidden"); inp.value = t; App.update({ ticker: t }); render(); };
    inp.addEventListener("focus", () => { inp.select(); hl = 0; show(); });
    inp.addEventListener("input", () => { hl = 0; show(); });
    inp.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { hl = Math.min(hl + 1, items.length - 1); show(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { hl = Math.max(hl - 1, 0); show(); e.preventDefault(); }
      else if (e.key === "Enter") { const t = items[hl] ? items[hl].t : inp.value.trim().toUpperCase().replace(/\.SA$/, ""); if (t) pick(t); e.preventDefault(); }
      else if (e.key === "Escape") { list.classList.add("hidden"); inp.blur(); }
    });
    list.addEventListener("mousedown", (e) => { const b = e.target.closest("[data-t]"); if (b) { e.preventDefault(); pick(b.dataset.t); } });
    inp.addEventListener("blur", () => setTimeout(() => { list.classList.add("hidden"); inp.value = App.csv ? "CSV enviado" : App.state.ticker; }, 150));

    // Estrutura
    $("p-preset").addEventListener("change", (e) => {
      const k = e.target.value;
      if (k === "__import") { e.target.value = App.state.presetKey; $("p-json").click(); return; }
      if (k === "custom") App.setStructure(E.structure("Estrutura customizada", [E.leg("stock")]), "custom", false);
      else App.setStructure(E.PRESETS[k].build(), k);
    });
    $("p-json").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try { const s = E.fromJSON(await f.text()); App.setStructure(s, s.preset && E.PRESETS[s.preset] ? s.preset : "custom"); App.toast(`Estrutura “${s.name}” importada`); }
      catch (err) { App.toast("Não foi possível ler o JSON: " + err.message); }
      e.target.value = "";
    });

    // Prazo
    root.querySelectorAll("[data-term]").forEach((b) => b.addEventListener("click", () => { App.update({ term: Object.assign({}, App.state.term, { mode: b.dataset.term }) }); render(); }));
    const termIn = (id, key, parse) => { const el = $(id); if (el) el.addEventListener("change", () => { const v = parse(el.value); if (v != null) App.update({ term: Object.assign({}, App.state.term, { [key]: v }) }); }); };
    termIn("p-months", "months", (v) => { const n = App.parseNum(v); return n > 0 ? Math.round(n) : null; });
    root.querySelectorAll("[data-months]").forEach((b) => b.addEventListener("click", () => { App.update({ term: Object.assign({}, App.state.term, { months: +b.dataset.months }) }); render(); }));
    termIn("p-du", "du", (v) => { const n = App.parseNum(v); return n > 0 ? Math.round(n) : null; });
    termIn("p-trade", "trade", (v) => v || null);
    termIn("p-expiry", "expiry", (v) => v || null);

    // Valor e custo
    $("p-invested").addEventListener("change", (e) => { const v = App.parseNum(e.target.value); if (v != null && v >= 0) { App.update({ invested: v }); e.target.value = F.num(v, 2); } });
    root.querySelectorAll("[data-cost]").forEach((b) => b.addEventListener("click", () => { App.update({ costMode: b.dataset.cost }); render(); }));
    $("p-cost").addEventListener("change", (e) => { const v = App.parseNum(e.target.value); App.update({ costInformed: v == null ? 0 : v / 100 }); });
    $("p-adv").addEventListener("click", () => { App.state.advOpen = !App.state.advOpen; App.store.set("state", App.state); render(); });

    if (!App.state.advOpen) return;
    $("a-start").addEventListener("change", (e) => e.target.value && setAdv({ start: e.target.value }));
    $("a-adj").addEventListener("change", (e) => setAdv({ adjusted: e.target.value === "1" }));
    $("a-reg").addEventListener("change", (e) => setAdv({ regimeAdjust: e.target.value === "1" }));
    $("a-mon").addEventListener("change", (e) => setAdv({ monitoring: e.target.value }));
    $("a-extra").addEventListener("change", (e) => setAdv({ extra: optPct(e.target.value) || 0 }));
    $("a-vol").addEventListener("change", (e) => setAdv({ vol: optPct(e.target.value) }));
    $("a-rate").addEventListener("change", (e) => setAdv({ rate: optPct(e.target.value) }));
    $("a-q").addEventListener("change", (e) => setAdv({ q: optPct(e.target.value) || 0 }));
    $("a-pp").addEventListener("change", (e) => setAdv({ pricingPaths: +e.target.value }));
    $("a-mcm").addEventListener("change", (e) => { setAdv({ mcMethod: e.target.value }); render(); });
    if ($("a-vm")) $("a-vm").addEventListener("change", (e) => setAdv({ volModel: e.target.value }));
    if ($("a-drift")) $("a-drift").addEventListener("change", (e) => { setAdv({ mcDrift: e.target.value }); render(); });
    if ($("a-prem")) $("a-prem").addEventListener("change", (e) => { const v = optPct(e.target.value); if (v != null) setAdv({ mcPremium: v }); });
    if ($("a-custom")) $("a-custom").addEventListener("change", (e) => setAdv({ mcCustom: optPct(e.target.value) }));
    if ($("a-block")) $("a-block").addEventListener("change", (e) => { const v = App.parseNum(e.target.value); if (v >= 1) setAdv({ mcBlock: Math.round(v) }); });
    $("a-mcp").addEventListener("change", (e) => setAdv({ mcPaths: +e.target.value }));
    $("a-seed").addEventListener("change", (e) => { const v = App.parseNum(e.target.value); if (v != null) setAdv({ mcSeed: Math.round(v) }); });
    const intIn = (id, key, min) => $(id).addEventListener("change", (e) => { const v = App.parseNum(e.target.value); if (v != null && v >= min) setAdv({ [key]: Math.round(v) }); });
    $("x-on").addEventListener("change", (e) => setAdv({ exitOn: e.target.value === "1" }));
    $("x-trig").addEventListener("change", (e) => { const v = App.parseNum(e.target.value); if (v > 0) setAdv({ exitTrigger: v / 100 }); });
    $("x-spread").addEventListener("change", (e) => setAdv({ exitSpread: optPct(e.target.value) || 0 }));
    intIn("x-delay", "exitDelay", 0);
    intIn("x-min", "exitMinDays", 0);
    $("x-vol").addEventListener("change", (e) => setAdv({ exitVolMode: e.target.value }));
    $("x-voladd").addEventListener("change", (e) => setAdv({ exitVolAdd: optPct(e.target.value) || 0 }));
    $("x-cal").addEventListener("change", (e) => setAdv({ exitCalibrate: e.target.value === "1" }));
    $("a-reset").addEventListener("click", () => { if (confirm("Restaurar todos os parâmetros e a estrutura padrão (Collar Knock In de 3 meses)?")) { App.csv = null; App.reset(); } });
    $("a-csv").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try { App.csv = App.parseCsv(await f.text()); App.toast(`CSV carregado: ${F.int(App.csv.d.length)} pregões`); App.recompute(0); render(); }
      catch (err) { App.toast("CSV inválido: " + err.message); }
    });
    const rm = $("a-csv-rm"); if (rm) rm.addEventListener("click", (e) => { e.preventDefault(); App.csv = null; App.recompute(0); render(); });
  }

  /* Linha de status abaixo da barra (dados usados, prazo, cálculo em andamento). */
  function status(ctx) {
    const el = document.getElementById("p-status");
    if (!el || !ctx) return;
    const parts = [];
    if (ctx.dataError) parts.push(`<span class="neg">${esc(ctx.dataError)}</span>`);
    else if (ctx.priceError) parts.push(`<span class="neg">${esc(ctx.priceError)}</span>`);
    else if (ctx.P) {
      const info = App.data.byTicker && App.data.byTicker[ctx.ticker];
      parts.push(`<span><b>${esc(ctx.ticker)}</b>${info ? " · " + esc(info.n) : ""}</span>`);
      parts.push(`<span>${F.int(ctx.P.c.length)} pregões de ${F.date(ctx.P.d[0])} a ${F.date(ctx.P.d[ctx.P.d.length - 1])}</span>`);
    }
    if (ctx.n) parts.push(`<span>Prazo: <b>${App.termText(ctx)}</b></span>`);
    if (ctx.termError) parts.push(`<span class="neg">${esc(ctx.termError)}</span>`);
    if (isFinite(ctx.sigma)) parts.push(`<span>Vol. ${F.pct(ctx.sigma, 1, false)} a.a. · taxa ${F.pct(ctx.rateAnnual, 2, false)} a.a.</span>`);
    if (ctx.loading) parts.push(`<span class="muted">Calculando…</span>`);
    el.innerHTML = parts.join("");
  }

  App.on("results", status);
  App.on("params", render);
  App.renderParams = render;
})();
