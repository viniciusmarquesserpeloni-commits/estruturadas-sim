# Contexto do projeto — para continuar em outra conversa

> **Como usar:** cole este arquivo (ou peça para a IA lê-lo em
> `estruturadas-sim/docs/CONTEXTO_DO_PROJETO.md`) no início de uma nova conversa. Ele resume o que existe,
> as decisões já tomadas, o estado atual e as armadilhas conhecidas. Detalhes de cálculo estão no
> [README](../README.md); a metodologia em linguagem de usuário, em [METODOLOGIA.md](../METODOLOGIA.md).
>
> Última atualização: 29/10/2026 (inclui a saída antecipada e as Fases 1 e 2 da revisão metodológica).

## 1. Quem é o usuário e como trabalhar com ele

- Especialista de investimentos; usa lâminas de operações estruturadas da mesa de uma corretora. O app deve
  "falar a língua" dessas lâminas (Composição da Estratégia, Quadro de rentabilidade, Knock Up/Down In/Out).
- **Tudo voltado ao usuário em português do Brasil** (interface, README, mensagens, commits). Nomes de código
  podem ser em inglês.
- **Não fazer `git push` sem perguntar antes.** Cada push é autorizado caso a caso.
- **Não usar marca, logo ou nome do Itaú** no produto. O tema visual do site veio do painel do próprio usuário
  ("Relatório de Fundos"), mas o logotipo foi trocado por um símbolo neutro (uma linha de payoff).
- Commits pequenos e descritivos em pt-BR, terminando com
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Ferramenta educacional: manter os avisos (não é recomendação, retornos brutos de IR, passado não garante
  futuro).

## 2. Endereços

| O quê | Onde |
|---|---|
| Site público | https://viniciusmarquesserpeloni-commits.github.io/estruturadas-sim/ |
| Repositório | https://github.com/viniciusmarquesserpeloni-commits/estruturadas-sim (público, branch `main`) |
| Pasta local | `C:\Users\vinim\OneDrive\Área de Trabalho\Códigos\estruturadas-sim` (Windows, OneDrive, caminho com acentos) |
| Painel de referência do layout | https://dashboard-gerencial-analise-073.github.io/ — código em `..\Relatorio_Fundos\dashboard` (outro repositório do usuário; não alterar) |
| Manual de preenchimento | Documento no claude.ai: https://claude.ai/code/artifact/eaf6f98e-eff9-4f97-8d54-d45a609d5172 |

## 3. Decisões já tomadas (não reabrir sem o usuário pedir)

1. **Stack Python:** Python 3.11+ (local: 3.13), Streamlit, Plotly, NumPy/pandas/SciPy, yfinance, requests,
   pytest. Motor Python = **referência**.
2. **Site público estático** no GitHub Pages, com **o mesmo layout do painel "Relatório de Fundos"**: HTML/CSS/JS
   puro (sem framework nem build), ECharts 5.6 copiado em `site/assets/vendor/`, CSS do painel copiado e
   estendido. O usuário escolheu isso em vez de publicar o Streamlit com CSS aproximado.
3. **Motor duplicado em JS** (`site/assets/js/engine/`), validado contra o Python por fixtures
   (`scripts/make_js_fixtures.py` → `tests/js/fixtures.json`). **Qualquer mudança de cálculo deve ser feita
   nos dois motores**, depois regenerar as fixtures e rodar os dois conjuntos de testes.
4. **Dados do site** gerados por GitHub Actions (diário, 19h30 de Brasília em dias úteis + a cada push):
   preços de ~95 ações (`scripts/tickers.py`) desde 2008, CDI (SGS 12) e Selic meta (SGS 432). Ficam em
   `site/data/` (no `.gitignore`, publicados só pelo artefato do Pages).
5. **Metodologia:** janelas históricas móveis (base) + Monte Carlo (complemento: bootstrap em blocos padrão, ou
   GBM com drift histórico/zero/CDI).
6. **Custo das opções híbrido:** *Informado* (cotação da mesa, 0 = sem custo) ou *Teórico* (Black-Scholes
   para vanilla, MC neutro ao risco para barreiras, ≥ 50 mil caminhos, antitéticas, seed fixa, erro padrão).
7. **Núcleo genérico:** toda estrutura é uma lista de pernas; presets só preenchem a lista; estrutura
   customizada e import/export de lâminas em JSON (`formato: estruturadas-sim/v1`).
8. **Convenções das lâminas:** S0 = fechamento da contratação; apuração no fechamento de D−1 do vencimento;
   1 mês = 21 du; ano = 252; preço ajustado por proventos por padrão; monitoramento de barreira no fechamento
   por padrão (intradiário opcional: High/Low no histórico, BGK β = 0,5826 no MC).
