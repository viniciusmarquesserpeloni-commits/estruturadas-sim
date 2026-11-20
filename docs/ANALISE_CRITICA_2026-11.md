# Análise crítica do simulador — objetivos e métodos estatísticos

> Feita em 15/11/2026 (Claude Fable 5.2), com os dados publicados pelo site até 13/11/2026.
> Pergunta do autor: *o projeto cumpre os objetivos estabelecidos e usa as melhores métricas estatísticas para
> simular?* Todos os números abaixo saem de testes reproduzíveis em `scripts/pesquisa/exp4…exp9` (seção 7).
> A análise em si não alterou o simulador. **Atualização de 20/11/2026:** as três correções de prioridade 1
> (seção 6) foram implementadas depois, a pedido do autor — filtro de dados, GARCH com alvo de variância e IC de
> Wilson; ver README, seção 4.21. Os números abaixo são os de antes das correções.

## 1. Resumo

**Objetivos de entrega: cumpridos.** Site público no ar com atualização diária funcionando, linguagem das
lâminas, backtest, Monte Carlo, ex-post, saída antecipada, 73 + 20 testes, documentação e guia.

**Objetivo central — "qual a chance de dar certo se eu contratar agora?": cumprido em parte.** A arquitetura
está certa (histórico re-ancorado no CDI de hoje + Monte Carlo com a vol de hoje + faixas de incerteza), mas
cinco problemas medidos reduzem a confiabilidade dos números:

| # | Achado | Tamanho | Gravidade |
|---|---|---|---|
| 1 | **Erros de dados** não detectados: saltos de 2–3× num dia (desdobramento/cisão não ajustados) e trechos longos de preço parado | ≥ 5 ações com saltos falsos desde 2010; 7 ações com 10%–59% dos dias sem variação | Alta |
| 2 | **GARCH frágil**: o ajuste degenera com um choque extremo ou um dado errado | 15 de 94 ações (16%) com "vol de longo prazo" absurda (até 1.045%) | Alta |
| 3 | **"IC 95%" estreito demais** | cobre 82%–90% em vez de 95%; mostra "0–0%" quando o evento nunca ocorreu | Média |
| 4 | **Faixa de cenários de vol (×0,8–×1,2) otimista** | a vol realizada caiu dentro dela só 46% das vezes | Média |
| 5 | **Vol condicional não melhora, sozinha, as probabilidades** | num evento que só depende de vol, o FHS-GJR empata com a frequência histórica (−0,5%); o bootstrap ganha (+2,0%) | Média |

**O que os testes confirmam como sólido:** o backtest por janelas com ajuste ao CDI de hoje; o sorteio
independente dos choques no FHS; o drift neutro como padrão; e a mensagem que o site já passa — as
probabilidades servem para comparar estruturas e dimensionar barreira, não para prever direção.

**Recomendação em uma frase:** corrigir dados e robustez primeiro (itens 1–3 da seção 6), depois trocar o
número principal do Monte Carlo pela **média dos três métodos**, que foi a única previsão com ganho
significativo nos dois eventos testados.

## 2. Cumprimento dos objetivos

| Objetivo (origem) | Situação | Evidência |
|---|---|---|
| Falar a língua das lâminas; pernas, presets, JSON (especificação) | Cumprido | 9 presets, editor de pernas, import/export, casos das lâminas nos testes |
| Backtest histórico + Monte Carlo + ex-post (especificação) | Cumprido | três páginas no site; paridade Python × JS testada |
| Custo híbrido Informado/Teórico + solver (especificação) | Cumprido, com ressalva | o modo Teórico usa a vol de 252 pregões (39,6% em BBDC4 hoje) enquanto o Monte Carlo usa a do GARCH (49,9%): dois números de vol na mesma tela |
| Site público no layout do painel, dados diários (decisão 2 e 4) | Cumprido | 6 últimos deploys agendados com sucesso; 94 ações até 13/11/2026 |
| Saída antecipada a 150% do CDI (decisão 10) | Implementado, **não validado** | a regra está certa; a marcação a modelo nunca foi comparada com um preço real de desmontagem (spread de 1% e +3 pts de vol são estimativas) |
| "Chance de dar certo se contratar **agora**" (revisão, seção 0) | Em parte | CDI de hoje: sim. Vol de hoje: sim, mas frágil (achados 2 e 5) |
| Comunicar incerteza com faixas (revisão) | Em parte | as faixas existem, mas são estreitas demais (achados 3 e 4) |
| P(lucro) → P(> CDI de hoje) → P(barreira) (revisão) | Cumprido | ordem e rótulos no site e no Streamlit |
| Painel de calibração (revisão 2.5) | Cumprido, com ressalva | não informa se o ganho é estatisticamente distinguível de zero |
| "Mais útil para comparar estruturas" (limitações) | **Não atendido pela interface** | não há comparação lado a lado de duas estruturas (está no roadmap) |
| Documentação atualizada | Em parte | README e Metodologia em dia; o guia em PDF cita números fixos de 28/10/2026; o manual antigo no claude.ai é anterior às Fases 1 e 2 |

