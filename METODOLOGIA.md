### Como o simulador funciona

**1. A estrutura é uma lista de pernas.** Cada linha da tabela espelha a "Composição da Estratégia" das
lâminas: tipo (ação, call, put), posição (comprada/vendida), preço de exercício e barreira em % do valor
inicial, tipo de barreira (Knock Up/Down and In/Out) e proporção (opções por ação). Os presets só
preenchem essa tabela.

**2. Tudo é normalizado.** O valor inicial da ação vale 1 (100%). Assim, os mesmos parâmetros em % podem
ser aplicados a qualquer período do histórico.

**3. Payoff no vencimento.** Para cada caminho de preços, o simulador verifica se cada barreira foi tocada
(knock-in: a opção só passa a existir se tocar; knock-out: deixa de existir se tocar) e soma o valor final
das pernas no preço de apuração S_T.

**4. Retorno.** Com *c* = custo líquido das opções em % do valor inicial (positivo = débito):

- estruturas com ação: retorno = valor final / (1 + c) − 1;
- estruturas só com opções: retorno = valor final / c − 1 (exige c > 0);
- custos/taxas adicionais (% do valor investido) são subtraídos do retorno.

Os retornos são **brutos de IR**, como nas lâminas.

**5. Backtest por janelas históricas (base).** Para cada pregão *t* com N pregões à frente, o caminho é
P[t+1 … t+N] / P[t]. A estrutura, com os mesmos parâmetros em %, é aplicada em todas as janelas. A
fração de janelas com lucro estima a probabilidade de lucro "se você tivesse contratado em um dia
qualquer do passado".

**6. Monte Carlo (complemento).**

- *Bootstrap em blocos* (padrão): sorteia blocos consecutivos (≈ 20 dias) dos log-retornos diários
  históricos e os encadeia. Preserva caudas gordas e parte da aglomeração de volatilidade.
- *GBM*: caminhos log-normais com a vol histórica e drift histórico, zero (retorno esperado nulo) ou CDI.

**7. Modo ex-post.** Aplica a estrutura no caminho realmente observado entre a contratação e a apuração.
Se o vencimento ainda não chegou, mostra a marcação **intrínseca** "até hoje", que não é o valor de
mercado da estrutura.

**8. Custo das opções.**

- *Informado*: o custo cotado pela mesa (0 nas estruturas sem custo, caso da maioria das lâminas).
- *Teórico*: Black-Scholes-Merton para opções vanilla; Monte Carlo neutro ao risco (GBM, passos
  diários, antitéticas, seed fixa, 50 mil caminhos ou mais, com erro padrão) para opções com barreira.
  A taxa (Selic meta, efetiva ao ano) é convertida para contínua: r = ln(1 + Selic).
- *Solver de custo zero*: escolhe uma perna e um parâmetro (strike, barreira ou proporção) e encontra,
  por bisseção de Brent, o valor que zera o custo líquido teórico.

**9. Saída antecipada.** As estruturas podem ser desmontadas antes do vencimento. Regra simulada: quando o
retorno acumulado desde a contratação, já descontado o *spread de saída*, atinge o *gatilho* (padrão: 150% do
CDI acumulado no mesmo período), o investidor é orientado a pedir a desmontagem; com o OK dele, ela acontece
alguns pregões depois (padrão: 1), pelo valor daquele dia. Sem gatilho, a operação vai até o vencimento.

- *Marcação diária a modelo:* ação + valor de cada opção com o prazo que falta. Vanilla: Black-Scholes.
  Barreira já tocada: knock-in vira vanilla, knock-out vale zero. Barreira não tocada: fórmula fechada de
  Reiner-Rubinstein, com a barreira afastada do preço por B·e^(±0,5826·σ·√(1/252)) para reproduzir o
  monitoramento no fechamento (correção de Broadie-Glasserman-Kou).
- *Volatilidade implícita:* sem histórico público, usa-se a vol realizada dos últimos 63 pregões + um
  adicional (padrão 3 pontos), ou a vol da contratação fixa. A marcação é *calibrada ao preço pago*: a
  diferença entre o preço pago e o modelo no dia da contratação é somada e amortizada linearmente até o
  vencimento.
- *Juros:* com CDI alto, a parte de renda fixa da estrutura vale menos e a régua de 150% do CDI sobe mais
  rápido, então a saída fica mais rara e mais tardia. O backtest mostra o resultado separado pelo CDI no início
  de cada janela; o Monte Carlo usa o CDI atual e vol constantes, nos primeiros 2.000 caminhos.
- Os retornos são comparados ao CDI do período efetivamente investido e anualizados pelo prazo de cada janela.
  A marcação é uma estimativa; o preço de desmontagem efetivo é o da mesa.

### Convenções

- 1 mês = 21 dias úteis; ano = 252 pregões.
- Valor inicial = fechamento do dia da contratação; apuração no fechamento de D−1 do vencimento
  (liquidação em D+1, apenas informativa).
- Calendário de pregões: as datas da própria série de preços. Para datas futuras, usa-se uma aproximação
  dos feriados da B3.
- Preço padrão: fechamento **ajustado por proventos** (as lâminas ajustam strikes e barreiras em eventos
  corporativos). Há opção de usar o preço bruto.
- Monitoramento de barreira: *fechamento diário* (padrão) ou *intradiário* (máxima para barreiras de alta e
  mínima para as de baixa, no histórico; no Monte Carlo, que só gera fechamentos, aplica-se a correção de
  Broadie-Glasserman-Kou, deslocando a barreira em 0,5826·σ·√Δt em direção ao preço).
- CDI histórico: série diária 12 do SGS/BCB. Sem acesso à API, usa-se a taxa informada na barra lateral.

### Limitações

- **Passado não garante futuro.** As janelas se sobrepõem e são fortemente correlacionadas: a amostra
  efetiva (janelas não sobrepostas) é muito menor que o número de janelas.
- Os parâmetros em % são aplicados igualmente em todas as janelas; a estrutura **não é reprecificada** com
  a vol e os juros de cada época (no mundo real, os strikes e barreiras de custo zero mudam com o cenário).
- As lâminas nem sempre dizem se a barreira é monitorada no fechamento ou no intradiário, e isso muda a
  probabilidade de acionamento.
- Retornos brutos de IR. Não modela risco de contraparte, chamada de margem, liquidez nem resgate
  antecipado a mercado.
- O modo Teórico é uma referência e pode divergir do preço da mesa (spread, vol implícita, skew, dividendos).
- Ferramenta **educacional**; não é recomendação de investimento. O app não é afiliado a nenhuma
  instituição financeira.