9. **Retorno:** com ação `payoff/(1+c) − 1`; só opções `payoff/c − 1` (exige c > 0); custos adicionais
   subtraídos; brutos de IR.
10. **Saída antecipada** (pedido do usuário em 22/10/2026; regras confirmadas por ele):
    - gatilho = retorno acumulado desde a contratação ≥ 150% do CDI acumulado no mesmo período;
    - quando bate, a mesa orienta o investidor a desmontar (sem carência); depende do OK do investidor →
      modelado como desmontagem `delay` pregões depois (padrão 1), pelo valor daquele dia;
    - spread de saída **desconhecido** pelo usuário → parâmetro, padrão 1% (estimativa; ajustar quando souber);
    - condição avaliada sobre o retorno já líquido do spread;
    - marcação diária a modelo: Black-Scholes + fórmula fechada de barreira (Reiner-Rubinstein) com BGK
      **afastando** a barreira (aproxima monitoramento diário); vol = realizada 63d + 3 pts (ou fixa da
      contratação); **calibrada ao preço pago** (offset do dia 0 amortizado linearmente) por padrão;
    - MC: 2.000 primeiros caminhos, vol e CDI constantes; histórico: CDI de cada dia;
    - resultado "com saída" sempre ao lado de "até o vencimento"; % do CDI e anualização pelo prazo efetivo;
    - histórico separado por nível de CDI no início (≤ 8%, 8–12%, > 12%): o nível de juros domina o resultado
      (essa tabela só aparece com o ajuste ao CDI de hoje desligado).
11. **Revisão metodológica** (`docs/REVISAO_METODOLOGICA.md`, feita em outro chat; decisões do usuário em 28/10/2026):
    - pergunta = "chance de dar certo se eu contratar **agora**" → condicional ao momento (CDI e vol de hoje);
    - prazos típicos 3 meses (63 pregões), às vezes 6, 9 ou 12 → **padrão Collar KI 100/106/112, 3 meses**, com
      atalhos de vértice 3/6/9/12m; a lâmina Proteção Total BBDC4 continua como preset;
    - **CDI de referência = CDI efetivo mais recente** (série 12), editável (DI futuro do vencimento);
    - **ajuste de regime** ligado por padrão nas janelas (e na saída antecipada); P(> CDI da época) secundária;
    - **IC 95% por moving block bootstrap** (bloco = N, B = 1.000, gerador mulberry32 compartilhado Python/JS);
    - **drift do MC = CDI por padrão** (opções: CDI + prêmio, zero, histórico com aviso, personalizado), também no
      bootstrap; grade de 9 cenários drift × vol (5.000 caminhos, mesmos sorteios) com faixa mín–máx;
    - extras escolhidos: **CVaR 5%** e **bootstrap sorteando fechamento + máxima + mínima juntos**;
    - indicadores na ordem P(lucro) → P(> CDI de hoje) → P(barreira), sempre com faixa;
    - **Fase 2** (aval do usuário em 29/10/2026: "Ok, siga para a FASE 2"): Monte Carlo **FHS-GJR** como padrão,
      painel de vol, saída antecipada marcada com a vol do GARCH, painel de calibração walk-forward (sob demanda).
12. **Decisões de implementação da Fase 2:**
    - **GJR-GARCH como padrão** (inclui o GARCH(1,1) como caso γ = 0; nos testes walk-forward os dois empatam);
      seleção "Modelo de vol" para trocar;
    - **GARCH ajustado na hora**, inclusive no site (Web Worker; 0,05–0,9 s), em vez de pré-calcular no
      `build_site_data.py` — assim respeita o período "Desde" e CSV enviado;
    - Nelder-Mead **escrito igual** em Python e JS, 2 pontos iniciais + reinícios, passo 0,25 (o passo 0,5 com
      1 início parava na borda p = 0,999 na série do Yahoo com o pregão de 29/10 → vol de longo prazo 150%);
    - FHS com sorteio i.i.d. pelo **mulberry32 vetorizado** (mesmos caminhos nos dois motores);
    - máxima/mínima **padronizadas pela vol GARCH do dia** e sorteadas junto (sem BGK no FHS);
    - marcação da saída: vol média prevista para o prazo restante + 3 pts; parâmetros do período inteiro;
    - calibração: datas a cada 10 pregões após 504, 1.000 caminhos, GARCH reestimado a cada 252, chute fixo =
      frequência nas janelas já encerradas até a data; Brier e diagrama de confiabilidade (faixas de 10 p.p.).

