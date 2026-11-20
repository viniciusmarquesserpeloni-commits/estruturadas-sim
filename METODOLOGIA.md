### A pergunta que o simulador responde

**"Qual a chance de esta estrutura dar certo se eu contratar agora?"** Por isso as probabilidades são
condicionadas ao momento atual: a régua é o **CDI de hoje** (o CDI efetivo mais recente, editável — use o DI
futuro do vencimento, se souber), as janelas históricas são re-ancoradas nos juros de hoje e o Monte Carlo
parte de um retorno esperado neutro (o próprio CDI). Os indicadores principais vêm nesta ordem: **P(lucro)**,
**P(retorno > CDI de hoje)** e **P(barreira acionada)**, sempre com uma faixa de incerteza.

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

- *Ajuste ao CDI de hoje (padrão):* cada caminho é multiplicado por (1 + CDI de hoje)^(k/252) ÷ (CDI acumulado da
  época de t a t+k). Isso preserva o excesso de retorno da ação sobre o CDI de cada época e o re-ancora nos juros de
  hoje. Sem o ajuste, estruturas com piso ou cupom fixo ficam infladas quando testadas em épocas de CDI baixo (ex.:
  Proteção Total 12m em BBDC4: P(> CDI) de 35% com o CDI da época, 23% com o CDI de hoje).
- *Intervalo de confiança (IC 95%):* as janelas se sobrepõem (em 3 meses, são só ≈ 61 janelas não sobrepostas),
  então cada probabilidade vem com um **intervalo de Wilson** calculado como se houvesse 1,5 × esse número de
  observações independentes. O fator 1,5 foi calibrado por simulação: com ele o intervalo contém o valor verdadeiro
  em 94%–97% dos casos (o block bootstrap usado antes ficava em 82%–90%). O intervalo de Wilson também não degenera
  quando o evento nunca aconteceu: P(perda) = 0% aparece como "0–4%", não "0–0%". Ex.: Collar Knock In 3m em BBDC4,
  P(lucro) = 57% (IC 47%–67%).

**6. Monte Carlo (complemento).**

- *Média dos 3 métodos* (padrão): os três métodos abaixo, com 1/3 dos caminhos cada, juntos — cada probabilidade
  é a média das três. Cada método tem um ponto fraco (o FHS exagera a vol logo depois de choques, o bootstrap usa a
  vol média do passado, o GBM supõe retornos normais); nos testes fora da amostra, a combinação foi a única previsão
  com ganho significativo sobre a frequência histórica tanto na barreira do Collar KI quanto num evento só de vol.
  Os indicadores mostram também o menor e o maior valor entre os três ("métodos").
- *FHS-GARCH* (*Filtered Historical Simulation*, Barone-Adesi, Giannopoulos & Vosper, 1999): primeiro
  estima-se a vol de cada dia do histórico por um **GJR-GARCH(1,1)** (ou GARCH(1,1)):
  h(t+1) = ω + (α + γ·1[ε(t) < 0])·ε(t)² + β·h(t), por máxima verossimilhança gaussiana com **alvo de variância**
  (a vol de longo prazo fica presa à do próprio histórico e só a dinâmica α, γ, β é estimada — sem isso, um choque
  extremo ou um dado errado levava a vol de longo prazo a valores absurdos em 1 de cada 6 ações). Dividindo cada retorno pela
  vol do seu dia, obtêm-se os **choques padronizados** z = ε/√h — os "sustos" reais da ação, sem o nível de vol da
  época. A simulação parte da **vol de hoje** e, a cada dia, sorteia um choque z* do histórico (com a máxima e a
  mínima daquele dia, também padronizadas), aplica e = √h·z* e atualiza h pela mesma equação: a vol de cada caminho
  reage aos próprios choques e volta à média de longo prazo no ritmo da meia-vida. No GJR, quedas aumentam a vol
  mais do que altas (efeito alavancagem).
- *Bootstrap em blocos*: sorteia blocos consecutivos (≈ 20 dias) de dias reais e os encadeia — fechamento,
  máxima e mínima de cada dia juntos (barreiras intradiárias usam os extremos sorteados). Preserva caudas gordas
  e parte da aglomeração de volatilidade, mas usa a vol média do período, não a de hoje.