## 3. Achados sobre os dados

Os dados vêm do Yahoo sem nenhum filtro de qualidade além de preço positivo. Varredura das 94 ações:

**Saltos com assinatura de erro (desde 2010).** Retorno de um dia acima de 30% em módulo, fora de dias de
queda geral, com razão de preço perto de 2 ou 3 e, muitas vezes, preço parado no dia seguinte:

| Ação | Data | Variação | Provável causa |
|---|---|---|---|
| B3SA3 | 09/05/2011 | −66% (11,88 → 4,02) | desdobramento 3:1 não ajustado |
| PCAR3 | 7 datas entre 2010 e 2023 | de −67% a +139% | cisões (Assaí, Éxito) e ajustes |
| NATU3 | 16/09/2019 e 02/07/2025 | −48% e −72% | reorganizações societárias |
| UGPA3 | 28/06/2021 | +119% | ajuste de evento |
| COGN3 | 3 datas em 2012 | −33% a +82% | desdobramento |

Há ainda saltos em EQTL3 (25/08/2010), CSNA3 (09/06/2010), KEPL3 e TEND3 que pedem conferência manual.
Outros são reais (PETR4 em 09/03/2020, HAPV3 em 13/11/2025, AXIA3 em 22/08/2017).

**Efeito medido em B3SA3** (corrigindo só o dia 09/05/2011):

| | Como está | Corrigido |
|---|---|---|
| Forward Knock Out 6m: pior retorno / CVaR 5% | −77,4% / −56,3% | −36,4% / −22,4% |
| GJR: persistência / vol de longo prazo | 0,999 / 1.045% | 0,986 / 42% |
| GJR: vol de hoje | 36% | 117% |

**Preço parado tratado como histórico.** Fração de pregões com retorno exatamente zero desde 2010: PCAR3 59%,
SUZB3 47% (até nov/2017), TEND3 44% (até mai/2017), BHIA3 30%, ENGI11 24%, UGPA3 11%, TAEE11 10%. São períodos
sem negociação (papel ainda não listado nessa classe ou ilíquido). Nessas janelas a ação "não se mexe": a
P(barreira) sai baixa demais (16% no Monte Carlo do Collar KI 3m em SUZB3, contra ~50% nas demais) e a vol, subestimada.

**O dia 26/10/2026.** A base registra queda mediana de 18% nas 94 ações, com MGLU3 −58%, VAMO3 −57% e HAPV3
−55% (o pior dia da covid teve mediana de −14,6%). Esse único dia domina hoje todos os números condicionais.
Não tenho como conferi-lo em outra fonte; vale confirmar, porque se houver erro nesse dia o painel de vol
inteiro está contaminado.

## 4. Achados sobre os métodos

### 4.1 O GARCH padrão é frágil (16% das ações)

Com o ajuste atual (quase-verossimilhança gaussiana, variância de longo prazo livre), 15 das 94 ações ficam
com persistência colada no limite de 0,999 ou vol de longo prazo fora de 0,5–2× a amostral: B3SA3 (1.045%),
HAPV3 (550%), NATU3 (288%), VAMO3 (189%), ASAI3 (141%), IRBR3, CVCB3, CSAN3, AURE3, AXIA3, CPFE3, EZTC3,
IGTI11, SUZB3, YDUQ3. Para elas o painel de vol e o Monte Carlo padrão mostram números sem sentido, sem aviso.
Causa: um choque extremo (ou dado errado) domina a verossimilhança gaussiana.