## 4. Estado atual (28/10/2026)

- Commits na `main` (todos enviados até `7de331d`; conferir com `git status` / `git log origin/main..` se há
  algo só local). Primeiros commits:
  - `e5e97a6` estrutura inicial · `bae8245` motor de payoff + presets · `27faaee` precificação ·
    `7980c97` dados/backtest/métricas · `8c18b52` fix pandas 3 · `c12226f` app Streamlit · `217b8b7` README ·
    `5c49e4a` motor JS · `218b596` site estático + workflow.
- **Testes:** 73 pytest + 20 node, todos passando.
- **Deploy:** GitHub Pages ativo com *Source: GitHub Actions*; primeiro deploy (run 39344983819) passou em todas
  as etapas; site conferido no ar (BBDC4/Proteção Total: 3.924 janelas, P(lucro) 100%, P>CDI 35,07%, barreira
  acionada 27,55%, ex-post +23,42% até 19/10/2026).
- **Streamlit:** funciona localmente; **não** foi publicado no Streamlit Community Cloud.
- **Saída antecipada (22/10/2026):** implementada nos dois motores, no site (Mais opções → Saída antecipada;
  blocos no Backtest, Monte Carlo e Ex-post) e no Streamlit (seção 7 da barra lateral). Exemplo BBDC4:
  histórico 69,1% de saídas (dia mediano 62), MC 21,9% (dia 224); operação real a 0,59 p.p. do gatilho em
  22/10/2026. Commits `bfed7af` (Python), `04387b4` (JS) e `2688dc9` (site/Streamlit/docs), enviados.
- **Fase 1 da revisão (28/10/2026):** implementada nos dois motores, no site e no Streamlit (commits `1c7a4fb`,
  `5df8527`, `194f71b`, `7de331d`); **enviada e publicada** (deploy run 40807283702, site conferido no ar com
  dados até 28/10/2026 e CDI de hoje 13,65%). Números de referência (Collar KI 3m BBDC4, dados até 28/10/2026,
  ajuste ligado): P(lucro) 57,8% (IC 50–65%), P(> CDI de hoje) 48,3% (IC 41–56%), P(barreira) 44,6%.
- **Fase 2 da revisão (29/10/2026):** implementada nos dois motores, no site e no Streamlit; commits locais
  (conferir `git log origin/main..`) — **pedir aval antes do push**. Referência (mesmo exemplo): GJR α 0,092 ·
  γ 0 · β 0,878 · persistência 0,970; vol de hoje 114,7%, prevista para 3 meses 82,0%, longo prazo 37,0%,
  meia-vida 23 pregões. MC FHS: P(lucro) 47,5%, P(> CDI) 43,6%, P(barreira) 62,0% (bootstrap: 55,5 / 47,1 /
  45,6%). Saída antecipada: histórico 47,7% (dia 39) com marcação GARCH (53,4% com a vol móvel); MC 50,2%
  (dia 14). Calibração (Brier, ganho sobre o chute fixo, FHS-GJR): BBDC4 +1,0 / +2,1 / +4,1%; PETR4 +2,9 /
  +2,2 / +7,0%; VALE3 +0,9 / +3,2 / +7,7% (lucro / > CDI / barreira); bootstrap sempre pior.
- **Pedido pendente do usuário (29/10/2026):** depois da Fase 2, um **PDF com o layout do simulador**,
  didático para especialistas de investimentos: o que é estruturada, tipos e descrições, como funciona o
  modelo, métodos estatísticos e passo a passo de uso com exemplos práticos e imagens de cada passo.
- **Mercado em 26/10/2026:** Ibovespa −13,9% em um dia (BBDC4 −24,5%, ITUB4 −13,7%); dado real, conferido. A vol
  realizada de 63 pregões de BBDC4 foi a 63% (≈ 1,9× a média) — argumento a favor da Fase 2 (vol condicional).
- **Pendências do usuário:** o GitHub exige ativar a verificação em duas etapas até **23/11/2026**, senão a conta
  fica restrita (afeta pushes). Há um comentário aberto no manual perguntando se as barreiras das lâminas da
  mesa costumam ser monitoradas no fechamento ou no intradiário.

## 5. Mapa do código

