/* Página "Backtest histórico" (janelas móveis) + utilitários compartilhados com a página de Monte Carlo. */
(function () {
  "use strict";
  const App = window.App, E = App.E, F = App.fmt, esc = App.esc, CH = () => App.charts;
  App.views = App.views || {};

  /* ---------------- Utilitários compartilhados ---------------- */
  const UI = (App.ui = {});
  UI.kpi = (label, value, hint) => `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div>${hint ? `<div class="hint">${hint}</div>` : ""}</div>`;
  /* Faixa de incerteza de uma probabilidade: IC 95% (histórico) ou mín–máx entre cenários (Monte Carlo). */
  UI.ciText = (sm, k) => (sm.ci && sm.ci[k] ? `IC 95%: ${F.num(sm.ci[k][0] * 100, 0)}–${F.num(sm.ci[k][1] * 100, 0)}%` : null);
  UI.scenRange = (scen, k) => {
    if (!scen) return null;
    const v = scen.map((r) => r[k]).filter((x) => isFinite(x));
    return v.length ? `cenários: ${F.num(Math.min(...v) * 100, 0)}–${F.num(Math.max(...v) * 100, 0)}%` : null;
  };
  /* Indicadores na ordem da revisão: P(lucro) → P(> CDI de hoje) → P(barreira), cada um com sua faixa. */
  UI.kpis = function (sm, invested, what, scen) {
    const band = (k, fallback) => UI.ciText(sm, k) || UI.scenRange(scen, k) || fallback;
    const hasBar = isFinite(sm.p_barreira);
    return [
      UI.kpi("P(lucro > 0)", F.pct(sm.p_lucro, 1, false), band("p_lucro", `${what}: ${F.int(sm.n)}`)),
      UI.kpi("P(retorno > CDI de hoje)", F.pct(sm.p_cdi, 1, false), band("p_cdi", `CDI no prazo: ${F.pct(sm.cdi_hoje, 2, false)}`)),
      UI.kpi("P(barreira acionada)", hasBar ? F.pct(sm.p_barreira, 1, false) : "—", hasBar ? band("p_barreira", "") : "estrutura sem barreira"),
      UI.kpi("P(perda)", F.pct(sm.p_perda, 1, false), band("p_perda", `pior: ${F.pct(sm.pior)}`)),
      UI.kpi("Retorno mediano", App.signed(sm.mediana), `média ${F.pct(sm.media)} · ${F.brl(invested * sm.mediana)}`),
      UI.kpi("CVaR 5%", App.signed(sm.cvar5), `média dos 5% piores · P5 ${F.pct(sm.p5)}`),
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
      const ci = (s) => (s.ci && s.ci[k] && isFinite(s[k]) ? ` <span class="muted small">(${F.num(s.ci[k][0] * 100, 0)}–${F.num(s.ci[k][1] * 100, 0)}%)</span>` : "");
      rows.push(`<tr><td style="white-space:normal">${label}</td>${sums.map((s) => `<td>${signedRow && isFinite(s[k]) ? App.signed(s[k]) : cell(s[k], kind)}${ci(s)}</td>`).join("")}</tr>`);
    });
    return `<div style="overflow-x:auto"><table class="compact"><thead><tr><th>Métrica</th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  };
  /* Grade de cenários do Monte Carlo: retorno esperado (linhas) × volatilidade (colunas). */
  UI.scenarioCard = function (ctx, res) {
    const head = `<div class="card" style="margin-top:16px"><div class="card-h"><h3>Sensibilidade às premissas</h3><span class="sub">retorno esperado da ação × volatilidade · 5.000 caminhos por cenário</span></div>`;
    if (ctx.scenError) return head + `<div class="card-b"><div class="err-note">${esc(ctx.scenError)}</div></div></div>`;
    if (!ctx.scen) return head + `<div class="card-b"><div class="loading">Rodando 9 cenários…</div></div></div>`;
    const rows = ctx.scen, vols = E.SCENARIO_VOLS, prem = rows.find((r) => r.drift === "cdi_premio");
    const lbl = { zero: "Zero", cdi: `CDI (${F.pct(ctx.rateAnnual, 1, false)})`, cdi_premio: `CDI + ${F.num((prem.mu - ctx.rateAnnual) * 100, 0)} p.p.` };
    const sig = (v) => rows.find((r) => r.volScale === v).sigma;
    const table = (k, title) => `<div><div class="small" style="font-weight:600;margin-bottom:6px">${title}</div><table class="compact"><thead><tr><th>Retorno ↓ · vol →</th>${vols.map((v) => `<th>${F.pct(sig(v), 0, false)}</th>`).join("")}</tr></thead><tbody>
      ${E.SCENARIO_DRIFTS.map((d) => `<tr><td>${lbl[d]}</td>${vols.map((v) => { const r = rows.find((x) => x.drift === d && x.volScale === v); const c = d === "cdi" && v === 1; return `<td${c ? ' style="font-weight:700"' : ""}>${isFinite(r[k]) ? F.pct(r[k], 1, false) : "—"}</td>`; }).join("")}</tr>`).join("")}
      </tbody></table></div>`;
    const v63 = ctx.P ? E.histVol(ctx.P.c, 63) : NaN, base = rows.find((r) => r.volScale === 1).sigma / 1;
    const baseTxt = res && res.method === "fhs_garch" ? `vol média prevista pelo GARCH para o prazo (${F.pct(base, 1, false)} a.a.; no FHS a escala multiplica a vol de cada dia, que continua reagindo aos choques)`
      : `vol histórica do período carregado (${F.pct(base, 1, false)} a.a.)`;
    return head + `<div class="card-b"><div class="grid g-3">${table("p_lucro", "P(lucro > 0)")}${table("p_cdi", "P(retorno > CDI de hoje)")}${table("p_barreira", "P(barreira acionada)")}</div></div>
      <div class="card-note">Em negrito, o cenário central (retorno esperado = CDI, vol de base). Vol de base = ${baseTxt}; a vol realizada dos últimos 63 pregões é ${F.pct(v63, 1, false)} a.a.${isFinite(v63) ? ` (${F.num(v63 / base, 2)}× a base)` : ""}. Mesmos números aleatórios em todos os cenários.</div></div>`;
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

  /* ---------------- Saída antecipada (compartilhado com a página de Monte Carlo) ---------------- */
  UI.exitPremises = (cfg) => `Desmontagem ${cfg.delay === 0 ? "no próprio dia do gatilho" : `${cfg.delay} pregão(ões) após o gatilho (OK do investidor)`}, pelo valor daquele dia ·
    spread de saída ${F.pct(cfg.exitSpread, 2, false)} · ${cfg.minDays ? `carência de ${cfg.minDays} pregões · ` : ""}marcação: ${cfg.volMode === "fixed" ? "vol da contratação" : cfg.volMode === "garch" ? "vol GARCH prevista para o prazo restante" : "vol realizada de 63 pregões"} + ${F.num(cfg.volAdd * 100, 1)} pts, ${cfg.calibrate ? "calibrada ao preço pago na contratação" : "modelo puro (sem calibração)"}.`;
  /* kind = "hist" | "mc": o bloco mostra os dois métodos na tabela e destaca o da página. */
  UI.exitBlock = function (ctx, kind) {
    const st = App.state, cfg = ctx.exitCfg || App.exitCfg(st);
    const title = `<div class="section-title">Saída antecipada — gatilho de ${F.num(cfg.trigger * 100, 0)}% do CDI</div>`;
    if (!st.adv.exitOn) return title + `<div class="card"><div class="card-b small muted">Simulação de saída antecipada desativada em <b>Mais opções → Saída antecipada</b>.</div></div>`;
    if (ctx.exitError) return title + `<div class="err-note">${esc(ctx.exitError)}</div>`;
    const res = kind === "hist" ? ctx.hexit : ctx.mcexit;
    if (!res) return title + `<div class="card"><div class="loading">Marcando a estrutura dia a dia em cada ${kind === "hist" ? "janela" : "caminho"}…</div></div>`;
    const sm = E.summarizeExit(res), base = E.summarize(kind === "hist" ? ctx.hist : ctx.mc);
    const days = isFinite(sm.dias_mediana) ? `${F.int(sm.dias_mediana)} pregões` : "—";
    const cols = {};
    if (ctx.hexit) cols["Histórico"] = E.summarizeExit(ctx.hexit);
    if (ctx.mcexit) cols[`Monte Carlo (${F.int(ctx.mcexit.n)} caminhos)`] = E.summarizeExit(ctx.mcexit);
    const names = Object.keys(cols), sums = Object.values(cols);
    const table = `<div style="overflow-x:auto"><table class="compact"><thead><tr><th>Com saída antecipada</th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>
      ${E.EXIT_ROWS.map(([k, label, kind2]) => `<tr><td style="white-space:normal">${label}</td>${sums.map((s) => `<td>${!isFinite(s[k]) ? "—" : kind2 === "int" ? F.int(s[k]) : F.pct(s[k], 2, false)}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div>`;
    let regimes = "";
    if (kind === "hist" && !res.cfg.regimeAdjust && !(ctx.hist && ctx.hist.regimeAdjust)) {
      const rows = E.exitByCdiRegime(res), cur = ctx.rateAnnual;
      regimes = `<div class="card" style="margin-top:16px"><div class="card-h"><h3>Saída antecipada por nível de juros no início da janela</h3><span class="sub">CDI atual: ${F.pct(cur, 2, false)} a.a.</span></div>
        <div class="card-b"><div style="overflow-x:auto"><table class="compact"><thead><tr><th>Juros no início</th><th>Janelas</th><th>P(saída antecipada)</th><th>Dia mediano da saída</th><th>P(&gt; CDI) com saída</th><th>Retorno médio com saída</th><th>Retorno médio no vencimento</th></tr></thead><tbody>
        ${rows.map((r) => { const [lo, hi] = E.CDI_REGIMES.find((x) => x[2] === r.label); const now = cur > lo && cur <= hi;
          return `<tr${now ? ' style="background:var(--lime-soft)"' : ""}><td>${esc(r.label)}${now ? " <b>(atual)</b>" : ""}</td><td>${F.int(r.n)}</td><td>${F.pct(r.pSaida, 1, false)}</td><td>${isFinite(r.diaMediano) ? F.int(r.diaMediano) : "—"}</td><td>${F.pct(r.pCdi, 1, false)}</td><td>${App.signed(r.media)}</td><td>${App.signed(r.mediaVenc)}</td></tr>`; }).join("")}
        </tbody></table></div></div>
        <div class="card-note">Com juros altos, a parte "renda fixa" da estrutura vale menos e a régua de ${F.num(cfg.trigger * 100, 0)}% do CDI sobe mais rápido: a saída antecipada fica mais rara e mais tardia. A linha destacada é a mais parecida com o cenário atual.</div></div>`;
    }
    return title + `
      <div class="card kpi-strip">
        ${UI.kpi("P(saída antecipada)", F.pct(sm.p_saida, 1, false), UI.ciText(sm, "p_saida") || `gatilho atingido em ${F.pct(sm.p_gatilho, 1, false)}`)}
        ${UI.kpi("Dia mediano da saída", days, isFinite(sm.dias_p25) ? `metade entre ${F.int(sm.dias_p25)} e ${F.int(sm.dias_p75)}` : "nenhuma saída")}
        ${UI.kpi("Retorno médio com saída", App.signed(sm.media), `no vencimento: ${F.pct(sm.media_venc)}`)}
        ${UI.kpi("P(&gt; CDI) com saída", F.pct(sm.p_cdi, 1, false), `no vencimento: ${F.pct(base.p_cdi, 1, false)}`)}
        ${UI.kpi("% do CDI mediano", F.pct(sm.pct_cdi_mediana, 0, false), "do período efetivamente investido")}
        ${UI.kpi("Retorno anualizado mediano", App.signed(sm.anual_mediana), `prazo médio ${F.int(sm.dias_medio)} pregões`)}
      </div>
      <div class="grid g-2" style="margin-top:16px">
        <div class="card"><div class="card-h"><h3>Quando acontece a saída</h3><span class="sub">fração das ${kind === "hist" ? "janelas" : "simulações"} por mês da operação</span></div>
          <div class="card-b"><div class="chart" id="${kind}-exitdays"></div></div>
          <div class="card-note">${UI.exitPremises(cfg)}</div></div>
        <div class="card"><div class="card-h"><h3>Métricas com saída antecipada</h3><span class="sub">histórico × Monte Carlo</span></div><div class="card-b">${table}</div>
          <div class="card-note">Retornos comparados ao CDI do período em que o dinheiro ficou de fato na estrutura. Monte Carlo: marcação com CDI constante e ${ctx.mc && ctx.mc.method === "fhs_garch" && cfg.volMode !== "fixed" ? "a vol GARCH de cada caminho" : "vol constante"} nos primeiros ${F.int(E.EXIT_PATHS)} caminhos.</div></div>
      </div>${regimes}`;
  };
  UI.mountExit = function (rootEl, ctx, kind) {
    const el = rootEl.querySelector(`#${kind}-exitdays`);
    if (!el) return;
    const sets = [];
    if (ctx.hexit) sets.push({ name: "Histórico", color: CH().COLORS.BLUE, res: ctx.hexit });
    if (ctx.mcexit) sets.push({ name: "Monte Carlo", color: CH().COLORS.ORANGE, res: ctx.mcexit });
    CH().exitDays(el, sets, (ctx.hexit || ctx.mcexit).N);
  };

  /* ---------------- Página ---------------- */
  let root = null, winIdx = null;
  const alive = () => root && document.body.contains(root) && App.route === "backtest";
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
      <div class="card"><div class="kpi-strip">${UI.kpis(sm, st.invested, "janelas")}</div>
        <div class="card-note">${res.regimeAdjust ? `Caminhos re-ancorados no <b>CDI de hoje (${F.pct(ctx.rateAnnual, 2, false)} a.a.)</b>, preservando o excesso de retorno da ação sobre o CDI de cada época — “e se eu contratasse agora?”.` : `Ajuste ao CDI de hoje desligado: cada janela usa os juros da sua época.`}
        Janelas vizinhas se sobrepõem: a amostra efetiva é de ≈ ${F.int(sm.nEff)} janelas independentes, daí as faixas (IC 95% por block bootstrap).
        Em testes fora da amostra, a probabilidade de direção foi só um pouco mais precisa que a frequência histórica (confira no teste de calibração, na página Monte Carlo): use para comparar estruturas e dimensionar o risco de barreira.</div></div>
      <div class="card" style="margin-top:16px"><div class="card-h"><h3>Retorno de cada janela pela data de início</h3><span class="sub">cor = lucro / sem lucro · triângulo = barreira acionada</span></div>
        <div class="card-b"><div class="chart tall" id="b-ts"></div></div>
        <div class="card-note">Janelas vizinhas compartilham quase todo o caminho de preços: os pontos não são observações independentes.</div></div>
      <div class="grid g-2" style="margin-top:16px">
        <div class="card"><div class="card-h"><h3>Distribuição dos retornos</h3><span class="sub">histórico × Monte Carlo</span></div>
          <div class="card-b"><div class="chart" id="b-hist"></div></div>
          <div class="card-note">${ctx.mc ? "" : "Monte Carlo ainda em cálculo. "}Linha do CDI = CDI médio das janelas históricas.</div></div>
        <div class="card"><div class="card-h"><h3>Métricas: histórico × Monte Carlo</h3></div><div class="card-b">${UI.sideBySide(ctx)}</div></div>
      </div>
      ${UI.exitBlock(ctx, "hist")}
      <div class="section-title">Janela em destaque</div>
      <div class="card"><div class="card-h"><h3>Preço da ação e janela em destaque</h3><span class="sub">padrão: a pior janela</span></div>
        <div class="card-b">
          <div class="range-row"><input type="range" id="b-win" min="0" max="${res.ret.length - 1}" value="${winIdx}" aria-label="Janela (data de início)"><span id="b-win-txt" class="small"></span></div>
          <div class="chart" id="b-price" style="margin-top:8px"></div>
        </div></div>`;
    CH().windows(root.querySelector("#b-ts"), res);
    const sets = [{ name: "Janelas históricas", color: CH().COLORS.BLUE, values: res.ret }];
    if (ctx.mc) sets.push({ name: "Monte Carlo", color: CH().COLORS.ORANGE, values: ctx.mc.ret });
    CH().histogram(root.querySelector("#b-hist"), sets, sm.cdi_medio);
    UI.mountExit(root, ctx, "hist");
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
