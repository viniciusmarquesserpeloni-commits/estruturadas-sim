"""Estatísticas dos resultados e tabelas para exibição."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .backtest import BacktestResult
from .formatting import fmt_num, fmt_pct
from .legs import Structure, expiry_payoff, returns_from_payoff

TOL = 1e-9
TRADING_DAYS = 252
Z95 = 1.959963984540054  # quantil 97,5% da normal
EFFECTIVE_FACTOR = 1.5  # amostra efetiva das janelas sobrepostas = 1,5 × janelas não sobrepostas


def effective_sample(n: int, n_days: int) -> float:
    """Amostra efetiva de ``n`` janelas sobrepostas de ``n_days`` pregões para o intervalo de confiança:
    1,5 × n/N. Janelas vizinhas compartilham quase todos os dias; n/N são as janelas não sobrepostas, e as
    sobrepostas acrescentam alguma informação. O fator 1,5 foi calibrado por simulação (processo GARCH
    conhecido, prazos de 3, 6 e 12 meses): com ele o intervalo de Wilson cobre 94%–97% (ver
    docs/ANALISE_CRITICA_2026-11.md); o block bootstrap usado antes cobria 82%–90%."""
    return max(1.0, EFFECTIVE_FACTOR * n / max(1, n_days))


def wilson_ci(p: float, n_eff: float, z: float = Z95) -> tuple[float, float]:
    """Intervalo de Wilson para uma proporção ``p`` medida em ``n_eff`` observações independentes. Ao
    contrário do intervalo normal, nunca sai de [0, 1] e não degenera quando p = 0 ou 1 (com p = 0, o
    limite superior é z²/(n + z²): "nunca aconteceu" não vira "0–0%")."""
    if not (n_eff > 0) or p != p:
        return float("nan"), float("nan")
    den = 1.0 + z * z / n_eff
    center = (p + z * z / (2.0 * n_eff)) / den
    half = z * math.sqrt(p * (1.0 - p) / n_eff + z * z / (4.0 * n_eff * n_eff)) / den
    return max(0.0, center - half), min(1.0, center + half)


def cvar(r, q: float = 0.05) -> float:
    """CVaR (expected shortfall): média dos ``q`` piores resultados (pelo menos um)."""
    s = np.sort(np.asarray(r, dtype=float))
    k = max(1, int(math.ceil(q * len(s))))
    return float(s[:k].mean())


def annualize(r: float, n_days: int) -> float:
    if r is None or not np.isfinite(r) or r <= -1:
        return float("nan")
    return (1 + r) ** (TRADING_DAYS / n_days) - 1


def summarize(res: BacktestResult) -> dict:
    """Métricas de um backtest (histórico ou MC). Valores numéricos (frações)."""
    df = res.df
    r = df["retorno"].to_numpy(dtype=float)
    stock = df["retorno_acao"].to_numpy(dtype=float)
    out: dict = {
        "n": len(r),
        "n_effective": res.n_effective,
        "p_lucro": float(np.mean(r > TOL)),
        "p_perda": float(np.mean(r < -TOL)),
        "p_zero": float(np.mean(np.abs(r) <= TOL)),
        "p_max": float(np.mean(r >= res.return_max - 1e-6)) if res.return_max is not None else float("nan"),
        "media": float(np.mean(r)),
        "mediana": float(np.median(r)),
        "p5": float(np.percentile(r, 5)),
        "p25": float(np.percentile(r, 25)),
        "p75": float(np.percentile(r, 75)),
        "p95": float(np.percentile(r, 95)),
        "pior": float(np.min(r)),
        "melhor": float(np.max(r)),
        "acao_media": float(np.mean(stock)),
        "acao_mediana": float(np.median(stock)),
        "acao_p_lucro": float(np.mean(stock > TOL)),
        "p_bate_acao": float(np.mean(r > stock + TOL)),
        "barreiras": {lbl: float(df[col].mean()) for lbl, col in res.event_cols.items()},
        "cvar5": cvar(r, 0.05),
    }
    hit = df["barreira_qualquer"].to_numpy(dtype=bool)
    out["p_barreira"] = float(hit.mean()) if res.event_cols else float("nan")
    out["media_anual"] = annualize(out["media"], res.n_days)
    out["mediana_anual"] = annualize(out["mediana"], res.n_days)
    out["acao_media_anual"] = annualize(out["acao_media"], res.n_days)
    # régua do CDI: de hoje (padrão) e da época de cada janela (secundária, só no histórico)
    ref = df["retorno_cdi_hoje"] if "retorno_cdi_hoje" in df else df.get("retorno_cdi")
    out["p_cdi"] = float(np.mean(r > ref.to_numpy(dtype=float) + TOL)) if ref is not None else float("nan")
    out["cdi_hoje"] = float(ref.iloc[0]) if ref is not None and "retorno_cdi_hoje" in df else float("nan")
    # retorno médio − CDI de hoje no prazo: com retorno esperado = CDI (Monte Carlo neutro), mede o custo embutido
    # da estrutura — o quanto ela rende, em média, abaixo (ou acima) do CDI
    out["excesso_cdi"] = out["media"] - out["cdi_hoje"] if np.isfinite(out["cdi_hoje"]) else float("nan")
    if "retorno_cdi" in df and res.kind == "historico":
        era = df["retorno_cdi"].to_numpy(dtype=float)
        base = df["retorno_sem_ajuste"].to_numpy(dtype=float) if "retorno_sem_ajuste" in df else r
        out["p_cdi_epoca"] = float(np.mean(base > era + TOL))
        out["cdi_medio"] = float(np.mean(era))
        out["cdi_medio_anual"] = annualize(out["cdi_medio"], res.n_days)
    else:
        out["p_cdi_epoca"] = out["cdi_medio"] = out["cdi_medio_anual"] = float("nan")
    out["ci"] = {}
    if res.kind == "historico":
        inds = {"p_lucro": r > TOL, "p_perda": r < -TOL}
        if ref is not None:
            inds["p_cdi"] = r > ref.to_numpy(dtype=float) + TOL
        if res.event_cols:
            inds["p_barreira"] = hit
        n_eff = effective_sample(len(r), res.n_days)
        out["ci"] = {k: wilson_ci(float(np.mean(v)), n_eff) for k, v in inds.items()}
        out["n_ef_ic"] = n_eff
    return out


_ROWS = [
    ("n", "Nº de janelas / caminhos", "int"),
    ("n_effective", "Amostra efetiva (janelas não sobrepostas)", "int"),
    ("p_lucro", "P(lucro > 0)", "pct"),
    ("p_cdi", "P(retorno > CDI de hoje)", "pct"),
    ("p_barreira", "P(barreira acionada)", "pct"),
    ("p_perda", "P(perda)", "pct"),
    ("p_cdi_epoca", "P(retorno > CDI da época)", "pct"),
    ("p_zero", "P(retorno = 0)", "pct"),
    ("p_max", "P(atingir o retorno máximo)", "pct"),
    ("media", "Retorno médio", "pct"),
    ("media_anual", "Retorno médio anualizado (base 252)", "pct"),
    ("excesso_cdi", "Retorno médio − CDI de hoje (no prazo)", "pct"),
    ("mediana", "Mediana", "pct"),
    ("p5", "Percentil 5", "pct"),
    ("cvar5", "CVaR 5% (média dos 5% piores)", "pct"),
    ("p25", "Percentil 25", "pct"),
    ("p75", "Percentil 75", "pct"),
    ("p95", "Percentil 95", "pct"),
    ("pior", "Pior", "pct"),
    ("melhor", "Melhor", "pct"),
    ("acao_media", "Só a ação: retorno médio", "pct"),
    ("acao_media_anual", "Só a ação: retorno médio anualizado", "pct"),
    ("acao_mediana", "Só a ação: mediana", "pct"),
    ("acao_p_lucro", "Só a ação: P(lucro > 0)", "pct"),
    ("p_bate_acao", "P(estrutura > só a ação)", "pct"),
    ("cdi_hoje", "CDI de hoje no prazo", "pct"),
    ("cdi_medio", "CDI médio da época (janelas)", "pct"),
    ("cdi_medio_anual", "CDI médio da época, anualizado", "pct"),
]


def fmt_ci(v, ci) -> str:
    """'56,0% (IC 48–64%)'."""
    if ci is None or not all(math.isfinite(x) for x in ci):
        return _fmt(v, "pct")
    return f"{fmt_pct(v, 1)} (IC {fmt_num(100 * ci[0], 0)}–{fmt_num(100 * ci[1], 0)}%)"


def _fmt(v, kind: str) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return fmt_num(v, 0) if kind == "int" else fmt_pct(v)


def comparison_table(summaries: dict[str, dict]) -> pd.DataFrame:
    """Tabela lado a lado (linhas = métricas, colunas = métodos), já formatada."""
    labels = []
    for s in summaries.values():
        for lbl in s.get("barreiras", {}):
            if lbl not in labels:
                labels.append(lbl)
    rows, index = [], []
    for key, name, kind in _ROWS:
        index.append(name)
        rows.append([fmt_ci(s.get(key), s.get("ci", {}).get(key)) if key in s.get("ci", {}) else _fmt(s.get(key), kind)
                     for s in summaries.values()])
        if key == "p_max":
            for lbl in labels:
                index.append(f"Barreira acionada ({lbl})")
                rows.append([_fmt(s.get("barreiras", {}).get(lbl), "pct") for s in summaries.values()])
    return pd.DataFrame(rows, index=index, columns=list(summaries.keys()))


# ---------------------------------------------------------------------------
# Quadro de rentabilidade no vencimento (formato das lâminas)
# ---------------------------------------------------------------------------

def default_variations(structure: Structure) -> list[float]:
    vs = {-0.30, -0.20, -0.10, 0.0, 0.10, 0.20, 0.30}
    for k in structure.strikes:
        vs.add(math.floor(round(100 * (k - 1), 6)) / 100)
    for direction, level in structure.events:
        if direction == "up":
            edge = math.floor(round(100 * (level - 1), 6)) / 100
            vs.update({edge, edge + 0.10})
        else:
            edge = math.ceil(round(100 * (level - 1), 6)) / 100
            vs.update({edge, edge - 0.10})
    return sorted(round(v, 4) for v in vs if -0.95 <= v <= 3.0)


def profitability_table(structure: Structure, cost: float, variations, extra_cost: float = 0.0,
                        formatted: bool = True) -> pd.DataFrame:
    v = np.asarray(sorted(variations), dtype=float)
    s_T = 1 + v
    cols = {"Variação da ação": v}
    branches = [("none", "Barreira não atingida"), ("all", "Barreira atingida")] if structure.events \
        else [("none", "Retorno da estrutura")]
    for b, name in branches:
        p = expiry_payoff(structure, s_T, b)
        cols[name] = np.where(np.isfinite(p), returns_from_payoff(np.nan_to_num(p), cost, structure.has_stock,
                                                                  extra_cost), np.nan)
    df = pd.DataFrame(cols)
    if formatted:
        for c in df.columns:
            sign = c == "Variação da ação"
            df[c] = [fmt_pct(x, 2, sign=sign) if np.isfinite(x) else "—" for x in df[c]]
    return df


# ---------------------------------------------------------------------------
# Saída antecipada
# ---------------------------------------------------------------------------

def summarize_exit(res) -> dict:
    """Métricas da estratégia "sair quando bater o gatilho" × "levar até o vencimento".

    ``res`` = EarlyExitResult. Prazos diferentes por janela: retornos comparados ao CDI do período
    efetivamente investido e anualizados pelo prazo de cada janela."""
    df, N = res.df, res.n_days
    r = df["retorno_final"].to_numpy(dtype=float)
    hold = df["retorno_vencimento"].to_numpy(dtype=float)
    days = df["dias"].to_numpy(dtype=float)
    cdi = df["cdi_periodo"].to_numpy(dtype=float)
    early = df["saida_antecipada"].to_numpy(dtype=bool)
    exit_days = df.loc[early, "dia_saida"].to_numpy(dtype=float)
    ann = (1 + r) ** (TRADING_DAYS / days) - 1
    with np.errstate(divide="ignore", invalid="ignore"):
        pct_cdi = np.where(cdi > 0, r / cdi, np.nan)
    q = np.percentile(exit_days, [25, 50, 75]) if early.any() else [np.nan] * 3
    ci = {"p_saida": wilson_ci(float(early.mean()), effective_sample(len(df), N))} if "cdi_inicio" in df else {}
    return {
        "ci": ci, "cvar5": cvar(r, 0.05),
        "n": len(r),
        "p_gatilho": float(df["gatilho"].mean()),
        "p_saida": float(early.mean()),
        "dias_p25": float(q[0]), "dias_mediana": float(q[1]), "dias_p75": float(q[2]),
        "ret_saida_media": float(r[early].mean()) if early.any() else float("nan"),
        "media": float(np.mean(r)), "mediana": float(np.median(r)),
        "media_venc": float(np.mean(hold)),
        "p_lucro": float(np.mean(r > TOL)), "p_perda": float(np.mean(r < -TOL)),
        "p_cdi": float(np.mean(r > cdi + TOL)),
        "pct_cdi_mediana": float(np.nanmedian(pct_cdi)),
        "anual_mediana": float(np.median(ann)),
        "dias_medio": float(np.mean(days)),
    }


_EXIT_ROWS = [
    ("p_gatilho", "P(gatilho atingido)", "pct"),
    ("p_saida", "P(saída antes do vencimento)", "pct"),
    ("dias_mediana", "Dia mediano da saída (pregões)", "int"),
    ("dias_medio", "Prazo médio investido (pregões)", "int"),
    ("ret_saida_media", "Retorno médio nas saídas antecipadas", "pct"),
    ("media", "Retorno médio (com saída)", "pct"),
    ("media_venc", "Retorno médio levando ao vencimento", "pct"),
    ("mediana", "Retorno mediano (com saída)", "pct"),
    ("anual_mediana", "Retorno anualizado mediano (com saída)", "pct"),
    ("p_lucro", "P(lucro > 0) com saída", "pct"),
    ("p_perda", "P(perda) com saída", "pct"),
    ("p_cdi", "P(retorno > CDI do período investido)", "pct"),
    ("pct_cdi_mediana", "% do CDI mediano (período investido)", "pct"),
]


def exit_table(summaries: dict[str, dict]) -> pd.DataFrame:
    rows = [[_fmt(s.get(k), kind) for s in summaries.values()] for k, _, kind in _EXIT_ROWS]
    return pd.DataFrame(rows, index=[name for _, name, _ in _EXIT_ROWS], columns=list(summaries.keys()))


CDI_REGIMES = [(0.0, 0.08, "CDI até 8% a.a."), (0.08, 0.12, "CDI entre 8% e 12% a.a."), (0.12, 1.0, "CDI acima de 12% a.a.")]


def exit_by_cdi_regime(res) -> pd.DataFrame:
    """Saída antecipada nas janelas históricas agrupadas pelo CDI no início da janela: o nível de juros
    muda o valor da estrutura e a régua de 150% do CDI, então a média geral mistura cenários diferentes."""
    df = res.df
    rows = []
    for lo, hi, label in CDI_REGIMES:
        sel = df[(df["cdi_inicio"] > lo) & (df["cdi_inicio"] <= hi)]
        if sel.empty:
            continue
        early = sel["saida_antecipada"]
        rows.append({
            "Juros no início": label, "Janelas": len(sel),
            "P(saída antecipada)": float(early.mean()),
            "Dia mediano da saída": float(sel.loc[early, "dia_saida"].median()) if early.any() else float("nan"),
            "P(> CDI) com saída": float((sel["retorno_final"] > sel["cdi_periodo"] + TOL).mean()),
            "Retorno médio com saída": float(sel["retorno_final"].mean()),
            "Retorno médio no vencimento": float(sel["retorno_vencimento"].mean()),
        })
    return pd.DataFrame(rows)
