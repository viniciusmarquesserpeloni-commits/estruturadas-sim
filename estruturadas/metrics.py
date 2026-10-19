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
    }
    out["media_anual"] = annualize(out["media"], res.n_days)
    out["mediana_anual"] = annualize(out["mediana"], res.n_days)
    out["acao_media_anual"] = annualize(out["acao_media"], res.n_days)
    if "retorno_cdi" in df:
        cdi = df["retorno_cdi"].to_numpy(dtype=float)
        out["p_cdi"] = float(np.mean(r > cdi + TOL))
        out["cdi_medio"] = float(np.mean(cdi))
        out["cdi_medio_anual"] = annualize(out["cdi_medio"], res.n_days)
    else:
        out["p_cdi"] = out["cdi_medio"] = out["cdi_medio_anual"] = float("nan")
    return out


_ROWS = [
    ("n", "Nº de janelas / caminhos", "int"),
    ("n_effective", "Amostra efetiva (janelas não sobrepostas)", "int"),
    ("p_lucro", "P(lucro > 0)", "pct"),
    ("p_cdi", "P(retorno > CDI do período)", "pct"),
    ("p_perda", "P(perda)", "pct"),
    ("p_zero", "P(retorno = 0)", "pct"),
    ("p_max", "P(atingir o retorno máximo)", "pct"),
    ("media", "Retorno médio", "pct"),
    ("media_anual", "Retorno médio anualizado (base 252)", "pct"),
    ("mediana", "Mediana", "pct"),
    ("p5", "Percentil 5", "pct"),
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
    ("cdi_medio", "CDI médio do período", "pct"),
    ("cdi_medio_anual", "CDI médio anualizado", "pct"),
]


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
        rows.append([_fmt(s.get(key), kind) for s in summaries.values()])
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
