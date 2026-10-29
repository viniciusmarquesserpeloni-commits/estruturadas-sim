"""Gera tests/js/fixtures.json com resultados do motor Python, usados para validar a porta em JS.

    python scripts/make_js_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from estruturadas import io as sio  # noqa: E402
from estruturadas import presets  # noqa: E402
from estruturadas.backtest import run_ex_post, run_historical  # noqa: E402
from estruturadas.data import (b3_holidays, cdi_factor_on_index, count_trading_days,  # noqa: E402
                               previous_business_day, term_from_dates)
from estruturadas.legs import evaluate_paths, expiry_payoff, payoff_profile_summary, returns_from_payoff  # noqa: E402
from estruturadas.metrics import default_variations, profitability_table, summarize  # noqa: E402
from estruturadas.pricing import bs_price  # noqa: E402


def clean(x):
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, np.ndarray):
        return clean(x.tolist())
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, pd.Timestamp):
        return x.strftime("%Y-%m-%d")
    return x


def synthetic_prices(n=420, seed=11):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.022, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.012, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.012, n)))
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close}, index=idx)


def main() -> None:
    rng = np.random.default_rng(2024)
    out: dict = {"presets": {}, "bs": [], "historico": [], "calendario": {}, "expost": []}

    # Payoffs de cada preset em caminhos aleatórios (fechamento e intradiário)
    for key, p in presets.PRESETS.items():
        s = p.builder()
        cost = 0.0 if s.has_stock else 0.05
        close = np.exp(np.cumsum(rng.normal(0, 0.06, (40, 15)), axis=1))
        high = close * (1 + np.abs(rng.normal(0, 0.03, close.shape)))
        low = close * (1 - np.abs(rng.normal(0, 0.03, close.shape)))
        ev_c = evaluate_paths(s, close, high, low, "close")
        ev_i = evaluate_paths(s, close, high, low, "intraday")
        grid = np.round(np.linspace(0.4, 1.8, 57), 6)
        prof = payoff_profile_summary(s, cost)
        var = default_variations(s)
        out["presets"][key] = {
            "json": sio.structure_to_dict(s), "cost": cost,
            "close": close, "high": high, "low": low,
            "payoff_close": ev_c.payoff, "payoff_intra": ev_i.payoff,
            "ret_close": returns_from_payoff(ev_c.payoff, cost, s.has_stock),
            "hit_close": ev_c.any_hit.astype(int), "hit_intra": ev_i.any_hit.astype(int),
            "grid": grid, "exp_none": expiry_payoff(s, grid, "none"), "exp_all": expiry_payoff(s, grid, "all"),
            "profile": {k: prof[k] for k in ("return_max", "return_min", "gain_unlimited", "loss_unlimited")},
            "variations": var,
            "table": profitability_table(s, cost, var, formatted=False).drop(columns=["Variação da ação"]).to_numpy(),
        }

    # Black-Scholes
    for kind in ("call", "put"):
        for K in (0.7, 0.9, 1.0, 1.1, 1.3):
            for T in (0.1, 0.5, 1.0, 2.0):
                for sig in (0.1, 0.3, 0.6):
                    out["bs"].append([kind, K, T, sig, float(bs_price(kind, 1.0, K, T, 0.12, 0.02, sig))])

    # Backtest histórico numa série sintética
    prices = synthetic_prices()
    out["prices"] = {"d": [d.strftime("%Y-%m-%d") for d in prices.index], "c": prices["Close"].to_numpy(),
                     "h": prices["High"].to_numpy(), "l": prices["Low"].to_numpy()}
    cf = cdi_factor_on_index(prices.index, None, 0.10)
    for key, N, mon in (("protecao_total", 40, "close"), ("fko", 30, "intraday"), ("collar_ki", 60, "intraday"),
                        ("booster", 21, "close")):
        s = presets.PRESETS[key].builder()
        res = run_historical(s, prices, N, 0.0, mon, 0.002, cf)
        summ = summarize(res)
        out["historico"].append({"preset": key, "N": N, "monitoring": mon, "extra": 0.002,
                                 "ret": res.df["retorno"].to_numpy(), "hit": res.df["barreira_qualquer"].astype(int).to_numpy(),
                                 "cdi": res.df["retorno_cdi"].to_numpy(), "n_effective": res.n_effective,
                                 "summary": {k: v for k, v in summ.items() if k not in ("barreiras", "ci")},
                                 "ci": summ["ci"]})

    # Ex-post
    for key, t0, exp, mon in (("collar_ki", "2020-02-03", "2020-08-14", "intraday"), ("fko", "2020-06-01", "2021-06-01", "close"),
                              ("protecao_total", "2021-03-01", "2022-12-30", "close")):
        s = presets.PRESETS[key].builder()
        r = run_ex_post(s, prices, t0, exp, 0.0, mon)
        out["expost"].append({"preset": key, "trade": t0, "expiry": exp, "monitoring": mon, "obs": r.obs_date,
                              "last": r.last_date, "finished": r.finished, "ret": r.retorno, "n": r.n_days_elapsed,
                              "hits": [[lbl, hit, when] for lbl, (hit, when) in r.hits.items()]})

    # Saída antecipada (marcação diária, gatilho de % do CDI)
    from estruturadas.early_exit import (EarlyExitConfig, cdi_rate_series, rolling_vol, run_ex_post_exit,
                                         run_historical_exit, structure_value)
    from estruturadas.pricing import barrier_price
    days = np.arange(len(prices))
    cf_var = np.cumprod(np.r_[1.0, (1 + 0.00035 + 0.00015 * np.sin(days[1:] / 40.0))])
    out["saida"] = {"cdiF": cf_var, "rolling_vol": rolling_vol(prices["Close"].to_numpy(), 63),
                    "cdi_rate": cdi_rate_series(cf_var), "barreira": [], "valor": [], "historico": [], "expost": []}
    for kind in ("call", "put"):
        for barrier, H in (("up_in", 1.3), ("up_out", 1.3), ("down_in", 0.75), ("down_out", 0.75)):
            for K in (0.7, 1.0, 1.4):
                for S in (0.9, 1.0, 1.1):
                    v = float(barrier_price(kind, barrier, S, K, H, 0.6, 0.11, 0.01, 0.35))
                    out["saida"]["barreira"].append([kind, barrier, S, K, H, v])
    pt = presets.protecao_total_bbdc4()
    for S, mx, mn, T, mon in ((1.0, 1.0, 1.0, 1.0, "close"), (1.2, 1.25, 0.95, 0.5, "close"),
                              (1.1, 1.4, 0.9, 0.3, "close"), (0.85, 1.1, 0.8, 0.2, "intraday")):
        v = float(structure_value(pt, np.array([S]), np.array([mx]), np.array([mn]), T, np.array([0.12]),
                                  np.array([0.3]), mon)[0])
        out["saida"]["valor"].append([S, mx, mn, T, mon, v])
    cases = [("protecao_total", 60, "close", EarlyExitConfig()),
             ("protecao_total", 60, "close", EarlyExitConfig(calibrate=False, delay=0)),
             ("collar_ki", 45, "intraday", EarlyExitConfig(min_days=10, exit_spread=0.02, delay=2)),
             ("fko", 50, "close", EarlyExitConfig(vol_mode="fixed", vol_add=0.0, trigger=1.2)),
             ("booster", 30, "close", EarlyExitConfig(exit_spread=0.0))]
    for key, N, mon, cfg in cases:
        s = presets.PRESETS[key].builder()
        h = run_historical(s, prices, N, 0.0, mon, 0.0, cf_var)
        ee = run_historical_exit(s, prices, N, 0.0, cfg, cf_var, h.df["retorno"].to_numpy(), mon)
        d = ee.df
        out["saida"]["historico"].append({
            "preset": key, "N": N, "monitoring": mon, "cfg": vars(cfg),
            "gatilho": d["gatilho"].astype(int).to_numpy(), "dia_gatilho": d["dia_gatilho"].to_numpy(),
            "saida": d["saida_antecipada"].astype(int).to_numpy(), "dia_saida": d["dia_saida"].to_numpy(),
            "retorno_final": d["retorno_final"].to_numpy(), "cdi_periodo": d["cdi_periodo"].to_numpy(),
            "cdi_inicio": d["cdi_inicio"].to_numpy()})
    for key, t0, N, cfg in (("protecao_total", "2020-03-02", 120, EarlyExitConfig()),
                            ("collar", "2020-09-01", 400, EarlyExitConfig(delay=0, exit_spread=0.0))):
        s = presets.PRESETS[key].builder()
        x = run_ex_post_exit(s, prices, t0, N, 0.0, cfg, cf_var)
        out["saida"]["expost"].append({"preset": key, "trade": t0, "N": N, "cfg": vars(cfg),
                                       "dates": [d.strftime("%Y-%m-%d") for d in x.dates], "ret": x.ret,
                                       "threshold": x.threshold,
                                       "trigger": x.trigger_date.strftime("%Y-%m-%d") if x.trigger_date is not None else None,
                                       "exit": x.exit_date.strftime("%Y-%m-%d") if x.exit_date is not None else None,
                                       "exit_return": x.exit_return})

    # Fase 1 da revisão: gerador compartilhado, IC por block bootstrap, ajuste de regime, CVaR
    from estruturadas.metrics import block_bootstrap_ci, cvar, summarize_exit
    from estruturadas.rng import Mulberry32
    g = Mulberry32(2026)
    rr = np.random.default_rng(9)
    ind = (np.cumsum(rr.normal(size=700)) > 0).astype(float)
    out["fase1"] = {
        "rng": [g.uni() for _ in range(25)],
        "rng_int": (lambda m: [m.int(13) for _ in range(20)])(Mulberry32(77)),
        "ci": [{"ind": ind, "block": b, "ci": block_bootstrap_ci(ind, b)} for b in (1, 21, 63, 700)],
        "cvar": [[[0.03, -0.2, 0.1, -0.05, 0.0, 0.07, -0.01], 0.05, cvar([0.03, -0.2, 0.1, -0.05, 0.0, 0.07, -0.01], 0.05)],
                 [[1, 2, 3, 4], 0.5, cvar([1, 2, 3, 4], 0.5)]],
        "regime": [], "saida_regime": [],
    }
    CDI_REF = 0.1365
    for key, N, mon in (("collar_ki", 63, "close"), ("protecao_total", 120, "intraday"), ("fko", 40, "close")):
        s = presets.PRESETS[key].builder()
        res = run_historical(s, prices, N, 0.0, mon, 0.001, cf_var, cdi_ref=CDI_REF, regime_adjust=True)
        summ = summarize(res)
        out["fase1"]["regime"].append({"preset": key, "N": N, "monitoring": mon, "extra": 0.001,
                                       "ret": res.df["retorno"].to_numpy(), "ret_raw": res.df["retorno_sem_ajuste"].to_numpy(),
                                       "hit": res.df["barreira_qualquer"].astype(int).to_numpy(),
                                       "summary": {k: v for k, v in summ.items() if k not in ("barreiras", "ci")},
                                       "ci": summ["ci"]})
        if key != "fko":
            ee = run_historical_exit(s, prices, N, 0.0, EarlyExitConfig(), cf_var, res.df["retorno"].to_numpy(), mon,
                                     0.001, cdi_ref=CDI_REF, regime_adjust=True)
            se = summarize_exit(ee)
            out["fase1"]["saida_regime"].append({
                "preset": key, "N": N, "monitoring": mon, "dia_saida": ee.df["dia_saida"].to_numpy(),
                "retorno_final": ee.df["retorno_final"].to_numpy(), "cdi_periodo": ee.df["cdi_periodo"].to_numpy(),
                "summary": {k: v for k, v in se.items() if k != "ci"}, "ci": se["ci"]})
    out["fase1"]["cdi_ref"] = CDI_REF

    # Calendário
    out["calendario"] = {
        "feriados": {str(y): [d.isoformat() for d in b3_holidays(y)] for y in (2025, 2026, 2027)},
        "anterior": [[d, previous_business_day(d)] for d in ("2026-11-25", "2026-11-23", "2027-01-01", "2026-02-18", "2027-03-29")],
        "contagem": [[a, b, count_trading_days(a, b)] for a, b in (("2026-11-18", "2026-11-24"), ("2026-10-19", "2027-10-19"),
                                                                    ("2025-12-20", "2026-03-10"))],
        "termo_com_serie": [[a, b, *term_from_dates(a, b, prices.index)] for a, b in (("2020-03-02", "2021-03-01"), ("2021-06-01", "2021-08-10"))],
    }
    path = ROOT / "tests" / "js" / "fixtures.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(out)), encoding="utf-8")
    print(f"OK: {path} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