Estimar com **alvo de variância** (a vol de longo prazo fica presa à amostral e só a dinâmica é estimada;
Engle e Mezrich, 1996) reduz os casos de 15 para 4, com perda desprezível de aderência (0,001 de
log-verossimilhança por observação) e sem mudar a calibração (seção 4.3).

### 4.2 Previsão de volatilidade fora da amostra

Walk-forward em 25 ações líquidas (dados desde 2008), a cada 5 pregões: prever a variância média dos próximos
N pregões só com dados até a data. Perda QLIKE (menor é melhor; robusta ao ruído do alvo, Patton, 2011);
"RV/F" = variância realizada média ÷ prevista média (1,00 = sem viés).

| Previsor (N = 63 pregões) | QLIKE mediana | QLIKE média | RV/F | RV/F após choque > 4σ | Vence o atual em |
|---|---|---|---|---|---|
| **GJR do projeto (atual)** | 0,210 | 0,332 | 0,87 | 0,60 | — |
| GJR com alvo de variância | 0,213 | 0,270 | 0,86 | 0,60 | 11/25 |
| GJR com alvo + vol de 252 pregões (média geométrica) | 0,205 | 0,234 | 0,96 | 0,91 | 19/25 |
| GJR com retornos limitados a ±5 desvios robustos | 0,188 | 0,247 | 0,98 | 0,88 | 20/25 |
| idem + vol de 252 pregões | 0,195 | 0,225 | 1,02 | 1,05 | 18/25 |
| Vol móvel de 252 pregões | 0,250 | 0,277 | 1,01 | 1,26 | 6/25 |
| HAR em logs (com amplitude máxima–mínima) | 0,235 | 0,277 | 1,08 | 1,20 | 8/25 |
| EWMA 0,94 | 0,276 | 0,340 | 1,01 | 0,38 | 4/25 |

Leitura:
- A família GARCH é a certa (ganha de janelas móveis, EWMA e HAR), mas o GJR atual **superestima a variância
  em 15% (3 meses) a 25% (12 meses)** e, logo depois de choques extremos, em **67%** — exatamente a situação
  de hoje. Em 126 e 252 pregões o padrão é o mesmo (RV/F de 0,83 e 0,80).
- Combinar o GARCH com a vol de 252 pregões tira o viés e reduz a perda média em ~30%.
- **Ressalva importante:** prever bem a variância não garante probabilidades melhores (seção 4.3). A variante
  de retornos limitados é a melhor nesta tabela e a pior na calibração.

### 4.3 As probabilidades acertam? (26 ações, 9.323 previsões, 2012–2026)

Mesmo teste walk-forward do painel de calibração do site, em 26 ações. "Ganho" = redução do Brier em relação
ao chute fixo (frequência histórica do evento até a data); "t" = estatística de Diebold-Mariano com erro
padrão robusto à sobreposição das janelas e à correlação entre ações (|t| > 2 ≈ significativo a 5%).

**Collar Knock In 100/106/112, 3 meses (retorno esperado = CDI):**

| Método | Lucro | > CDI | Barreira | Previsto × realizado (barreira) |
|---|---|---|---|---|
| **FHS-GJR (padrão)** | −0,2% (t 0,0) | **+2,9% (t 2,2)** | **+3,4% (t 2,4)** | 44,3% × 47,1% |
| FHS-GJR com alvo de variância | −0,4% (t −0,1) | +2,9% (t 2,2) | +3,3% (t 2,4) | 43,9% × 47,1% |
| FHS-GJR com alvo + vol de 252 pregões | −0,7% (t −0,3) | +2,9% (t 2,2) | +3,7% (t 2,5) | 43,3% × 47,1% |
| Bootstrap em blocos | −1,2% (t −0,6) | +1,9% (t 1,3) | +2,2% (t 1,7) | 42,8% × 47,1% |
| GBM | +0,3% (t 0,5) | +2,0% (t 1,7) | +3,9% (t 2,1) | 48,6% × 47,1% |
| FHS com retornos limitados (teste) | −2,0% (t −1,3) | +2,9% (t 1,8) | +1,0% (t 0,5) | 41,5% × 47,1% |
| **Média FHS + bootstrap + GBM** | 0,0% (t 0,2) | +2,6% (t 2,0) | **+3,8% (t 2,8)** | — |
| FHS-GJR com retorno esperado CDI + 5 p.p. | −0,7% (t −0,2) | +3,1% (t 2,2) | +3,6% (t 2,2) | 46,7% × 47,1% |

