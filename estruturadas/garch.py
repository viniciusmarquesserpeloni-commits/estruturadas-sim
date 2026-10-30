"""Volatilidade condicional: GARCH(1,1) e GJR-GARCH(1,1) + Monte Carlo por Filtered Historical Simulation.

Modelo (log-retornos sem a média, ε_t = r_t − média):

    h_{t+1} = ω + (α + γ·1[ε_t < 0])·ε_t² + β·h_t          (GARCH(1,1): γ = 0)

ajustado por máxima verossimilhança gaussiana (quase-verossimilhança: os resíduos não precisam ser
normais). O GJR (Glosten, Jagannathan & Runkle, 1993) deixa as quedas aumentarem a vol mais do que as
altas — o "efeito alavancagem" típico de ações.

FHS (Barone-Adesi, Giannopoulos & Vosper, 1999): os resíduos padronizados z_t = ε_t/√h_t são os
"choques" reais da ação já sem o efeito do nível de vol de cada época. O Monte Carlo parte da vol de
hoje (previsão de 1 passo) e, a cada dia, sorteia um choque z* do histórico, aplica e = √h·z* e
atualiza h pela equação acima: a vol simulada reage aos próprios choques e converge para a média de
longo prazo no ritmo estimado (meia-vida). A máxima e a mínima do dia sorteado vão junto, também
padronizadas pela vol GARCH daquele dia.

Otimizador: Nelder-Mead determinístico, idêntico ao do motor JS (engine/garch.js), numa
parametrização sem restrições que garante ω > 0, α, γ, β ≥ 0 e persistência < 0,999.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from .rng import integers

TRADING_DAYS = 252
VOL_MODEL_LABELS = {"gjr": "GJR-GARCH (assimétrico)", "garch": "GARCH(1,1)"}
P_MAX = 0.999  # persistência máxima na estimação
MIN_OBS = 250  # mínimo de log-retornos para estimar o modelo
RESTARTS = 5  # reinícios do Nelder-Mead a partir do melhor ponto


def _exp(x: float) -> float:
    """exp com estouro virando infinito (como o Math.exp do JS), para o otimizador poder passar por regiões absurdas."""
    try:
        return math.exp(x)
    except OverflowError:
        return math.inf


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + _exp(-x))


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _seqsum(a) -> float:
    """Soma sequencial (mesma ordem do laço do motor JS)."""
    a = np.asarray(a, dtype=float)
    return float(np.cumsum(a)[-1]) if len(a) else 0.0


def unpack_params(x, model: str, s2: float) -> tuple[float, float, float, float]:
    """Parâmetros irrestritos -> (ω, α, γ, β).

    x[0]: log da variância de longo prazo relativa à amostral; x[1]: persistência p = α + γ/2 + β
    (logística em (0; 0,999)); x[2]: fração de p que vem dos choques (α + γ/2) contra β; x[3] (GJR):
    fração dos choques que é assimétrica (γ/2 contra α)."""
    v_long = s2 * _exp(x[0])
    p = P_MAX * _logistic(x[1])
    a = _logistic(x[2])
    shock, beta = a * p, (1.0 - a) * p
    if model == "gjr":
        g = _logistic(x[3])
        gamma, alpha = 2.0 * g * shock, (1.0 - g) * shock
    else:
        gamma, alpha = 0.0, shock
    return v_long * (1.0 - p), alpha, gamma, beta


START_POINTS = ((0.97, 0.08, 0.625), (0.90, 0.12, 0.5))  # (persistência, choques, fração assimétrica no GJR)
NM_STEP = 0.25  # passo do simplex inicial (passos grandes podem levar o otimizador para a borda p = 0,999)


def start_params(model: str, k: int = 0) -> list[float]:
    """Pontos iniciais: persistência 0,97 com choques 0,08 (no GJR, 3/8 simétricos e 5/8 assimétricos) e
    persistência 0,90 com choques 0,12."""
    p, shock, g = START_POINTS[k]
    x = [0.0, _logit(p / P_MAX), _logit(shock / p)]
    return x + [_logit(g)] if model == "gjr" else x


def garch_filter(eps, omega: float, alpha: float, gamma: float, beta: float, h0: float) -> np.ndarray:
    """Variância condicional h (n+1,): h[0] = h0, h[t+1] = ω + (α + γ·1[ε_t<0])·ε_t² + β·h[t].
    h[t] é a variância do retorno t, conhecida no fechamento anterior; h[n] = previsão para o próximo pregão."""
    eps = np.asarray(eps, dtype=float)
    x = omega + (alpha + gamma * (eps < 0)) * (eps * eps)
    y, _ = lfilter([1.0], [1.0, -beta], x, zi=[beta * h0])
    return np.concatenate([[h0], y])


def nelder_mead(f, x0, step: float = NM_STEP, max_iter: int = 2000, xtol: float = 1e-7, ftol: float = 1e-11):
    """Nelder-Mead padrão (reflexão 1, expansão 2, contração 0,5, encolhimento 0,5), determinístico e
    escrito igual ao do motor JS. Devolve (x, f(x), iterações)."""
    n = len(x0)
    simplex = [list(map(float, x0))]
    for i in range(n):
        v = list(map(float, x0))
        v[i] += step
        simplex.append(v)
    fs = [f(v) for v in simplex]
    it = 0
    while it < max_iter:
        order = sorted(range(n + 1), key=lambda i: fs[i])
        simplex = [simplex[i] for i in order]
        fs = [fs[i] for i in order]
        spread = 0.0
        for i in range(1, n + 1):
            for j in range(n):
                spread = max(spread, abs(simplex[i][j] - simplex[0][j]))
        if fs[n] - fs[0] <= ftol and spread <= xtol:
            break
        it += 1
        c = [0.0] * n
        for i in range(n):
            for j in range(n):
                c[j] += simplex[i][j]
        c = [cj / n for cj in c]
        w = simplex[n]
        xr = [c[j] + (c[j] - w[j]) for j in range(n)]
        fr = f(xr)
        if fr < fs[0]:
            xe = [c[j] + 2.0 * (c[j] - w[j]) for j in range(n)]
            fe = f(xe)
            simplex[n], fs[n] = (xe, fe) if fe < fr else (xr, fr)
            continue
        if fr < fs[n - 1]:
            simplex[n], fs[n] = xr, fr
            continue
        if fr < fs[n]:
            xc = [c[j] + 0.5 * (xr[j] - c[j]) for j in range(n)]
            fc = f(xc)
            ok = fc <= fr
        else:
            xc = [c[j] + 0.5 * (w[j] - c[j]) for j in range(n)]
            fc = f(xc)
            ok = fc < fs[n]
        if ok:
            simplex[n], fs[n] = xc, fc
            continue
        b = simplex[0]
        for i in range(1, n + 1):
            simplex[i] = [b[j] + 0.5 * (simplex[i][j] - b[j]) for j in range(n)]
            fs[i] = f(simplex[i])
    best = min(range(n + 1), key=lambda i: fs[i])
    return simplex[best], fs[best], it


@dataclass
class GarchFit:
    model: str  # "garch" | "gjr"
    omega: float
    alpha: float
    gamma: float
    beta: float
    mean: float  # média dos log-retornos (removida antes do ajuste)
    s2: float  # variância amostral (início do filtro)
    loglik: float  # log-verossimilhança gaussiana
    n: int  # nº de log-retornos
    h: np.ndarray  # (n+1,) variância condicional; h[n] = previsão para o próximo pregão
    z: np.ndarray  # resíduos padronizados, re-normalizados (média 0, desvio 1)
    up: np.ndarray  # máxima do dia padronizada: ln(H/C)/√h (≥ 0)
    dn: np.ndarray  # mínima do dia padronizada: ln(L/C)/√h (≤ 0)
    kappa: float  # E[z²·1(z<0)] dos resíduos (0,5 se simétricos)
    iterations: int

    @property
    def n_params(self) -> int:
        return 4 if self.model == "gjr" else 3

    @property
    def persistence(self) -> float:
        """α + γ·κ + β: quanto de um choque na variância sobra no dia seguinte."""
        return min(self.alpha + self.gamma * self.kappa + self.beta, 0.9999)

    @property
    def h_next(self) -> float:
        return float(self.h[-1])

    @property
    def long_run_var(self) -> float:
        return self.omega / (1.0 - self.persistence)

    @property
    def half_life(self) -> float:
        """Pregões para a diferença entre a vol de hoje e a de longo prazo cair pela metade."""
        return math.log(0.5) / math.log(self.persistence)

    @property
    def bic(self) -> float:
        return -2.0 * self.loglik + self.n_params * math.log(self.n)

    def params(self) -> dict:
        return {"model": self.model, "omega": self.omega, "alpha": self.alpha, "gamma": self.gamma, "beta": self.beta,
                "mean": self.mean, "s2": self.s2, "kappa": self.kappa, "loglik": self.loglik, "n": self.n,
                "persistence": self.persistence, "h_next": self.h_next, "iterations": self.iterations}


def _neg_loglik(x, eps, model: str, s2: float) -> float:
    omega, alpha, gamma, beta = unpack_params(x, model, s2)
    h = garch_filter(eps, omega, alpha, gamma, beta, s2)[:-1]
    return 0.5 * _seqsum(np.log(h) + eps * eps / h) / len(eps)


def filtered(lr, omega: float, alpha: float, gamma: float, beta: float, model: str = "gjr",
             up=None, dn=None, iterations: int = 0) -> GarchFit:
    """Aplica parâmetros já estimados a uma série (resíduos, variância e previsão de hoje), sem reestimar."""
    lr = np.asarray(lr, dtype=float)
    n = len(lr)
    m = _seqsum(lr) / n
    eps = lr - m
    s2 = _seqsum(eps * eps) / n
    h = garch_filter(eps, omega, alpha, gamma, beta, s2)
    sh = np.sqrt(h[:-1])
    z = eps / sh
    zm = _seqsum(z) / n
    zs = math.sqrt(_seqsum((z - zm) * (z - zm)) / n)
    z = (z - zm) / zs
    kappa = _seqsum(np.where(z < 0, z * z, 0.0)) / n
    ll = -0.5 * _seqsum(math.log(2 * math.pi) + np.log(h[:-1]) + eps * eps / h[:-1])
    u = np.zeros(n) if up is None else np.asarray(up, dtype=float) / sh
    d = np.zeros(n) if dn is None else np.asarray(dn, dtype=float) / sh
    return GarchFit(model, omega, alpha, gamma, beta, m, s2, ll, n, h, z, u, d, kappa, iterations)


def fit_garch(lr, model: str = "gjr", up=None, dn=None) -> GarchFit:
    """Estima o GARCH(1,1) ou o GJR-GARCH(1,1) por quase-máxima verossimilhança gaussiana."""
    if model not in VOL_MODEL_LABELS:
        raise ValueError(f"Modelo de vol inválido: {model}")
    lr = np.asarray(lr, dtype=float)
    if len(lr) < MIN_OBS:
        raise ValueError(f"Histórico insuficiente para o GARCH: {len(lr)} retornos (mínimo {MIN_OBS}).")
    n = len(lr)
    eps = lr - _seqsum(lr) / n
    s2 = _seqsum(eps * eps) / n
    f = lambda v: _neg_loglik(v, eps, model, s2)  # noqa: E731
    # o Nelder-Mead pode estagnar antes do ótimo (simplex degenerado numa região plana): parte de dois pontos
    # iniciais e, em cada um, reinicia a partir do melhor ponto até não haver melhora
    best, it = None, 0
    for k in range(len(START_POINTS)):
        x, fx, n_it = nelder_mead(f, start_params(model, k))
        it += n_it
        for _ in range(RESTARTS):
            x2, f2, n_it = nelder_mead(f, x)
            it += n_it
            improved = fx - f2 > 1e-10
            if f2 < fx:
                x, fx = x2, f2
            if not improved:
                break
        if best is None or fx < best[1]:
            best = (x, fx)
    omega, alpha, gamma, beta = unpack_params(best[0], model, s2)
    return filtered(lr, omega, alpha, gamma, beta, model, up, dn, it)


def expected_var(fit: GarchFit, h1, k):
    """E[h_{T+k}] dado h_{T+1} = h1 (k = 1, 2, …): v_L + p^(k−1)·(h1 − v_L)."""
    vl, p = fit.long_run_var, fit.persistence
    return vl + np.power(p, np.asarray(k, dtype=float) - 1.0) * (np.asarray(h1, dtype=float) - vl)


def term_var(fit: GarchFit, h1, m):
    """Variância diária média esperada nos próximos m pregões, dado h_{T+1} = h1:
    v_L + (h1 − v_L)·(1 − p^m)/(m·(1 − p))."""
    vl, p = fit.long_run_var, fit.persistence
    m = np.maximum(np.asarray(m, dtype=float), 1.0)
    return vl + (np.asarray(h1, dtype=float) - vl) * (1.0 - np.power(p, m)) / (m * (1.0 - p))


def term_vol(fit: GarchFit, h1, m):
    """Vol anualizada média esperada para os próximos m pregões."""
    return np.sqrt(term_var(fit, h1, m) * TRADING_DAYS)


def vol_panel(fit: GarchFit, lr, n_days: int, window: int = 63) -> dict:
    """Resumo para o painel de volatilidade (tudo anualizado, base 252)."""
    lr = np.asarray(lr, dtype=float)
    tail = lr[-window:]
    return {
        "modelo": VOL_MODEL_LABELS[fit.model],
        "vol_hoje": math.sqrt(fit.h_next * TRADING_DAYS),
        "vol_longo_prazo": math.sqrt(fit.long_run_var * TRADING_DAYS),
        "vol_prazo": float(term_vol(fit, fit.h_next, n_days)),
        "vol_realizada": float(np.std(tail, ddof=1) * math.sqrt(TRADING_DAYS)) if len(tail) > 1 else float("nan"),
        "meia_vida": fit.half_life,
        "persistencia": fit.persistence,
        "alpha": fit.alpha, "gamma": fit.gamma, "beta": fit.beta, "omega": fit.omega,
        "n": fit.n, "bic": fit.bic,
    }


def fhs_drift_daily(lr, mu: float | None, scale: float = 1.0) -> float:
    """Drift diário do FHS. Com ``mu``: ln(1 + mu)/252, e o termo −½·h de cada dia faz E[S_T] ≈ (1 + mu)^(N/252).
    Sem ``mu`` (média histórica): média dos log-retornos + ½·scale²·variância, mantendo a média do log."""
    lr = np.asarray(lr, dtype=float)
    if mu is None:
        n = len(lr)
        m = _seqsum(lr) / n
        return m + 0.5 * scale * scale * _seqsum((lr - m) * (lr - m)) / (n - 1)
    return math.log1p(mu) / TRADING_DAYS


def fhs_paths(fit: GarchFit, n_paths: int, n_days: int, seed: int = 42, drift_daily: float = 0.0,
              scale: float = 1.0, intraday: bool = True):
    """Caminhos FHS a partir da vol de hoje. Sorteio i.i.d. dos dias (mesma sequência do motor JS:
    caminho a caminho, dia a dia). ``scale`` multiplica a vol (grade de cenários) sem mudar a dinâmica.

    Devolve (fechamento, máxima, mínima, variância): matrizes (n_paths, n_days) relativas a S0; a
    variância [i, j] é a h prevista para o dia seguinte ao dia j+1 (usada na marcação da saída antecipada)."""
    L = len(fit.z)
    idx = integers(seed, n_paths * n_days, L).reshape(n_paths, n_days)
    z, u, d = fit.z, fit.up, fit.dn
    omega, alpha, gamma, beta = fit.omega, fit.alpha, fit.gamma, fit.beta
    s2 = scale * scale
    h = np.full(n_paths, fit.h_next)
    x = np.zeros(n_paths)
    logc = np.empty((n_paths, n_days))
    logh = np.empty((n_paths, n_days)) if intraday else None
    logl = np.empty((n_paths, n_days)) if intraday else None
    hv = np.empty((n_paths, n_days))
    for j in range(n_days):
        q = idx[:, j]
        sh = np.sqrt(h)
        e = sh * z[q]
        x = x + (drift_daily - 0.5 * s2 * h + scale * e)
        logc[:, j] = x
        if intraday:
            logh[:, j] = x + scale * sh * u[q]
            logl[:, j] = x + scale * sh * d[q]
        h = omega + (alpha + gamma * (e < 0)) * (e * e) + beta * h
        hv[:, j] = h
    close = np.exp(logc)
    if not intraday:
        return close, close, close, hv
    return close, np.exp(logh), np.exp(logl), hv
