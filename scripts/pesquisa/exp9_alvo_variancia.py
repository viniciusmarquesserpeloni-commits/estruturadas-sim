"""Experimento 9 — GARCH com alvo de variância (variance targeting) resolve os ajustes degenerados?

No ajuste do projeto a variância de longo prazo é um parâmetro livre; com um choque extremo (ou erro de dado) ela
pode ir a valores absurdos. Com alvo de variância (Engle e Mezrich, 1996) ela fica presa à variância amostral
(ω = s²·(1 − p)) e só a dinâmica (α, γ, β) é estimada.

Nota: o alvo de variância foi adotado no motor depois desta análise. Para reproduzir a comparação "livre ×
alvo" (modo fits), use o commit cd1edbf; nos commits seguintes os dois lados dão o mesmo ajuste.

Modos:
  fits  <pasta com todas as ações>            conta ajustes degenerados com e sem alvo de variância
  vol   <pasta> <saida.json>                  repete o exp4 (QLIKE) com alvo de variância
  calib <pasta> <saida.pkl> <preset> <N>      repete o exp6 (walk-forward do FHS) com alvo de variância
  calib252 <pasta> <saida.pkl> <preset> <N>   idem, com a vol do prazo combinada com a de 252 pregões
"""
from __future__ import annotations

import glob
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from estruturadas import garch as G  # noqa: E402


def fit_vt(lr, model="gjr", up=None, dn=None):
    if len(G.start_params("garch")) == 2:  # motor já com alvo de variância (adotado depois desta análise)
        return G.fit_garch(lr, model, up, dn)
    lr = np.asarray(lr, dtype=float)
    n = len(lr)
    if n < G.MIN_OBS:
        raise ValueError(f"Histórico insuficiente para o GARCH: {n} retornos (mínimo {G.MIN_OBS}).")
    eps = lr - G._seqsum(lr) / n
    s2 = G._seqsum(eps * eps) / n
    f = lambda v: G._neg_loglik([0.0] + list(v), eps, model, s2)  # noqa: E731
    best = None
    for k in range(len(G.START_POINTS)):
        x, fx, _ = G.nelder_mead(f, G.start_params(model, k)[1:])
        for _ in range(G.RESTARTS):
            x2, f2, _ = G.nelder_mead(f, x)
            improved = fx - f2 > 1e-10
            if f2 < fx:
                x, fx = x2, f2
            if not improved:
                break
        if best is None or fx < best[1]:
            best = (x, fx)
    omega, alpha, gamma, beta = G.unpack_params([0.0] + list(best[0]), model, s2)
    return G.filtered(lr, omega, alpha, gamma, beta, model, up, dn, 0)


def main():
    mode, folder = sys.argv[1], sys.argv[2]
    if mode == "fits":
        from estruturadas.backtest import ohlc_log_returns
        from exp6_calib import load_prices
        rows = []
        for f in sorted(glob.glob(os.path.join(folder, "*.json"))):
            tk = os.path.basename(f)[:-5]
            if tk in ("cdi", "index"):
                continue
            lr = ohlc_log_returns(load_prices(f))[0]
            if len(lr) < 300:
                continue
            a, b = G.fit_garch(lr, "gjr"), fit_vt(lr, "gjr")
            am = float(lr.std() * math.sqrt(252))
            rows.append((tk, am, a.persistence, math.sqrt(a.long_run_var * 252), math.sqrt(a.h_next * 252),
                         b.persistence, math.sqrt(b.long_run_var * 252), math.sqrt(b.h_next * 252),
                         (a.loglik - b.loglik) / len(lr)))
        bad = lambda p, lp, am: p >= 0.997 or lp > 2 * am or lp < 0.5 * am  # noqa: E731
        print(f"ações: {len(rows)} | degenerados (persistência ≥ 0,997 ou vol de longo prazo fora de 0,5–2× a amostral): "
              f"livre {sum(bad(r[2], r[3], r[1]) for r in rows)} · alvo de variância {sum(bad(r[5], r[6], r[1]) for r in rows)}")
        print(f"vol de longo prazo > 2× a amostral: livre {sum(r[3] > 2 * r[1] for r in rows)} · alvo {sum(r[6] > 2 * r[1] for r in rows)}")
        print(f"persistência ≥ 0,997: livre {sum(r[2] >= 0.997 for r in rows)} · alvo {sum(r[5] >= 0.997 for r in rows)}")
        print(f"perda de verossimilhança média por observação com o alvo: {np.mean([r[8] for r in rows]):.5f}")
        for r in sorted(rows, key=lambda r: -r[3] / r[1])[:12]:
            print(f"  {r[0]:7s} amostral {r[1]:4.0%} | livre: p {r[2]:.4f} LP {r[3]:5.0%} hoje {r[4]:4.0%} | alvo: p {r[5]:.4f} LP {r[6]:4.0%} hoje {r[7]:4.0%}")
    elif mode == "vol":
        import exp4_vol
        exp4_vol.fit_garch = fit_vt
        sys.argv = [sys.argv[0], folder] + sys.argv[3:]
        exp4_vol.main()
    elif mode == "calib252":
        calib_blend(folder, sys.argv[3], sys.argv[4], int(sys.argv[5]))
    elif mode == "calib":
        import estruturadas.calibration as C
        import exp6_calib
        C.fit_garch = fit_vt
        out, key, N = sys.argv[3], sys.argv[4], int(sys.argv[5])
        if not os.path.exists(out):
            exp6_calib.run(folder, out, key, N, ["fhs_garch"])
        exp6_calib.report(out, N)


def fitter_vt(lr, params=None):
    if params is None:
        g = fit_vt(lr, "gjr")
        return g, (g.omega, g.alpha, g.gamma, g.beta)
    return G.filtered(lr, *params, "gjr"), params


def calib_blend(folder, out, key, N):
    """Walk-forward do FHS com alvo de variância e vol do prazo combinada com a de 252 pregões."""
    import json
    import time

    import pandas as pd

    from estruturadas.data import cdi_factor_on_index
    from exp6_calib import load_prices, report, structure_for
    from exp8_vol_robusta import walk_forward_robust
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
            t0 = time.time()
            d = walk_forward_robust(s, px, N, 0.0, cdi_factor_on_index(px.index, cdi, 0.1365), True, fitter=fitter_vt)
            d["acao"], d["metodo"] = tk, "fhs_gjr_alvo+252"
            frames.append(d)
            print(f"{tk}: {len(d)} datas, {time.time() - t0:.0f}s", flush=True)
        pd.concat(frames, ignore_index=True).to_pickle(out)
    report(out, N)


if __name__ == "__main__":
    main()