- *GBM*: caminhos log-normais com a vol histórica (barreira intradiária pela correção de Broadie-Glasserman-Kou).
- *Retorno esperado da ação (drift):* **CDI (padrão, visão neutra)**, CDI + prêmio (padrão 5 p.p.), zero, média
  histórica ou personalizado. No bootstrap, troca-se a média dos log-retornos pelo drift escolhido:
  lr* = (lr − média) + [ln(1 + μ) − σ²/2]/252, de modo que E[S_T] ≈ (1 + μ)^(N/252). A média histórica é pouco
  confiável: seu erro padrão é ≈ σ/√anos (≈ ±8 p.p. a.a. em BBDC4), maior que o próprio prêmio de risco. No FHS,
  o log-retorno de cada dia é ln(1 + μ)/252 − h/2 + √h·z*, o que dá o mesmo E[S_T].
- *Sensibilidade às premissas:* com milhares de caminhos o erro de sorteio é desprezível; a incerteza que importa
  é de premissa. Por isso roda-se uma grade de 9 cenários — retorno esperado {zero, CDI, CDI + prêmio} × vol
  {0,6; 1,0; 1,3} × a vol de base (no FHS, a vol prevista para o prazo) —, com os mesmos números aleatórios, e as
  faixas dos indicadores mostram o mínimo e o máximo entre eles. As escalas 0,6 e 1,3 são, aproximadamente, os
  percentis 10 e 90 do erro histórico da previsão de vol em 3 meses (a grade anterior, 0,8–1,2, cobria só 46% dos
  desfechos).
- *Vol prevista para o prazo:* média geométrica entre a previsão do GARCH para o prazo,
  v_L + (h − v_L)·(1 − p^N)/(N·(1 − p)), e a variância realizada dos últimos 252 pregões. Sozinho, o GARCH
  superestimava a variância do prazo em 15%–25% (67% logo depois de choques extremos); a combinação ficou sem viés.
  É a vol usada no FHS **e** no modo Teórico (vol única).
- *Painel de volatilidade:* vol de hoje (previsão para o próximo pregão), vol prevista para o prazo (com as duas
  parcelas), vol de longo prazo √(ω/(1 − p)), meia-vida ln(0,5)/ln(p) pregões (p = α + γ·κ + β, a persistência;
  κ = fração média de z² vinda de quedas) e a vol realizada de 63 pregões.
- *Calibração walk-forward (sob demanda):* a cada 10 pregões, depois de 2 anos de dados, o simulador estima
  P(lucro), P(> CDI) e P(barreira) **só com os dados até aquela data** (GARCH reestimado a cada 252 pregões, CDI da
  data como régua, 1.000 caminhos) e confere o que aconteceu de fato. A régua é o **chute fixo** — a frequência do
  evento nas janelas já encerradas até a data. Métrica: *Brier score*, a média de (probabilidade − resultado 0/1)²;
  se o Brier do modelo não for menor que o do chute fixo, a probabilidade deve ser lida como ordem de grandeza. A
  coluna *t* é a estatística de Diebold-Mariano da diferença de perdas, com erro padrão robusto à sobreposição das
  janelas: com |t| < 2 a diferença não se distingue de ruído (o caso mais comum numa ação só). O diagrama de
  confiabilidade agrupa as previsões em faixas de 10 p.p. e compara com a frequência realizada.

**7. Modo ex-post.** Aplica a estrutura no caminho realmente observado entre a contratação e a apuração.
Se o vencimento ainda não chegou, mostra a marcação **intrínseca** "até hoje", que não é o valor de
mercado da estrutura.

**8. Custo das opções.**

- *Informado*: o custo cotado pela mesa (0 nas estruturas sem custo, caso da maioria das lâminas).
- *Teórico*: Black-Scholes-Merton para opções vanilla; Monte Carlo neutro ao risco (GBM, passos
  diários, antitéticas, seed fixa, 50 mil caminhos ou mais, com erro padrão) para opções com barreira. A vol padrão
  é a vol prevista para o prazo (a mesma do Monte Carlo); se souber a vol implícita da mesa, informe-a.
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
- *Volatilidade implícita:* sem histórico público, usa-se a **vol média prevista pelo GARCH para o prazo
  restante** (padrão; variância do dia só com dados até ele) + um adicional (padrão 3 pontos), ou a vol realizada
  dos últimos 63 pregões, ou a vol da contratação fixa. No Monte Carlo FHS, cada caminho é marcado com a própria
  vol simulada. A marcação é *calibrada ao preço pago*: a
  diferença entre o preço pago e o modelo no dia da contratação é somada e amortizada linearmente até o
  vencimento.
