"""Precificação teórica (modo "Teórico").

* Vanilla: Black-Scholes-Merton fechado.
* Barreiras: Monte Carlo neutro ao risco (GBM), passos diários (252/ano),
  variáveis antitéticas e seed fixa (números aleatórios comuns entre pernas e
  entre iterações do solver).
* Solver de custo zero: ``scipy.optimize.brentq`` sobre um parâmetro de uma perna.

Taxas: ``r`` e ``q`` são taxas contínuas ao ano. Para converter a Selic/CDI
(taxa efetiva anual, base 252) use :func:`annual_to_continuous`.
Preços são em fração de S0 (S0 = 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from .legs import Leg, Structure, leg_active, leg_payoff, event_hits, PathSummary, summarize_paths

TRADING_DAYS = 252
BGK_BETA = 0.5826  # constante de Broadie-Glasserman-Kou


def annual_to_continuous(rate_annual: float) -> float:
    return float(np.log1p(rate_annual))


# ---------------------------------------------------------------------------
# Black-Scholes-Merton
# ---------------------------------------------------------------------------

def bs_price(kind: str, S, K, T, r: float, q: float, sigma: float):
    """Preço de call/put europeia (vetorizado)."""
    S, K, T = (np.asarray(x, dtype=float) for x in (S, K, T))
    if kind not in ("call", "put"):
        raise ValueError("kind deve ser 'call' ou 'put'")
    df_r, df_q = np.exp(-r * T), np.exp(-q * T)
    if sigma <= 0 or np.all(T <= 0):
        fwd = S * df_q / np.where(df_r > 0, df_r, 1)
        intrinsic = np.maximum(fwd - K, 0) if kind == "call" else np.maximum(K - fwd, 0)
        return df_r * intrinsic
    sqrtT = np.sqrt(np.maximum(T, 1e-16))
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    if kind == "call":
        return S * df_q * norm.cdf(d1) - K * df_r * norm.cdf(d2)
    return K * df_r * norm.cdf(-d2) - S * df_q * norm.cdf(-d1)


# ---------------------------------------------------------------------------
# Geração de caminhos
# ---------------------------------------------------------------------------

def gbm_paths(n_paths: int, n_days: int, sigma: float, log_drift_daily: float,
              seed: int = 42, antithetic: bool = True) -> np.ndarray:
    """Caminhos GBM normalizados (S0 = 1), matriz (n_caminhos × n_dias).

    Com ``antithetic=True`` a segunda metade dos caminhos usa −Z da primeira.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / TRADING_DAYS
    if antithetic:
        half = (n_paths + 1) // 2
        z = rng.standard_normal((half, n_days))
        z = np.vstack([z, -z])[:n_paths]
    else:
        z = rng.standard_normal((n_paths, n_days))
    log_inc = log_drift_daily + sigma * np.sqrt(dt) * z
    return np.exp(np.cumsum(log_inc, axis=1))


def risk_neutral_paths(n_paths: int, n_days: int, sigma: float, r: float, q: float = 0.0,
                       seed: int = 42, antithetic: bool = True) -> np.ndarray:
    dt = 1.0 / TRADING_DAYS
    return gbm_paths(n_paths, n_days, sigma, (r - q - 0.5 * sigma**2) * dt, seed, antithetic)


# ---------------------------------------------------------------------------
# Precificação de estruturas
# ---------------------------------------------------------------------------

@dataclass
class LegPrice:
    leg: Leg
    unit_price: float  # preço de 1 opção (fração de S0)
    signed_price: float  # posição × proporção × preço unitário (contribuição ao custo)
    method: str  # "BS" ou "MC"
    stderr: float = 0.0


@dataclass
class PricingResult:
    legs: list[LegPrice]
    net_cost: float  # soma dos signed_price das opções (+ = débito)
    net_stderr: float  # erro padrão do MC sobre o custo líquido
    n_paths: int
    params: dict = field(default_factory=dict)


@dataclass
class MCContext:
    """Caminhos neutros ao risco pré-gerados (reutilizados pelo solver)."""

    summary: PathSummary
    n_paths: int
    n_days: int
    sigma: float
    r: float
    q: float
    antithetic: bool
    barrier_shift: float

    @property
    def T(self) -> float:
        return self.n_days / TRADING_DAYS


