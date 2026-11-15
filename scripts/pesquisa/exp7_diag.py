"""Experimento 7 — as premissas do FHS valem? (resíduos i.i.d., média dos caminhos, sorteio em blocos)

Para cada ação (desde 2010): ajusta o GJR do projeto e testa os resíduos padronizados z:
* Ljung-Box de 10 defasagens em z e em z² (p-valor; < 5% = ainda há dependência que o sorteio i.i.d. ignora);
* assimetria e curtose de z; correlação entre z de hoje e z² de amanhã (alavancagem que sobrou);
* E[S_T] dos caminhos FHS ÷ alvo (1 + CDI)^(N/252): quanto a média simulada desvia do retorno esperado pedido;
* P(barreira) do Collar KI 3m com sorteio i.i.d. × em blocos de 5 e 10 dias de z (sensibilidade à premissa).

Uso: python scripts/pesquisa/exp7_diag.py <pasta de dados>
"""
from __future__ import annotations

import glob
import math
import os
import sys

import numpy as np
from scipy.stats import chi2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from estruturadas import presets  # noqa: E402
from estruturadas.backtest import ohlc_log_returns  # noqa: E402
from estruturadas.garch import fhs_drift_daily, fit_garch  # noqa: E402
from estruturadas.legs import evaluate_paths  # noqa: E402
from exp6_calib import load_prices  # noqa: E402

CDI, N, PATHS = 0.1365, 63, 20000


def ljung_box(x, lags=10):
    x = x - x.mean()
    n, den = len(x), float(x @ x)
    q = sum((float(x[k:] @ x[:-k]) / den) ** 2 / (n - k) for k in range(1, lags + 1)) * n * (n + 2)
    return float(chi2.sf(q, lags))


def simulate(fit, idx, drift):
    """Igual a garch.fhs_paths (fechamento), mas com os índices dos dias sorteados dados de fora."""
    n_paths, n_days = idx.shape
    h, x = np.full(n_paths, fit.h_next), np.zeros(n_paths)
    out = np.empty((n_paths, n_days))
    for j in range(n_days):
        e = np.sqrt(h) * fit.z[idx[:, j]]
        x = x + (drift - 0.5 * h + e)
        out[:, j] = x
        h = fit.omega + (fit.alpha + fit.gamma * (e < 0)) * (e * e) + fit.beta * h
    return np.exp(out)


def block_idx(rng, L, n_paths, n_days, block):
    nb = math.ceil(n_days / block)
    st = rng.integers(0, L, size=(n_paths, nb))
    return ((st[:, :, None] + np.arange(block)[None, None, :]) % L).reshape(n_paths, nb * block)[:, :n_days]


def main():
    folder = sys.argv[1]
    s = presets.collar_ki(1.0, 1.06, 1.12)
    rng = np.random.default_rng(3)
    print(f"{'ação':6s} {'α':>6s} {'γ':>6s} {'β':>6s} {'persist':>7s} {'LB z':>6s} {'LB z²':>6s} {'assim':>6s} {'curt':>5s} "
          f"{'corr(z,z²+1)':>12s} {'E[S_T]/alvo':>11s} {'P(bar) iid':>10s} {'bloco 5':>8s} {'bloco 10':>8s}")
    acc = []
    for f in sorted(glob.glob(os.path.join(folder, "*.json"))):
        tk = os.path.basename(f)[:-5]
        if tk in ("cdi", "index"):
            continue
        lr, up, dn = ohlc_log_returns(load_prices(f))
        g = fit_garch(lr, "gjr", up, dn)
        z = g.z
        drift = fhs_drift_daily(lr, CDI)
        L = len(z)
        res = []
        for block in (1, 5, 10):
            close = simulate(g, block_idx(rng, L, PATHS, N, block), drift)
            res.append((close[:, -1].mean(), float(np.mean(evaluate_paths(s, close).any_hit))))
        skew = float(np.mean(z ** 3))
        kurt = float(np.mean(z ** 4))
        lev = float(np.corrcoef(z[:-1], z[1:] ** 2)[0, 1])
        row = (g.alpha, g.gamma, g.beta, g.persistence, ljung_box(z), ljung_box(z * z), skew, kurt, lev,
               res[0][0] / (1 + CDI) ** (N / 252), res[0][1], res[1][1], res[2][1])
        acc.append(row)
        print(f"{tk:6s} {row[0]:6.3f} {row[1]:6.3f} {row[2]:6.3f} {row[3]:7.3f} {row[4]:6.2f} {row[5]:6.2f} {row[6]:+6.2f} {row[7]:5.1f} "
              f"{row[8]:+12.3f} {row[9]:11.4f} {row[10]:10.1%} {row[11]:8.1%} {row[12]:8.1%}", flush=True)
    a = np.array(acc)
    print(f"\nMédias: γ {a[:, 1].mean():.3f} · persistência {a[:, 3].mean():.3f} · curtose {a[:, 7].mean():.1f} · E[S_T]/alvo {a[:, 9].mean():.4f}")
    print(f"Ljung-Box rejeita a 5%: z em {int((a[:, 4] < 0.05).sum())}/{len(a)} ações; z² em {int((a[:, 5] < 0.05).sum())}/{len(a)}")
    print(f"P(barreira) médio: i.i.d. {a[:, 10].mean():.1%} · bloco 5 {a[:, 11].mean():.1%} · bloco 10 {a[:, 12].mean():.1%}")


if __name__ == "__main__":
    main()
