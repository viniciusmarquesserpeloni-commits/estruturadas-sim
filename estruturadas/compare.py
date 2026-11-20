"""Comparação lado a lado de estruturas (mesma ação, prazo e premissas; cada uma com o seu custo).

As probabilidades do simulador servem mais para comparar estruturas e dimensionar barreiras do que para prever a
direção da ação: esta tabela junta, por estrutura, o perfil no vencimento, o backtest histórico (com IC 95%) e o
Monte Carlo. O melhor valor de cada linha é marcado; quando os ICs se sobrepõem, a diferença pode ser ruído.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .formatting import fmt_num, fmt_pct
from .legs import Structure, payoff_profile_summary

MAX_ITEMS = 4

# (rótulo, origem, chave, maior_é_melhor, com_sinal) — origem "h" = histórico, "m" = Monte Carlo
ROWS = (
    ("P(lucro > 0)", "h", "p_lucro", True, False),
    ("P(retorno > CDI de hoje)", "h", "p_cdi", True, False),
    ("P(barreira acionada)", "h", "p_barreira", None, False),
    ("Retorno mediano", "h", "mediana", True, True),
    ("Retorno médio − CDI de hoje", "h", "excesso_cdi", True, True),
    ("CVaR 5% (média dos 5% piores)", "h", "cvar5", True, True),
    ("P(lucro > 0)", "m", "p_lucro", True, False),
    ("P(retorno > CDI de hoje)", "m", "p_cdi", True, False),
    ("P(barreira acionada)", "m", "p_barreira", None, False),
    ("Retorno médio − CDI de hoje", "m", "excesso_cdi", True, True),
    ("CVaR 5% (média dos 5% piores)", "m", "cvar5", True, True),
)
SECTION = {"h": "Histórico", "m": "Monte Carlo"}


@dataclass
class CompareItem:
    name: str
    structure: Structure
    cost: float
    hist: dict | None = None  # summarize() do backtest histórico
    mc: dict | None = None    # summarize() do Monte Carlo


def unique_name(name: str, existing: list[str]) -> str:
    """Evita nomes repetidos na comparação: "Collar", "Collar (2)", ..."""
    if name not in existing:
        return name
    k = 2
    while f"{name} ({k})" in existing:
        k += 1
    return f"{name} ({k})"


def best_indices(values: list[float], higher: bool | None) -> list[int]:
    """Índices com o melhor valor; empates entram juntos e nada é marcado se todos forem iguais."""
    if higher is None:
        return []
    ok = [v for v in values if v is not None and np.isfinite(v)]
    if len(ok) < 2:
        return []
    t = max(ok) if higher else min(ok)
    idx = [i for i, v in enumerate(values) if v is not None and np.isfinite(v) and abs(v - t) < 1e-9]
    return [] if len(idx) == len(ok) else idx


def compare_values(items: list[CompareItem]) -> list[tuple[str, list[float], list[int]]]:
    """Linhas numéricas: (rótulo com a seção, valores por estrutura, índices dos melhores)."""
    out = []
    for label, src, key, higher, _ in ROWS:
        vals = []
        for it in items:
            sm = it.hist if src == "h" else it.mc
            vals.append(float(sm[key]) if sm is not None and key in sm else np.nan)
        out.append((f"{SECTION[src]} · {label}", vals, best_indices(vals, higher)))
    return out


def compare_table(items: list[CompareItem], extra_cost: float = 0.0) -> pd.DataFrame:
    """Tabela formatada (pt-BR) para exibir; o melhor valor de cada linha vem marcado com ★."""
    cols = [it.name for it in items]
    rows: list[list[str]] = []

    def prof(it):
        try:
            return payoff_profile_summary(it.structure, it.cost)
        except Exception:  # noqa: BLE001 - custo inválido para a estrutura
            return None

    profs = [prof(it) for it in items]
    rows.append(["Custo das opções"] + [fmt_pct(it.cost) for it in items])
    rows.append(["Retorno máximo no vencimento"] + [
        "—" if p is None else "ilimitado" if p["gain_unlimited"] else
        fmt_pct(None if p["return_max"] is None else p["return_max"] - extra_cost) for p in profs])
    rows.append(["Pior retorno no vencimento"] + [
        "—" if p is None else "ilimitado" if p["loss_unlimited"] else
        fmt_pct(None if p["return_min"] is None else p["return_min"] - extra_cost) for p in profs])
    for (label, src, key, _, signed), (_, vals, best) in zip(ROWS, compare_values(items)):
        cells = []
        for i, (it, v) in enumerate(zip(items, vals)):
            sm = it.hist if src == "h" else it.mc
            if sm is None:
                cells.append("—")
                continue
            if not np.isfinite(v):
                cells.append("sem barreira" if key == "p_barreira" else "—")
                continue
            txt = fmt_pct(v, 2, sign=True) if signed else fmt_pct(v, 1)
            ci = (sm.get("ci") or {}).get(key) if src == "h" else None
            if ci:
                txt += f" ({fmt_num(100 * ci[0], 0)}–{fmt_num(100 * ci[1], 0)}%)"
            cells.append(("★ " if i in best else "") + txt)
        rows.append([f"{SECTION[src]} · {label}"] + cells)
    return pd.DataFrame(rows, columns=["Indicador"] + cols)