```
estruturadas-sim/
  app.py                     Streamlit (barra lateral + 5 abas)
  METODOLOGIA.md             texto da aba de metodologia do Streamlit
  estruturadas/              motor Python (legs, presets, pricing, data, backtest, garch, calibration, early_exit, metrics, rng, io, charts, formatting)
  presets/protecao_total_bbdc4.json   lâmina de exemplo
  scripts/
    build_site_data.py       gera site/data/ (preços Yahoo + CDI/Selic BCB)
    tickers.py               lista de ações do site
    make_js_fixtures.py      gera tests/js/fixtures.json a partir do motor Python
  site/
    index.html               layout do painel; assets com ?v=__V__ (trocado pelo hash no deploy)
    assets/css/styles.css    tema do painel + estilos do simulador (final do arquivo)
    assets/js/engine/        legs.js, presets.js, pricing.js, garch.js, backtest.js, early.js, calib.js (porta do Python; window/globalThis.Estr)
    assets/js/worker.js      Web Worker (price, solve, hist, mc, scen, hexit, mcexit, calib com progresso)
    assets/js/core.js        App: formatação, estado (localStorage "es:state"), dados, Worker, orquestração
    assets/js/charts.js      ECharts
    assets/js/params.js      barra de parâmetros + "Mais opções"
    assets/js/views/         estrutura, backtest (+ App.ui compartilhado), montecarlo, expost, metodologia
    assets/js/app.js         roteador por hash, cabeçalho, rodapé
    assets/vendor/echarts.min.js
  tests/                     pytest + tests/js/engine.test.mjs (+ fixtures.json)
  .github/workflows/pages.yml  testes + dados + deploy
  docs/CONTEXTO_DO_PROJETO.md  este arquivo
```

Padrões do site: cada página exporta `App.views.<rota> = { render(el) }` e escuta `App.on("results", …)`;
editores (tabela de pernas, solver) só são reconstruídos no evento `structure` para não perder o foco;
`App.update(patch, {structural})` salva e agenda o recálculo; `App.setStructure(s, presetKey, resetMeta)`
troca a estrutura (preset, JSON, solver).

## 6. Ambiente local e comandos

- Windows 11; shells Git Bash e PowerShell. Python do sistema 3.13; venv em `estruturadas-sim/.venv`
  (no `.gitignore`). Node 24.
- Identidade git configurada **só neste repositório** (`user.name "Vinicius Marques Serpeloni"`,
  e-mail `vinimarquesserpeloni@outlook.com`). Não há `gh` (GitHub CLI); o push usa o Git Credential Manager.
- `..\.claude\launch.json` (na pasta `Códigos`) tem as entradas `estruturadas-sim` (Streamlit, porta 8501) e
  `estruturadas-site` (http.server na pasta `site`, porta 8770) para o painel de navegador do Claude.

```bash
cd estruturadas-sim
.venv/Scripts/python -m pip install -r requirements.txt     # se o venv sumir: python -m venv .venv
.venv/Scripts/python -m pytest -q                            # 73 testes
node --test tests/js/engine.test.mjs                         # 20 testes (no Windows, passar o arquivo, não a pasta)
.venv/Scripts/python scripts/make_js_fixtures.py             # após mudar o motor Python
.venv/Scripts/python scripts/build_site_data.py PETR4 BBDC4  # dados locais do site (todas: sem argumentos, ~1 min)
python -m http.server 8770 --directory site                  # site local em http://localhost:8770
.venv/Scripts/python -m streamlit run app.py                 # app Streamlit
```

Para acompanhar um deploy sem o `gh`:
`curl -s "https://api.github.com/repos/viniciusmarquesserpeloni-commits/estruturadas-sim/actions/runs?per_page=1"`.

## 7. Armadilhas já encontradas

