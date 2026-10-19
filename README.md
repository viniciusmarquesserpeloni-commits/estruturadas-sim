# Simulador de Operações Estruturadas (B3)

Estime a **probabilidade de sair no lucro** em uma operação estruturada com opções sobre ações da B3
(Collar, Booster, Proteção Total, Forward Knock Out…) a partir do histórico de preços da ação.

O app "fala a língua" das lâminas de operações estruturadas das corretoras: cada estrutura é a tabela
**Composição da Estratégia** (ação, calls e puts compradas/vendidas, strikes e barreiras em % do valor
inicial, tipo de barreira Knock Up/Down and In/Out e proporção), e os resultados aparecem também no formato
**Quadro de rentabilidade no vencimento**.

**Acesse o simulador:** https://viniciusmarquesserpeloni-commits.github.io/estruturadas-sim/

> ⚠️ Ferramenta **educacional**. Não é recomendação de investimento. Passado não garante futuro.
> Retornos **brutos de IR**. O projeto não é afiliado a nenhuma instituição financeira.

## O que o app faz

- **Monta a estrutura** a partir de presets ou de uma tabela editável de pernas; importa/exporta em JSON
  (para salvar as lâminas da mesa como presets).
- **Explica a estrutura em linguagem simples** ("se a ação nunca subir mais que X%…") e desenha o
  **payoff no vencimento**, com os ramos "barreira tocada" e "não tocada".
- **Backtest por janelas históricas**: aplica a estrutura, com os mesmos parâmetros em %, em todas as datas
  de início possíveis desde 2010 (configurável) e mede P(lucro), P(retorno > CDI), P(perda), acionamento
  das barreiras, distribuição dos retornos e comparação com "só a ação" e com o CDI.
- **Monte Carlo** como complemento: bootstrap em blocos dos retornos históricos ou GBM (drift histórico,
  zero ou CDI).
- **Modo ex-post**: aplica a estrutura no caminho realizado de uma operação real (ex.: a Proteção Total
  em BBDC4 de 19/11/2025 a 25/11/2026), mostrando se e quando a barreira foi tocada.
- **Custo das opções híbrido**: *Informado* (cotação da mesa; 0 = estrutura sem custo) ou *Teórico*
  (Black-Scholes para vanilla e Monte Carlo neutro ao risco para barreiras), com **solver de custo zero**.
- Download dos resultados em CSV (formato brasileiro, `;` e vírgula decimal) e da estrutura em JSON.

## Duas versões

| | Site público (GitHub Pages) | App Streamlit |
|---|---|---|
| Onde | [`site/`](site/) — HTML/JS estático, mesmo layout do painel "Relatório de Fundos" | [`app.py`](app.py) |
| Motor | JavaScript ([`site/assets/js/engine/`](site/assets/js/engine/)), validado contra o Python | Python ([`estruturadas/`](estruturadas/)) |
| Ações | ~95 ações líquidas da B3 (lista em [`scripts/tickers.py`](scripts/tickers.py)) + upload de CSV | qualquer ticker do Yahoo Finance |
| Dados | atualizados todo dia útil às 19h30 (GitHub Actions) | baixados na hora |

As duas usam a mesma metodologia. Os testes em [`tests/js/`](tests/js/) comparam o motor JS com
resultados gerados pelo motor Python ([`scripts/make_js_fixtures.py`](scripts/make_js_fixtures.py)):
payoffs de todos os presets, Black-Scholes, backtest histórico, ex-post, quadro de rentabilidade e calendário.

### Site estático: como funciona a publicação

O workflow [`.github/workflows/pages.yml`](.github/workflows/pages.yml) roda a cada push na `main`, em dias
úteis às 19h30 (Brasília) e sob demanda (*Actions → Site (GitHub Pages) → Run workflow*). Ele:

1. roda os testes Python (`pytest`) e JS (`node --test tests/js/engine.test.mjs`);
2. gera `site/data/` com `python scripts/build_site_data.py` (preços do Yahoo Finance, CDI e Selic do BCB);
3. publica a pasta `site/` no GitHub Pages.

Se algum passo falhar, a versão anterior do site continua no ar. Pré-requisito (uma vez só): em
*Settings → Pages*, escolher **Source: GitHub Actions**. O GitHub pausa agendamentos após 60 dias sem
atividade no repositório; nesse caso, basta reativar o workflow na aba *Actions*.

Para testar o site localmente:

```bash
python scripts/build_site_data.py PETR4 VALE3 BBDC4
python -m http.server 8000 --directory site
```

e abra http://localhost:8000. Para incluir uma ação, acrescente-a em `scripts/tickers.py`.

## Como rodar o app Streamlit

Requer Python 3.11 ou mais recente.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Testes:

```bash
pytest
```

