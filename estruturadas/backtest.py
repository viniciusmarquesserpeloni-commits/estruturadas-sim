"""Backtest: janelas históricas móveis, Monte Carlo (bootstrap/GBM) e modo ex-post."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .data import TRADING_DAYS, previous_business_day
from .legs import (Evaluation, Structure, event_label, evaluate_paths, first_hit_index,
                   payoff_profile_summary, returns_from_payoff)
from .pricing import BGK_BETA, gbm_paths

DRIFT_LABELS = {"historico": "Histórico", "zero": "Zero", "cdi": "CDI"}
MC_METHOD_LABELS = {"bootstrap": "Bootstrap em blocos", "gbm": "GBM (log-normal)"}
EXIT_PATHS = 2000  # caminhos guardados para a simulação da saída antecipada


@dataclass
class BacktestResult:
    df: pd.DataFrame  # uma linha por janela/caminho
    event_cols: dict  # rótulo da barreira -> nome da coluna em df
    n_days: int
    n_effective: int  # nº de janelas não sobrepostas
    return_max: float | None
    kind: str  # "historico" ou "mc"
    meta: dict = field(default_factory=dict)


@dataclass
class Windows:
    start_dates: pd.DatetimeIndex
    end_dates: pd.DatetimeIndex
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray


def historical_windows(prices: pd.DataFrame, n_days: int) -> Windows:
    """Para cada data inicial t com N pregões à frente: caminho = P[t+1 : t+N] / P[t]."""
    if n_days < 1:
        raise ValueError("O prazo deve ter pelo menos 1 pregão.")
    close = prices["Close"].to_numpy(dtype=float)
    if len(close) <= n_days:
        raise ValueError(f"Histórico insuficiente: {len(close)} pregões para um prazo de {n_days}.")
    high = prices["High"].to_numpy(dtype=float) if "High" in prices else close
    low = prices["Low"].to_numpy(dtype=float) if "Low" in prices else close
    wc = sliding_window_view(close, n_days + 1)
    base = wc[:, :1]
    return Windows(
        start_dates=prices.index[: len(wc)],
        end_dates=prices.index[n_days:],
        close=wc[:, 1:] / base,
        high=sliding_window_view(high, n_days + 1)[:, 1:] / base,
        low=sliding_window_view(low, n_days + 1)[:, 1:] / base,
    )


def _event_columns(structure: Structure) -> dict:
    return {event_label(ev): f"barreira_{i + 1}" for i, ev in enumerate(structure.events)}


def _return_max(structure: Structure, cost: float, extra_cost: float) -> float | None:
    try:
        rmax = payoff_profile_summary(structure, cost)["return_max"]
    except ValueError:
        return None
    return None if rmax is None else rmax - extra_cost


def _results_frame(structure: Structure, ev: Evaluation, cost: float, extra_cost: float) -> pd.DataFrame:
    df = pd.DataFrame({
        "acao_final": ev.s_T,
        "valor_final": ev.payoff,
        "retorno": returns_from_payoff(ev.payoff, cost, structure.has_stock, extra_cost),
        "retorno_acao": ev.s_T - 1.0,
    })
    for i, evnt in enumerate(structure.events):
        df[f"barreira_{i + 1}"] = ev.hits[evnt]
    df["barreira_qualquer"] = ev.any_hit
    return df


def run_historical(structure: Structure, prices: pd.DataFrame, n_days: int, cost: float,
                   monitoring: str = "close", extra_cost: float = 0.0,
                   cdi_factor: np.ndarray | None = None) -> BacktestResult:
    """Aplica a estrutura (mesmos parâmetros em %) em todas as janelas históricas.

    ``cdi_factor``: fator acumulado do CDI alinhado ao índice de ``prices``."""
    w = historical_windows(prices, n_days)
    ev = evaluate_paths(structure, w.close, w.high, w.low, monitoring)
    df = _results_frame(structure, ev, cost, extra_cost)
    df.insert(0, "data_inicio", w.start_dates)
    df.insert(1, "data_fim", w.end_dates)
    if cdi_factor is not None:
        cf = np.asarray(cdi_factor, dtype=float)
        df["retorno_cdi"] = cf[n_days:] / cf[: len(cf) - n_days] - 1.0
    n = len(df)
    return BacktestResult(df, _event_columns(structure), n_days, int(np.ceil(n / n_days)),
                          _return_max(structure, cost, extra_cost), "historico",
                          {"monitoring": monitoring})


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def log_returns(prices: pd.DataFrame) -> np.ndarray:
    lr = np.diff(np.log(prices["Close"].to_numpy(dtype=float)))
    return lr[np.isfinite(lr)]


def block_bootstrap_paths(lr: np.ndarray, n_paths: int, n_days: int, block: int = 20,
                          seed: int = 42) -> np.ndarray:
    """Bootstrap circular em blocos dos log-retornos diários: preserva parte da
    autocorrelação e da aglomeração de volatilidade."""
    if len(lr) < 2:
        raise ValueError("Histórico insuficiente para o bootstrap.")
    block = int(max(1, min(block, len(lr))))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n_days / block))
    starts = rng.integers(0, len(lr), size=(n_paths, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % len(lr)
    sampled = lr[idx.reshape(n_paths, n_blocks * block)[:, :n_days]]
    return np.exp(np.cumsum(sampled, axis=1))


def gbm_drift_daily(lr: np.ndarray, sigma: float, drift: str, cdi_annual: float) -> float:
    """Drift logarítmico diário do GBM.

    * historico: média dos log-retornos diários históricos;
    * zero: retorno esperado aritmético zero (log-drift = −σ²/2);
    * cdi: retorno esperado aritmético igual ao CDI."""
    dt = 1.0 / TRADING_DAYS
    if drift == "historico":
        return float(np.mean(lr))
    if drift == "zero":
        return -0.5 * sigma**2 * dt
    if drift == "cdi":
        return (np.log1p(cdi_annual) - 0.5 * sigma**2) * dt
    raise ValueError(f"Drift inválido: {drift}")


def run_monte_carlo(structure: Structure, prices: pd.DataFrame, n_days: int, cost: float,
                    method: str = "bootstrap", n_paths: int = 10_000, block: int = 20,
                    drift: str = "historico", cdi_annual: float = 0.10, seed: int = 42,
                    monitoring: str = "close", extra_cost: float = 0.0,
                    vol_window: int | None = None) -> BacktestResult:
    """Simula caminhos a partir do histórico e aplica a estrutura.

    No MC só há fechamentos; com monitoramento intradiário aplica-se a correção
    de Broadie-Glasserman-Kou (barreira deslocada em 0,5826·σ·√Δt)."""
    lr = log_returns(prices)
    sigma = float(np.std(lr[-vol_window:] if vol_window else lr, ddof=1) * np.sqrt(TRADING_DAYS))
    if method == "bootstrap":
        paths = block_bootstrap_paths(lr, n_paths, n_days, block, seed)
    elif method == "gbm":
        mu = gbm_drift_daily(lr, sigma, drift, cdi_annual)
        paths = gbm_paths(n_paths, n_days, sigma, mu, seed, antithetic=True)
    else:
        raise ValueError(f"Método inválido: {method}")
    shift = BGK_BETA * sigma * np.sqrt(1.0 / TRADING_DAYS) if monitoring == "intraday" else 0.0
    ev = evaluate_paths(structure, paths, monitoring="close", barrier_shift=shift)
    df = _results_frame(structure, ev, cost, extra_cost)
    df["retorno_cdi"] = (1 + cdi_annual) ** (n_days / TRADING_DAYS) - 1
    meta = {"method": method, "sigma": sigma, "drift": drift, "block": block, "seed": seed,
            "monitoring": monitoring, "paths_sample": paths[: min(200, len(paths))],
            "paths_exit": paths[: min(EXIT_PATHS, len(paths))]}
    return BacktestResult(df, _event_columns(structure), n_days, len(df),
                          _return_max(structure, cost, extra_cost), "mc", meta)


# ---------------------------------------------------------------------------
# Ex-post
# ---------------------------------------------------------------------------

@dataclass
class ExPostResult:
    trade_date: pd.Timestamp  # pregão usado como data de contratação (valor inicial)
    obs_date: pd.Timestamp  # data de apuração prevista (D−1 do vencimento)
    expiry_date: pd.Timestamp
    last_date: pd.Timestamp  # último pregão usado
    finished: bool
    s0_price: float
    n_days_elapsed: int
    path: pd.DataFrame  # data, preço, nível (% de S0), máxima/mínima relativas
    payoff: float
    retorno: float
    retorno_acao: float
    hits: dict  # rótulo -> (tocou?, data do primeiro toque ou None)


def run_ex_post(structure: Structure, prices: pd.DataFrame, trade_date, expiry_date, cost: float,
                monitoring: str = "close", extra_cost: float = 0.0) -> ExPostResult:
    """Aplica a estrutura no caminho realizado entre a contratação e a apuração.

    Se o vencimento ainda não chegou, devolve a marcação intrínseca "até hoje":
    o payoff como se a apuração fosse no último pregão disponível, com o status
    das barreiras até então (NÃO é o valor de mercado da estrutura)."""
    idx = prices.index
    t0 = pd.Timestamp(trade_date).normalize()
    expiry = pd.Timestamp(expiry_date).normalize()
    if expiry <= t0:
        raise ValueError("O vencimento deve ser posterior à data de contratação.")
    prior = idx[idx <= t0]
    if len(prior) == 0:
        raise ValueError("Não há preço na data de contratação (ou antes dela) no histórico carregado.")
    t0_used = prior[-1]
    obs = previous_business_day(expiry, idx)
    after = prices.loc[(idx > t0_used) & (idx <= obs)]
    if after.empty:
        raise ValueError("Ainda não há pregões após a data de contratação no histórico carregado.")
    finished = after.index[-1] >= obs
    s0 = float(prices.loc[t0_used, "Close"])
    rel = after[["Close", "High", "Low"]].to_numpy(dtype=float) / s0
    close, high, low = rel[:, 0], rel[:, 1], rel[:, 2]
    ev = evaluate_paths(structure, close[None, :], high[None, :], low[None, :], monitoring)
    payoff = float(ev.payoff[0])
    hits = {}
    for evnt in structure.events:
        i = first_hit_index(close, evnt, high, low, monitoring)
        hits[event_label(evnt)] = (i >= 0, after.index[i] if i >= 0 else None)
    path = pd.DataFrame({"preco": after["Close"].to_numpy(), "nivel": close,
                         "maxima": high, "minima": low}, index=after.index)
    path.loc[t0_used] = [s0, 1.0, 1.0, 1.0]
    path = path.sort_index()
    return ExPostResult(
        trade_date=t0_used, obs_date=obs, expiry_date=expiry, last_date=after.index[-1],
        finished=bool(finished), s0_price=s0, n_days_elapsed=len(after), path=path, payoff=payoff,
        retorno=float(returns_from_payoff(payoff, cost, structure.has_stock, extra_cost)),
        retorno_acao=float(close[-1] - 1.0), hits=hits,
    )
