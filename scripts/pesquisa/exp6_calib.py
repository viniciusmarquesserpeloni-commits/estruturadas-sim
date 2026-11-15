"""Experimento 6 — as probabilidades do simulador acertam fora da amostra? (várias ações, com significância)

Roda o teste walk-forward do próprio projeto (estruturadas.calibration.walk_forward) em várias ações e métodos e
junta tudo:

* Brier do modelo × chute fixo (frequência histórica até a data) e ganho relativo, por indicador;
* significância do ganho: estatística t de Diebold-Mariano sobre a média entre ações da diferença de perdas em
  cada data, com erro padrão HAC (janelas se sobrepõem e as ações andam juntas);
* viés (previsto − realizado), inclinação de calibração (regressão do resultado na previsão) e decomposição de
  Murphy (confiabilidade, resolução);
* mistura: Brier de w·modelo + (1 − w)·chute fixo.

Uso: python scripts/pesquisa/exp6_calib.py <pasta de dados> <saida.pkl> [preset] [N] [métodos separados por vírgula]
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
from estruturadas import presets  # noqa: E402
from estruturadas.calibration import walk_forward  # noqa: E402
from estruturadas.data import cdi_factor_on_index  # noqa: E402

START = "2010-01-01"
EVENTS = ("lucro", "cdi", "barreira")


def load_prices(path):
    raw = json.load(open(path))
    c = np.array(raw["ca"] if raw.get("ca") else raw["c"], float)
    f = c / np.array(raw["c"], float)
    h, lo = np.array(raw["h"], float) * f, np.array(raw["l"], float) * f
    df = pd.DataFrame({"Close": c, "High": np.where(h > 0, np.maximum(h, c), c), "Low": np.where(lo > 0, np.minimum(lo, c), c)},
                      index=pd.to_datetime(raw["d"]))
    return df[df.index >= START]


def structure_for(key):
    if key == "collar_ki":
        return presets.collar_ki(1.0, 1.06, 1.12)
    if key == "fko":
        return presets.forward_knock_out(1.10, 0.70)
    if key == "dois_lados":
        # evento que depende quase só da vol: tocar +12% ou −12% em algum fechamento (barreiras dos dois lados)
        from estruturadas.legs import Leg, Structure
        return Structure("Toque em ±12%", [Leg("stock", +1), Leg("call", -1, 1.5, "up_in", 1.12),
                                           Leg("put", +1, 0.5, "down_in", 0.88)])
    return presets.PRESETS[key].builder()


def run(folder, out, key, N, methods):
    cdi = json.load(open(os.path.join(folder, "cdi.json")))
    cdi = pd.Series(cdi["r"], index=pd.to_datetime(cdi["d"]))
    s = structure_for(key)
    frames = []
    for f in sorted(glob.glob(os.path.join(folder, "*.json"))):
        tk = os.path.basename(f)[:-5]
        if tk in ("cdi", "index"):
            continue
        px = load_prices(f)
        F = cdi_factor_on_index(px.index, cdi, 0.1365)
        for m in methods:
            t0 = time.time()
            try:
                cal = walk_forward(s, px, N, 0.0, m, cdi_factor=F, drift=os.environ.get("EXP_DRIFT", "cdi"))
            except ValueError as e:
                print(tk, m, "pulado:", e, flush=True)
                continue
            d = cal.df.copy()
            d["acao"], d["metodo"] = tk, m
            frames.append(d)
            print(f"{tk} {m}: {len(d)} datas, {time.time() - t0:.0f}s", flush=True)
    pd.concat(frames, ignore_index=True).to_pickle(out)


def hac_t(x, lags):
    x = np.asarray(x, float)
    n = len(x)
    d = x - x.mean()
    v = float(d @ d) / n
    for k in range(1, min(lags, n - 1) + 1):
        v += 2 * (1 - k / (lags + 1)) * float(d[k:] @ d[:-k]) / n
    return x.mean() / math.sqrt(max(v, 1e-300) / n)


def murphy(p, y, bins=10):
    b = np.minimum((p * bins).astype(int), bins - 1)
    rel = res = 0.0
    for i in range(bins):
        m = b == i
        if m.any():
            rel += m.sum() * (p[m].mean() - y[m].mean()) ** 2
            res += m.sum() * (y[m].mean() - y.mean()) ** 2
    return rel / len(p), res / len(p), y.mean() * (1 - y.mean())


def report(path, N, step=10):
    df = pd.read_pickle(path)
    lags = math.ceil(N / step) + 2
    for m, g in df.groupby("metodo"):
        print(f"\n=== {m}: {g['acao'].nunique()} ações, {len(g)} previsões ===")
        print(f"{'indicador':9s} {'Brier mod':>9s} {'Brier chute':>11s} {'ganho':>7s} {'t (DM-HAC)':>10s} {'ações com ganho':>15s} "
              f"{'previsto':>8s} {'real':>6s} {'inclin.':>7s} {'confiab.':>8s} {'resol.':>7s} | Brier da mistura w=0,25/0,5/0,75")
        for k in EVENTS:
            if f"prev_{k}" not in g or g[f"prev_{k}"].isna().all():
                continue
            p, c, y = (g[f"{a}_{k}"].to_numpy(float) for a in ("prev", "clim", "real"))
            bm, bc = np.mean((p - y) ** 2), np.mean((c - y) ** 2)
            # média entre ações em quinzenas de calendário (as datas de teste não coincidem entre as ações)
            bucket = ((pd.to_datetime(g["data"]) - pd.Timestamp("2000-01-01")).dt.days // 14).to_numpy()
            dd = g.assign(d=(c - y) ** 2 - (p - y) ** 2, q=bucket).groupby("q")["d"].mean().sort_index()
            wins = sum(np.mean((x[f"clim_{k}"] - x[f"real_{k}"]) ** 2) > np.mean((x[f"prev_{k}"] - x[f"real_{k}"]) ** 2)
                       for _, x in g.groupby("acao"))
            slope = np.cov(p, y)[0, 1] / np.var(p, ddof=1)
            rel, res, unc = murphy(p, y)
            mix = [np.mean((w * p + (1 - w) * c - y) ** 2) for w in (0.25, 0.5, 0.75)]
            print(f"{k:9s} {bm:9.4f} {bc:11.4f} {1 - bm / bc:+7.1%} {hac_t(dd.to_numpy(), lags):10.2f} "
                  f"{wins:8d}/{g['acao'].nunique():<6d} {p.mean():8.1%} {y.mean():6.1%} {slope:7.2f} {rel:8.4f} {res:7.4f} | "
                  + " ".join(f"{v:.4f}" for v in mix))


if __name__ == "__main__":
    folder, out = sys.argv[1], sys.argv[2]
    key = sys.argv[3] if len(sys.argv) > 3 else "collar_ki"
    N = int(sys.argv[4]) if len(sys.argv) > 4 else 63
    methods = sys.argv[5].split(",") if len(sys.argv) > 5 else ["fhs_garch", "bootstrap", "gbm"]
    if not os.path.exists(out):
        run(folder, out, key, N, methods)
    report(out, N)
