"""Experimento 8 — a vol robusta melhora as probabilidades? (calibração walk-forward com o FHS modificado)

Mesmo teste do exp6 (walk-forward do projeto), trocando só a volatilidade do FHS:

* gjr_w: GJR estimado e filtrado com os retornos limitados a ±5 desvios robustos (MAD dos retornos não nulos,
  só com dados até a data); os choques z continuam vindo dos retornos brutos (as caudas ficam no sorteio);
* gjr_w+252: o mesmo, com a vol do prazo puxada para a média geométrica entre a previsão do GJR robusto e a
  variância realizada de 252 pregões (via escala de vol do Monte Carlo).

Uso: python scripts/pesquisa/exp8_vol_robusta.py <pasta de dados> <saida.pkl> [preset] [N]
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from estruturadas.backtest import ohlc_log_returns, run_historical, run_monte_carlo  # noqa: E402
from estruturadas.data import cdi_factor_on_index  # noqa: E402
from estruturadas.garch import GarchFit, fit_garch, garch_filter, term_var  # noqa: E402
from exp6_calib import load_prices, report, structure_for  # noqa: E402

TOL = 1e-9


def robust_cap(lr):
    nz = lr[lr != 0]
    med = float(np.median(nz))
    return med, 5 * 1.4826 * float(np.median(np.abs(nz - med)))


def robust_fit(lr, params=None):
    """GJR com retornos limitados; devolve (GarchFit com z dos retornos brutos, parâmetros para reaproveitar)."""
    if params is None:
        med, cap = robust_cap(lr)
        f = fit_garch(np.clip(lr, med - cap, med + cap), "gjr")
        params = (f.omega, f.alpha, f.gamma, f.beta, med, cap)
    omega, alpha, gamma, beta, med, cap = params
    x = np.clip(lr, med - cap, med + cap)
    m = float(x.mean())
    eps_c = x - m
    s2 = float(np.mean(eps_c * eps_c))
    h = garch_filter(eps_c, omega, alpha, gamma, beta, s2)
    z = (lr - m) / np.sqrt(h[:-1])
    z = (z - z.mean()) / z.std()
    kappa = float(np.mean(np.where(z < 0, z * z, 0.0)))
    zero = np.zeros(len(lr))
    return GarchFit("gjr", omega, alpha, gamma, beta, m, s2, 0.0, len(lr), h, z, zero, zero, kappa, 0), params


def walk_forward_robust(structure, prices, N, cost, cdi_factor, blend, step=10, start=504, n_paths=1000, refit=252,
                        fitter=None):
    fitter = fitter or robust_fit
    n = len(prices)
    start = max(start, N + 252)
    hist = run_historical(structure, prices, N, cost, "close", 0.0, cdi_factor=cdi_factor).df
    real = {"lucro": (hist["retorno"] > TOL).to_numpy(float), "cdi": (hist["retorno"] > hist["retorno_cdi"] + TOL).to_numpy(float),
            "barreira": hist["barreira_qualquer"].to_numpy(float)}
    csum = {k: np.concatenate([[0.0], np.cumsum(v)]) for k, v in real.items()}
    F = np.asarray(cdi_factor, float)
    lr_all = ohlc_log_returns(prices)[0]
    params, fit_t, rows = None, -10**9, []
    for t in range(start, n - N, step):
        lr = lr_all[:t]
        if params is None or t - fit_t >= refit:
            g, params = fitter(lr)
            fit_t = t
        else:
            g, _ = fitter(lr, params)
        scale = 1.0
        if blend:
            f_g = float(term_var(g, g.h_next, N))
            f_252 = float(np.mean(lr[-252:] ** 2))
            scale = math.sqrt(math.sqrt(f_g * f_252) / f_g)
        rate = float((F[t] / F[t - 1]) ** 252 - 1)
        r = run_monte_carlo(structure, prices.iloc[: t + 1], N, cost, "fhs_garch", n_paths, 20, "cdi", rate, 42, "close", 0.0,
                            vol_scale=scale, garch=g)
        md = r.df
        closed = t - N + 1
        row = {"data": prices.index[t], "vol": r.meta["sigma"], "prev_lucro": float((md["retorno"] > TOL).mean()),
               "prev_cdi": float((md["retorno"] > md["retorno_cdi_hoje"] + TOL).mean()),
               "prev_barreira": float(md["barreira_qualquer"].mean())}
        for k in real:
            row[f"clim_{k}"] = csum[k][closed] / closed
            row[f"real_{k}"] = real[k][t]
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    folder, out = sys.argv[1], sys.argv[2]
    key = sys.argv[3] if len(sys.argv) > 3 else "collar_ki"
    N = int(sys.argv[4]) if len(sys.argv) > 4 else 63
    if not os.path.exists(out):
        cdi = json.load(open(os.path.join(folder, "cdi.json")))
        cdi = pd.Series(cdi["r"], index=pd.to_datetime(cdi["d"]))
        s = structure_for(key)
        frames = []
        for f in sorted(glob.glob(os.path.join(folder, "*.json"))):
            tk = os.path.basename(f)[:-5]
            if tk in ("cdi", "index"):
                continue
            px = load_prices(f)
            Fc = cdi_factor_on_index(px.index, cdi, 0.1365)
            for name, blend in (("fhs_gjr_w", False), ("fhs_gjr_w+252", True)):
                t0 = time.time()
                d = walk_forward_robust(s, px, N, 0.0, Fc, blend)
                d["acao"], d["metodo"] = tk, name
                frames.append(d)
                print(f"{tk} {name}: {len(d)} datas, {time.time() - t0:.0f}s", flush=True)
        pd.concat(frames, ignore_index=True).to_pickle(out)
    report(out, N)
