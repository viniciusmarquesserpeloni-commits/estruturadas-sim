# Revisão metodológica do simulador de estruturadas — briefing para implementação

> Documento gerado a partir de uma revisão (Claude, out/2026) do projeto `estruturadas-sim`.
> Destinatário: Claude Code. Objetivo: implementar as melhorias abaixo em **Python (`estruturadas/`, `app.py`)
> e JS (`site/assets/js/engine/`, `views/`, `worker.js`)**, mantendo a paridade entre os dois motores
> (`scripts/make_js_fixtures.py` + `tests/js/engine.test.mjs`).

---

## 0. Contexto e decisões do autor

- **Pergunta que a ferramenta deve responder:** *"qual a chance de eu acertar esta estruturada se eu contratar AGORA?"*
  → o foco é **probabilidade condicional ao momento atual** (vol de hoje, CDI de hoje), não "como teria sido no passado".
- **Prazos típicos:** maioria **3 meses (63 pregões)**, no máximo **6 meses (126 pregões)**.
- **Sem acesso a vol implícita/skew** da mesa → continuar com vol realizada (+ adicional) onde hoje já se usa.
- **Manter P(lucro) como primeiro indicador.** P(>CDI) já existe (`p_cdi`), mas deve passar a usar o **CDI de hoje** como régua.
- Público: colegas da mesa → a ferramenta precisa **comunicar incerteza** (faixas), não números "cravados".

### O que já está bom (não mexer na essência)
Janelas móveis como base (alinhado ao PRIIPs revisado, Reg. Delegado UE 2021/2268), bootstrap em blocos, amostra
efetiva exibida, correção Broadie-Glasserman-Kou, OHLC ajustado por proventos, separação P (probabilidade) × Q (preço).

---

## 1. Principais achados dos testes (BBDC4/PETR4, 2010–out/2026)

Scripts de referência em `scripts/pesquisa/` (`exp2.py`, `exp3.py`): payoffs simplificados de Collar KI
(3m: 100/106/112; 6m: 100/110/120) e Proteção Total (12m), CDI de hoje = 13,65% a.a. (derivado da Selic meta 13,75%
em `site/data/index.json`). São ilustrativos — servem de ordem de grandeza / sanity check, não de fixture exata.

### 1.1 Incerteza amostral (janelas sobrepostas)
| Prazo | Janelas | Amostra efetiva | Margem típica IC95% |
|---|---|---|---|
| 63 pregões | ~4.100 | ~65 | ±8 p.p. |
| 126 pregões | ~4.050 | ~32 | ±10 p.p. |
| 252 pregões | ~3.900 | ~15 | ±12–15 p.p. |

Ex.: Collar KI 3m BBDC4 → P(lucro) = 56%, **IC95% [48%, 64%]** (moving block bootstrap, bloco = N).

### 1.2 Capacidade preditiva (walk-forward, 722 datas, Collar KI 3m)
Brier score (menor = melhor; 0,25 = chutar 50%):

| BBDC4 | Vol incondicional | Realizada 63d | EWMA 0,94 | GARCH(1,1) | Chute fixo (freq. histórica) |
|---|---|---|---|---|---|
| P(lucro) | 0,247 | 0,250 | 0,249 | 0,249 | **0,246** |
| P(barreira) | 0,247 | 0,248 | 0,246 | **0,242** | 0,248 |
| P(>CDI) | 0,251 | 0,252 | 0,252 | 0,252 | **0,250** |

PETR4: mesmo padrão. **Conclusão:** para direção (lucro / >CDI) nenhum modelo supera o chute climatológico; GARCH
melhora levemente a **probabilidade de barreira** (vol é previsível no curto prazo, direção não).
Com drift = CDI, P(lucro) previsto médio 50–53% vs realizado 56–60% (o período teve ações acima do CDI).
→ A ferramenta deve **mostrar faixas e forma da distribuição**, e deixar clara a baixa capacidade preditiva para direção.

### 1.3 Regime de juros
| Estrutura | P(>CDI) c/ CDI da época | P(>CDI) c/ CDI de hoje + caminho ajustado |
|---|---|---|
| Collar KI 3m BBDC4 | 48% | 48% |
| Collar KI 6m BBDC4 | 50% | 50% |
| Proteção Total 12m BBDC4 | 34% | **22%** |
| Proteção Total 12m PETR4 | 21% | **11%** |

Estruturas atreladas à ação quase não mudam (o drift da ação sobe junto com o CDI); estruturas com **piso/cupom
fixo** ficam infladas quando testadas em épocas de CDI baixo.

### 1.4 Sensibilidade (Collar KI 3m, BBDC4)
- **Drift** (σ = 37%): −10% a.a. → P(lucro) 41% · 0% → 46% · CDI → 53% · CDI+5% → 55%.
- **Vol** (drift = CDI): σ 20/30/40/50% → P(barreira) 31/45/55/60% · P(lucro) 61/55/52/50%.
- Erro padrão do drift histórico anual ≈ σ/√anos: BBDC4 ≈ ±8 p.p., PETR4 ≈ ±10,5 p.p. → média histórica ≈ ruído (Merton, 1980).
- Tamanho do bloco do bootstrap (20 vs 60) teve impacto pequeno.