Dados: preços do Yahoo Finance via `yfinance` (tickers com sufixo `.SA`; digite só `PETR4` que o app
completa), Selic meta (série 432) e CDI diário (série 12) da API SGS do Banco Central. Sem internet, você
pode enviar um CSV com as colunas `Date, Close[, High, Low]` (também aceita `Data;Fechamento;Máxima;Mínima`
com vírgula decimal) e informar a taxa manualmente.

## Publicar no Streamlit Community Cloud

1. Suba este repositório para o GitHub (público ou privado).
2. Acesse [share.streamlit.io](https://share.streamlit.io), entre com sua conta do GitHub e clique em
   **Create app**.
3. Escolha o repositório, a branch (`main`) e o arquivo principal `app.py`. Em *Advanced settings*,
   selecione Python 3.11 ou mais recente.
4. Clique em **Deploy**. O `requirements.txt` é instalado automaticamente. O app não precisa de segredos
   (`secrets.toml`).

## Metodologia (resumo didático)

A explicação completa está na aba **Metodologia e limitações** do app e em [METODOLOGIA.md](METODOLOGIA.md).

1. **Normalização**: o valor inicial da ação vale 1 (100%). Strikes e barreiras são frações desse valor
   (1,041 = 104,10%).
2. **Payoff**: em cada caminho de preços, verifica-se se cada barreira foi tocada (knock-in: a opção só
   passa a existir se tocar; knock-out: deixa de existir se tocar) e soma-se o valor final das pernas no
   preço de apuração S_T. Tudo vetorizado em numpy, numa matriz *caminhos × dias*.
3. **Retorno**, com *c* = custo líquido das opções em % do valor inicial (positivo = débito):
   - com ação: `retorno = valor_final / (1 + c) − 1`;
   - só opções: `retorno = valor_final / c − 1` (exige c > 0);
   - custos adicionais (% do valor investido) são subtraídos.
4. **Janelas históricas**: para cada pregão *t* com N pregões à frente, caminho = `P[t+1 … t+N] / P[t]`
   (`numpy.lib.stride_tricks.sliding_window_view`). A fração de janelas com lucro responde a: "se eu tivesse
   contratado esta estrutura em um dia qualquer do passado, quantas vezes teria ganhado?".
5. **Monte Carlo**: bootstrap em blocos de ≈ 20 dias dos log-retornos diários (preserva caudas e aglomeração
   de volatilidade) ou GBM com a vol histórica.
6. **Monitoramento de barreira**: *fechamento diário* (padrão) ou *intradiário* (máxima/mínima do dia no
   histórico; correção de Broadie-Glasserman-Kou no Monte Carlo).
7. **Modo Teórico**: Black-Scholes-Merton para opções vanilla; para barreiras, Monte Carlo neutro ao risco
   com passos diários, variáveis antitéticas, seed fixa (números aleatórios comuns) e erro padrão. A Selic
   (efetiva ao ano) vira taxa contínua: `r = ln(1 + Selic)`. O solver de custo zero usa `scipy.optimize.brentq`.

### Convenções

- 1 mês = 21 dias úteis; ano = 252 pregões.
- Valor inicial = fechamento do dia da contratação; apuração no fechamento de **D−1 do vencimento**
  (liquidação em D+1, apenas informativa).
- Calendário: datas da própria série de preços; para datas futuras, uma aproximação dos feriados da B3.
- Preço padrão: **ajustado por proventos** (as lâminas ajustam strikes e barreiras em eventos corporativos).

## Presets e fórmulas do payoff

Valores em % do valor inicial (S0 = 1). "Valor final" é o valor da carteira no vencimento; o retorno vem da
fórmula da seção anterior. Nos exemplos com ação, custo das opções = 0.

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

## Como digitar uma lâmina no montador (passo a passo: Proteção Total BBDC4)

A tabela "Composição da Estratégia" da lâmina tem quatro linhas. No app:

1. Na barra lateral, em **Preset**, escolha **Customizada (em branco)**. A tabela começa com uma linha
   "Ação comprada".
2. Na aba **Estrutura**, adicione as linhas (clique na última linha vazia da tabela) e preencha cada uma:

   | Perna | Tipo | Posição | Preço de exercício (%) | Tipo de barreira | Valor da barreira (%) | Proporção |
   |---|---|---|---|---|---|---|
   | 1 | Ação | Comprada | — | Não se aplica | — | 1,0000 |
   | 2 | Put | Comprada | 104,10 | Não se aplica | — | 1,0000 |
   | 3 | Call | Vendida | 104,10 | Knock Up and In | 138,10 | 1,0000 |
   | 4 | Call | Comprada | 100,00 | Knock Up and Out | 138,10 | 0,5000 |

3. Em **Código da ação**, digite `BBDC4`.
4. Em **Prazo**, escolha **Datas**: contratação 19/11/2025 e vencimento 25/11/2026. O app calcula os
   pregões até a apuração (D−1 = 24/11/2026).
5. Em **Custo das opções**, deixe **Informado = 0** (a lâmina é "sem custo").
6. Confira o **Resumo em linguagem simples** e o **Quadro de rentabilidade** com as variações da lâmina
   (−20; −10; 0; 4; 28; 38; 48).
7. Clique em **Baixar estrutura (JSON)** para guardar a lâmina. Depois é só importá-la pela barra lateral.
   O arquivo [presets/protecao_total_bbdc4.json](presets/protecao_total_bbdc4.json) é exatamente esse exemplo.

Formato do JSON (strikes e barreiras em fração do valor inicial):

```json
{
  "formato": "estruturadas-sim/v1",
  "nome": "Proteção Total (BBDC4)",
  "ticker": "BBDC4",
  "data_contratacao": "2025-11-19",
  "data_vencimento": "2026-11-25",
  "custo_opcoes": 0.0,
  "pernas": [
    {"tipo": "stock", "posicao": "comprada", "proporcao": 1.0},
    {"tipo": "put", "posicao": "comprada", "strike": 1.041, "barreira_tipo": "none", "barreira": null, "proporcao": 1.0},
    {"tipo": "call", "posicao": "vendida", "strike": 1.041, "barreira_tipo": "up_in", "barreira": 1.381, "proporcao": 1.0},
    {"tipo": "call", "posicao": "comprada", "strike": 1.0, "barreira_tipo": "up_out", "barreira": 1.381, "proporcao": 0.5}
  ]
}
```

`barreira_tipo` aceita `none`, `up_in`, `up_out`, `down_in`, `down_out` (ou os nomes da lâmina, como
"Knock Up and In").

## Estrutura do repositório

```
site/                   # site estático (GitHub Pages)
  index.html            # mesmo layout do painel "Relatório de Fundos"
  assets/js/engine/     # motor em JS (payoff, precificação, backtest, métricas, calendário)
  assets/js/views/      # páginas: Estrutura, Backtest, Monte Carlo, Ex-post, Metodologia
  assets/js/worker.js   # cálculos pesados em Web Worker
scripts/                # build_site_data.py, tickers.py, make_js_fixtures.py
.github/workflows/      # publicação diária no GitHub Pages
app.py                  # interface Streamlit
METODOLOGIA.md          # texto da aba "Metodologia e limitações"
estruturadas/
  legs.py               # pernas, validação e avaliação vetorizada do payoff
  presets.py            # estruturas pré-definidas e textos explicativos
  io.py                 # import/export de estruturas em JSON
  pricing.py            # Black-Scholes, Monte Carlo p/ barreiras, solver de custo zero
  data.py               # yfinance, CSV, Selic/CDI (BCB), calendário de pregões
  backtest.py           # janelas históricas, bootstrap, GBM, ex-post
  metrics.py            # estatísticas, tabela comparativa, quadro de rentabilidade
  charts.py             # gráficos Plotly (pt-BR)
  formatting.py         # números no formato brasileiro
presets/                # lâminas de exemplo em JSON
tests/                  # pytest (Python) e tests/js (motor JS × Python)
```

## Premissas e limitações

- **Passado não garante futuro.** Janelas sobrepostas são fortemente correlacionadas: a amostra efetiva
  (janelas não sobrepostas, exibida no app) é muito menor que o número de janelas.
- Os parâmetros em % são aplicados igualmente em todas as janelas: a estrutura **não é reprecificada** com
  a vol e os juros de cada época.
- As lâminas nem sempre dizem se a barreira é monitorada no fechamento ou no intradiário, e isso muda a
  probabilidade de acionamento (compare os dois modos no app).
- Retornos brutos de IR. Não modela risco de contraparte, chamada de margem, liquidez nem resgate
  antecipado a mercado.
- No modo ex-post antes do vencimento, o resultado "até hoje" é a **marcação intrínseca**, não o valor de
  mercado da estrutura.
- O modo Teórico é uma referência e pode divergir do preço da mesa (vol implícita, skew, spread, dividendos).
- Preço ajustado por proventos aproxima o ajuste de strikes/barreiras que as lâminas fazem em eventos
  corporativos; os valores em R$ podem diferir da lâmina, mas as variações percentuais são comparáveis.
- O calendário futuro usa uma aproximação dos feriados da B3.

## Roadmap

- Reprecificar a estrutura em cada janela histórica com a vol e os juros da época (strikes/barreiras de
  custo zero variáveis no tempo).
- Vol implícita e skew (superfície) no modo Teórico; dividendos discretos.
- Monitoramento intradiário no Monte Carlo com caminhos de máxima/mínima simulados (ponte browniana).
- Autocalls e estruturas com cupom; estruturas com mais de um ativo.
- Comparação lado a lado de várias estruturas na mesma ação.
- IR e come-cotas para comparar com o CDI líquido.

## Licença

[MIT](LICENSE).
