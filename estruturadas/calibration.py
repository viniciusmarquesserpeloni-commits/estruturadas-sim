"""Painel de calibração walk-forward: as probabilidades do Monte Carlo teriam acertado no passado?

A cada ``step`` pregões (a partir de ``start`` pregões de histórico), usa **só os dados até a data t**
para estimar P(lucro), P(retorno > CDI) e P(barreira) com o método do Monte Carlo escolhido (GARCH
reestimado a cada ``refit`` pregões; entre uma estimação e outra, os mesmos parâmetros são aplicados aos
dados novos) e compara com o que aconteceu de fato na janela [t, t+N] (caminho real, CDI da época).

Régua: o "chute fixo" (climatologia) = frequência do evento nas janelas já encerradas até t. Brier =
média de (probabilidade − resultado 0/1)²; se o modelo não tiver Brier menor que o chute fixo, a
probabilidade deve ser lida como ordem de grandeza, não como previsão. Diagrama de confiabilidade:
previsões agrupadas em faixas de 10 p.p. × frequência realizada em cada faixa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import ohlc_log_returns, run_historical, run_monte_carlo
from .data import TRADING_DAYS
from .garch import filtered, fit_garch
from .legs import Structure

TOL = 1e-9
CALIB_EVENTS = [("lucro", "P(lucro > 0)"), ("cdi", "P(retorno > CDI)"), ("barreira", "P(barreira acionada)")]


@dataclass
class CalibrationResult:
    df: pd.DataFrame  # uma linha por data testada: prev_*, clim_*, real_*
    n_days: int
    step: int
    method: str
    n_paths: int
    meta: dict = field(default_factory=dict)

    def events(self) -> list[tuple[str, str]]:
        return [(k, label) for k, label in CALIB_EVENTS if f"prev_{k}" in self.df]

    def brier(self) -> pd.DataFrame:
        """Brier do modelo × do chute fixo, ganho relativo (1 − modelo/chute) e médias previstas × realizadas."""
        rows = []
        for k, label in self.events():
            y = self.df[f"real_{k}"].to_numpy(dtype=float)
            p = self.df[f"prev_{k}"].to_numpy(dtype=float)
            c = self.df[f"clim_{k}"].to_numpy(dtype=float)
            bm, bc = float(np.mean((p - y) ** 2)), float(np.mean((c - y) ** 2))
            rows.append({"indicador": label, "chave": k, "brier_modelo": bm, "brier_chute": bc,
                         "ganho": 1.0 - bm / bc if bc > 0 else float("nan"),
                         "prev_media": float(p.mean()), "chute_medio": float(c.mean()), "real": float(y.mean()),
                         "n": len(y)})
        return pd.DataFrame(rows)

    def reliability(self, key: str, bins: int = 10) -> pd.DataFrame:
        """Previsões agrupadas em faixas iguais de probabilidade: média prevista × frequência realizada."""
        p = self.df[f"prev_{key}"].to_numpy(dtype=float)
        y = self.df[f"real_{key}"].to_numpy(dtype=float)
        b = np.minimum((p * bins).astype(int), bins - 1)
        rows = []
        for i in range(bins):
            m = b == i
            if m.any():
                rows.append({"faixa": f"{i * 100 // bins}–{(i + 1) * 100 // bins}%", "prev_media": float(p[m].mean()),
                             "real": float(y[m].mean()), "n": int(m.sum())})
        return pd.DataFrame(rows)


def walk_forward(structure: Structure, prices: pd.DataFrame, n_days: int, cost: float, method: str = "fhs_garch",
                 step: int = 10, start: int = 504, n_paths: int = 1000, cdi_factor=None, cdi_annual: float = 0.10,
                 monitoring: str = "close", extra_cost: float = 0.0, block: int = 20, seed: int = 42,
                 drift: str = "cdi", premium: float = 0.05, vol_model: str = "gjr", refit: int = 252,
                 progress=None) -> CalibrationResult:
    """Teste walk-forward da estrutura escolhida (ver docstring do módulo).

    ``cdi_factor``: CDI acumulado alinhado a ``prices`` (régua realizada e CDI de cada data); sem ele, usa
    ``cdi_annual`` constante. ``progress(fração)`` é chamado a cada data."""
    N = n_days
    n = len(prices)
    start = max(start, N + 252)
    dates = list(range(start, n - N, step))
    if not dates:
        raise ValueError(f"Histórico insuficiente para a calibração: são necessários mais de {start + N} pregões.")
    hist = run_historical(structure, prices, N, cost, monitoring, extra_cost, cdi_factor=cdi_factor)
    d = hist.df
    has_bar = bool(structure.events)
    real = {"lucro": (d["retorno"] > TOL).to_numpy(dtype=float)}
    if "retorno_cdi" in d:
        real["cdi"] = (d["retorno"] > d["retorno_cdi"] + TOL).to_numpy(dtype=float)
    else:
        real["cdi"] = (d["retorno"] > (1 + cdi_annual) ** (N / TRADING_DAYS) - 1 + TOL).to_numpy(dtype=float)
    if has_bar:
        real["barreira"] = d["barreira_qualquer"].to_numpy(dtype=float)
    csum = {k: np.concatenate([[0.0], np.cumsum(v)]) for k, v in real.items()}
    F = None if cdi_factor is None else np.asarray(cdi_factor, dtype=float)
    lr_all, up_all, dn_all = ohlc_log_returns(prices)
    fit, fit_t = None, -10**9
    rows = []
    for j, t in enumerate(dates):
        sub = prices.iloc[: t + 1]
        rate = cdi_annual if F is None else float((F[t] / F[t - 1]) ** TRADING_DAYS - 1)
        garch = None
        if method == "fhs_garch":
            lr, up, dn = lr_all[:t], up_all[:t], dn_all[:t]
            if fit is None or t - fit_t >= refit:
                fit, fit_t = fit_garch(lr, vol_model, up, dn), t
                garch = fit
            else:
                garch = filtered(lr, fit.omega, fit.alpha, fit.gamma, fit.beta, vol_model, up, dn)
        r = run_monte_carlo(structure, sub, N, cost, method, n_paths, block, drift, rate, seed, monitoring, extra_cost,
                            premium=premium, vol_model=vol_model, garch=garch)
        md = r.df
        closed = t - N + 1  # janelas iniciadas em 0..t−N já terminaram até t
        row = {"data": prices.index[t], "cdi_ref": rate, "vol": r.meta["sigma"],
               "prev_lucro": float((md["retorno"] > TOL).mean()),
               "prev_cdi": float((md["retorno"] > md["retorno_cdi_hoje"] + TOL).mean())}
        if has_bar:
            row["prev_barreira"] = float(md["barreira_qualquer"].mean())
        for k in real:
            row[f"clim_{k}"] = csum[k][closed] / closed
            row[f"real_{k}"] = real[k][t]
        rows.append(row)
        if progress:
            progress((j + 1) / len(dates))
    return CalibrationResult(pd.DataFrame(rows), N, step, method, n_paths,
                             {"start": start, "refit": refit, "vol_model": vol_model, "drift": drift, "seed": seed})