---

## 2. Plano de implementação

**Fase 1 (fazer primeiro):** itens 2.1, 2.2, 2.3. **Fase 2:** itens 2.4, 2.5. Itens 2.6 opcionais.
Confirmar com o autor antes de iniciar a Fase 2.

### 2.1 P(>CDI) contra o CDI de hoje + ajuste de regime nos caminhos históricos
- Novo parâmetro **`cdi_ref`** (taxa anual efetiva, base 252). Padrão: taxa já usada na barra lateral
  (`ctx.rateAnnual` / Selic meta); campo editável com dica "use o DI futuro do vencimento, se souber".
- Em `run_historical` / `E.runHistorical`: opção **`regime_adjust`** (padrão **ligado**):
  ```
  path_adj[t, k] = path[t, k] * (1 + cdi_ref)^(k/252) / (CDIfator[t+k] / CDIfator[t])     k = 1..N
  ```
  aplicado igualmente a close, high e low. Preserva o excesso de retorno da ação sobre o CDI de cada época e o
  "re-ancora" no CDI de hoje. Se a série de CDI não estiver disponível, desligar e avisar.
- Coluna `retorno_cdi_hoje = (1 + cdi_ref)^(N/252) − 1`; KPI **"P(retorno > CDI de hoje)"** ao lado de P(lucro)
  (P(lucro) continua sendo o primeiro). Manter "P(> CDI da época)" na tabela detalhada como métrica secundária.
- Monte Carlo já usa CDI constante → apenas garantir que usa o mesmo `cdi_ref`.
- **Testes:** com CDI histórico constante e igual a `cdi_ref`, `path_adj == path`; P(>CDI de hoje) da Proteção
  Total BBDC4 12m deve cair claramente em relação a P(>CDI da época) (ordem de 34% → ~22%).

### 2.2 Intervalos de confiança e faixas de cenário
- **Backtest histórico:** IC 95% por **moving block bootstrap** sobre a série de indicadores por janela (0/1),
  bloco = N, B = 1000 (Python) / 500 (JS, se pesar), seed fixa. Aplicar a: P(lucro), P(>CDI hoje), P(perda),
  P(barreira acionada). Exibir como `56% (IC 48–64%)` e uma nota curta: *"janelas se sobrepõem; amostra efetiva ≈ N_eff"*.
  Implementar em `metrics.py` (`block_bootstrap_ci(indicator, block, B, seed)`) e equivalente JS.
- **Monte Carlo:** o erro de sorteio é desprezível; a incerteza relevante é de **premissa**. Rodar uma grade
  pequena de cenários e mostrar **faixa min–máx**:
  - drift ∈ {0, CDI, CDI + prêmio (padrão 5 p.p.)}
  - vol ∈ {vol de hoje × 0,8; × 1,0; × 1,2} (vol de hoje = item 2.4, ou realizada 63d na Fase 1)
  Para não pesar: 2.000–5.000 caminhos por cenário no JS (worker), mesmos números aleatórios entre cenários.
- **UI:** KPI principal = cenário central; abaixo "faixa entre cenários: X%–Y%". Tabela de sensibilidade (drift × vol)
  para P(lucro), P(>CDI) e P(barreira).

### 2.3 Drift controlado pelo usuário (inclusive no bootstrap)
- Opções: **`cdi` (padrão)**, `zero`, `cdi_premio` (input, padrão 5 p.p.), `historico` (mantido, com aviso
  "estatisticamente pouco confiável: erro padrão ≈ σ/√anos"), `personalizado`.
- **Bootstrap:** remover a média dos log-retornos e somar o drift escolhido:
  ```
  lr_boot = (lr − mean(lr)) + (ln(1 + mu_anual) − 0,5·σ²)/252
  ```
  (assim E[S_T] ≈ (1 + mu)^(N/252)). Aplicar em `block_bootstrap_paths` e `E.blockBootstrapSummary`.
- GBM: `gbm_drift_daily` já cobre `zero`/`cdi`/`historico`; acrescentar `cdi_premio`/`personalizado`.
- Mudar o padrão de `mcDrift` de `"historico"` para `"cdi"` (`core.js`, `app.py`).
- **Testes:** média do log-retorno acumulado do bootstrap ≈ (ln(1+mu) − 0,5σ²)·N/252 (tolerância MC).

### 2.4 Vol condicional: Monte Carlo FHS-GARCH (Fase 2)
Filtered Historical Simulation (Barone-Adesi, Giannopoulos & Vosper, 1999) — vira o **método padrão** do MC.
1. Ajuste **GARCH(1,1)** por máxima verossimilhança gaussiana nos log-retornos sem média:
   `h_t = ω + α·ε²_{t−1} + β·h_{t−1}`, restrições ω>0, α,β≥0, α+β<0,999 (Nelder-Mead ou L-BFGS-B com reparametrização).