**Evento que só depende de vol — tocar +12% ou −12% em 3 meses (realizado: 74,1%):**

| Método | Ganho | Previsto |
|---|---|---|
| FHS-GJR (padrão) | −0,5% (t −0,8) | 73,6% |
| FHS-GJR com alvo de variância | −0,9% (t −1,0) | 73,1% |
| FHS-GJR com alvo + vol de 252 pregões | +0,6% (t 0,7) | 71,5% |
| **Bootstrap em blocos** | **+2,0% (t 3,5)** | 73,2% |
| GBM | −2,3% (t −1,5) | 83,0% |
| FHS com retornos limitados (teste) | −8,9% (t −3,9) | 68,8% |
| **Média FHS + bootstrap** | **+2,2% (t 4,2)** | — |
| **Média FHS + bootstrap + GBM** | **+2,5% (t 2,8)** | — |

Leitura:
1. **Direção não é previsível.** P(lucro) não ganha do chute fixo em nenhum método; a inclinação de calibração
   é negativa (quando o modelo diz "mais provável", acontece um pouco menos). O site já avisa isso — está
   correto e deve continuar em destaque.
2. **O ganho do FHS-GJR é real, mas pequeno e não vem só da vol.** Ele é significativo em P(> CDI) e na
   barreira do Collar KI, porém no evento de dois lados, que isola a vol, ele empata com o chute fixo e perde
   do bootstrap. As previsões do FHS são extremas demais (inclinação 0,70–0,75): quando o GARCH aponta vol
   alta, o evento acontece menos do que o previsto.
3. **Nenhum método vence sozinho nos dois eventos; a média vence.** A média simples de FHS, bootstrap e GBM
   tem ganho significativo nos dois (+3,8% e +2,5%). É o resultado clássico de combinação de previsões.
4. **O retorno esperado = CDI subestima as frequências em ~3 pontos** (lucro 54,2% × 56,6%; > CDI 47,1% ×
   50,6%; barreira 44,3% × 47,1%). Com CDI + 5 p.p. o viés some, sem ganho de Brier. O padrão neutro é
   defensável; o viés deve ser informado, e a grade de cenários já cobre a alternativa.
5. **A métrica certa para escolher o modelo é a calibração do evento, não a previsão de variância.** A
   variante de retornos limitados, a melhor em QLIKE, foi a pior aqui: ao normalizar os choques com os
   extremos incluídos, ela encolhe os movimentos típicos e subestima os toques de barreira.

### 4.4 O "IC 95%" do backtest cobre 82%–90%

Simulação: 300 "histórias" de 4.180 pregões de um GJR-GARCH com choques t (processo conhecido), estrutura
aplicada em todas as janelas, IC calculado como no projeto e conferido contra a probabilidade verdadeira.

| Estrutura (amostra efetiva) | Indicador | IC do projeto (bloco = N) | Wilson, n = 1,5 × janelas não sobrepostas |
|---|---|---|---|
| Collar KI 3m (≈ 66) | lucro | 89,7% (largura 16,5 p.p.) | 94,0% (19,0) |
| | > CDI | 88,7% (16,7) | 94,7% (19,3) |
| | barreira | 89,7% (15,8) | 97,3% (19,1) |
| FKO 6m (≈ 33) | lucro | 81,3% (12,6) | 94,7% (16,0) |
| | barreira | 81,0% (13,0) | 94,7% (16,2) |
| Proteção Total 12m (≈ 16) | > CDI | 87,3% (17,4) | 99,7% (30,9) |
| | barreira | 86,7% (30,0) | 96,0% (35,3) |

