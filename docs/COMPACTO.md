# Compacto — Simulador de Operações Estruturadas (para colar em um chat novo)

> Resumo de 1 página. Detalhes: `docs/CONTEXTO_DO_PROJETO.md` (decisões, armadilhas, comandos) e `README.md`
> (todas as fórmulas). Atualizado em 28/10/2026.

**O que é:** simulador/backtest de operações estruturadas com opções sobre ações da B3, na linguagem das lâminas
da mesa ("Composição da Estratégia", "Quadro de rentabilidade", Knock Up/Down and In/Out). Mede a chance de
lucro aplicando a estrutura ao histórico (janelas móveis) e ao Monte Carlo, mostra o ex-post de operações reais
e simula a **saída antecipada** (desmontagem quando a estrutura rende ≥ 150% do CDI).

**Onde:** site público https://viniciusmarquesserpeloni-commits.github.io/estruturadas-sim/ · repositório
github.com/viniciusmarquesserpeloni-commits/estruturadas-sim (branch `main`) · pasta local
`C:\Users\vinim\OneDrive\Área de Trabalho\Códigos\estruturadas-sim` (Windows; venv em `.venv`).

**Usuário e regras de trabalho:** especialista de investimentos. Tudo em **português do Brasil**. **Perguntar
antes de cada `git push`.** **Nada de marca/logo do Itaú.** Commits pequenos em pt-BR terminando com
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Ferramenta educacional (manter avisos).

**Arquitetura:**
- `estruturadas/` — motor Python de **referência**: `legs` (pernas, payoff vetorizado), `presets` (9 estruturas +
  textos), `pricing` (Black-Scholes, Monte Carlo neutro ao risco, fórmula fechada de barreira, solver de custo
  zero), `data` (Yahoo/CSV, CDI/Selic do BCB, calendário B3), `backtest` (janelas, bootstrap, GBM, ex-post),
  `early_exit` (saída antecipada), `metrics`, `io` (JSON das lâminas), `charts` (Plotly).
- `app.py` — Streamlit (local; não publicado).
- `site/` — site estático no **mesmo layout do painel "Relatório de Fundos"** do usuário: HTML/CSS/JS puro,
  ECharts; motor JS em `site/assets/js/engine/` (**porta do Python**, validada por fixtures); cálculos pesados em
  Web Worker; páginas Estrutura, Backtest histórico, Monte Carlo, Ex-post, Metodologia.
- `scripts/` — `build_site_data.py` (dados do site), `tickers.py` (~95 ações), `make_js_fixtures.py`.
- `.github/workflows/pages.yml` — testes + dados + deploy no Pages a cada push e dias úteis 19h30.

**Metodologia em 6 linhas:** S0 = 1, strikes/barreiras em % · retorno = valor final/(1+c) − 1 (só opções:
/c) · janelas históricas `P[t+1..t+N]/P[t]` + amostra efetiva · MC bootstrap em blocos (padrão) ou GBM ·
custo Informado (mesa) ou Teórico (BS + MC, antitéticas, seed fixa) · apuração em D−1 do vencimento, preço
ajustado por proventos, barreira no fechamento (intradiário opcional, BGK 0,5826).

**Saída antecipada (regras confirmadas pelo usuário):** gatilho = retorno acumulado líquido do spread ≥ 150%
do CDI acumulado; sem carência; depende do OK do investidor → desmontagem 1 pregão depois, pelo valor do dia;
spread de saída desconhecido → 1% (parâmetro). Marcação diária: BS + Reiner-Rubinstein com BGK **afastando** a
barreira, vol realizada 63d + 3 pts, **calibrada ao preço pago** (offset do dia 0 amortizado). Juros dominam o
resultado (histórico separado por CDI ≤ 8%, 8–12%, > 12%).

**Revisão metodológica** (`docs/REVISAO_METODOLOGICA.md`): pergunta = "chance de dar certo se contratar **agora**".
**Fase 1 feita** (não enviada ao GitHub até o usuário revisar): CDI de hoje como régua (CDI efetivo, editável) e
ajuste de regime nas janelas, IC 95% por block bootstrap (mulberry32 igual nos dois motores), drift do MC = CDI
(padrão) inclusive no bootstrap, grade de cenários drift × vol, CVaR 5%, bootstrap com máxima/mínima, padrão
Collar KI 100/106/112 em 3 meses com vértices 3/6/9/12m. **Fase 2 pendente:** FHS-GARCH/GJR, painel de vol,
painel de calibração walk-forward.

**Números de referência (Proteção Total BBDC4, 19/11/2025 → 25/11/2026, 249 pregões):** quadro 4,10 / 6,10 /
42,00 / 57,00% (lâmina arredonda 42/57) · histórico: P(lucro) 100%, P(>CDI) 35%, barreira 27,5% · saída
antecipada: histórico 69% (dia mediano 62), MC 22% (dia 224) · operação real a 0,59 p.p. do gatilho em
22/10/2026.

**Estado:** no GitHub até `2688dc9` (saída antecipada); o compacto e a Fase 1 da revisão estão só locais até o
usuário revisar (conferir com `git log origin/main..`). Testes: 66 pytest + 16 node. Mercado: Ibovespa −13,9% em 26/10/2026 (vol muito alta). Pendências do usuário: ativar 2FA no GitHub até 23/11/2026; descobrir o spread real de saída.

**Comandos:** `.venv/Scripts/python -m pytest -q` · `node --test tests/js/engine.test.mjs` ·
`.venv/Scripts/python scripts/make_js_fixtures.py` (após mudar o motor Python) ·
`.venv/Scripts/python scripts/build_site_data.py PETR4 BBDC4` + `python -m http.server 8770 --directory site`.

**Regra de ouro:** mudou cálculo → alterar Python **e** JS, regenerar fixtures, rodar os dois testes,
atualizar README/CONTEXTO, commitar e **pedir aval antes do push**.
