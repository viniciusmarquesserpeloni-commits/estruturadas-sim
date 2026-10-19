/* Roteador (hash), cabeçalho e rodapé. */
(function () {
  "use strict";
  const App = window.App, F = App.fmt;
  const view = document.getElementById("view");
  const V = App.views || {};
  document.getElementById("btn-print").addEventListener("click", () => window.print());

  function header() {
    const idx = App.data.index;
    document.getElementById("pill-db").textContent = idx ? F.date(idx.dados_ate) : "—";
    document.getElementById("pill-acoes").innerHTML = idx ? `<b>${idx.acoes.length}</b> ações` : "";
    document.getElementById("footer").innerHTML = `
      <div><b>Fontes de dados</b></div>
      <div class="src">
        <a href="https://finance.yahoo.com/" target="_blank" rel="noopener">Yahoo Finance — cotações diárias (yfinance)</a>
        <a href="https://www3.bcb.gov.br/sgspub/" target="_blank" rel="noopener">Banco Central do Brasil — SGS série 12 (CDI)</a>
        <a href="https://www3.bcb.gov.br/sgspub/" target="_blank" rel="noopener">Banco Central do Brasil — SGS série 432 (Selic meta)</a>
      </div>
      <div>Dados até: <b>${idx ? F.date(idx.dados_ate) : "—"}</b>${idx ? ` · Atualizado em ${F.date(idx.gerado_em)}` : ""} · Metodologia: consultar <a href="#/metodologia">Metodologia e fontes</a> · <a href="https://github.com/viniciusmarquesserpeloni-commits/estruturadas-sim" target="_blank" rel="noopener">código-fonte</a>.</div>
      <div style="margin-top:6px">Ferramenta educacional e independente, de código aberto; não é afiliada a nenhuma instituição financeira e não é material oficial de nenhuma corretora.</div>
      <div style="margin-top:6px">Sem recomendação de investimento. Rentabilidade passada não representa garantia de rentabilidade futura. Retornos simulados brutos de IR; não consideram risco de contraparte, liquidez nem resgate antecipado. Leia a lâmina da operação antes de investir.</div>`;
  }

  const routes = { estrutura: V.estrutura, backtest: V.backtest, "monte-carlo": V["monte-carlo"], "ex-post": V["ex-post"], metodologia: V.metodologia };
  function go() {
    const name = (location.hash.replace(/^#\/?/, "").split("/")[0]) || "estrutura";
    const route = routes[name] ? name : "estrutura";
    App.charts.disposeIn(view);
    view.innerHTML = "";
    document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-current", t.dataset.route === route ? "page" : "false"));
    document.getElementById("params").classList.toggle("hidden", route === "metodologia");
    routes[route].render(view);
    window.scrollTo(0, 0);
  }

  window.addEventListener("hashchange", go);
  App.renderParams();
  header();
  go();
  App.loadIndex().then(() => { header(); App.renderParams(); }).catch(() => header());
  App.recompute(0);
})();