def make_mc_context(n_days: int, sigma: float, r: float, q: float = 0.0, n_paths: int = 50_000,
                    seed: int = 42, monitoring: str = "close", antithetic: bool = True) -> MCContext:
    """Gera os caminhos em blocos e guarda só o resumo (S_T, máximo, mínimo) para
    economizar memória. Ordem: primeira metade +Z, segunda metade −Z (antitéticas)."""
    rng = np.random.default_rng(seed)
    dt = 1.0 / TRADING_DAYS
    drift = (r - q - 0.5 * sigma**2) * dt
    vol = sigma * np.sqrt(dt)
    n_base = (n_paths + 1) // 2 if antithetic else n_paths
    signs = (1.0, -1.0) if antithetic else (1.0,)
    parts = {sg: [] for sg in signs}
    chunk = 5_000
    for start in range(0, n_base, chunk):
        z = rng.standard_normal((min(chunk, n_base - start), n_days))
        for sg in signs:
            paths = np.exp(np.cumsum(drift + vol * sg * z, axis=1))
            parts[sg].append(summarize_paths(paths))
    summaries = [s for sg in signs for s in parts[sg]]
    summary = PathSummary(
        s_T=np.concatenate([s.s_T for s in summaries]),
        run_max=np.concatenate([s.run_max for s in summaries]),
        run_min=np.concatenate([s.run_min for s in summaries]),
    )
    shift = BGK_BETA * sigma * np.sqrt(dt) if monitoring == "intraday" else 0.0
    return MCContext(summary, len(summary.s_T), n_days, sigma, r, q, antithetic, shift)


def _pair_average(x: np.ndarray, antithetic: bool) -> np.ndarray:
    """Com antitéticas, as amostras independentes são as médias dos pares (i, i + n/2)."""
    if not antithetic:
        return x
    half = len(x) // 2
    return 0.5 * (x[:half] + x[half:2 * half])


def mc_leg_samples(leg: Leg, ctx: MCContext, hits: dict) -> np.ndarray:
    """Payoff descontado de UMA opção (sem posição/proporção) em cada caminho."""
    unit = Leg(leg.kind, +1, leg.strike, leg.barrier, leg.barrier_level, 1.0)
    act = leg_active(unit, hits, ctx.summary.s_T.shape)
    return np.exp(-ctx.r * ctx.T) * leg_payoff(unit, ctx.summary.s_T, act)


def mc_price_leg(leg: Leg, ctx: MCContext) -> tuple[float, float]:
    """(preço, erro padrão) de uma opção por Monte Carlo."""
    hits = event_hits(ctx.summary, [leg.event] if leg.event else [], ctx.barrier_shift)
    samples = _pair_average(mc_leg_samples(leg, ctx, hits), ctx.antithetic)
    return float(samples.mean()), float(samples.std(ddof=1) / np.sqrt(len(samples)))


def price_structure_ctx(structure: Structure, ctx: MCContext, force_mc: bool = False) -> PricingResult:
    hits = event_hits(ctx.summary, structure.events, ctx.barrier_shift)
    leg_prices: list[LegPrice] = []
    mc_total = np.zeros(ctx.summary.s_T.shape)
    for leg in structure.option_legs:
        if leg.has_barrier or force_mc:
            samples = mc_leg_samples(leg, ctx, hits)
            paired = _pair_average(samples, ctx.antithetic)
            price = float(paired.mean())
            se = float(paired.std(ddof=1) / np.sqrt(len(paired)))
            mc_total += leg.position * leg.ratio * samples
            method = "MC"
        else:
            price = float(bs_price(leg.kind, 1.0, leg.strike, ctx.T, ctx.r, ctx.q, ctx.sigma))
            se, method = 0.0, "BS"
        leg_prices.append(LegPrice(leg, price, leg.position * leg.ratio * price, method, se))
    net = float(sum(lp.signed_price for lp in leg_prices))
    paired_total = _pair_average(mc_total, ctx.antithetic)
    net_se = float(paired_total.std(ddof=1) / np.sqrt(len(paired_total))) if np.any(mc_total) else 0.0
    params = {"sigma": ctx.sigma, "r": ctx.r, "q": ctx.q, "n_days": ctx.n_days}
    return PricingResult(leg_prices, net, net_se, ctx.n_paths, params)