- *Juros:* com CDI alto, a parte de renda fixa da estrutura vale menos e a régua de 150% do CDI sobe mais
  rápido, então a saída fica mais rara e mais tardia. O backtest mostra o resultado separado pelo CDI no início
  de cada janela; o Monte Carlo usa o CDI atual (e, no FHS, a vol de cada caminho), nos primeiros 2.000 caminhos.
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
  mínima para as de baixa, no histórico; no FHS e no bootstrap, a máxima e a mínima sorteadas junto com o dia; no
  GBM, que só gera fechamentos, a correção de Broadie-Glasserman-Kou, deslocando a barreira em 0,5826·σ·√Δt em
  direção ao preço).
- CDI histórico: série diária 12 do SGS/BCB. Sem acesso à API, usa-se a taxa informada e o ajuste ao CDI de
  hoje é desligado (o app avisa).
- CDI de referência: CDI efetivo do último dia, (1 + CDI diário)^252 − 1, editável.
- CVaR 5%: média dos 5% piores resultados, ao lado do percentil 5.
- Qualidade dos dados: a base é filtrada a cada atualização. Salto isolado de preço com razão de desdobramento
  (2, 3, 4, 5 ou 10:1) é corrigido reescalando o histórico anterior; outras variações extremas de um dia (queda acima
  de 30% ou alta acima de 42%), fora de dias de movimento geral do mercado, são sinalizadas; e o trecho inicial em
  que a fonte repete o mesmo preço (papel sem negociação) é descartado. Os avisos aparecem na tela. No app local
  (Streamlit), sem a referência do mercado, os saltos são só sinalizados.

### Limitações

- **Passado não garante futuro.** As janelas se sobrepõem e são fortemente correlacionadas: a amostra
  efetiva (janelas não sobrepostas) é muito menor que o número de janelas — por isso os ICs.
- **Baixa capacidade preditiva para direção.** Em testes fora da amostra (walk-forward, 2012–2026, Collar Knock In
  3m em BBDC4, PETR4 e VALE3), o FHS-GARCH melhorou o Brier do chute fixo em só 1%–3% nas probabilidades de lucro e
  de superar o CDI, e em 4%–8% na de barreira: a vol é previsível no curto prazo, a direção quase nada. O simulador
  é mais útil para **comparar estruturas, dimensionar o risco de barreira e visualizar a distribuição** de
  resultados do que para prever se a ação vai subir. O painel de calibração refaz o teste para a estrutura e a
  ação escolhidas.
- O GARCH reage forte a choques extremos: logo depois de um dia como 26/10/2026 (BBDC4 −24,5%), a vol de hoje
  passa de 100% a.a. e a P(barreira) sobe bastante. É o comportamento desejado ("contratar agora"), mas a vol
  implícita da mesa pode estar abaixo disso; os cenários de vol ×0,8 mostram a sensibilidade.
- O ajuste ao CDI de hoje preserva o excesso de retorno da ação sobre o CDI de cada época: o histórico ainda
  carrega o prêmio de risco do período (2010–2026). O Monte Carlo com retorno esperado = CDI é a visão neutra.
- Os parâmetros em % são aplicados igualmente em todas as janelas; a estrutura **não é reprecificada** com
  a vol e os juros de cada época (no mundo real, os strikes e barreiras de custo zero mudam com o cenário).
- As lâminas nem sempre dizem se a barreira é monitorada no fechamento ou no intradiário, e isso muda a
  probabilidade de acionamento.
- Retornos brutos de IR. Não modela risco de contraparte, chamada de margem, liquidez nem resgate
  antecipado a mercado.
- O modo Teórico é uma referência e pode divergir do preço da mesa (spread, vol implícita, skew, dividendos).
- Ferramenta **educacional**; não é recomendação de investimento. O app não é afiliado a nenhuma
  instituição financeira.