O block bootstrap percentil subestima a incerteza quando há poucos blocos, e degenera quando a frequência é
0% ou 100% ("IC 0–0%" para P(perda) — o correto seria "até ≈ 4%" com 99 observações efetivas). Aumentar o
bloco (2N, 3N) ou alargar pelo quantil t melhora pouco (83%–95%, conforme o caso). O **intervalo de Wilson com amostra efetiva
de 1,5 × n/N** fica entre 94% e 97% em 3 e 6 meses, é conservador em 12 meses, resolve o caso 0%/100% e é
mais simples de explicar e de portar para o JS (fórmula fechada, sem sorteios). No mundo real, com mudanças
de regime, a incerteza verdadeira é ainda maior que a de qualquer um dos dois.

### 4.5 A faixa de cenários de vol é estreita e mal centrada

A grade usa 0,8×, 1,0× e 1,2× a vol prevista. Distribuição histórica de (vol realizada em 63 pregões ÷ vol
prevista pelo GJR atual), 25 ações:

| Percentil | 5% | 10% | 50% | 90% | 95% |
|---|---|---|---|---|---|
| GJR atual | 0,46 | 0,57 | 0,83 | 1,21 | 1,40 |
| GJR + vol de 252 pregões | 0,64 | 0,69 | 0,91 | 1,29 | 1,49 |

A vol realizada ficou dentro de 0,8–1,2× em 46% das vezes, abaixo de 0,8× em 44% e acima de 1,2× em 11%.
A "faixa entre cenários" exibida ao lado dos indicadores do Monte Carlo cobre, portanto, menos da metade dos
desfechos de vol. Uma grade de **0,6× / 1,0× / 1,3×** (≈ percentis 10 e 90 do erro histórico) seria honesta.

### 4.6 Premissas do FHS

- **Sorteio independente dos choques: sustenta-se.** Ljung-Box (10 defasagens) rejeita independência dos z² em
  1 de 26 ações; sortear em blocos de 5 ou 10 dias muda a P(barreira) média de 54,3% para 53,7% e 53,5%.
- **Média dos caminhos: pequeno viés para baixo.** E[S_T] simulado ÷ alvo = 0,997 na média; chega a 0,969
  (MGLU3) e 0,982 (CYRE3) em ações de vol muito alta, porque a correção −½·h supõe choques normais. Um
  reescalonamento da média dos caminhos (correção martingal empírica, Duan e Simonato, 1998) elimina o desvio.
- **Assimetria do GJR:** γ > 0,01 em 50 de 94 ações; manter o GJR como padrão está justificado.

### 4.7 Outros pontos

- **Duas vols na mesma tela.** Custo teórico com a vol de 252 pregões; Monte Carlo com a do GARCH. Vale
  explicitar ou oferecer a vol do prazo como opção no modo Teórico.
- **Painel de calibração sem significância.** Ele classifica ganho acima de 2% como "o modelo foi melhor";
  com ≈ 57 períodos independentes numa única ação, um ganho de 2%–4% não se distingue de ruído.
- **Saída antecipada sem âncora empírica.** É a parte do modelo com mais premissas não testáveis com dados
  públicos; dois ou três extratos de marcação da mesa bastariam para calibrar spread e adicional de vol.
- **Métrica que falta:** "retorno médio − CDI" no Monte Carlo neutro. Com retorno esperado = CDI, esse número
  mede o custo embutido da estrutura (no exemplo padrão, com dados de 28/10/2026: +2,67% − 3,25% = −0,58% no trimestre) e é mais
  informativo para comparar estruturas do que P(lucro).

## 5. O que não mexer

- Janelas históricas com ajuste ao CDI de hoje como base empírica.
- Retorno esperado = CDI como padrão (com o viés informado).
- A ordem dos indicadores e os avisos de baixa capacidade preditiva para direção.
- A paridade Python × JS por fixtures e o gerador compartilhado.
- A família GARCH/FHS como um dos métodos — com as correções abaixo.

## 6. Recomendações, em ordem