| Armadilha | Solução adotada |
|---|---|
| pandas 3: `to_numpy()` pode devolver array somente-leitura | `to_numpy(dtype=float, copy=True)` antes de escrever |
| Streamlit trata dois `$` na mesma frase como LaTeX ("R$ … R$") | `md_brl()` no `app.py` escapa `\$` em textos Markdown |
| Docs do claude.ai também tratam `$…$` como fórmula | escrever "reais" em vez de dois "R$" na mesma linha |
| `Object.assign` copia `undefined` (apagava as pernas em `E.structure`) | `E.structure` define `name`/`legs` depois do assign |
| Cache do navegador servia JS/CSS antigos | `?v=__V__` nos assets, trocado pelo hash do commit no workflow; o Worker herda a versão |
| Classe `.ac` do painel tem `flex: 1 1 280px` (vira altura numa coluna) | `.pfield .ac { flex: none }` |
| Tickers deslistados/renomeados no Yahoo (ELET3→AXIA3, EMBR3→EMBJ3, BRFS3/MRFG3→MBRF3…) | `build_site_data.py` ignora quem não tem dados; lista já limpa |
| API SGS do BCB limita séries diárias a 10 anos por consulta | download do CDI em blocos de 5 anos |
| `node --test tests/js/` (pasta) falha no Windows | rodar o arquivo `tests/js/engine.test.mjs` |
| RNG do Python (PCG64) ≠ JS (mulberry32) | bootstrap/GBM comparam só estatisticamente; o FHS usa o mulberry32 vetorizado nos dois e dá os mesmos caminhos |
| Nelder-Mead parava na borda p = 0,999 (vol de longo prazo 150%) | passo 0,25, 2 pontos iniciais e reinícios; teste contra o scipy |
| `math.exp` estoura no Python (o JS devolve Infinity) | `_exp` com OverflowError → inf no `garch.py` |
| Fixtures antigas da saída antecipada passaram a usar o GARCH (novo padrão) e divergiam por 1e-9 | casos antigos fixados em `vol_mode="rolling"`; o GARCH tem fixtures próprios com os parâmetros do Python |
| Enunciado original pedia 42,10%/57,10% na Proteção Total | com as pernas da lâmina o exato é 42,00%/57,00% (a lâmina arredonda 42/57); testes usam o exato e explicam |
| Máximo "logo abaixo da barreira" | supremo não atingido: P(atingir retorno máximo) pode ser 0% |
| `streamlit` ≥ 1.50: `use_container_width` descontinuado | usar o padrão (`width="stretch"`) |
| Agendamento do GitHub pausa após 60 dias sem atividade | reativar o workflow na aba Actions |
| BGK tem dois sentidos | caminhos diários → intradiário: barreira em direção ao preço (pricing/MC); fórmula contínua → diário: barreira afastada (early_exit). Errar o sentido dá erro de 20–30 erros padrão |
| Regra "≥ 150% do CDI" sem calibração dispara no 1º–2º dia em épocas de juros baixos | calibração ao preço pago (padrão) |
| Histórico × MC da saída antecipada muito diferentes | é o nível do CDI (MC usa o atual, 13,75%); ver quebra por regime de juros |
| `scipy.stats.norm.cdf` lento em laços grandes | `scipy.special.ndtr` nas funções vetorizadas |
| Streamlit: mesmo gráfico em duas abas → `StreamlitDuplicateElementId` | passar `key=` distinto |
| `build_site_data.py PETR4 …` com poucas ações apaga os JSON das outras em `site/data/precos` | normal (pasta local, fora do git); rodar sem argumentos para todas |
| Yahoo devolve máxima/mínima = 0 (e volume 0) no pregão em andamento | `clean_prices` troca valores ≤ 0 pelo fechamento (o site já tratava) |
| API do BCB com falha momentânea → CDI `None` → ajuste de regime desligado em silêncio | `fetch_cdi_daily` tenta 3 vezes por bloco; no Streamlit a falha não fica em cache |
| Grade de cenários com 2.000 caminhos tinha ruído de ±1 p.p. (célula central ≠ MC principal) | 5.000 caminhos por cenário |
| Heredocs longos no Bash deste ambiente quebram ("unexpected EOF") | escrever scripts de patch com a ferramenta de escrita e executá-los |

## 8. Ideias de próximos passos (roadmap)

- Reprecificar a estrutura em cada janela com a vol/juros da época.
- Vol implícita e skew; dividendos discretos no modo Teórico.
- Monitoramento intradiário no MC com ponte browniana.
- Autocalls/estruturas com cupom; mais de um ativo.
- Comparar várias estruturas lado a lado; IR e CDI líquido.
- Link compartilhável com a estrutura codificada na URL (hoje o estado fica no `localStorage`).
- Opcionais da revisão: bootstrap estacionário com bloco automático; GARCH com resíduos t; benchmark "ação + CDI
  com o mesmo delta".
- Publicar o Streamlit no Community Cloud, se o usuário quiser.
- Saída antecipada: calibrar spread de saída e adicional de vol com extratos de marcação do banco; vol
  implícita real via COTAHIST da B3 (ações com opções líquidas); vol variável no MC.

## 9. Checklist ao mudar algo

1. Mudou cálculo? Altere `estruturadas/*.py` **e** `site/assets/js/engine/*.js`.
2. Rode `pytest`, regenere as fixtures (`make_js_fixtures.py`) e rode `node --test tests/js/engine.test.mjs`.
3. Mudou o site? Teste local (`build_site_data.py` com 2–3 ações + `http.server`), confira o console sem erros,
   largura de celular (375 px) sem rolagem horizontal.
4. Atualize o README (seção de cálculos) e, se for decisão nova, este arquivo.
5. Commit em pt-BR; **pergunte antes do push**. O push dispara o deploy; confira o run no Actions.