2. Resíduos padronizados `z_t = ε_t/√h_t`, re-normalizados (média 0, desvio 1).
3. Simulação: `h` inicial = previsão de 1 passo de hoje; a cada dia sorteia `z*` (iid dos resíduos), `e = √h·z*`,
   `log-ret = mu_dt − 0,5·h + e`, `h ← ω + α·e² + β·h`. `mu_dt` vem do item 2.3.
4. Barreira intradiária: manter BGK, mas com σ do passo (`√h` por dia) em vez de σ incondicional.
5. **JS:** para os tickers do site, pré-calcular no `scripts/build_site_data.py` (ω, α, β, h_T e os `z`) e gravar
   em `site/data/precos/XXXX.json` (ou `site/data/garch/XXXX.json`); para CSV enviado pelo usuário, ajustar no
   worker (Nelder-Mead simples em JS). Python ajusta na hora.
6. **UI:** painel "Vol": vol de hoje (√(h_T·252)), vol média de longo prazo (√(ω/(1−α−β)·252)), vol média prevista
   para o prazo, meia-vida = ln(0,5)/ln(α+β) pregões, e a vol realizada 63d para comparação.
- Manter "Bootstrap em blocos" e "GBM" como alternativas.
- **Testes:** recuperar parâmetros em série GARCH simulada (tolerância folgada); com α=0 e β=0 o FHS deve reduzir a
  bootstrap iid com vol constante.

### 2.5 Painel de calibração walk-forward (Fase 2)
"Selo de confiabilidade" da ferramenta: como as previsões teriam se saído no passado para **a estrutura escolhida**.
- A cada `passo` pregões (padrão 10) a partir de 504 pregões de histórico: usar **só dados até t**, estimar
  P(lucro), P(>CDI) e P(barreira) com o método selecionado (caminhos reduzidos: 1.000–2.000), e comparar com o
  resultado realizado da janela [t, t+N].
- Métricas: **Brier score** do modelo vs **Brier do chute climatológico** (frequência histórica até t),
  e **diagrama de confiabilidade** (previsto × realizado por decis).
- Rodar no worker com barra de progresso, sob demanda (botão "Testar calibração"); GARCH re-ajustado a cada 252 pregões.
- Texto de leitura: "Se o Brier do modelo não for menor que o do chute fixo, trate a probabilidade como
  ordem de grandeza, não como previsão."

### 2.6 Opcionais / baixa prioridade
- Bootstrap estacionário (Politis-Romano) com bloco automático (Politis & White 2004; correção Patton et al. 2009).
- No bootstrap, sortear **(fechamento, máxima/fech. anterior, mínima/fech. anterior)** juntos, em vez de BGK.
- Métricas de cauda: **CVaR 5%** (média dos 5% piores) ao lado do P5; comparação com benchmark "ação + CDI com mesmo delta".
- Backtest dinâmico (re-resolver custo zero a cada data com vol/CDI da época): responde "contratar sistematicamente
  vale a pena?" — **não** é prioridade para o objetivo "agora".
- Vol implícita: sem acesso pela mesa; a brapi tem histórico de IV por série (plano Pro; sem token só séries PETR).

---

## 3. Documentação e comunicação
- Atualizar `METODOLOGIA.md` e `site/assets/js/views/metodologia.js`: CDI de referência e ajuste de regime, IC por
  block bootstrap, drift padrão = CDI e por quê, FHS-GARCH, painel de calibração.
- Em "Limitações", incluir: *"Em testes walk-forward (2012–2026), as probabilidades de lucro/superar o CDI não foram
  mais precisas que a frequência histórica; o modelo é mais útil para comparar estruturas, dimensionar o risco de
  barreira e visualizar a distribuição de resultados."*
- Manter o aviso de ferramenta educacional, sem afiliação institucional.

## 4. Critérios de aceite
- [ ] `pytest` e `node tests/js/engine.test.mjs` passam; fixtures de paridade regeneradas e atualizadas.
- [ ] KPIs na ordem: P(lucro) (com IC) → P(>CDI de hoje) (com IC) → P(barreira) (com IC).
- [ ] MC mostra cenário central + faixa de cenários + tabela de sensibilidade drift × vol.
- [ ] Padrões: drift `cdi`; `regime_adjust` ligado; (Fase 2) método MC `fhs_garch`.
- [ ] Desempenho no site aceitável (cálculos pesados no worker, com progresso).
- [ ] Metodologia atualizada nos dois lugares.

## 5. Referências
- Barone-Adesi, Giannopoulos & Vosper (1999), *VaR without correlations for portfolios of derivative securities*, J. Futures Markets — FHS.
- Politis & White (2004); Patton, Politis & White (2009), *Correction to automatic block-length selection…*, Econometric Reviews.
- Merton (1980), *On estimating the expected return on the market*, JFE — imprecisão da média.
- Broadie, Glasserman & Kou (1997) — correção de monitoramento discreto de barreira (já implementada).
- Regulamento Delegado (UE) 2021/2268 (PRIIPs) — cenários por janelas históricas móveis.
- Vokata (2021), *Engineering lemons*, JFE; De Genaro (FGV EAESP) sobre COE vs CDB — contexto sobre produtos estruturados de varejo.
