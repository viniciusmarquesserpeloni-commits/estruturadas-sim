"""Experimento 4 — qual previsor de volatilidade é melhor para o prazo das estruturas?

Walk-forward em várias ações: a cada 5 pregões (a partir de 3 anos de dados), só com dados até a data, prevê a
variância diária média dos próximos N pregões e compara com a realizada (média dos retornos² em [t, t+N)).

Previsores: GJR-GARCH e GARCH(1,1) do projeto (vol do prazo; reestimados a cada 252 pregões), EWMA 0,94,
variância móvel de 63 e 252 pregões, variância de todo o histórico até a data, HAR em logs (regressão direta do
log da variância futura nos logs das variâncias de 5/21/63/252 pregões e da amplitude máxima–mínima de
Parkinson de 5/21 pregões) e médias geométricas.

Perdas: QLIKE = RV/F − ln(RV/F) − 1 (robusta ao ruído do alvo; Patton, 2011), erro quadrático do log e viés
(média de ln(RV/F): negativo = previsão alta demais). Também o viés logo depois de choques extremos.

Uso: python scripts/pesquisa/exp4_vol.py <pasta com os JSON de preços do site> [saida.json]
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from estruturadas.garch import fit_garch, garch_filter, term_var  # noqa: E402

HORIZONS = (21, 63, 126, 252)
STEP, START, REFIT = 5, 756, 252


def load(path):
    raw = json.load(open(path))
    c = np.array(raw["ca"] if raw.get("ca") else raw["c"], float)
    f = c / np.array(raw["c"], float)
    h, lo = np.array(raw["h"], float) * f, np.array(raw["l"], float) * f
    h, lo = np.where(h > 0, np.maximum(h, c), c), np.where(lo > 0, np.minimum(lo, c), c)
    lr = np.diff(np.log(c))
    park = np.log(h[1:] / lo[1:]) ** 2 / (4 * np.log(2))  # variância diária pela amplitude (sem o gap de abertura)
    return lr, park


def rolling_mean(x, w):
    """m[t] = média de x[t-w:t] (só passado); nan no início."""
    cs = np.concatenate([[0.0], np.cumsum(x)])
    out = np.full(len(x) + 1, np.nan)
    out[w:] = (cs[w:] - cs[:-w]) / w
    return out


def har_forecasts(r2, park, dates, N):
    """Regressão direta em logs, expansiva, reestimada a cada 63 datas; alvo conhecido só até t − N."""
    eps = 1e-10
    feats = np.column_stack([np.log(rolling_mean(r2, w) + eps) for w in (5, 21, 63, 252)]
                            + [np.log(rolling_mean(park, w) + eps) for w in (5, 21)])
    n = len(r2)
    fut = np.full(n + 1, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(r2)])
    idx = np.arange(0, n - N + 1)
    fut[idx] = (cs[idx + N] - cs[idx]) / N
    y = np.log(fut + eps)
    out = np.full(len(dates), np.nan)
    beta, s2, last = None, 0.0, -10**9
    for j, t in enumerate(dates):
        if beta is None or t - last >= 63:
            tr = np.arange(252, t - N + 1)
            X = np.column_stack([np.ones(len(tr)), feats[tr]])
            beta, *_ = np.linalg.lstsq(X, y[tr], rcond=None)
            s2 = float(np.var(y[tr] - X @ beta))
            last = t
        out[j] = np.exp(np.r_[1.0, feats[t]] @ beta + 0.5 * s2)
    return out


def run_ticker(lr, park):
    n = len(lr)
    r2 = lr * lr
    res = {}
    # GARCH/GJR: parâmetros reestimados a cada REFIT; h[t] = variância prevista para lr[t]
    # "gjr_w": o mesmo GJR, mas com os retornos limitados a ±5 desvios robustos (MAD, só com dados até T) na
    # estimação e no filtro — um choque absurdo (ou erro de dado) deixa de dominar o ajuste
    hs = {m: np.full(n + 1, np.nan) for m in ("gjr", "garch", "gjr_w")}
    fits = {m: {} for m in hs}
    for T in range(START, n, REFIT):
        for m in hs:
            x = lr
            if m == "gjr_w":
                med = np.median(lr[:T])
                cap = 5 * 1.4826 * np.median(np.abs(lr[:T] - med))
                x = np.clip(lr, med - cap, med + cap)
            f = fit_garch(x[:T], "gjr" if m == "gjr_w" else m)
            eps = x - f.mean
            h = garch_filter(eps, f.omega, f.alpha, f.gamma, f.beta, f.s2)
            hs[m][T:T + REFIT] = h[T:T + REFIT]
            for t in range(T, min(T + REFIT, n + 1)):
                fits[m][t] = f
    ew = np.empty(n + 1)
    ew[0] = r2[:252].mean()
    for t in range(n):
        ew[t + 1] = 0.94 * ew[t] + 0.06 * r2[t]
    roll63, roll252 = rolling_mean(r2, 63), rolling_mean(r2, 252)
    cs = np.concatenate([[0.0], np.cumsum(r2)])
    sig_unc = np.sqrt(r2.mean())
    for N in HORIZONS:
        dates = np.arange(START, n - N + 1, STEP)
        rv = (cs[dates + N] - cs[dates]) / N
        F = {
            "gjr": np.array([float(term_var(fits["gjr"][t], hs["gjr"][t], N)) for t in dates]),
            "garch": np.array([float(term_var(fits["garch"][t], hs["garch"][t], N)) for t in dates]),
            "gjr_w": np.array([float(term_var(fits["gjr_w"][t], hs["gjr_w"][t], N)) for t in dates]),
            "ewma": ew[dates], "movel63": roll63[dates], "movel252": roll252[dates],
            "longo": cs[dates] / dates, "har": har_forecasts(r2, park, dates, N),
        }
        F["gjr+longo"] = np.sqrt(F["gjr"] * F["longo"])
        F["gjr+har"] = np.sqrt(F["gjr"] * F["har"])
        F["har+longo"] = np.sqrt(F["har"] * F["longo"])
        F["gjr_w+longo"] = np.sqrt(F["gjr_w"] * F["longo"])
        F["gjr_w+252"] = np.sqrt(F["gjr_w"] * F["movel252"])
        # datas até 10 pregões depois de um choque de mais de 4 desvios (do período inteiro)
        big = np.abs(lr) > 4 * sig_unc
        recent = np.array([big[max(0, t - 10):t].any() for t in dates])
        ok = (rv > 1e-7) & np.all([np.isfinite(v) & (v > 1e-7) for v in F.values()], axis=0)  # sem negociação: fora
        res[N] = {"dates": dates[ok], "rv": rv[ok], "F": {k: v[ok] for k, v in F.items()}, "shock": recent[ok]}
    return res


def losses(rv, f):
    x = rv / f
    return {"qlike": float(np.mean(x - np.log(x) - 1)), "mse_log": float(np.mean(np.log(x) ** 2)),
            "vies": float(np.mean(np.log(x))), "razao_medias": float(rv.mean() / f.mean())}


def main():
    folder = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    files = sorted(f for f in glob.glob(os.path.join(folder, "*.json")) if not f.endswith(("cdi.json", "index.json")))
    allres = {}
    for f in files:
        tk = os.path.basename(f)[:-5]
        t0 = time.time()
        lr, park = load(f)
        allres[tk] = run_ticker(lr, park)
        print(f"{tk}: {len(lr)} retornos, {time.time() - t0:.0f}s", flush=True)
    summary = {}
    for N in HORIZONS:
        names = list(next(iter(allres.values()))[N]["F"])
        tab = {k: {"qlike": [], "mse_log": [], "vies": [], "razao_medias": [], "vies_choque": [], "rm_choque": [], "razao": []} for k in names}
        for tk, r in allres.items():
            d = r[N]
            for k in names:
                ls = losses(d["rv"], d["F"][k])
                for a in ("qlike", "mse_log", "vies", "razao_medias"):
                    tab[k][a].append(ls[a])
                if d["shock"].any():
                    tab[k]["vies_choque"].append(float(np.mean(np.log(d["rv"][d["shock"]] / d["F"][k][d["shock"]]))))
                    tab[k]["rm_choque"].append(float(d["rv"][d["shock"]].mean() / d["F"][k][d["shock"]].mean()))
                tab[k]["razao"].append(np.sqrt(d["rv"] / d["F"][k]))
        best = [min(names, key=lambda k: tab[k]["qlike"][i]) for i in range(len(allres))]
        print(f"\n=== Horizonte {N} pregões ({len(allres)} ações) — médias entre ações ===")
        print(f"{'previsor':12s} {'QLIKE':>7s} {'EQ log':>7s} {'viés log':>8s} {'RV/F médias':>11s} {'pós-choque: viés log':>20s} {'RV/F':>6s} {'melhor em':>10s}   razão vol realizada/prevista (p5 p25 p50 p75 p95)")
        summary[N] = {}
        for k in sorted(names, key=lambda k: np.median(tab[k]["qlike"])):
            rz = np.concatenate(tab[k]["razao"])
            q = np.percentile(rz, [5, 25, 50, 75, 95])
            row = {"qlike": float(np.median(tab[k]["qlike"])), "qlike_media": float(np.mean(tab[k]["qlike"])),
                   "mse_log": float(np.median(tab[k]["mse_log"])), "vies": float(np.median(tab[k]["vies"])),
                   "razao_medias": float(np.median(tab[k]["razao_medias"])),
                   "vies_choque": float(np.median(tab[k]["vies_choque"])), "rm_choque": float(np.median(tab[k]["rm_choque"])),
                   "melhor": best.count(k), "razao_q": q.tolist()}
            summary[N][k] = row
            print(f"{k:12s} {row['qlike']:7.4f} {row['mse_log']:7.4f} {row['vies']:+8.3f} {row['razao_medias']:11.2f} {row['vies_choque']:+20.3f} {row['rm_choque']:6.2f} {row['melhor']:10d}   "
                  + " ".join(f"{v:.2f}" for v in q))
    if out:
        json.dump(summary, open(out, "w"), indent=1)
        import pickle
        pickle.dump(allres, open(out.replace(".json", ".pkl"), "wb"))


if __name__ == "__main__":
    main()
