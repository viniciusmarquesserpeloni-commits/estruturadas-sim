# Simulador de Operações Estruturadas (B3)

Estime a **probabilidade de sair no lucro** em uma operação estruturada com opções sobre ações da B3
(Collar, Booster, Proteção Total, Forward Knock Out, travas…) aplicando a estrutura ao histórico de preços
da ação — por janelas históricas móveis e por Monte Carlo — e veja o resultado real de operações já
contratadas (modo ex-post).

**Acesse o simulador:** https://viniciusmarquesserpeloni-commits.github.io/estruturadas-sim/

O simulador "fala a língua" das lâminas de operações estruturadas das corretoras: cada estrutura é a tabela
**Composição da Estratégia** (ação, calls e puts compradas/vendidas, strikes e barreiras em % do valor
inicial, tipo de barreira *Knock Up/Down and In/Out* e proporção), e os resultados aparecem também no formato
**Quadro de rentabilidade no vencimento**.

> ⚠️ Ferramenta **educacional** e independente. Não é recomendação de investimento. Passado não garante
> futuro. Retornos **brutos de IR**. O projeto não é afiliado a nenhuma instituição financeira e não usa
> marcas de terceiros.

---

## Sumário

1. [O que o simulador faz](#1-o-que-o-simulador-faz)
2. [Duas versões: site público e app Streamlit](#2-duas-versões-site-público-e-app-streamlit)
3. [Arquitetura e fluxo de dados](#3-arquitetura-e-fluxo-de-dados)
4. [Cálculos e seus racionais](#4-cálculos-e-seus-racionais)
   - 4.1 Normalização · 4.2 Pernas e barreiras · 4.3 Retorno · 4.4 Perfil no vencimento ·
     4.5 Validações · 4.6 Prazo e calendário · 4.7 Preços e ajustes · 4.8 CDI e Selic ·
     4.9 Backtest por janelas históricas · 4.10 Monte Carlo · 4.11 Monitoramento intradiário ·
     4.12 Ex-post · 4.13 Métricas · 4.14 Quadro de rentabilidade · 4.15 Precificação teórica ·
     4.16 Solver de custo zero · 4.17 Textos em linguagem simples · 4.18 Saída antecipada ·
     4.19 Incerteza: intervalos de confiança e cenários · 4.20 Volatilidade condicional (FHS-GARCH) e calibração
5. [Presets e fórmulas do payoff](#5-presets-e-fórmulas-do-payoff)
6. [Módulos: Python, JavaScript e demais linguagens](#6-módulos-python-javascript-e-demais-linguagens)
7. [Bibliotecas e serviços externos](#7-bibliotecas-e-serviços-externos)
8. [Testes e validação cruzada Python × JS](#8-testes-e-validação-cruzada-python--js)
9. [Como rodar, publicar e atualizar](#9-como-rodar-publicar-e-atualizar)
10. [Formato dos arquivos (lâmina JSON, dados do site, CSV)](#10-formato-dos-arquivos)
11. [Como digitar uma lâmina (passo a passo BBDC4)](#11-como-digitar-uma-lâmina-passo-a-passo-bbdc4)
12. [Premissas, limitações e roadmap](#12-premissas-limitações-e-roadmap)

Documentação complementar: [METODOLOGIA.md](METODOLOGIA.md) (texto da aba de metodologia) e
[docs/CONTEXTO_DO_PROJETO.md](docs/CONTEXTO_DO_PROJETO.md) (resumo técnico e histórico de decisões, para dar
continuidade ao projeto em outra conversa ou com outra pessoa).

---

## 1. O que o simulador faz

**A pergunta que ele responde:** *"qual a chance de esta estrutura dar certo se eu contratar agora?"*. Por isso
as probabilidades são condicionadas ao momento atual — régua no **CDI de hoje**, histórico re-ancorado nos juros
de hoje, Monte Carlo com retorno esperado neutro (CDI) — e sempre aparecem com uma **faixa de incerteza**. Os
indicadores principais vêm nesta ordem: **P(lucro) → P(retorno > CDI de hoje) → P(barreira acionada)**. Essa
orientação vem da revisão metodológica em [docs/REVISAO_METODOLOGICA.md](docs/REVISAO_METODOLOGICA.md)
(Fase 1: CDI de hoje, ICs, drift e cenários; Fase 2: Monte Carlo FHS-GARCH com a vol de hoje, painel de vol e
painel de calibração walk-forward — seções 4.19 e 4.20).

| Recurso | Descrição |
|---|---|
| Montador de estruturas | Toda estrutura é uma **lista de pernas**; 9 presets apenas preenchem essa lista, que pode ser editada livremente ou montada do zero. |
| Payoff e explicação | Gráfico do retorno no vencimento × variação da ação, com dois ramos quando há barreira (tocada / não tocada), e um resumo em linguagem simples. |
| Quadro de rentabilidade | Mesmo formato das lâminas: linhas de variação da ação × colunas "Barreira não atingida / atingida", em % e R$. |
| Backtest histórico | A estrutura aplicada em **todas as datas de início** possíveis do histórico (padrão: desde 2010). |
| Monte Carlo | Bootstrap em blocos dos retornos históricos (padrão) ou GBM com drift histórico, zero ou CDI. |
| Ex-post | A estrutura aplicada ao caminho realmente observado entre contratação e apuração; antes do vencimento, marcação intrínseca "até hoje". |
| Custo das opções | **Informado** (cotação da mesa) ou **Teórico** (Black-Scholes + Monte Carlo neutro ao risco). |
| Solver de custo zero | Encontra o strike, a barreira ou a proporção que zera o custo líquido teórico. |
| Saída antecipada | Desmontagem antes do vencimento quando a estrutura rende acima de 150% do CDI (configurável): marcação diária a modelo em todas as janelas, nos caminhos do Monte Carlo e na operação real (ex-post). |
| Exportações | Estrutura em JSON (para guardar lâminas) e resultados em CSV no formato brasileiro. |

## 2. Duas versões: site público e app Streamlit

| | Site público (GitHub Pages) | App Streamlit |
|---|---|---|
| Onde | [`site/`](site/) — HTML/CSS/JS estático | [`app.py`](app.py) |
| Visual | Mesmo layout do painel "Relatório de Fundos" (barra superior, abas, cards, ECharts) | Layout padrão do Streamlit, gráficos Plotly |
| Motor de cálculo | JavaScript ([`site/assets/js/engine/`](site/assets/js/engine/)), validado contra o Python | Python ([`estruturadas/`](estruturadas/)) |
| Ações | ~95 ações líquidas da B3 ([`scripts/tickers.py`](scripts/tickers.py)) + upload de CSV | Qualquer ticker do Yahoo Finance + CSV |
| Dados | Gerados pelo GitHub Actions todo dia útil às 19h30 (Brasília) | Baixados na hora (com cache de 6 h) |
| Hospedagem | Gratuita, sem servidor (GitHub Pages) | Local ou Streamlit Community Cloud |

As duas versões usam **a mesma metodologia**. O motor Python é a referência: os testes em
[`tests/js/`](tests/js/) comparam o motor JavaScript com resultados gerados pelo Python.

## 3. Arquitetura e fluxo de dados

```
                         ┌────────────────────────── Python (referência) ──────────────────────────┐
 Yahoo Finance ─┐        │ estruturadas/data.py   preços, CSV, CDI/Selic, calendário                │
 (yfinance)     ├──────► │ estruturadas/legs.py   pernas, barreiras, payoff vetorizado (numpy)      │
 BCB / SGS ─────┘        │ estruturadas/pricing.py  Black-Scholes, MC neutro ao risco, solver        │
 (séries 12, 432)        │ estruturadas/backtest.py janelas, bootstrap, GBM, ex-post                 │
                         │ estruturadas/metrics.py  estatísticas e quadro de rentabilidade            │
                         │ app.py (Streamlit) + estruturadas/charts.py (Plotly)                      │
                         └──────────────────────────────────────────────────────────────────────────┘
                                    │ scripts/make_js_fixtures.py (resultados de referência)
                                    ▼
 scripts/build_site_data.py ──► site/data/*.json ──► site/ (HTML + JS) ──► GitHub Pages
   (GitHub Actions, diário)                           engine/*.js  = porta do motor Python
                                                      worker.js    = cálculos pesados em segundo plano
                                                      views/*.js   = páginas; charts.js = ECharts
```

No site, o fluxo de uma simulação é: o usuário altera um campo → `App.update()` salva o estado no
`localStorage` → `App.recompute()` (com 120 ms de espera para agrupar digitação) carrega os preços da ação
(`data/precos/<TICKER>.json`), calcula o prazo, valida a estrutura, pede ao **Web Worker** o custo teórico,
o backtest histórico e o Monte Carlo (em sequência, com cache por parâmetros) e emite eventos `results` a
cada etapa; cada página redesenha só o que mudou.

## 4. Cálculos e seus racionais

### 4.1 Normalização

O valor inicial da ação vale **S0 = 1** (100%). Strikes e barreiras são frações desse valor
(`1,041 = 104,10%`). Um caminho de preços é uma matriz `n_caminhos × N` com os preços dos dias 1…N divididos
por S0; o último dia é a data de apuração (`S_T`).

*Racional:* as lâminas definem tudo em % do valor inicial, e normalizar permite aplicar **os mesmos
parâmetros** a qualquer janela do passado, qualquer que fosse o preço da ação na época.

### 4.2 Pernas, barreiras e payoff

Cada perna tem `tipo` (ação, call, put), `posição` (+1 comprada / −1 vendida), `strike K`, `tipo de barreira`,
`nível da barreira B` e `proporção q` (opções por ação, aceita fracionário). O valor final de cada perna:

```
ação:  posição · q · S_T
call:  posição · q · max(S_T − K, 0) · ativa
put:   posição · q · max(K − S_T, 0) · ativa
valor final da estrutura = soma das pernas
```

`ativa` depende da barreira:

| Tipo de barreira | Toque | `ativa` |
|---|---|---|
| Não se aplica | — | 1 |
| Knock Up and In | máximo do caminho ≥ B | 1 se tocou, 0 se não |
| Knock Up and Out | máximo do caminho ≥ B | 0 se tocou, 1 se não |
| Knock Down and In | mínimo do caminho ≤ B | 1 se tocou, 0 se não |
| Knock Down and Out | mínimo do caminho ≤ B | 0 se tocou, 1 se não |

Detalhes de implementação:

- O toque usa `≥ B − 10⁻¹²` (alta) e `≤ B + 10⁻¹²` (baixa): um preço exatamente na barreira conta como toque.
- Pernas com a mesma direção e o mesmo nível compartilham o mesmo **evento de barreira** (ex.: a call UI e a
  call UO da Proteção Total, ambas em 138,10%), e cada evento é medido uma vez.
- Para avaliar barreiras basta o **resumo do caminho**: `S_T`, o máximo e o mínimo monitorados. Isso torna o
  cálculo vetorizado e barato: `summarize_paths` → `event_hits` → `evaluate_summary` em
  [`legs.py`](estruturadas/legs.py) (e as funções equivalentes em
  [`engine/legs.js`](site/assets/js/engine/legs.js)).

### 4.3 Retorno sobre o capital investido

Com `c` = custo líquido das opções em % de S0 (positivo = débito, você paga; negativo = crédito):

```
estruturas com ação:          retorno = valor_final / (1 + c) − 1
estruturas só com opções:     retorno = valor_final / c − 1        (exige c > 0)
custos adicionais (% do investido) são subtraídos do retorno
resultado em R$ = valor investido × retorno
```

*Racional:* com ação, o investidor desembolsa a ação mais o prêmio líquido das opções (1 + c); numa estrutura
só de opções, o capital é o próprio prêmio pago. Os retornos são **brutos de IR**, como nas lâminas.

### 4.4 Perfil no vencimento (gráfico de payoff, retorno máximo e mínimo)

`expiry_payoff(estrutura, S_T, ramo)` calcula o valor final como função de `S_T` em dois ramos:

- **"none" — nenhuma barreira tocada:** `S_T` precisa estar do lado de dentro de todas as barreiras
  (`S_T < B` para alta, `S_T > B` para baixa). Fora disso o ponto é **inviável** e vira vazio (é o "—" do
  quadro de rentabilidade: com monitoramento no fechamento, não dá para terminar acima de uma barreira de alta
  sem tê-la tocado).
- **"all" — todas as barreiras tocadas** em algum momento: qualquer `S_T` é possível.

Retorno máximo e mínimo (`payoff_profile_summary`): avalia uma grade de 6.001 pontos de 0 a 3× o maior nível
(strikes, barreiras, 100%), mais cada nível e o ponto logo abaixo dele, nos dois ramos. Ganho ou perda
**ilimitados** são detectados pela inclinação do payoff em `S_T` muito alto (10× e 20× o topo da grade):
inclinação positiva = ganho ilimitado; negativa = perda ilimitada (calls vendidas sem cobertura).

Observação: quando o máximo fica "logo abaixo da barreira" (ex.: Proteção Total, 57,15% em S_T → 138,10⁻),
ele é um supremo não atingido; por isso P(atingir o retorno máximo) pode ser 0%.

### 4.5 Validações

`validate()` devolve erros (bloqueiam o cálculo) e avisos:

| Regra | Nível |
|---|---|
| Proporção ≤ 0 | erro |
| Opção sem strike válido (> 0) | erro |
| Barreira ausente, ou de alta ≤ 100%, ou de baixa ≥ 100% | erro |
| Estrutura só com opções e custo ≤ 0 | erro |
| Ação vendida a descoberto | aviso |
| Perda ilimitada na alta | aviso |

### 4.6 Prazo, datas e calendário

- **Meses:** `N = meses × 21` pregões. **Dias úteis:** N informado.
- **Datas** (convenção das lâminas): valor inicial = **fechamento do dia da contratação**; apuração no
  **fechamento de D−1 do vencimento** (pregão anterior ao vencimento); liquidação em D+1 é só informativa.
  `N` = número de pregões em (contratação, apuração].
- **Calendário:** usa as datas da própria série de preços onde há dados; para o trecho futuro, conta dias
  úteis com uma **aproximação dos feriados da B3**: 1/1, Carnaval (segunda e terça, 48 e 47 dias antes da
  Páscoa), Sexta-feira Santa, 21/4, 1/5, Corpus Christi (60 dias após a Páscoa), 7/9, 12/10, 2/11, 15/11,
  20/11 (desde 2024), 24/12, 25/12 e 31/12. A Páscoa vem do algoritmo de Meeus/Jones/Butcher.

Exemplo: Proteção Total BBDC4, contratação 19/11/2025, vencimento 25/11/2026 → apuração em 24/11/2026,
**249 pregões**.

### 4.7 Preços e ajustes

- Fonte: Yahoo Finance (`yfinance`), tickers da B3 com sufixo `.SA` (o app aceita `PETR4` e completa).
- **Preço ajustado por proventos (padrão):** fator `f = Adj Close / Close` aplicado a Open, High, Low e Close.
  *Racional:* as lâminas ajustam strikes e barreiras em eventos corporativos; usar o preço ajustado evita que
  um dividendo ou desdobramento pareça uma queda de preço e acione barreiras falsamente.
- Opção de **preço bruto** (sem ajuste).
- Limpeza: datas normalizadas, duplicatas removidas, preços ≤ 0 descartados; High/Low ausentes viram o Close;
  High ≥ Close ≥ Low é garantido.
- **Volatilidade histórica (padrão do modo Teórico):** desvio-padrão amostral dos log-retornos diários dos
  últimos 252 pregões × √252.

### 4.8 CDI e Selic

- **CDI de referência (CDI de hoje):** o CDI efetivo do último dia disponível, `(1 + CDI diário)^252 − 1`
  (13,65% a.a. em out/2026), editável — use o DI futuro do vencimento, se souber. É a régua de P(> CDI de hoje),
  a âncora do ajuste de regime, o drift "CDI" do Monte Carlo e a taxa do modo Teórico. Sem a série do BCB, cai
  para a Selic meta − 0,10 p.p.
- **Selic meta** (API SGS do BCB, série 432): referência secundária.
- **CDI diário** (série 12, % ao dia): usado no backtest histórico. A API limita consultas diárias a 10 anos,
  então o download é feito em blocos de 5 anos, com até 3 tentativas por bloco (a API tem falhas momentâneas;
  no Streamlit, uma falha não fica em cache).
- **Fator acumulado do CDI** em cada pregão da série: `fator_t = Π (1 + cdi_d)`, com o CDI de cada pregão
  sendo o último publicado até aquela data; sem dado, usa a taxa anual informada convertida para diária,
  `(1 + taxa)^(1/252) − 1`. O CDI de uma janela é `fator[t+N] / fator[t] − 1`.
- No Monte Carlo, o CDI do período é `(1 + taxa anual)^(N/252) − 1`.

### 4.9 Backtest por janelas históricas (método principal)

Para cada pregão `t` com N pregões à frente:

```
caminho_t = P[t+1 … t+N] / P[t]          (máxima/mínima também divididas por P[t])
```

No Python as janelas são construídas com `numpy.lib.stride_tricks.sliding_window_view` (uma "visão" sem
copiar dados); no JS, um laço que acumula S_T, máximo e mínimo de cada janela. A estrutura é aplicada a todas
as janelas com **os mesmos parâmetros em %**.

- **Nº de janelas** = nº de pregões − N.
- **Amostra efetiva** = ⌈nº de janelas / N⌉ — o número de janelas que **não se sobrepõem**.

*Racional:* responde "se eu tivesse contratado esta estrutura num dia qualquer do passado, quantas vezes
teria ganhado?", usando o comportamento real da ação (caudas, tendências, crises). Janelas vizinhas
compartilham quase todo o caminho, então os resultados são fortemente correlacionados: por isso a amostra
efetiva é exibida ao lado do número de janelas, e cada probabilidade tem um intervalo de confiança (4.19).

**Ajuste ao CDI de hoje (padrão ligado).** Para responder "e se eu contratasse agora?", cada caminho
(fechamento, máxima e mínima) é multiplicado por

```
f[t, k] = (1 + CDI_hoje)^(k/252) / (CDI acumulado da época de t a t+k)        k = 1..N
```

Isso preserva o **excesso de retorno da ação sobre o CDI** de cada época e o re-ancora nos juros de hoje.
*Por quê:* sem o ajuste, estruturas com piso ou cupom fixo ficam infladas quando testadas em épocas de CDI
baixo. Ex. (janelas desde 2010): Proteção Total 12m — P(> CDI) de 35% com o CDI da época contra **23%** com o
CDI de hoje em BBDC4; 21% → **11%** em PETR4. Estruturas atreladas à ação quase não mudam (Collar KI 3m em
BBDC4: 48% → 48%), porque o drift da ação sobe junto com o CDI. Observação: o ajuste mantém o prêmio de risco
do período (a ação de 2010–2026 rendeu acima do CDI), o que eleva um pouco P(lucro) (55,8% → 57,8% no Collar
KI 3m); a visão neutra é o Monte Carlo com retorno esperado = CDI. "P(> CDI da época)" (sem ajuste) segue na
tabela detalhada como métrica secundária.

### 4.10 Monte Carlo (complemento)

Três métodos. O padrão é o **FHS-GARCH** (seção 4.20), que parte da vol de hoje estimada por um GJR-GARCH e
sorteia choques reais padronizados. Bootstrap e GBM usam como vol de base o desvio-padrão dos log-retornos de
todo o histórico carregado × √252.

- **Bootstrap em blocos circular:** sorteia, para cada bloco de `L` dias (padrão 20), uma posição
  inicial aleatória na série e copia `L` dias consecutivos (dando a volta no fim da série) — **o fechamento, a
  máxima e a mínima de cada dia juntos** (`lr_t = ln(C_t/C_{t−1})`, `up_t = ln(H_t/C_t)`, `dn_t = ln(L_t/C_t)`);
  encadeia blocos até N dias: `ln S_j = Σ lr*`, máxima do dia `= S_j·e^{up}`, mínima `= S_j·e^{dn}`.
  *Racional:* reamostrar blocos preserva parte da autocorrelação e da aglomeração de volatilidade, além das
  caudas gordas reais; sortear a máxima/mínima junto dá barreiras intradiárias sem precisar da correção BGK.
- **GBM (log-normal):** `ln S_{j+1} − ln S_j = μ_d + σ·√(1/252)·Z`, com `Z ~ N(0,1)` e variáveis antitéticas;
  intradiário pela correção BGK (4.11).
- **Retorno esperado da ação (drift)**, escolhido pelo usuário e aplicado **aos três métodos**:

| Opção | Retorno esperado anual μ |
|---|---|
| **CDI (padrão)** | CDI de hoje — visão neutra |
| CDI + prêmio | CDI + 5 p.p. (editável) |
| Zero | 0 |
| Histórico | média dos log-retornos do período (com aviso) |
| Personalizado | valor informado |

  No GBM, `μ_d = (ln(1 + μ) − σ²/2)/252`. No bootstrap, troca-se a média dos log-retornos pelo drift escolhido
  e, opcionalmente, escalam-se os desvios por um fator de vol `k`:

```
lr* = [ln(1 + μ)/252 − ½·k²·var(lr)] + k · (lr − média(lr))        ⇒ E[S_T] ≈ (1 + μ)^(N/252)
```

  (testado: a aproximação de ½σ² difere da calibração exata de E[e^r] em menos de 0,1 p.p. a.a.).
  *Por que CDI como padrão:* a média histórica é estatisticamente pouco confiável — o erro padrão do drift
  anual é ≈ σ/√anos (≈ ±8 p.p. em BBDC4, ±10,5 p.p. em PETR4; Merton, 1980), maior que o próprio prêmio de
  risco —, e a sensibilidade é alta (revisão metodológica, Collar KI 3m em BBDC4, GBM com σ = 37%:
  drift −10% a.a. → P(lucro) 41%; 0% → 46%; CDI → 53%; CDI + 5 p.p. → 55%).
- Padrão: 10.000 caminhos, seed 42 (resultados reproduzíveis). No FHS, Python e JS usam o mesmo gerador
  (mulberry32) na mesma ordem e dão os mesmos caminhos; no bootstrap e no GBM os geradores são diferentes (NumPy
  PCG64 × mulberry32) e os números coincidem **estatisticamente**, não dígito a dígito.

### 4.11 Monitoramento de barreira: fechamento × intradiário

- **Fechamento diário (padrão):** compara a barreira com o Close de cada pregão.
- **Intradiário:** no histórico, no FHS e no bootstrap, usa a **máxima** do dia para barreiras de alta e a
  **mínima** para as de baixa (no FHS e no bootstrap, as sorteadas junto com o fechamento). No GBM (que só gera
  fechamentos) aplica a **correção de Broadie-Glasserman-Kou**: a barreira é deslocada em direção ao preço
  por `β·σ·√Δt`, com `β = 0,5826` e `Δt = 1/252`:

```
barreira de alta efetiva  = B · exp(−0,5826 · σ · √(1/252))
barreira de baixa efetiva = B · exp(+0,5826 · σ · √(1/252))
```

*Racional:* as lâminas nem sempre dizem como a barreira é monitorada, e o modo muda a probabilidade de
acionamento; o simulador permite comparar os dois.

### 4.12 Ex-post

Dadas a contratação e o vencimento de uma operação real: valor inicial = fechamento da contratação (ou do
último pregão anterior); caminho = pregões após a contratação até a apuração (D−1). Mostra o retorno, o
resultado em R$, se e quando cada barreira foi tocada (primeiro dia de toque) e o gráfico com strikes e
barreiras convertidos em R$ (nível × valor inicial).

Se o vencimento ainda não chegou, calcula a **marcação intrínseca "até hoje"**: o payoff como se a apuração
fosse no último pregão disponível, com o status das barreiras até então. Não é o valor de mercado da
estrutura, que inclui o valor temporal das opções.

### 4.13 Métricas

Para janelas históricas e Monte Carlo, lado a lado (`summarize`, tolerância numérica de 10⁻⁹):

| Métrica | Cálculo |
|---|---|
| P(lucro > 0) | fração com retorno > 0 — **primeiro indicador**, com IC 95% no histórico |
| P(retorno > CDI de hoje) | fração com retorno > `(1 + CDI_hoje)^(N/252) − 1`, com IC 95% |
| P(barreira acionada) | fração das janelas em que alguma barreira foi tocada, com IC 95% |
| P(perda) / P(retorno = 0) | fração com retorno < 0 / = 0 (P(perda) com IC 95%) |
| P(retorno > CDI da época) | só no histórico: retorno sem ajuste × CDI da própria janela (secundária) |
| CVaR 5% | média dos 5% piores resultados (pelo menos um), ao lado do P5 |
| P(atingir o retorno máximo) | fração com retorno ≥ máximo teórico − 10⁻⁶ |
| Barreira acionada | fração das janelas em que cada evento de barreira foi tocado |
| Média, mediana, P5, P25, P75, P95, pior, melhor | estatísticas do retorno; percentis com interpolação linear |
| Retorno anualizado | `(1 + r)^(252/N) − 1` |
| Só a ação | as mesmas estatísticas para `S_T − 1` |
| P(estrutura > só a ação) | fração em que a estrutura rendeu mais que a ação |
| CDI de hoje no prazo / CDI médio da época | `(1 + CDI_hoje)^(N/252) − 1` / média do CDI das janelas, e anualizado |

### 4.14 Quadro de rentabilidade

Linhas = variações da ação; colunas = retorno sem toque e com toque na barreira (ou uma coluna, se não houver
barreira), em % e em R$. As variações padrão incluem −30%…+30% em passos de 10 p.p., cada strike − 100%
(arredondado para baixo), e, para cada barreira de alta, o nível − 100% arredondado para baixo e +10 p.p.
acima (para baixa, arredondado para cima e −10 p.p.). Ex.: Proteção Total → −20, −10, 0, +4, +28, +38, +48%,
como na lâmina. O usuário pode digitar a própria lista.

### 4.15 Precificação teórica (modo "Teórico")

- **Taxa:** a Selic meta é efetiva ao ano; o modelo usa taxa contínua `r = ln(1 + Selic)`. Dividend yield `q`
  (padrão 0), prazo `T = N/252`.
- **Opções sem barreira — Black-Scholes-Merton:**

```
d1 = [ln(S/K) + (r − q + σ²/2)·T] / (σ·√T)        d2 = d1 − σ·√T
call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2)
put  = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)
```

  No JS, `N(·)` usa o algoritmo de Hart (implementação de Graeme West), com precisão de dupla; os testes
  conferem os preços contra o `scipy.stats.norm` até 10⁻¹².
- **Opções com barreira — Monte Carlo neutro ao risco:** GBM com drift `(r − q − σ²/2)·Δt`, passos diários,
  **variáveis antitéticas** (cada sorteio Z gera dois caminhos, +Z e −Z, o que reduz a variância), **seed
  fixa** e, por padrão, 50.000 caminhos. Preço = média de `e^(−rT) × payoff`; o **erro padrão** é calculado
  sobre a média de cada par antitético (as amostras independentes). Todas as pernas usam os **mesmos
  caminhos** (números aleatórios comuns), o que dá consistência ao custo líquido e ao solver. Para economizar
  memória, os caminhos são gerados em blocos e só o resumo (S_T, máximo, mínimo) é guardado.
- **Custo líquido** = Σ posição × proporção × preço unitário das opções (a ação não entra).
- No modo **Informado**, o custo teórico aparece ao lado para comparação; a diferença aproxima a remuneração
  da estrutura mais diferenças de vol e taxa em relação à mesa.

### 4.16 Solver de custo zero

Escolhe-se uma ou mais pernas e um parâmetro (strike, barreira ou proporção). O solver procura `x` tal que
`custo_líquido(x) − alvo = 0` (alvo padrão 0) pelo **método de Brent** (`scipy.optimize.brentq` no Python;
implementação própria do *zeroin* no JS), com tolerância 10⁻⁷ e os **mesmos caminhos** de Monte Carlo em
todas as iterações. Várias pernas marcadas recebem o mesmo valor (ex.: a put e a call do FKO compartilham o
strike). Intervalos padrão: strike 30%–300%; barreira de alta 100,01%–300%; de baixa 5%–99,99%;
proporção 0,0001–10. Se o custo tem o mesmo sinal nos dois extremos, não há raiz no intervalo e o solver
avisa.

Exemplos validados nos testes: Kc do Collar dado Kp; K do FKO dado B; proporção da call UO da Proteção Total.

### 4.17 Textos em linguagem simples

Cada preset tem um gerador de texto que lê **as pernas atuais e o custo** (não valores fixos) e calcula os
números citados com a própria função de payoff (ex.: "se a ação nunca subir 38,10% ou mais… até cerca de
57,15% logo abaixo da barreira"). Se a "forma" da estrutura mudar (tipos, posições e barreiras das pernas
diferentes das do preset), usa-se um texto genérico com cenários de −30% a +50% nos dois ramos.

### 4.18 Saída antecipada (desmontagem antes do vencimento)

As estruturas da mesa não são europeias na prática: podem ser desmontadas antes do vencimento. A regra
simulada reproduz a orientação da mesa:

1. Em cada pregão `k`, calcula-se o **retorno de saída**, o que o investidor receberia se desmontasse hoje,
   já descontado o spread de saída e os custos adicionais:

```
retorno_saída(k) = valor_estrutura(k) / (1 + c) − 1 − spread_saída − custos
(estrutura só com opções: valor_estrutura(k) / c − 1 − spread_saída − custos)
```

2. O **gatilho** é atingido no primeiro pregão em que
   `retorno_saída(k) ≥ múltiplo × CDI acumulado(0, k)` e `retorno_saída(k) > 0`, com `k ≥ carência`.
   Padrão: múltiplo = 1,5 (150% do CDI), carência = 0.
3. Com o **OK do investidor**, a desmontagem acontece `delay` pregões depois (padrão 1), pelo retorno de saída
   **daquele dia**, mesmo que a estrutura tenha caído entre o gatilho e a desmontagem. Se o gatilho não é
   atingido, ou se a desmontagem cairia no dia da apuração ou depois, vale o payoff do vencimento.

**Marcação a modelo (valor da estrutura no dia k)**, com prazo restante `T = (N − k)/252`, taxa `r` e vol `σ`:

| Perna | Valor |
|---|---|
| Ação | `S_k` |
| Opção sem barreira | Black-Scholes (seção 4.15) |
| Barreira já tocada | knock-in = opção vanilla; knock-out = 0 |
| Barreira ainda não tocada | fórmula fechada de Reiner-Rubinstein (abaixo), com a barreira ajustada pelo BGK |

Fórmula fechada de barreira (Reiner-Rubinstein, como em Haug; sem rebate), com `b = r − q`,
`μ = (b − σ²/2)/σ²`, `φ = +1` para call e `−1` para put, `η = −1` para barreira de alta e `+1` para de baixa:

```
x1 = ln(S/K)/(σ√T) + (1+μ)σ√T          x2 = ln(S/H)/(σ√T) + (1+μ)σ√T
y1 = ln(H²/(S·K))/(σ√T) + (1+μ)σ√T     y2 = ln(H/S)/(σ√T) + (1+μ)σ√T
A = φ·S·e^((b−r)T)·N(φx1) − φ·K·e^(−rT)·N(φx1 − φσ√T)
B = φ·S·e^((b−r)T)·N(φx2) − φ·K·e^(−rT)·N(φx2 − φσ√T)
C = φ·S·e^((b−r)T)·(H/S)^(2(μ+1))·N(ηy1) − φ·K·e^(−rT)·(H/S)^(2μ)·N(ηy1 − ησ√T)
D = φ·S·e^((b−r)T)·(H/S)^(2(μ+1))·N(ηy2) − φ·K·e^(−rT)·(H/S)^(2μ)·N(ηy2 − ησ√T)
```

| Opção | K > H | K < H |
|---|---|---|
| Call up-and-in | A | B − C + D |
| Call up-and-out | 0 | A − B + C − D |
| Call down-and-in | C | A − B + D |
| Call down-and-out | A − C | B − D |
| Put up-and-in | A − B + D | C |
| Put up-and-out | B − D | A − C |
| Put down-and-in | B − C + D | A |
| Put down-and-out | A − B + C − D | 0 |

*Racional:* uma fórmula fechada permite marcar a estrutura em todos os dias de todas as janelas (≈ 3.900
janelas × 249 dias no BBDC4) em segundos, sem rodar um Monte Carlo dentro de cada dia. A paridade in + out =
vanilla vale exatamente e é testada para todas as combinações.

**Correção BGK no sentido certo.** A fórmula supõe monitoramento contínuo; as barreiras das lâminas costumam
ser observadas no fechamento diário. Para reproduzir o monitoramento discreto com a fórmula contínua, a barreira
é **afastada** do preço: `H = B·e^(+0,5826·σ·√(1/252))` para alta e `B·e^(−0,5826·σ·√(1/252))` para baixa. (É
o sentido oposto ao da seção 4.11, que aproxima o intradiário a partir de caminhos diários.) Com o ajuste, a
fórmula bate com o Monte Carlo diário de 100 mil caminhos dentro de 1,5 erro padrão; sem ele, erra por 20–30
erros padrão. No modo intradiário a barreira não é ajustada.

**Volatilidade "implícita" da marcação.** Não há histórico público de vol implícita para a maioria das ações.
Opções implementadas:

- **Vol GARCH do prazo restante** (padrão desde a Fase 2): vol média prevista pelo GJR-GARCH para os pregões que
  faltam, a partir da variância do dia (seção 4.20), mais um **adicional** (padrão 3 pontos). No Monte Carlo FHS,
  cada caminho usa a própria variância simulada.
- **Vol realizada móvel:** desvio dos últimos 63 log-retornos até o próprio dia (sem olhar o futuro)
  × √252, mais o adicional, já que o mercado costuma cobrar vol acima da realizada.
- **Vol da contratação fixa:** a vol realizada do dia da contratação + adicional, durante toda a operação.

**Calibração ao preço pago (padrão).** O modelo raramente dá exatamente o preço da lâmina: a mesa usa vol
implícita, skew e margem próprios, e, no histórico, os mesmos parâmetros em % são aplicados em épocas de juros
e vol muito diferentes (no BBDC4 o valor teórico da Proteção Total no dia 0 vai de −8% a +6% do preço pago,
conforme a época). Por isso a diferença `preço pago − valor do modelo no dia 0` é somada à marcação e
amortizada linearmente até zerar no vencimento:

```
valor_calibrado(k) = valor_modelo(k) + [ (1 + c) − valor_modelo(0) ] · (N − k)/N
```

Isso equivale a supor que a lâmina estava a preço justo na contratação (a vol implícita está embutida no preço) e
acompanhar o mercado a partir daí. Sem a calibração ("modelo puro"), em épocas de juros baixos a estrutura já
nasce valendo mais que o preço pago e o gatilho dispara artificialmente nos primeiros dias (dia mediano 11,
contra 62 com calibração, no exemplo abaixo).

**Taxa de juros.** Histórico: o CDI de cada pregão, em taxa contínua `252·ln(1 + CDI do dia)`. Monte Carlo:
o CDI atual constante. Ex-post: o CDI realizado.

**Monte Carlo.** A saída antecipada usa os primeiros 2.000 caminhos completos (guardados pelo MC), com CDI
constante e vol de marcação constante (vol do método + adicional) — no FHS, a vol GARCH de cada caminho. Com monitoramento intradiário, os toques usam a barreira
deslocada em direção ao preço, como no payoff do MC.

**Juros mudam tudo.** Com CDI alto, a parte de renda fixa da estrutura (o piso) vale menos e a régua de 150%
do CDI cresce mais rápido; com CDI baixo acontece o contrário. Por isso o backtest separa o resultado pelo CDI
no início de cada janela (até 8%, 8–12%, acima de 12% a.a.) e destaca a faixa do CDI atual.

**Métricas** (`summarize_exit` / `E.summarizeExit`): P(gatilho atingido), P(saída antes do vencimento), dia da
saída (quartis), retorno médio e mediano com saída × levando ao vencimento, P(lucro), P(perda),
P(retorno > CDI do período **efetivamente investido**), % do CDI mediano do período investido e retorno
anualizado mediano `(1 + r)^(252/dias) − 1`, já que cada janela tem prazo diferente.

**Exemplo — Proteção Total BBDC4** (249 pregões, janelas desde 2010, gatilho 150% do CDI, spread de saída 1%,
desmontagem 1 pregão após o gatilho, vol móvel + 3 pontos, calibrada):

| | Histórico | Monte Carlo (CDI 13,75%, motor Python) |
|---|---|---|
| P(saída antecipada) | 69,1% | 21,9% |
| Dia mediano da saída | 62 | 224 |
| Retorno médio com saída × no vencimento | 5,5% × 11,0% | 7,9% × 8,6% |
| P(> CDI) com saída × no vencimento | 68,2% × 35,1% | 23,4% × 16,6% |

No histórico, as janelas que começaram com CDI acima de 12% tiveram saída antecipada em 50% dos casos (dia
mediano 160), contra 81% com CDI até 8%. **Leitura:** sair no gatilho troca retorno médio por consistência,
porque corta os cenários de alta forte; e o cenário de juros define a chance de sair cedo. Na operação real
(contratada em 19/11/2025), o retorno de saída estimado em 22/10/2026 era 18,85%, contra gatilho de 19,44%.

**Limitações.** A marcação é um modelo: o preço de desmontagem efetivo é o da mesa (vol implícita, skew,
spread real). O spread de saída padrão (1%) é uma estimativa: ajuste quando souber o valor praticado. O modelo
supõe que o investidor sempre aceita a desmontagem quando orientado.

### 4.19 Incerteza: intervalos de confiança e cenários

A revisão metodológica testou a capacidade preditiva do simulador (walk-forward, 722 datas, Collar KI 3m) com
o *Brier score* (menor = melhor; 0,25 = chutar 50%): para **direção** (P(lucro), P(> CDI)), nenhum modelo — vol
incondicional, realizada 63d, EWMA, GARCH — superou com folga o "chute climatológico" (a frequência histórica); o
GARCH melhorou a **probabilidade de barreira** (volatilidade é previsível no curto prazo, direção não). O painel
de calibração da Fase 2 (seção 4.20) refaz esse teste para qualquer estrutura e ação. Por isso a ferramenta
comunica faixas, não números cravados.

**Histórico — IC 95% por moving block bootstrap.** Para cada indicador 0/1 por janela (lucro, > CDI de hoje,
perda, barreira, saída antecipada): sorteiam-se blocos de `N` janelas consecutivas (N = prazo, o tamanho da
sobreposição) até completar a série, 1.000 vezes, e tomam-se os percentis 2,5% e 97,5% da média. Seed fixa e
gerador **mulberry32 idêntico nos dois motores** ([`estruturadas/rng.py`](estruturadas/rng.py) e `E.rng`), de
modo que Python e JS dão o mesmo intervalo (testado a 10⁻¹²). Margem típica: ±8 p.p. em 63 pregões (amostra
efetiva ≈ 66), ±10 p.p. em 126, ±12–15 p.p. em 252. Ex.: Collar KI 3m em BBDC4, P(lucro) = 56% (IC 48%–64%).

**Monte Carlo — grade de cenários.** Com 10.000 caminhos o erro de sorteio é desprezível; a incerteza que
importa é de **premissa**. Roda-se uma grade de 9 cenários — retorno esperado {zero, CDI, CDI + prêmio} × vol
{0,8; 1,0; 1,2} × a vol de base —, com 5.000 caminhos cada e os **mesmos números aleatórios**, e mostram-se:
o cenário central (CDI, vol 1,0) em destaque, a faixa mínimo–máximo de cada indicador e três tabelas de
sensibilidade (P(lucro), P(> CDI de hoje), P(barreira)). A nota da tabela compara a vol de base com a vol
realizada dos últimos 63 pregões, para mostrar se o momento atual está mais ou menos volátil que a média.

### 4.20 Volatilidade condicional (FHS-GARCH), painel de vol e calibração walk-forward

Fase 2 da revisão metodológica. A pergunta "qual a chance **se eu contratar agora**?" depende muito da vol de
**hoje**, e a vol tem memória: dias agitados vêm em sequência. O bootstrap e o GBM usam a vol média do período
(≈ 34% a.a. em BBDC4); logo depois do crash de 26/10/2026 (BBDC4 −24,5%, Ibovespa −13,9%), a vol de hoje está
muito acima disso.

**GJR-GARCH(1,1)** ([`estruturadas/garch.py`](estruturadas/garch.py), `engine/garch.js`). Sobre os log-retornos
sem a média, `ε_t = r_t − média`:

```
h(t+1) = ω + (α + γ·1[ε(t) < 0])·ε(t)² + β·h(t)          (GARCH(1,1): γ = 0)
```

`h` é a variância do dia seguinte: um choque grande hoje (ε²) aumenta a vol de amanhã, e β dá a memória. No GJR
(Glosten, Jagannathan & Runkle, 1993), quedas pesam mais (γ > 0, efeito alavancagem); quando não há assimetria
nos dados o ajuste dá γ ≈ 0 e o modelo vira o GARCH(1,1) — por isso o GJR é o padrão. Estimação por
**quase-máxima verossimilhança gaussiana** (`−½·Σ[ln h_t + ε_t²/h_t]`, h₀ = variância amostral), com
**Nelder-Mead determinístico escrito igual nos dois motores**, numa parametrização sem restrições que garante
ω > 0, α, γ, β ≥ 0 e persistência < 0,999 (`x0`: log da variância de longo prazo; `x1`: logística da persistência;
`x2`, `x3`: frações de choque e de assimetria). Dois pontos iniciais (persistência 0,97 e 0,90) e reinícios a
partir do melhor ponto evitam que o otimizador pare cedo (num caso real, a primeira versão parava na borda
p = 0,999 e dava vol de longo prazo de 150%); em 80 séries testadas o ajuste coincide com o ótimo do scipy até
10⁻¹³. Tempo: 0,05–0,9 s em Python e menos no navegador — o site ajusta o GARCH na hora, no Web Worker, para o
período e a ação escolhidos (inclusive CSV).

Grandezas derivadas (painel de vol):

| Grandeza | Fórmula | BBDC4, 28/10/2026 |
|---|---|---|
| Persistência p | α + γ·κ + β, κ = média de z²·1[z<0] dos resíduos (≈ 0,5) | 0,970 |
| Vol de hoje | √(252·h(T+1)) | 114,7% |
| Vol de longo prazo | √(252·ω/(1 − p)) | 37,0% |
| Vol média prevista para o prazo N | √(252·[v_L + (h − v_L)·(1 − p^N)/(N·(1 − p))]) | 82,0% (63 pregões) |
| Meia-vida | ln(0,5)/ln(p) pregões | 23 |
| Vol realizada (comparação) | desvio dos últimos 63 log-retornos × √252 | 63,3% |

**FHS — Filtered Historical Simulation** (Barone-Adesi, Giannopoulos & Vosper, 1999), método padrão do Monte
Carlo. Os **choques padronizados** `z_t = ε_t/√h_t` (re-normalizados para média 0 e desvio 1) são os "sustos"
reais da ação sem o nível de vol da época; a máxima e a mínima de cada dia também são padronizadas
(`u_t = ln(H_t/C_t)/√h_t`, `d_t = ln(L_t/C_t)/√h_t`). Cada caminho parte de `h = h(T+1)` e, a cada dia:

```
sorteia um dia q do histórico (i.i.d.)          e = √h · z_q
ln S += μ_d − ½·k²·h + k·e                       μ_d = ln(1 + μ)/252  ⇒  E[S_T] ≈ (1 + μ)^(N/252)
máxima = ln S + k·√h·u_q   ·   mínima = ln S + k·√h·d_q
h ← ω + (α + γ·1[e < 0])·e² + β·h
```

`k` é a escala de vol da grade de cenários (a dinâmica de h não muda; a vol média do caminho é multiplicada por
k). Com o drift "histórico", `μ_d = média(lr) + ½·k²·var(lr)`. Racional: o FHS combina a **vol condicional** do
GARCH (o nível de hoje e a volta gradual à média) com a **distribuição empírica** dos choques (caudas gordas e
assimetria reais), sem supor normalidade. Com α = γ = β = 0 ele vira um bootstrap i.i.d. com vol constante
(testado). Os sorteios usam o **mulberry32 vetorizado** em Python (`rng.integers`), na mesma ordem do JS
(caminho a caminho, dia a dia): Python e JS dão **os mesmos caminhos** (S_T igual a 10⁻¹¹), diferente do
bootstrap e do GBM, que coincidem só estatisticamente.

Efeito no exemplo padrão (Collar KI 100/106/112, 3 meses, BBDC4, 28/10/2026, drift CDI, 10.000 caminhos):

| Método | Vol usada | P(lucro) | P(> CDI de hoje) | P(barreira) | Saída antecipada (dia mediano) |
|---|---|---|---|---|---|
| Bootstrap em blocos | 33,7% (média do período) | 55,5% | 47,1% | 45,6% | — |
| **FHS-GJR (padrão)** | 82,0% (prevista para o prazo) | 47,5% | 43,6% | 62,0% | 50,2% (14 pregões) |

**Saída antecipada com GARCH** (modo de marcação padrão). No histórico, a vol de marcação no dia k é a vol média
prevista para o prazo restante a partir da variância daquele dia — `√(252·termo(h_k, N − k))` + adicional —, com
h_k calculada só com dados até o dia (os parâmetros são os do período inteiro). No Monte Carlo FHS, cada caminho
guarda a própria variância simulada e é marcado com ela. No exemplo, a saída antecipada no histórico passa de
53,4% (vol móvel 63d) para 47,7% (GARCH), com dia mediano 39.

**Painel de calibração walk-forward** ([`estruturadas/calibration.py`](estruturadas/calibration.py),
`engine/calib.js`; botão "Testar calibração" na página Monte Carlo, com barra de progresso no Worker). A cada 10
pregões, a partir de 504 pregões de histórico (e pelo menos N + 252): usa **só os dados até a data t**, estima
P(lucro), P(> CDI) e P(barreira) com o método e as premissas escolhidos (1.000 caminhos; GARCH reestimado a cada
252 pregões e, entre uma estimação e outra, os mesmos parâmetros aplicados aos dados novos; CDI da data como
régua) e compara com o que aconteceu na janela [t, t+N] (caminho real, CDI realizado). Régua de comparação: o
**chute fixo** (climatologia) — a frequência do evento nas janelas que já tinham terminado em t.

```
Brier = média[(p − y)²]          ganho = 1 − Brier_modelo / Brier_chute          (y = 0/1)
```

Diagrama de confiabilidade: previsões agrupadas em faixas de 10 p.p. × frequência realizada em cada faixa.
Resultado no Collar KI 3m (362 datas, 2012–2026):

| Ação | Método | Ganho: lucro | Ganho: > CDI | Ganho: barreira |
|---|---|---|---|---|
| BBDC4 | FHS-GJR | +1,0% | +2,1% | +4,1% |
| BBDC4 | Bootstrap | −0,1% | +0,9% | +2,2% |
| PETR4 | FHS-GJR | +2,9% | +2,2% | +7,0% |
| PETR4 | Bootstrap | +1,9% | +1,2% | +4,5% |
| VALE3 | FHS-GJR | +0,9% | +3,2% | +7,7% |
| VALE3 | Bootstrap | +0,2% | +3,3% | +5,1% |

O FHS-GJR supera o bootstrap e, por pouco, o chute fixo; o ganho é pequeno para direção e maior para barreira
(vol é previsível no curto prazo; direção, quase nada). GARCH simétrico e GJR empatam na média (o GJR foi
mantido como padrão por incluir o GARCH como caso particular). Como as janelas vizinhas se sobrepõem (≈ 57
períodos independentes em 3 meses), diferenças pequenas de Brier são ruído — o painel diz isso ao usuário.

## 5. Presets e fórmulas do payoff

Valores em % do valor inicial (S0 = 1). Nos exemplos com ação, custo das opções = 0.

| Preset | Pernas | Valor final | Exemplo padrão |
|---|---|---|---|
| **Booster** | +1 ação; +1 call K1; −2 calls K2 | `S_T + max(S_T−K1,0) − 2·max(S_T−K2,0)` | K1=100%, K2=112,5%: 2x até +12,5%, teto de 25% |
| **Collar** | +1 ação; +1 put Kp; −1 call Kc | `min(max(S_T, Kp), Kc)` | Kp=100%, Kc=115%: piso 0%, teto 15% |
| **Collar Knock In** | +1 ação; +1 put Kp; −1 call up-and-in Kc (barreira B) | `S_T + max(Kp−S_T,0) − 1{tocou B}·max(S_T−Kc,0)` | Kp=100%, Kc=113%, B=143% |
| **Forward Knock Out** | +1 ação; +1 put down-and-out K; −1 call down-and-out K (barreira B) | sem toque: `K` (fixo); com toque: `S_T` | K=110%, B=70%: 10% fixo se não tocar |
| **Trava de alta** | +1 call K1; −1 call K2 (K2 > K1) | `max(S_T−K1,0) − max(S_T−K2,0)` | K1=100%, K2=120% |
| **Trava de baixa** | +1 put K1; −1 put K2 (K2 < K1) | `max(K1−S_T,0) − max(K2−S_T,0)` | K1=100%, K2=80% |
| **Straddle** | +1 call K; +1 put K | `abs(S_T − K)` | K=100% |
| **Strangle** | +1 put Kp; +1 call Kc | `max(Kp−S_T,0) + max(S_T−Kc,0)` | Kp=95%, Kc=105% |
| **Proteção Total (BBDC4)** | +1 ação; +1 put 104,10%; −1 call up-and-in 104,10% (B 138,10%); +0,5 call up-and-out 100% (B 138,10%) | sem toque: `S_T + max(1,041−S_T,0) + 0,5·max(S_T−1,0)`; com toque: `1,041` | lâmina de 19/11/2025, vencimento 25/11/2026 |

Travas, straddle e strangle são estruturas **só com opções**: o retorno é sobre o prêmio pago, então é
preciso informar um custo positivo (ou usar o modo Teórico).

> **Nota sobre a Proteção Total BBDC4.** Com as pernas da lâmina, o retorno sem toque na barreira é de
> 4,10% (S_T = 80% ou 100%), 6,10% (104%), **42,00%** (128%) e **57,00%** (138%). A lâmina arredonda para
> 4%, 6%, 42% e 57%. Com toque na barreira, o retorno é 4,10% fixo.

## 6. Módulos: Python, JavaScript e demais linguagens

Cerca de 5.600 linhas de código próprio. Linguagens: **Python** (motor de referência, app, scripts e testes),
**JavaScript** (motor e interface do site, testes em Node), **HTML/CSS** (site), **YAML** (CI/CD do GitHub
Actions), **JSON** (dados, lâminas e fixtures) e **TOML/INI** (configurações).

### 6.1 Pacote Python `estruturadas/` (motor de referência)

| Módulo | Responsabilidade | Principais funções |
|---|---|---|
| [`legs.py`](estruturadas/legs.py) | Modelo de pernas e estruturas; validação; avaliação vetorizada do payoff em matrizes de caminhos; retornos; perfil no vencimento | `Leg`, `Structure`, `validate`, `summarize_paths`, `event_hits`, `evaluate_paths`, `first_hit_index`, `returns_from_payoff`, `expiry_payoff`, `payoff_profile_summary` |
| [`presets.py`](estruturadas/presets.py) | 9 estruturas pré-definidas, fórmulas e textos em linguagem simples | `booster`, `collar`, `collar_ki`, `forward_knock_out`, `trava_alta`, `trava_baixa`, `straddle`, `strangle`, `protecao_total_bbdc4`, `PRESETS`, `describe` |
| [`pricing.py`](estruturadas/pricing.py) | Black-Scholes (escalar e vetorizado); fórmula fechada de barreira; Monte Carlo neutro ao risco com antitéticas e BGK; custo líquido; solver de custo zero | `bs_price`, `bs_price_vec`, `barrier_price`, `gbm_paths`, `make_mc_context`, `mc_price_leg`, `price_structure`, `solve_zero_cost` |
| [`data.py`](estruturadas/data.py) | Preços (yfinance, CSV), ajuste por proventos, vol histórica, Selic/CDI (API SGS), calendário de pregões | `normalize_ticker`, `load_prices_yf`, `parse_price_csv`, `historical_vol`, `fetch_selic_meta`, `fetch_cdi_daily`, `cdi_factor_on_index`, `b3_holidays`, `previous_business_day`, `count_trading_days`, `term_from_dates` |
| [`garch.py`](estruturadas/garch.py) | GARCH(1,1)/GJR-GARCH por quase-máxima verossimilhança (Nelder-Mead igual ao do JS), previsões de vol, painel de vol, caminhos FHS | `fit_garch`, `filtered`, `garch_filter`, `nelder_mead`, `expected_var`, `term_var`, `term_vol`, `vol_panel`, `fhs_drift_daily`, `fhs_paths`, `GarchFit` |
| [`calibration.py`](estruturadas/calibration.py) | Painel de calibração walk-forward: Brier do modelo × chute fixo, diagrama de confiabilidade | `walk_forward`, `CalibrationResult` (`brier`, `reliability`) |
| [`backtest.py`](estruturadas/backtest.py) | Janelas históricas (com ajuste ao CDI de hoje), Monte Carlo FHS-GARCH (padrão), bootstrap em blocos com máxima/mínima, GBM, drift controlado, grade de cenários, ex-post | `historical_windows`, `regime_factor`, `run_historical`, `ohlc_log_returns`, `drift_annual`, `bootstrap_ohlc_paths`, `bootstrap_drift_daily`, `gbm_drift_daily`, `run_monte_carlo`, `run_scenarios`, `run_ex_post` |
| [`metrics.py`](estruturadas/metrics.py) | Estatísticas (com IC por block bootstrap e CVaR), tabela comparativa, quadro de rentabilidade, métricas da saída antecipada | `summarize`, `block_bootstrap_ci`, `cvar`, `comparison_table`, `default_variations`, `profitability_table`, `summarize_exit`, `exit_table`, `exit_by_cdi_regime` |
| [`rng.py`](estruturadas/rng.py) | Gerador mulberry32 idêntico ao do JS (ICs e caminhos FHS iguais nos dois motores), também vetorizado | `Mulberry32`, `uniforms`, `integers` |
| [`early_exit.py`](estruturadas/early_exit.py) | Saída antecipada: marcação diária a modelo (vol GARCH, móvel ou fixa), calibração, regra do gatilho; histórico, Monte Carlo e ex-post | `EarlyExitConfig`, `structure_value`, `garch_variance`, `rolling_vol`, `cdi_rate_series`, `simulate_exit`, `run_historical_exit`, `run_mc_exit`, `run_ex_post_exit` |
| [`io.py`](estruturadas/io.py) | Import/export de lâminas em JSON (aceita nomes em pt e en) | `dumps`, `loads`, `save`, `load` |
| [`charts.py`](estruturadas/charts.py) | Gráficos Plotly com separadores brasileiros | `payoff_chart`, `histogram_chart`, `windows_timeseries_chart`, `price_chart`, `ex_post_chart`, `mc_paths_chart`, `exit_days_chart`, `vol_chart`, `reliability_chart` |
| [`formatting.py`](estruturadas/formatting.py) | Números no formato 1.234,56 | `fmt_num`, `fmt_pct`, `fmt_brl`, `fmt_level` |

### 6.2 App Streamlit — [`app.py`](app.py)

Barra lateral (estrutura, ação e histórico, prazo, valor e custos, parâmetros de precificação, barreiras,
Monte Carlo) e abas *Estrutura*, *Backtest histórico*, *Monte Carlo*, *Ex-post* e *Metodologia e limitações*.
Tabela de pernas editável com `st.data_editor`; cache com `st.cache_data` (preços e taxas por 6 h; cálculos por
parâmetros). O texto da aba de metodologia vem de [METODOLOGIA.md](METODOLOGIA.md).

### 6.3 Scripts — [`scripts/`](scripts/)

| Script | Função |
|---|---|
| [`build_site_data.py`](scripts/build_site_data.py) | Baixa preços (desde 2008) das ações de `tickers.py` em lote, com novas tentativas; descarta ações com menos de 300 pregões ou sem cotação há mais de 15 dias; baixa CDI e Selic; grava `site/data/`. Falha (código 1) se menos da metade das ações vier, para o deploy não publicar um site incompleto. |
| [`tickers.py`](scripts/tickers.py) | Lista de ações do site (código → nome curto). |
| [`make_js_fixtures.py`](scripts/make_js_fixtures.py) | Gera `tests/js/fixtures.json` com resultados do motor Python para validar o JS. |

### 6.4 Site estático — [`site/`](site/)

| Arquivo | Função |
|---|---|
| `index.html` | Estrutura da página (barra superior, abas, barra de parâmetros, rodapé) e ordem de carga dos scripts; `?v=__V__` é trocado pelo hash do commit no deploy (evita cache antigo). |
| `assets/css/styles.css` | Tema do painel "Relatório de Fundos" + estilos do simulador (barra de parâmetros, editor de pernas). |
| `assets/js/engine/legs.js` | Porta de `legs.py` + import/export JSON + formatação pt-BR. |
| `assets/js/engine/presets.js` | Porta de `presets.py` (textos em HTML). |
| `assets/js/engine/pricing.js` | Black-Scholes (normal de Hart/West), gerador mulberry32 + Box-Muller, GBM antitético resumido, preço por perna, solver de Brent. |
| `assets/js/engine/backtest.js` | Calendário B3, preparação de preços, fator do CDI, janelas históricas, bootstrap, GBM (guarda 2.000 caminhos completos), ex-post, métricas, quadro de rentabilidade. |
| `assets/js/engine/garch.js` | Porta de `garch.py`: ajuste GARCH/GJR (Nelder-Mead), previsões, painel de vol e Monte Carlo FHS. |
| `assets/js/engine/early.js` | Porta de `early_exit.py`: fórmula de barreira, marcação diária calibrada (vol GARCH, móvel ou fixa), regra de saída, histórico, Monte Carlo, ex-post e métricas. |
| `assets/js/engine/calib.js` | Porta de `calibration.py`: teste walk-forward, Brier e diagrama de confiabilidade. |
| `assets/js/worker.js` | Web Worker que executa `price`, `solve`, `hist`, `mc`, `scen`, `hexit`, `mcexit` e `calib` (com avisos de progresso) fora da thread da página. |
| `assets/js/core.js` | Formatação, estado (persistido em `localStorage`, chave `es:state`), carga de dados, parser de CSV, chamada ao Worker (com fallback local) e orquestração/caches dos cálculos. |
| `assets/js/charts.js` | Gráficos ECharts: payoff, histograma, janelas, preço, ex-post, caminhos do MC, saída antecipada, vol condicional e diagrama de confiabilidade. |
| `assets/js/params.js` | Barra de parâmetros e "Mais opções". |
| `assets/js/views/*.js` | Páginas: `estrutura`, `backtest` (+ utilitários compartilhados), `montecarlo`, `expost`, `metodologia`. |
| `assets/js/app.js` | Roteador por hash (`#/estrutura` etc.), cabeçalho e rodapé. |
| `assets/vendor/echarts.min.js` | Apache ECharts 5.6.0 (licença Apache 2.0). |

### 6.5 Testes, CI e configurações

| Arquivo | Linguagem | Função |
|---|---|---|
| [`tests/test_payoffs.py`](tests/test_payoffs.py), [`test_pricing.py`](tests/test_pricing.py), [`test_backtest.py`](tests/test_backtest.py), [`test_early_exit.py`](tests/test_early_exit.py), [`test_conditioning.py`](tests/test_conditioning.py), [`test_garch.py`](tests/test_garch.py) | Python (pytest) | 73 testes do motor Python |
| [`tests/js/engine.test.mjs`](tests/js/engine.test.mjs) | JavaScript (node:test) | 20 testes do motor JS, incluindo comparação com o Python |
| [`scripts/pesquisa/`](scripts/pesquisa/) | Python | Experimentos da revisão metodológica (walk-forward, regime de juros) — referência, não produção |
| [`.github/workflows/pages.yml`](.github/workflows/pages.yml) | YAML | Testes + dados + deploy no GitHub Pages |
| [`.streamlit/config.toml`](.streamlit/config.toml) | TOML | Tema e servidor do Streamlit |
| [`pytest.ini`](pytest.ini), [`requirements.txt`](requirements.txt), `.gitignore`, `.gitattributes` | INI/texto | Configuração de testes, dependências e git (fim de linha LF) |
| [`presets/protecao_total_bbdc4.json`](presets/protecao_total_bbdc4.json) | JSON | Lâmina de exemplo |

## 7. Bibliotecas e serviços externos

| Biblioteca / serviço | Onde | Para quê |
|---|---|---|
| **NumPy** | Python | Matrizes de caminhos, vetorização, `sliding_window_view`, gerador aleatório |
| **pandas** | Python | Séries de preços, CDI, tabelas de resultados |
| **SciPy** | Python | `scipy.stats.norm` (Black-Scholes) e `scipy.optimize.brentq` (solver) |
| **yfinance** | Python | Preços diários do Yahoo Finance (OHLC + Adj Close) |
| **requests** | Python | API SGS do Banco Central |
| **Streamlit** | Python | Interface do app |
| **Plotly** | Python | Gráficos do app |
| **pytest** | Python | Testes |
| **Apache ECharts 5.6** | JS (site) | Gráficos do site |
| **Web Workers, `Intl.NumberFormat`, `fetch`, `localStorage`** | JS (navegador) | Cálculo em segundo plano, formato pt-BR, dados, estado |
| **Node.js (`node:test`)** | JS (testes) | Testes do motor JS |
| **Google Fonts (Inter)** | Site | Tipografia |
| **GitHub Actions + GitHub Pages** | CI/CD | Testes, dados diários e hospedagem gratuita |
| **Yahoo Finance** | Dados | Cotações |
| **Banco Central (SGS 12 e 432)** | Dados | CDI diário e Selic meta |

## 8. Testes e validação cruzada Python × JS

```bash
pytest                                   # 73 testes do motor Python
node --test tests/js/engine.test.mjs     # 20 testes do motor JS
python scripts/make_js_fixtures.py       # regenera as referências após mudar o motor Python
```

Casos das lâminas (Python e JS):

| Estrutura | Casos verificados |
|---|---|
| Booster (100 / 112,5) | S_T 1,10 → +20%; 1,30 → +25%; 0,90 → −10% |
| Collar (100 / 115) | S_T 0,80 → 0%; 1,10 → +10%; 1,30 → +15% |
| Collar KI (100 / 113 / B 143) | toca 1,43 e termina 1,50 → +13%; sem toque termina 1,40 → +40%; 0,80 → 0% |
| FKO (110 / B 70) | sem toque → +10% para qualquer S_T; com toque → S_T − 1 |
| Proteção Total BBDC4 | sem toque: 0,80 e 1,00 → 4,10%; 1,04 → 6,10%; 1,28 → 42,00%; 1,38 → 57,00%; com toque → 4,10% |

Outros testes: monitoramento intradiário (máxima acima da barreira e fechamento abaixo aciona só no modo
intradiário); paridade put-call; Black-Scholes contra valor de referência (Hull); paridade in/out
(`MC(up-in) + MC(up-out) = MC(vanilla)` caminho a caminho, e vanilla MC ≈ BS dentro de 3 erros padrão);
BGK aumenta o preço de knock-in; solver com |custo| < 10⁻⁶ e caso sem solução; backtest em série sintética
(número de janelas e retornos esperados); ex-post encerrado, em andamento e com data do toque; calendário;
round-trip de JSON (exportar → importar → payoff idêntico). Saída antecipada: paridade in + out = vanilla
da fórmula fechada em 8 casos (call/put × alta/baixa × strike acima/abaixo da barreira); fórmula + BGK × Monte Carlo diário; convergência
da marcação ao payoff perto do vencimento; regras de gatilho, delay, carência, spread e vencimento em casos
determinísticos; calibração no dia 0; histórico, Monte Carlo e ex-post. GARCH/FHS (Fase 2): mulberry32 vetorizado
igual ao escalar; recuperação dos parâmetros de uma série GJR simulada; ajuste igual ao ótimo do scipy, inclusive
com um choque enorme no fim da série; vol do prazo = média das previsões diárias; FHS com α = γ = β = 0 = bootstrap
i.i.d.; E[S_T] ≈ (1 + μ)^(N/252); choque no fim da série aumenta a vol e a P(barreira); saída antecipada com vol
GARCH e volta automática à vol móvel em histórico curto; calibração (datas, chute fixo e realizado).

**Validação cruzada:** `make_js_fixtures.py` grava payoffs de todos os presets em caminhos aleatórios
(fechamento e intradiário), perfis no vencimento, quadros de rentabilidade, preços de Black-Scholes, backtests
históricos em série sintética, ex-posts, casos de calendário e a saída antecipada (fórmulas de barreira,
marcação, vol móvel, taxa do CDI, dias de gatilho e de saída e retornos em 5 configurações, além do ex-post),
a Fase 1 (gerador, ICs, ajuste de regime) e a Fase 2 (parâmetros do GARCH e do GJR, filtro e resíduos, painel de
vol, caminhos FHS com os mesmos sorteios, saída antecipada marcada com GARCH e o teste walk-forward). O teste JS
exige igualdade até 10⁻¹⁰ (10⁻⁹ nos retornos da saída antecipada); os parâmetros do GARCH, que saem de otimizadores
independentes, até 10⁻⁵, e as previsões da calibração até alguns caminhos.

## 9. Como rodar, publicar e atualizar

### Site estático

Publicação automática pelo workflow [`.github/workflows/pages.yml`](.github/workflows/pages.yml): roda a cada
push na `main`, em dias úteis às 19h30 (Brasília) e sob demanda (*Actions → Site (GitHub Pages) → Run
workflow*). Etapas: instala dependências → `pytest` → testes JS → `build_site_data.py` → versiona os arquivos →
publica `site/`. Se algo falhar, a versão anterior continua no ar. Pré-requisito (feito uma vez): *Settings →
Pages → Source: GitHub Actions*. O GitHub pausa agendamentos após 60 dias sem atividade no repositório; nesse
caso, reative o workflow na aba *Actions*.

Teste local:

```bash
python scripts/build_site_data.py PETR4 VALE3 BBDC4
python -m http.server 8000 --directory site
```

e abra http://localhost:8000. Para incluir uma ação, acrescente-a em `scripts/tickers.py`.

### App Streamlit

Requer Python 3.11 ou mais recente.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Para publicar no Streamlit Community Cloud: em [share.streamlit.io](https://share.streamlit.io), *Create app*,
escolha o repositório, a branch `main` e o arquivo `app.py` (Python ≥ 3.11). Não há segredos a configurar.

## 10. Formato dos arquivos

### Lâmina (JSON)

Strikes e barreiras em fração do valor inicial. O mesmo formato vale para o Python e para o site.

```json
{
  "formato": "estruturadas-sim/v1",
  "nome": "Proteção Total (BBDC4)",
  "ticker": "BBDC4",
  "data_contratacao": "2025-11-19",
  "data_vencimento": "2026-11-25",
  "custo_opcoes": 0.0,
  "preset": "protecao_total",
  "observacoes": "Exemplo da lâmina de 19/11/2025.",
  "pernas": [
    {"tipo": "stock", "posicao": "comprada", "proporcao": 1.0},
    {"tipo": "put", "posicao": "comprada", "strike": 1.041, "barreira_tipo": "none", "barreira": null, "proporcao": 1.0},
    {"tipo": "call", "posicao": "vendida", "strike": 1.041, "barreira_tipo": "up_in", "barreira": 1.381, "proporcao": 1.0},
    {"tipo": "call", "posicao": "comprada", "strike": 1.0, "barreira_tipo": "up_out", "barreira": 1.381, "proporcao": 0.5}
  ]
}
```

`barreira_tipo` aceita `none`, `up_in`, `up_out`, `down_in`, `down_out` ou os nomes da lâmina ("Knock Up and
In"…); `posicao` aceita `comprada`/`vendida` ou `1`/`-1`.

### Dados do site (`site/data/`, gerados, fora do git)

| Arquivo | Conteúdo |
|---|---|
| `index.json` | `gerado_em`, `dados_ate`, `inicio`, `selic_meta` e `acoes: [{t, n, ini, fim, vol}]` |
| `cdi.json` | `d` (datas), `r` (CDI em fração ao dia), `selic_meta` |
| `precos/<TICKER>.json` | `d` (datas ISO), `c` (fechamento bruto), `ca` (fechamento ajustado), `h`, `l` (máxima e mínima brutas) |

### CSV de preços (upload)

Colunas `Date, Close` e, opcionalmente, `High, Low`. Também aceita `Data;Fechamento;Máxima;Mínima`, separador
`;` e vírgula decimal, datas `AAAA-MM-DD` ou `DD/MM/AAAA`.

### CSV de resultados (download)

Separador `;`, vírgula decimal, UTF-8 com BOM (abre direto no Excel): data de início e fim, ação final,
retornos da estrutura, da ação e do CDI, barreira acionada e resultado em R$.

## 11. Como digitar uma lâmina (passo a passo BBDC4)

No site (no Streamlit os campos estão na barra lateral, com os mesmos nomes):

1. Em **Estrutura**, escolha **Customizada**. A tabela começa com uma linha "Ação comprada".
2. Clique em **+ Adicionar perna** três vezes e preencha:

   | Perna | Tipo | Posição | Preço de exercício (%) | Tipo de barreira | Valor da barreira (%) | Proporção |
   |---|---|---|---|---|---|---|
   | 1 | Ação | Comprada | — | Não se aplica | — | 1,0000 |
   | 2 | Put | Comprada | 104,10 | Não se aplica | — | 1,0000 |
   | 3 | Call | Vendida | 104,10 | Knock Up and In | 138,10 | 1,0000 |
   | 4 | Call | Comprada | 100,00 | Knock Up and Out | 138,10 | 0,5000 |

3. Em **Ação**, digite `BBDC4`.
4. Em **Prazo → Datas**: contratação 19/11/2025 e vencimento 25/11/2026 (apuração em 24/11/2026, 249 pregões).
5. Em **Custo das opções**, deixe **Informado = 0** (estrutura sem custo).
6. Confira o resumo e o quadro de rentabilidade (variações −20; −10; 0; 4; 28; 38; 48).
7. Clique em **Exportar JSON** para guardar a lâmina e reimportá-la depois.

Atalho: o preset **Proteção Total (BBDC4)** já traz essa tabela, a ação e as datas.

## 12. Premissas, limitações e roadmap

### Premissas e limitações

- **Baixa capacidade preditiva para direção.** Em testes walk-forward (2012–2026), o FHS-GARCH melhorou o
  Brier do chute fixo em só 1%–3% nas probabilidades de lucro/superar o CDI (4%–8% na de barreira); o modelo é
  mais útil para comparar estruturas, dimensionar o risco de barreira e visualizar a distribuição de resultados.
- **O GARCH reage forte a choques extremos.** Logo depois de um crash, a vol de hoje passa de 100% a.a. e a
  P(barreira) sobe bastante; a vol implícita da mesa pode estar abaixo disso (os cenários de vol ×0,8 mostram a
  sensibilidade). Os parâmetros do GARCH usam o período inteiro carregado.
- **Passado não garante futuro.** Janelas sobrepostas são fortemente correlacionadas: a amostra efetiva é
  muito menor que o número de janelas.
- Os parâmetros em % são aplicados igualmente em todas as janelas: a estrutura **não é reprecificada** com a
  vol e os juros de cada época.
- As lâminas nem sempre dizem se a barreira é monitorada no fechamento ou no intradiário, e isso muda a
  probabilidade de acionamento.
- Retornos brutos de IR. Não modela risco de contraparte, chamada de margem, liquidez nem resgate antecipado.
- A marcação "até hoje" do ex-post é intrínseca, não o valor de mercado.
- O modo Teórico é uma referência: usa vol histórica, taxa contínua constante, sem skew nem dividendos
  discretos; pode divergir do preço da mesa.
- O preço ajustado aproxima o ajuste de strikes e barreiras das lâminas; valores em R$ podem diferir da
  lâmina, mas as variações percentuais são comparáveis.
- O calendário futuro usa uma aproximação dos feriados da B3.
- O site cobre uma lista fechada de ~95 ações, atualizada uma vez por dia útil.

### Roadmap

- Itens opcionais da revisão: bootstrap estacionário com bloco automático (Politis & White); GARCH com
  resíduos t de Student; comparação com um benchmark "ação + CDI com o mesmo delta".
- Reprecificar a estrutura em cada janela histórica com a vol e os juros da época.
- Vol implícita e skew no modo Teórico; dividendos discretos.
- Monitoramento intradiário no Monte Carlo com ponte browniana.
- Saída antecipada: calibrar o spread de saída e o adicional de vol com extratos de marcação do banco; vol
  implícita real (arquivos COTAHIST da B3) para as ações com opções líquidas; vol variável no Monte Carlo.
- Autocalls e estruturas com cupom; estruturas com mais de um ativo.
- Comparação lado a lado de várias estruturas na mesma ação.
- IR e come-cotas para comparar com o CDI líquido.

## Licença

[MIT](LICENSE). Apache ECharts é distribuído sob a licença Apache 2.0.
