"""Experimento 5 — o "IC 95%" do backtest histórico cobre mesmo 95%?

Simula muitas "histórias" de 4.180 pregões de um GJR-GARCH com choques t de Student (processo conhecido), aplica
a estrutura em todas as janelas de cada história, calcula o IC de cada método e conta em quantas histórias o IC
contém a probabilidade verdadeira (a média das frequências entre as histórias, já que o processo é estacionário).

Métodos: moving block bootstrap com bloco = N (o do projeto), 2N e 3N; normal e Wilson com amostra efetiva
n/N; normal com variância de longo prazo (HAC de Bartlett, banda 2N); MBB alargado pelo quantil t.

Uso: python scripts/pesquisa/exp5_ic.py [nº de histórias]
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from estruturadas import presets  # noqa: E402
from estruturadas.legs import evaluate_paths, returns_from_payoff  # noqa: E402

N_DAYS, BURN, CDI = 4180, 1500, 0.1365
OMEGA, ALPHA, GAMMA, BETA, NU = 1.2e-5, 0.05, 0.08, 0.88, 6.0  # persistência 0,97; vol ≈ 32% a.a.


def simulate(R, rng):
    T = N_DAYS + BURN
    z = rng.standard_t(NU, size=(T, R)) * math.sqrt((NU - 2) / NU)
    h = np.full(R, OMEGA / (1 - ALPHA - GAMMA / 2 - BETA))
    mu = math.log1p(CDI) / 252
    lr = np.empty((T, R))
    for t in range(T):
        e = np.sqrt(h) * z[t]
        lr[t] = mu - 0.5 * h + e
        h = OMEGA + (ALPHA + GAMMA * (e < 0)) * e * e + BETA * h
    return lr[BURN:].T  # (R, N_DAYS)


def indicators(structure, lr, N):
    logp = np.concatenate([[0.0], np.cumsum(lr)])
    w = sliding_window_view(logp, N + 1)
    close = np.exp(w[:, 1:] - w[:, :1])
    ev = evaluate_paths(structure, close)
    ret = returns_from_payoff(ev.payoff, 0.0, structure.has_stock)
    out = {"lucro": (ret > 1e-9).astype(float), "cdi": (ret > (1 + CDI) ** (N / 252) - 1 + 1e-9).astype(float)}
    if structure.events:
        out["barreira"] = np.asarray(ev.any_hit, dtype=float)
    return out


def mbb_ci(ind, block, rng, B=1000):
    n = len(ind)
    block = min(block, n)
    m, nb = n - block + 1, math.ceil(n / block)
    last = n - block * (nb - 1)
    cs = np.concatenate([[0.0], np.cumsum(ind)])
    st = rng.integers(0, m, size=(B, nb))
    ln = np.full(nb, block)
    ln[-1] = last
    means = (cs[st + ln] - cs[st]).sum(axis=1) / n
    return np.percentile(means, [2.5, 97.5])


def hac_ci(ind, bw):
    n = len(ind)
    x = ind - ind.mean()
    v = float(x @ x) / n
    for k in range(1, min(bw, n - 1) + 1):
        v += 2 * (1 - k / (bw + 1)) * float(x[k:] @ x[:-k]) / n
    se = math.sqrt(max(v, 0) / n)
    return ind.mean() - 1.96 * se, ind.mean() + 1.96 * se


def wilson_ci(ind, n_eff):
    """Intervalo de Wilson tratando a série como n_eff observações independentes."""
    p, z = float(ind.mean()), 1.96
    den = 1 + z * z / n_eff
    c = (p + z * z / (2 * n_eff)) / den
    hw = z * math.sqrt(p * (1 - p) / n_eff + z * z / (4 * n_eff * n_eff)) / den
    return c - hw, c + hw


def mbb_t_ci(ind, block, rng):
    """MBB com o intervalo alargado pelo quantil t com (nº de blocos − 1) graus de liberdade."""
    from scipy.stats import t as tdist
    lo, hi = mbb_ci(ind, block, rng)
    nb = max(2, len(ind) // block)
    k = tdist.ppf(0.975, nb - 1) / 1.96 * math.sqrt(nb / (nb - 1))
    m = float(ind.mean())
    return max(0.0, m - k * (m - lo)), min(1.0, m + k * (hi - m))


def wilson_mbb_ci(ind, block, rng, cap):
    """Wilson com a amostra efetiva estimada pela variância do MBB (limitada a `cap` observações)."""
    lo, hi = mbb_ci(ind, block, rng)
    p = float(ind.mean())
    se = (hi - lo) / (2 * 1.96)
    n_eff = cap if se <= 0 or p in (0.0, 1.0) else min(cap, p * (1 - p) / (se * se))
    return wilson_ci(ind, max(n_eff, 2.0))


def main():
    R = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    rng = np.random.default_rng(7)
    lr = simulate(R, rng)
    cases = [("Collar KI 100/106/112, 3m", presets.collar_ki(1.0, 1.06, 1.12), 63),
             ("FKO 110/70, 6m", presets.forward_knock_out(1.10, 0.70), 126),
             ("Proteção Total, 12m", presets.protecao_total_bbdc4(), 252)]
    for name, s, N in cases:
        inds = [indicators(s, lr[r], N) for r in range(R)]
        print(f"\n=== {name} — {R} histórias de {N_DAYS} pregões, amostra efetiva ≈ {math.ceil((N_DAYS - N) / N)} ===")
        print(f"{'indicador':10s} {'p real':>7s} {'desvio':>7s} | cobertura (largura média, em p.p.)")
        for key in inds[0]:
            ph = np.array([i[key].mean() for i in inds])
            p_true = ph.mean()
            methods = {"MBB N": lambda x: mbb_ci(x, N, rng), "MBB 2N": lambda x: mbb_ci(x, 2 * N, rng),
                       "MBB 3N": lambda x: mbb_ci(x, 3 * N, rng),
                       "normal n/N": lambda x: (x.mean() - 1.96 * math.sqrt(max(x.mean() * (1 - x.mean()), 1e-12) * N / len(x)),
                                                x.mean() + 1.96 * math.sqrt(max(x.mean() * (1 - x.mean()), 1e-12) * N / len(x))),
                       "HAC 2N": lambda x: hac_ci(x, 2 * N),
                       "Wilson n/N": lambda x: wilson_ci(x, len(x) / N),
                       "Wilson 1,5n/N": lambda x: wilson_ci(x, 1.5 * len(x) / N),
                       "Wilson 2n/N": lambda x: wilson_ci(x, 2 * len(x) / N),
                       "Wilson n_ef(MBB 2N)≤2n/N": lambda x: wilson_mbb_ci(x, 2 * N, rng, 2 * len(x) / N),
                       "Wilson n_ef(MBB 2N)≤1,5n/N": lambda x: wilson_mbb_ci(x, 2 * N, rng, 1.5 * len(x) / N),
                       "MBB N×t": lambda x: mbb_t_ci(x, N, rng), "MBB 2N×t": lambda x: mbb_t_ci(x, 2 * N, rng),
                       "união MBB N + Wilson": lambda x: (min(mbb_ci(x, N, rng)[0], wilson_ci(x, len(x) / N)[0]),
                                                          max(mbb_ci(x, N, rng)[1], wilson_ci(x, len(x) / N)[1]))}
            parts = []
            if len(sys.argv) > 2:
                methods = {k: v for k, v in methods.items() if k.startswith(sys.argv[2])}
            for mname, fn in methods.items():
                cis = np.array([fn(i[key]) for i in inds])
                cov = np.mean((cis[:, 0] <= p_true) & (p_true <= cis[:, 1]))
                parts.append(f"{mname}: {cov:5.1%} ({100 * np.mean(cis[:, 1] - cis[:, 0]):4.1f})")
            print(f"{key:10s} {p_true:7.1%} {ph.std():7.1%} | " + " · ".join(parts))
        print(f"   largura que daria 95% com erro normal: ±1,96 × desvio = lucro {100 * 2 * 1.96 * np.std([i['lucro'].mean() for i in inds]):.1f} p.p.")


if __name__ == "__main__":
    main()