def price_structure(structure: Structure, sigma: float, r: float, q: float = 0.0, n_days: int = 252,
                    n_paths: int = 50_000, seed: int = 42, monitoring: str = "close") -> PricingResult:
    """Custo teórico das opções da estrutura (fração de S0; + = débito)."""
    if any(leg.has_barrier for leg in structure.option_legs):
        ctx = make_mc_context(n_days, sigma, r, q, n_paths, seed, monitoring)
    else:
        # sem barreiras não precisa de caminhos; contexto mínimo só para os parâmetros
        ctx = MCContext(PathSummary(np.ones(2), np.ones(2), np.ones(2)), 0, n_days, sigma, r, q, False, 0.0)
    return price_structure_ctx(structure, ctx)


# ---------------------------------------------------------------------------
# Solver de custo zero
# ---------------------------------------------------------------------------

PARAMS = ("strike", "barrier", "ratio")
PARAM_LABELS = {"strike": "Preço de exercício", "barrier": "Valor da barreira", "ratio": "Proporção"}


@dataclass
class SolverResult:
    converged: bool
    value: float | None
    cost: float | None
    stderr: float | None
    message: str


def _with_param(structure: Structure, leg_indices, param: str, x: float) -> Structure:
    """Cópia da estrutura com ``param`` = x em uma ou mais pernas (pernas vinculadas,
    ex.: put e call do FKO compartilham o strike)."""
    s = structure.copy()
    for i in _as_list(leg_indices):
        leg = s.legs[i]
        if param == "strike":
            leg.strike = float(x)
        elif param == "barrier":
            leg.barrier_level = float(x)
        elif param == "ratio":
            leg.ratio = float(x)
        else:
            raise ValueError(param)
    return s


def _as_list(leg_indices) -> list[int]:
    return [int(leg_indices)] if np.isscalar(leg_indices) else [int(i) for i in leg_indices]


def default_bounds(leg: Leg, param: str) -> tuple[float, float]:
    if param == "strike":
        return (0.30, 3.00)
    if param == "barrier":
        return (1.0001, 3.00) if leg.barrier_dir == "up" else (0.05, 0.9999)
    return (1e-4, 10.0)


def solve_zero_cost(structure: Structure, leg_index, param: str, sigma: float, r: float,
                    q: float = 0.0, n_days: int = 252, n_paths: int = 50_000, seed: int = 42,
                    monitoring: str = "close", bounds: tuple[float, float] | None = None,
                    target: float = 0.0, xtol: float = 1e-7) -> SolverResult:
    """Encontra o valor do parâmetro que faz o custo líquido = ``target`` (padrão 0).

    ``leg_index`` pode ser um índice ou uma lista de índices (pernas vinculadas
    que recebem o mesmo valor)."""
    indices = _as_list(leg_index)
    if not indices or any(not 0 <= i < len(structure.legs) for i in indices):
        return SolverResult(False, None, None, None, "Perna inválida.")
    for i in indices:
        leg = structure.legs[i]
        if not leg.is_option:
            return SolverResult(False, None, None, None, "Escolha apenas pernas de opção (não a ação).")
        if param == "barrier" and not leg.has_barrier:
            return SolverResult(False, None, None, None, f"A perna {i + 1} não tem barreira.")
    leg = structure.legs[indices[0]]
    lo, hi = bounds or default_bounds(leg, param)

    needs_mc = any(lg.has_barrier for lg in structure.option_legs)
    if needs_mc:
        ctx = make_mc_context(n_days, sigma, r, q, n_paths, seed, monitoring)
    else:
        ctx = MCContext(PathSummary(np.ones(2), np.ones(2), np.ones(2)), 0, n_days, sigma, r, q, False, 0.0)

    def f(x: float) -> float:
        return price_structure_ctx(_with_param(structure, indices, param, x), ctx).net_cost - target

    try:
        f_lo, f_hi = f(lo), f(hi)
    except (ValueError, FloatingPointError) as exc:
        return SolverResult(False, None, None, None, f"Erro ao avaliar o custo: {exc}")
    if not (np.isfinite(f_lo) and np.isfinite(f_hi)) or f_lo * f_hi > 0:
        return SolverResult(
            False, None, None, None,
            "Não há solução no intervalo informado: o custo líquido tem o mesmo sinal nos dois extremos "
            f"({f_lo + target:+.4%} em {lo:.4f} e {f_hi + target:+.4%} em {hi:.4f}). "
            "Tente outro parâmetro, outra perna ou outro intervalo.")
    x = brentq(f, lo, hi, xtol=xtol, maxiter=200)
    res = price_structure_ctx(_with_param(structure, indices, param, x), ctx)
    return SolverResult(True, float(x), res.net_cost, res.net_stderr,
                        "Solução encontrada.")
