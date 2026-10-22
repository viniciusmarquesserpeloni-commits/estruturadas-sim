/* Página "Metodologia e fontes". */
(function () {
  "use strict";
  const App = window.App, E = App.E;
  App.views = App.views || {};

  function render(el) {
    const presetRows = Object.values(E.PRESETS).map((p) => `<li><b>${p.name}</b>: <code>${p.formula}</code></li>`).join("");
    el.innerHTML = `
      <div class="page-head"><div><h2>Metodologia e fontes</h2><p>Como o simulador calcula, quais convenções segue e o que ele não modela.</p></div></div>
      <div class="card"><div class="card-b prose">
        <h3>1. A estrutura é uma lista de pernas</h3>
        <p>Cada linha da tabela espelha a “Composição da Estratégia” das lâminas: tipo (ação, call, put), posição (comprada/vendida),
        preço de exercício e barreira em % do valor inicial, tipo de barreira (Knock Up/Down and In/Out) e proporção (opções por ação).
        Os presets apenas preenchem essa tabela.</p>

        <h3>2. Normalização e payoff</h3>
        <p>O valor inicial da ação vale 1 (100%), de modo que os mesmos parâmetros em % se aplicam a qualquer período do histórico.
        Em cada caminho de preços verifica-se se cada barreira foi tocada — <i>knock-in</i>: a opção só passa a existir se tocar;
        <i>knock-out</i>: deixa de existir se tocar — e soma-se o valor final das pernas no preço de apuração S<sub>T</sub>.</p>
        <ul>${presetRows}</ul>

        <h3>3. Retorno</h3>
        <p>Com <i>c</i> = custo líquido das opções em % do valor inicial (positivo = débito):</p>
        <span class="formula">com ação:        retorno = valor final / (1 + c) − 1
só com opções:   retorno = valor final / c − 1   (exige c &gt; 0)</span>
        <p>Custos/taxas adicionais (% do valor investido) são subtraídos do retorno. Os retornos são <b>brutos de IR</b>, como nas lâminas.</p>

        <h3>4. Backtest por janelas históricas (base)</h3>
        <p>Para cada pregão <i>t</i> com N pregões à frente, o caminho é <code>P[t+1 … t+N] / P[t]</code>, e a estrutura é aplicada com os
        mesmos parâmetros em todas as janelas. A fração de janelas com lucro estima a probabilidade de lucro “se você tivesse contratado num dia
        qualquer do passado”. A <b>amostra efetiva</b> (janelas não sobrepostas) é exibida porque janelas vizinhas são fortemente correlacionadas.</p>

        <h3>5. Monte Carlo (complemento)</h3>
        <ul>
          <li><b>Bootstrap em blocos</b> (padrão): sorteia blocos consecutivos (≈ 20 dias) dos log-retornos diários históricos e os encadeia —
          preserva caudas gordas e parte da aglomeração de volatilidade.</li>
          <li><b>GBM</b>: caminhos log-normais com a vol histórica e drift histórico, zero (retorno esperado nulo) ou CDI.</li>
        </ul>

        <h3>6. Modo ex-post</h3>
        <p>Aplica a estrutura no caminho realmente observado entre a contratação e a apuração. Antes do vencimento, mostra a marcação
        <b>intrínseca</b> “até hoje”, que não é o valor de mercado da estrutura.</p>

        <h3>7. Custo das opções</h3>
        <ul>
          <li><b>Informado</b>: o custo cotado pela mesa (0 nas estruturas sem custo, caso da maioria das lâminas).</li>
          <li><b>Teórico</b>: Black-Scholes-Merton para opções vanilla; Monte Carlo neutro ao risco (GBM, passos diários, variáveis antitéticas,
          seed fixa, 50 mil caminhos ou mais, com erro padrão) para opções com barreira. A taxa (Selic meta, efetiva ao ano) vira taxa contínua:
          <code>r = ln(1 + Selic)</code>. Padrões: vol histórica de 252 pregões e Selic meta do BCB, editáveis em “Mais opções”.</li>
          <li><b>Solver de custo zero</b>: escolhe uma ou mais pernas e um parâmetro (strike, barreira ou proporção) e encontra, pelo método de Brent,
          o valor que zera o custo líquido teórico (ou atinge um custo alvo).</li>
        </ul>

        <h3>8. Saída antecipada (desmontagem antes do vencimento)</h3>
        <p>As estruturas podem ser desmontadas antes do vencimento. A regra simulada: quando o retorno acumulado desde a contratação,
        já descontado o <b>spread de saída</b>, atinge o <b>gatilho</b> (padrão: 150% do CDI acumulado no mesmo período), o investidor é
        orientado a pedir a desmontagem; com o OK dele, ela acontece alguns pregões depois (padrão: 1), pelo valor daquele dia — mesmo que
        a estrutura tenha caído nesse meio-tempo. Sem o gatilho, a operação vai até o vencimento.</p>
        <span class="formula">retorno de saída no dia k = valor da estrutura(k) / (1 + c) − 1 − spread − custos
gatilho no dia k        = 1,5 × (CDI acumulado de 0 a k)</span>
        <p>O <b>valor da estrutura</b> em cada dia (marcação a modelo) é a ação mais o valor de cada opção com o prazo que falta:</p>
        <ul>
          <li>opção sem barreira: Black-Scholes;</li>
          <li>barreira já tocada: knock-in vira opção comum, knock-out vale zero;</li>
          <li>barreira ainda não tocada: fórmula fechada de Reiner-Rubinstein. Com monitoramento no fechamento, a barreira é afastada do preço
          por <code>B·e^(±0,5826·σ·√(1/252))</code> (correção de Broadie-Glasserman-Kou), o que reproduz o Monte Carlo diário dentro do erro
          padrão.</li>
        </ul>
        <p><b>Volatilidade implícita.</b> Não há histórico público de vol implícita para a maioria das ações. A marcação usa a vol realizada dos
        últimos 63 pregões (só com dados até o dia) mais um adicional (padrão: 3 pontos), ou a vol da contratação fixa. Para não depender de
        acertar o nível exato, a marcação é <b>calibrada ao preço pago</b>: a diferença entre o valor pago e o valor do modelo no dia da
        contratação é somada à marcação e amortizada linearmente até zerar no vencimento. Isso supõe que o preço da lâmina era justo
        naquele momento e acompanha o mercado a partir dali.</p>
        <p><b>Juros importam muito.</b> Com CDI alto, a parte "renda fixa" da estrutura vale menos e a régua de 150% do CDI sobe mais rápido:
        a saída antecipada fica mais rara e mais tardia. Por isso o backtest mostra o resultado separado pelo nível de CDI no início de cada
        janela. No Monte Carlo, a marcação usa o CDI atual e vol constantes, nos primeiros 2.000 caminhos.</p>
        <p>A comparação com o CDI considera o período em que o dinheiro ficou de fato aplicado, e o retorno anualizado usa o prazo de cada
        janela. A marcação é uma estimativa: o preço de desmontagem efetivo é o da mesa.</p>

        <h3>Convenções</h3>
        <ul>
          <li>1 mês = 21 dias úteis; ano = 252 pregões.</li>
          <li>Valor inicial = fechamento do dia da contratação; apuração no fechamento de <b>D−1 do vencimento</b> (liquidação em D+1, apenas informativa).</li>
          <li>Calendário de pregões: as datas da própria série de preços; para datas futuras, uma aproximação dos feriados da B3.</li>
          <li>Preço padrão: fechamento <b>ajustado por proventos</b> (as lâminas ajustam strikes e barreiras em eventos corporativos); há opção de preço bruto.</li>
          <li>Monitoramento de barreira: <b>fechamento diário</b> (padrão) ou <b>intradiário</b> (máxima para barreiras de alta e mínima para as de baixa;
          no Monte Carlo, que só gera fechamentos, aplica-se a correção de Broadie-Glasserman-Kou, deslocando a barreira em 0,5826·σ·√Δt).</li>
          <li>CDI histórico: série diária do BCB; sem ela, usa-se a taxa informada.</li>
        </ul>

        <h3>Limitações</h3>
        <ul>
          <li><b>Passado não garante futuro.</b> As janelas se sobrepõem: a amostra efetiva é muito menor que o número de janelas.</li>
          <li>Os parâmetros em % são aplicados igualmente em todas as janelas: a estrutura <b>não é reprecificada</b> com a vol e os juros de cada época.</li>
          <li>As lâminas nem sempre dizem se a barreira é monitorada no fechamento ou no intradiário, e isso muda a probabilidade de acionamento.</li>
          <li>Não modela risco de contraparte, chamada de margem, liquidez nem resgate antecipado a mercado.</li>
          <li>O modo Teórico é uma referência e pode divergir do preço da mesa (vol implícita, skew, spread, dividendos).</li>
          <li>Base de ações: lista de ações líquidas da B3, atualizada diariamente após o fechamento; para outras ações, envie um CSV.</li>
        </ul>

        <h3>Fontes de dados</h3>
        <ul>
          <li>Preços diários (fechamento, máxima, mínima e fechamento ajustado): Yahoo Finance, via biblioteca <code>yfinance</code>.</li>
          <li>CDI diário: Banco Central do Brasil — SGS, série 12. Selic meta: SGS, série 432.</li>
        </ul>
        <div class="disclaimer" style="margin-top:20px">Ferramenta educacional, de código aberto. Não é recomendação de investimento e não é afiliada a nenhuma instituição financeira.
        Código-fonte e versão em Python/Streamlit: <a href="https://github.com/viniciusmarquesserpeloni-commits/estruturadas-sim" target="_blank" rel="noopener">github.com/viniciusmarquesserpeloni-commits/estruturadas-sim</a>.</div>
      </div></div>`;
  }
  App.views.metodologia = { render };
})();
