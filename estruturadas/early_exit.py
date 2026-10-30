"""Saída antecipada: desmontagem da estrutura antes do vencimento quando ela rende >= X% do CDI.

Regra (padrão da mesa): quando o retorno acumulado da estrutura desde a contratação — já líquido do
spread de saída — atinge o gatilho (150% do CDI acumulado no mesmo período), o investidor é orientado a
pedir a desmontagem; com o OK dele, a estrutura é desmontada alguns pregões depois (``delay``), pelo
valor daquele dia, mesmo que tenha caído nesse meio-tempo.

Marcação a modelo de cada perna no dia k (prazo restante T = (N − k)/252):
* ação: preço do dia;
* opção sem barreira: Black-Scholes;
* opção com barreira já tocada: knock-in vira vanilla, knock-out vale zero;
* opção com barreira ainda não tocada: fórmula fechada de Reiner-Rubinstein. Com monitoramento no
  fechamento diário, a barreira é afastada do preço pela correção de Broadie-Glasserman-Kou
  (B·e^{±0,5826·σ·√Δt}), que aproxima o monitoramento discreto por uma fórmula contínua.

Volatilidade "implícita" usada na marcação (+ um adicional, padrão 3 pontos):
* GARCH (padrão): vol média prevista pelo GARCH/GJR para o prazo restante, a partir da variância
  condicional do dia (só com dados até o dia; parâmetros estimados no período inteiro). No Monte Carlo
  FHS, cada caminho usa a própria variância simulada;
* vol realizada móvel (padrão 63 pregões, só com dados até o dia);
* a mesma vol da contratação durante toda a operação.
Taxa: CDI do dia (histórico) ou CDI constante (Monte Carlo), em taxa contínua.

Calibração na contratação (padrão): o modelo raramente dá exatamente o preço pago (a mesa usa vol
implícita, skew e margem próprios; e no histórico os mesmos parâmetros em % são aplicados em épocas de
juros e vol diferentes). Calcula-se a diferença entre o preço pago e o valor do modelo no dia 0 e ela é
somada à marcação, amortizada linearmente até zerar no vencimento (quando vale o payoff). Equivale a
supor que o preço da lâmina era justo na contratação e acompanhar o mercado a partir dali.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .backtest import regime_factor
from .garch import GarchFit, fit_garch, term_vol
from .legs import Structure, returns_from_payoff
from .pricing import BGK_BETA, barrier_price, bs_price_vec

TRADING_DAYS = 252
VOL_MODE_LABELS = {"garch": "Vol GARCH do prazo restante + adicional", "rolling": "Vol realizada móvel + adicional",
                   "fixed": "Vol da contratação + adicional (fixa)"}


@dataclass
class EarlyExitConfig:
    trigger: float = 1.5  # múltiplo do CDI acumulado (1,5 = 150% do CDI)
    exit_spread: float = 0.01  # desconto sobre a marcação na desmontagem (fração do valor inicial)
    delay: int = 1  # pregões entre o gatilho e a desmontagem (OK do investidor)
    min_days: int = 0  # carência (pregões) antes de poder sair
    vol_mode: str = "garch"  # "garch" | "rolling" | "fixed"
    vol_model: str = "gjr"  # modelo do modo "garch": "gjr" | "garch"
    vol_window: int = 63  # janela da vol realizada (pregões)
    vol_add: float = 0.03  # adicional sobre a vol realizada (0,03 = 3 pontos)
    mc_paths: int = 2000  # caminhos do Monte Carlo usados na saída antecipada (subamostra)
    calibrate: bool = True  # marcação calibrada ao preço pago na contratação


@dataclass
class EarlyExitResult:
    df: pd.DataFrame  # uma linha por janela/caminho
    n_days: int
    config: EarlyExitConfig


# ---------------------------------------------------------------------------
# Séries auxiliares
# ---------------------------------------------------------------------------

def rolling_vol(close, window: int = 63) -> np.ndarray:
    """Vol realizada anualizada em cada pregão, com os ``window`` log-retornos até aquele dia
    (desvio amostral). Os primeiros dias, sem janela completa, recebem a primeira vol disponível."""
    close = np.asarray(close, dtype=float)
    lr = np.concatenate([[np.nan], np.diff(np.log(close))])
    vol = pd.Series(lr).rolling(window).std(ddof=1).to_numpy() * np.sqrt(TRADING_DAYS)
    vol = pd.Series(vol).bfill().fillna(0.30).to_numpy()
    return vol


def garch_variance(close, model: str = "gjr", fit: GarchFit | None = None):
    """(ajuste, h por pregão): h[i] = variância prevista no fechamento do pregão i para o dia seguinte.
    Devolve (None, None) se o histórico for curto demais para o GARCH (a marcação usa a vol móvel)."""
    lr = np.diff(np.log(np.asarray(close, dtype=float)))
    try:
        fit = fit or fit_garch(lr, model)
    except ValueError:
        return None, None
    return fit, fit.h if len(fit.h) == len(lr) + 1 else None


def cdi_rate_series(cdi_factor) -> np.ndarray:
    """Taxa contínua anual do CDI em cada pregão, a partir do fator acumulado: 252·ln(1 + CDI do dia)."""
    f = np.asarray(cdi_factor, dtype=float)
    if len(f) < 2:
        return np.zeros(len(f))
    d = f[1:] / f[:-1] - 1.0
    d = np.concatenate([[d[0]], d])
    return TRADING_DAYS * np.log1p(np.maximum(d, 0.0))


# ---------------------------------------------------------------------------
# Marcação a modelo
# ---------------------------------------------------------------------------

def structure_value(structure: Structure, S, run_max, run_min, T, r, sigma, monitoring: str = "close",
                    q: float = 0.0) -> np.ndarray:
    """Valor da estrutura (S0 = 1) com prazo restante T > 0. Arrays com o mesmo formato."""
    S = np.asarray(S, dtype=float)
    sigma = np.clip(np.asarray(sigma, dtype=float), 0.05, 2.0)
    shift = BGK_BETA * sigma * np.sqrt(1.0 / TRADING_DAYS) if monitoring == "close" else 0.0 * sigma
    total = np.zeros_like(S)
    for leg in structure.legs:
        if leg.kind == "stock":
            value = S
        else:
            van = bs_price_vec(leg.kind, S, leg.strike, T, r, q, sigma)
            if not leg.has_barrier:
                value = van
            else:
                B = leg.barrier_level
                up = leg.barrier_dir == "up"
                hit = (run_max >= B - 1e-12) if up else (run_min <= B + 1e-12)
                if_hit = van if leg.knock == "in" else np.zeros_like(S)
                H = B * np.exp(shift) if up else B * np.exp(-shift)
                beyond = (S >= H) if up else (S <= H)
                with np.errstate(all="ignore"):
                    alive = barrier_price(leg.kind, leg.barrier, S, leg.strike, H, T, r, q, sigma)
                value = np.where(hit | beyond, if_hit, alive)
        total = total + leg.position * leg.ratio * value
    return total


# ---------------------------------------------------------------------------
# Regra de saída
# ---------------------------------------------------------------------------

def paid_value(structure: Structure, cost: float) -> float:
    """Valor pago na contratação, na mesma escala da marcação (S0 = 1)."""
    return 1.0 + cost if structure.has_stock else cost


def initial_offset(structure: Structure, cost: float, cfg: EarlyExitConfig, N: int, rate0, sigma0,
                   monitoring: str) -> np.ndarray:
    """Diferença preço pago − valor do modelo no dia 0 (zero sem calibração)."""
    rate0 = np.atleast_1d(np.asarray(rate0, dtype=float))
    if not cfg.calibrate:
        return np.zeros_like(rate0)
    one = np.ones_like(rate0)
    v0 = structure_value(structure, one, one, one, N / TRADING_DAYS, rate0, sigma0, monitoring)
    return paid_value(structure, cost) - v0


def simulate_exit(structure: Structure, close, up, down, cdi_acc, rate, sigma, cost: float,
                  cfg: EarlyExitConfig, ret_hold, monitoring: str = "close", extra: float = 0.0,
                  rate0=None, sigma0=None) -> pd.DataFrame:
    """Aplica a regra de saída em ``n`` caminhos de ``N`` pregões.

    close, up, down: (n, N) preços relativos a S0 nos dias 1..N (``up``/``down`` = séries usadas para
    detectar toques nas barreiras de alta/baixa); cdi_acc: (n, N+1) CDI acumulado do dia 0 ao N;
    rate, sigma: (n, N) taxa contínua e vol de marcação de cada dia; ret_hold: (n,) retorno levando ao
    vencimento (já com custos adicionais); rate0, sigma0: (n,) taxa e vol do dia 0 (calibração)."""
    close = np.atleast_2d(np.asarray(close, dtype=float))
    n, N = close.shape
    run_max = np.maximum.accumulate(np.atleast_2d(up), axis=1)
    run_min = np.minimum.accumulate(np.atleast_2d(down), axis=1)
    ret = np.full((n, N), np.nan)
    offset = initial_offset(structure, cost, cfg, N, rate[:, 0] if rate0 is None else rate0,
                            sigma[:, 0] if sigma0 is None else sigma0, monitoring)
    for k in range(1, N):  # no dia N (vencimento) vale o payoff final
        c = k - 1
        value = structure_value(structure, close[:, c], run_max[:, c], run_min[:, c], (N - k) / TRADING_DAYS,
                                rate[:, c], sigma[:, c], monitoring) + offset * (N - k) / N
        ret[:, c] = returns_from_payoff(value, cost, structure.has_stock, extra) - cfg.exit_spread
    days = np.arange(1, N + 1)
    cdi_k = np.asarray(cdi_acc, dtype=float)[:, 1:]
    cond = (ret >= cfg.trigger * cdi_k) & (ret > 0) & (days[None, :] >= max(cfg.min_days, 1)) & (days[None, :] < N)
    cond = np.nan_to_num(cond, nan=False).astype(bool)
    triggered = cond.any(axis=1)
    trigger_day = np.where(triggered, cond.argmax(axis=1) + 1, 0)
    exit_day = np.where(triggered, trigger_day + cfg.delay, N)
    early = triggered & (exit_day < N)
    exit_day = np.where(early, exit_day, N)
    rows = np.arange(n)
    ret_exit = ret[rows, np.clip(exit_day - 1, 0, N - 1)]
    ret_final = np.where(early, ret_exit, np.asarray(ret_hold, dtype=float))
    cdi_period = np.asarray(cdi_acc, dtype=float)[rows, exit_day]
    return pd.DataFrame({
        "gatilho": triggered, "dia_gatilho": trigger_day, "saida_antecipada": early, "dia_saida": exit_day,
        "retorno_final": ret_final, "retorno_vencimento": np.asarray(ret_hold, dtype=float),
        "cdi_periodo": cdi_period, "dias": exit_day,
    })


def run_historical_exit(structure: Structure, prices: pd.DataFrame, n_days: int, cost: float,
                        cfg: EarlyExitConfig, cdi_factor, ret_hold, monitoring: str = "close",
                        extra: float = 0.0, cdi_ref: float | None = None,
                        regime_adjust: bool = False, garch: GarchFit | None = None) -> EarlyExitResult:
    """Saída antecipada em todas as janelas históricas (mesmas janelas de ``run_historical``).

    Com ``regime_adjust`` (e ``cdi_ref``), usa os caminhos re-ancorados no CDI de hoje e o CDI de hoje
    na régua do gatilho e na marcação — a mesma pergunta "e se eu contratasse agora?" do backtest.
    ``ret_hold`` deve vir do ``run_historical`` com o mesmo ajuste."""
    N = n_days
    close = prices["Close"].to_numpy(dtype=float)
    high = prices["High"].to_numpy(dtype=float) if "High" in prices else close
    low = prices["Low"].to_numpy(dtype=float) if "Low" in prices else close
    n = len(close) - N
    base = close[:n, None]
    S = sliding_window_view(close, N + 1)[:, 1:] / base
    if monitoring == "intraday":
        up = np.maximum(sliding_window_view(high, N + 1)[:, 1:] / base, S)
        down = np.minimum(sliding_window_view(low, N + 1)[:, 1:] / base, S)
    else:
        up = down = S
    F = np.asarray(cdi_factor, dtype=float)
    rates = cdi_rate_series(F)
    if regime_adjust and cdi_ref is not None:
        f = regime_factor(F, N, cdi_ref)[:, 1:]
        S, up, down = S * f, up * f, down * f
        k = np.arange(N + 1)
        cdi_acc = np.repeat(((1 + cdi_ref) ** (k / TRADING_DAYS) - 1)[None, :], n, axis=0)
        rate = np.full((n, N), np.log1p(cdi_ref))
        rate0 = np.full(n, np.log1p(cdi_ref))
    else:
        cdi_acc = sliding_window_view(F, N + 1) / F[:n, None] - 1.0
        rate = sliding_window_view(rates, N + 1)[:, 1:]
        rate0 = rates[:n]
    rv = rolling_vol(close, cfg.vol_window) + cfg.vol_add
    sigma0 = rv[:n]
    fit, hp = garch_variance(close, cfg.vol_model, garch) if cfg.vol_mode == "garch" else (None, None)
    if hp is not None:
        remaining = N - np.arange(1, N + 1)
        sigma = term_vol(fit, sliding_window_view(hp, N + 1)[:, 1:], remaining[None, :]) + cfg.vol_add
        sigma0 = term_vol(fit, hp[:n], N) + cfg.vol_add
    elif cfg.vol_mode == "fixed":
        sigma = np.repeat(rv[:n, None], N, axis=1)
    else:
        sigma = sliding_window_view(rv, N + 1)[:, 1:]
    df = simulate_exit(structure, S, up, down, cdi_acc, rate, sigma, cost, cfg, ret_hold, monitoring, extra,
                       rate0=rate0, sigma0=sigma0)
    df["cdi_inicio"] = np.expm1(rates[:n])  # CDI anual no início da janela (para separar por regime de juros)
    return EarlyExitResult(df, N, cfg)


def run_mc_exit(structure: Structure, paths, n_days: int, cost: float, cfg: EarlyExitConfig, ret_hold,
                sigma_hist: float, cdi_annual: float, monitoring: str = "close", extra: float = 0.0,
                high=None, low=None, var_paths=None, garch: GarchFit | None = None,
                vol_scale: float = 1.0) -> EarlyExitResult:
    """Saída antecipada nos primeiros ``cfg.mc_paths`` caminhos do Monte Carlo.

    Com máxima/mínima sorteadas (bootstrap, FHS), os toques intradiários usam esses extremos; sem elas
    (GBM), a barreira deslocada em direção ao preço. Marcação com CDI constante e vol constante (vol do
    método + adicional) ou, no FHS (``var_paths`` + ``garch``), a vol GARCH do prazo restante de cada caminho."""
    paths = np.asarray(paths, dtype=float)[: cfg.mc_paths]
    m, N = paths.shape
    if monitoring == "intraday" and high is not None and low is not None:
        # bootstrap com máxima/mínima sorteadas: toques pelos extremos do dia, sem correção BGK
        up, down = np.asarray(high, dtype=float)[:m], np.asarray(low, dtype=float)[:m]
    else:
        hit_shift = BGK_BETA * sigma_hist * np.sqrt(1.0 / TRADING_DAYS) if monitoring == "intraday" else 0.0
        up, down = paths * np.exp(hit_shift), paths * np.exp(-hit_shift)
    k = np.arange(N + 1)
    cdi_acc = np.repeat(((1 + cdi_annual) ** (k / TRADING_DAYS) - 1)[None, :], m, axis=0)
    rate = np.full((m, N), np.log1p(cdi_annual))
    sigma = np.full((m, N), sigma_hist + cfg.vol_add)
    if var_paths is not None and garch is not None and cfg.vol_mode != "fixed":
        remaining = N - np.arange(1, N + 1)
        sigma = vol_scale * term_vol(garch, np.asarray(var_paths, dtype=float)[:m], remaining[None, :]) + cfg.vol_add
    mon_mtm = "continuous" if monitoring == "intraday" else "close"
    df = simulate_exit(structure, paths, up, down, cdi_acc, rate, sigma, cost, cfg,
                       np.asarray(ret_hold, dtype=float)[:m], mon_mtm, extra, rate0=rate[:, 0],
                       sigma0=np.full(m, sigma_hist + cfg.vol_add))
    return EarlyExitResult(df, N, cfg)


@dataclass
class ExPostExit:
    dates: list  # datas dos pregões após a contratação (até o último disponível ou a apuração)
    ret: np.ndarray  # retorno de saída de cada pregão (líquido do spread); NaN no dia da apuração
    threshold: np.ndarray  # gatilho de cada pregão (múltiplo × CDI acumulado)
    trigger_date: object  # primeiro pregão em que o gatilho foi atingido (ou None)
    exit_date: object  # pregão da desmontagem (gatilho + delay) se já ocorreu (ou None)
    exit_return: float | None


def run_ex_post_exit(structure: Structure, prices: pd.DataFrame, trade_date, n_total: int, cost: float,
                     cfg: EarlyExitConfig, cdi_factor, monitoring: str = "close", extra: float = 0.0) -> ExPostExit | None:
    """Marcação diária e gatilho de saída no caminho realizado de uma operação.

    ``n_total`` = pregões da contratação até a apuração (prazo total da operação)."""
    idx = prices.index
    t0 = pd.Timestamp(trade_date).normalize()
    prior = np.flatnonzero(idx <= t0)
    if len(prior) == 0:
        return None
    i0 = int(prior[-1])
    close = prices["Close"].to_numpy(dtype=float)
    high = prices["High"].to_numpy(dtype=float)
    low = prices["Low"].to_numpy(dtype=float)
    m = min(n_total, len(close) - 1 - i0)
    if m < 1:
        return None
    s0 = close[i0]
    S = close[i0 + 1: i0 + 1 + m] / s0
    up = np.maximum(high[i0 + 1: i0 + 1 + m] / s0, S) if monitoring == "intraday" else S
    down = np.minimum(low[i0 + 1: i0 + 1 + m] / s0, S) if monitoring == "intraday" else S
    F = np.asarray(cdi_factor, dtype=float)
    cdi_acc = F[i0 + 1: i0 + 1 + m] / F[i0] - 1.0
    rate = cdi_rate_series(F)[i0 + 1: i0 + 1 + m]
    rv = rolling_vol(close, cfg.vol_window) + cfg.vol_add
    sigma = np.full(m, rv[i0]) if cfg.vol_mode == "fixed" else rv[i0 + 1: i0 + 1 + m]
    sigma0 = rv[i0]
    fit, hp = garch_variance(close, cfg.vol_model) if cfg.vol_mode == "garch" else (None, None)
    if hp is not None:
        sigma = term_vol(fit, hp[i0 + 1: i0 + 1 + m], n_total - np.arange(1, m + 1)) + cfg.vol_add
        sigma0 = float(term_vol(fit, hp[i0], n_total)) + cfg.vol_add
    run_max, run_min = np.maximum.accumulate(up), np.minimum.accumulate(down)
    offset = initial_offset(structure, cost, cfg, n_total, cdi_rate_series(F)[i0], sigma0, monitoring)[0]
    ks = np.arange(1, m + 1)
    live = ks < n_total
    ret = np.full(m, np.nan)
    if live.any():
        T = (n_total - ks[live]) / TRADING_DAYS
        value = structure_value(structure, S[live], run_max[live], run_min[live], T, rate[live], sigma[live],
                                monitoring) + offset * (n_total - ks[live]) / n_total
        ret[live] = returns_from_payoff(value, cost, structure.has_stock, extra) - cfg.exit_spread
    threshold = cfg.trigger * cdi_acc
    cond = np.nan_to_num((ret >= threshold) & (ret > 0) & (ks >= max(cfg.min_days, 1)), nan=False).astype(bool)
    dates = list(idx[i0 + 1: i0 + 1 + m])
    trig = int(np.argmax(cond)) if cond.any() else -1
    trigger_date = dates[trig] if trig >= 0 else None
    exit_date, exit_ret = None, None
    if trig >= 0:
        e = trig + cfg.delay
        if e < m and ks[e] < n_total:
            exit_date, exit_ret = dates[e], float(ret[e])
    return ExPostExit(dates, ret, threshold, trigger_date, exit_date, exit_ret)