**Prioridade 1 — corrigem erro (baixo risco, validado nos testes) — implementadas em 20/11/2026:**

1. **Filtro de dados em `scripts/build_site_data.py`.** (a) Detectar salto isolado: |retorno| > 35% num dia em
   que a mediana do mercado se moveu menos de 5%; se a razão for ≈ 2, 3, ½ ou ⅓ (ou o preço ficar parado em
   seguida), reescalar o histórico anterior; senão, marcar a ação com aviso. (b) Cortar o início do histórico
   até a fração de pregões sem variação em 252 dias cair abaixo de ~10%. (c) Publicar no `index.json` a lista
   de ações com aviso, para o site mostrar.
2. **GARCH com alvo de variância + guarda.** Prender a vol de longo prazo à amostral; se a persistência ficar
   ≥ 0,997 ou a vol de hoje passar de ~4× a amostral, avisar no painel de vol.
3. **Trocar o IC por Wilson com amostra efetiva de 1,5 × n/N** (Python e JS; remove os 1.000 sorteios).

**Prioridade 2 — tornam os números mais honestos:**

4. **Número principal do Monte Carlo = média de FHS, bootstrap e GBM**, com os três como faixa entre métodos.
5. **Grade de vol 0,6× / 1,0× / 1,3×**, rotulada como "faixa de 80% do erro histórico da previsão de vol".
6. **Painel de calibração com significância** (estatística t ou "não distinguível de zero") e texto ajustado.
7. **Vol do prazo combinada com a de 252 pregões** (média geométrica com a previsão do GARCH). Tira o viés da
   previsão de vol e, na calibração, não piora nada e melhora um pouco (barreira +3,7% contra +3,4%; evento de
   dois lados +0,6% contra −0,5%). Ganho pequeno: fazer junto com o item 2, não antes.
8. **Vol única** entre modo Teórico e Monte Carlo (ou explicação na tela).

**Prioridade 3 — evolução:**

9. Correção da média dos caminhos FHS; indicador "retorno médio − CDI".
10. Comparação lado a lado de duas estruturas (o uso que o próprio simulador recomenda).
11. Calibrar a saída antecipada com marcações reais da mesa.
12. Regenerar o guia em PDF depois das mudanças (os números citados são de 28/10/2026).

## 7. Como reproduzir

Dados: os JSON publicados em `…/estruturadas-sim/data/precos/` copiados para uma pasta (26 ações líquidas para
os testes de método; as 94 para a varredura de dados), mais `cdi.json`.

| Script | O que mede | Tempo |
|---|---|---|
| `exp4_vol.py <pasta> <saida.json>` | previsão de vol fora da amostra (QLIKE, viés, pós-choque) | ~10 min |
| `exp5_ic.py 300` | cobertura dos intervalos de confiança por simulação | ~5 min |
| `exp6_calib.py <pasta> <saida.pkl> <preset> <N> <métodos>` | calibração walk-forward com significância (`collar_ki`, `dois_lados`; `EXP_DRIFT=cdi_premio`) | ~15 min |
| `exp7_diag.py <pasta>` | premissas do FHS (resíduos, média dos caminhos, blocos) | ~3 min |
| `exp8_vol_robusta.py <pasta> <saida.pkl> <preset> <N>` | calibração com retornos limitados | ~15 min |
| `exp9_alvo_variancia.py fits\|vol\|calib\|calib252 …` | alvo de variância: ajustes degenerados, QLIKE, calibração | ~15 min |

## 8. Limites desta análise

- Os testes de método usam 26 ações líquidas, uma estrutura (Collar KI 3m) e um evento de vol; outras
  estruturas e prazos podem se comportar de outro jeito.
- A cobertura dos ICs foi medida num processo simulado estacionário; no mundo real a incerteza é maior.
- As janelas de 2012–2026 se sobrepõem e as ações andam juntas: mesmo com 9.323 previsões, há poucas dezenas
  de períodos independentes. Ganhos de 2%–4% de Brier são pequenos em termos práticos.
- Os saltos de preço foram classificados por assinatura estatística, não por conferência de fatos relevantes.
- O dia 26/10/2026 não foi conferido em fonte independente.
