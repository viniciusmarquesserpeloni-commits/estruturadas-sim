"""Fase 2 da revisão: GARCH/GJR, Monte Carlo FHS, marcação da saída com GARCH e calibração walk-forward."""
import math

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import minimize

from estruturadas import presets
from estruturadas.backtest import run_monte_carlo
from estruturadas.calibration import walk_forward
from estruturadas.early_exit import EarlyExitConfig, run_historical_exit, run_mc_exit
from estruturadas.garch import (_neg_loglik, expected_var, fhs_paths, filtered, fit_garch, start_params, term_var,
                                vol_panel)
from estruturadas.metrics import summarize, summarize_exit
from estruturadas.rng import Mulberry32, integers, uniforms


def gjr_series(n=3000, omega=1.2e-5, alpha=0.05, gamma=0.08, beta=0.88, seed=3):
    rng = np.random.default_rng(seed)
    h, out = omega / (1 - alpha - gamma / 2 - beta), np.empty(n)
    for t in range(n):
        e = math.sqrt(h) * rng.standard_normal()
        out[t] = e
        h = omega + (alpha + gamma * (e < 0)) * e * e + beta * h
    return out


def prices_from(lr, start="2014-01-02"):
    close = 40 * np.exp(np.cumsum(np.r_[0.0, lr]))
    idx = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame({"Close": close, "High": close * 1.01, "Low": close * 0.99}, index=idx)


def test_mulberry32_vectorizado_igual_ao_escalar():
    g = Mulberry32(123)
    np.testing.assert_array_equal(uniforms(123, 500), [g.uni() for _ in range(500)])
    g = Mulberry32(0)  # seed 0 usa a constante padrão
    np.testing.assert_array_equal(integers(0, 200, 37), [g.int(37) for _ in range(200)])


def test_ajuste_recupera_parametros_simulados():
    lr = gjr_series()
    g = fit_garch(lr, "gjr")
    assert abs(g.alpha - 0.05) < 0.04 and abs(g.gamma - 0.08) < 0.06 and abs(g.beta - 0.88) < 0.05
    assert abs(g.persistence - 0.97) < 0.02
    s = fit_garch(gjr_series(gamma=0.0, alpha=0.09), "garch")
    assert abs(s.alpha - 0.09) < 0.04 and abs(s.beta - 0.88) < 0.05 and s.gamma == 0.0
    # Nelder-Mead chega ao mesmo ótimo do otimizador do scipy, inclusive com um choque enorme no fim da série
    # (caso real: sem reinícios e com passo grande, o otimizador parava na borda p = 0,999)
    for x in (lr, np.r_[lr, -0.25, -0.04]):
        eps = x - x.mean()
        s2 = float(np.mean(eps * eps))
        ref = min(minimize(lambda v: _neg_loglik(v, eps, "gjr", s2), start_params("gjr", k), method="Nelder-Mead",
                           options={"xatol": 1e-10, "fatol": 1e-14, "maxiter": 40000, "maxfev": 80000}).fun
                  for k in (0, 1))
        fx = fit_garch(x, "gjr")
        assert -fx.loglik / len(x) - 0.5 * math.log(2 * math.pi) <= ref + 1e-9
        assert fx.persistence < 0.995


def test_previsao_e_vol_do_prazo():
    g = fit_garch(gjr_series(), "gjr")
    h1 = 3 * g.long_run_var
    assert expected_var(g, h1, 1) == pytest.approx(h1)
    assert term_var(g, h1, 1) == pytest.approx(h1)
    assert term_var(g, h1, 21) < h1 and term_var(g, h1, 21) > g.long_run_var
    assert term_var(g, h1, 100_000) == pytest.approx(g.long_run_var, rel=1e-2)
    # média das previsões dia a dia = fórmula fechada
    assert term_var(g, h1, 63) == pytest.approx(np.mean(expected_var(g, h1, np.arange(1, 64))), rel=1e-12)
    vp = vol_panel(g, gjr_series(), 63)
    assert vp["meia_vida"] == pytest.approx(math.log(0.5) / math.log(g.persistence))


def test_fhs_sem_dinamica_vira_bootstrap_iid():
    lr = gjr_series(n=800)
    eps = lr - lr.mean()
    s2 = float(np.mean(eps * eps))
    g = filtered(lr, s2, 0.0, 0.0, 0.0, "garch")
    np.testing.assert_allclose(g.h, s2)
    close, *_ = fhs_paths(g, 40, 25, seed=4, drift_daily=0.0002, intraday=False)
    idx = integers(4, 40 * 25, len(g.z)).reshape(40, 25)
    expected = np.exp(np.cumsum(0.0002 - 0.5 * s2 + math.sqrt(s2) * g.z[idx], axis=1))
    np.testing.assert_allclose(close, expected, rtol=1e-12)


def test_fhs_media_e_choque_de_vol():
    lr = gjr_series()
    px = prices_from(lr)
    s = presets.collar_ki(1.0, 1.06, 1.12)
    r = run_monte_carlo(s, px, 63, 0.0, "fhs_garch", 20_000, drift="cdi", cdi_annual=0.12, seed=1)
    assert r.meta["method"] == "fhs_garch" and r.meta["garch"] is not None
    sT = r.df["acao_final"].to_numpy()
    se = sT.std(ddof=1) / math.sqrt(len(sT))
    assert abs(sT.mean() - 1.12 ** (63 / 252)) < 4 * se + 2e-3
    # mesma série com um choque grande no fim: vol de hoje sobe e a P(barreira) também
    lr2 = np.r_[lr, -0.15]
    r2 = run_monte_carlo(s, prices_from(lr2), 63, 0.0, "fhs_garch", 20_000, drift="cdi", cdi_annual=0.12, seed=1)
    assert r2.meta["sigma"] > 1.3 * r.meta["sigma"]
    assert summarize(r2)["p_barreira"] > summarize(r)["p_barreira"]
    # cenário com vol ×1,2: σ escala e os caminhos de variância ficam guardados para a saída antecipada
    r3 = run_monte_carlo(s, px, 63, 0.0, "fhs_garch", 2000, drift="cdi", cdi_annual=0.12, vol_scale=1.2,
                         garch=r.meta["garch"])
    assert r3.meta["sigma"] == pytest.approx(1.2 * r.meta["sigma"])
    assert r3.meta["paths_exit_var"].shape == (2000, 63)


def test_saida_antecipada_com_vol_garch():
    lr = gjr_series(n=1500)
    px = prices_from(lr)
    s = presets.PRESETS["collar_ki"].builder()
    cf = np.cumprod(np.r_[1.0, np.full(len(px) - 1, 1.12 ** (1 / 252) - 1) + 1])
    from estruturadas.backtest import run_historical
    h = run_historical(s, px, 63, 0.0, cdi_factor=cf)
    a = run_historical_exit(s, px, 63, 0.0, EarlyExitConfig(), cf, h.df["retorno"].to_numpy())
    b = run_historical_exit(s, px, 63, 0.0, EarlyExitConfig(vol_mode="rolling"), cf, h.df["retorno"].to_numpy())
    for x in (a, b):
        sm = summarize_exit(x)
        assert 0 <= sm["p_saida"] <= 1 and np.isfinite(x.df["retorno_final"]).all()
    assert not np.array_equal(a.df["retorno_final"], b.df["retorno_final"])
    m = run_monte_carlo(s, px, 63, 0.0, "fhs_garch", 3000, cdi_annual=0.12)
    e = run_mc_exit(s, m.meta["paths_exit"], 63, 0.0, EarlyExitConfig(), m.df["retorno"].to_numpy(), m.meta["sigma"],
                    0.12, var_paths=m.meta["paths_exit_var"], garch=m.meta["garch"])
    assert len(e.df) == 2000 and np.isfinite(e.df["retorno_final"]).all()
    # histórico curto demais para o GARCH: a marcação volta para a vol móvel sem erro
    short = px.iloc[:200]
    hs = run_historical(s, short, 21, 0.0, cdi_factor=cf[:200])
    run_historical_exit(s, short, 21, 0.0, EarlyExitConfig(), cf[:200], hs.df["retorno"].to_numpy())


def test_calibracao_walk_forward():
    lr = gjr_series(n=1100)
    px = prices_from(lr)
    s = presets.collar_ki(1.0, 1.06, 1.12)
    cal = walk_forward(s, px, 21, 0.0, "fhs_garch", step=40, n_paths=300, cdi_annual=0.1)
    df = cal.df
    assert len(df) == len(range(504, len(px) - 21, 40))
    from estruturadas.backtest import run_historical
    h = run_historical(s, px, 21, 0.0).df
    real = (h["retorno"] > 1e-9).to_numpy(dtype=float)
    t0 = 504
    assert df["real_lucro"].iloc[0] == real[t0]
    assert df["clim_lucro"].iloc[0] == pytest.approx(real[: t0 - 21 + 1].mean())
    br = cal.brier()
    assert list(br["chave"]) == ["lucro", "cdi", "barreira"]
    assert ((br["brier_modelo"] >= 0) & (br["brier_modelo"] <= 1)).all()
    rel = cal.reliability("barreira")
    assert rel["n"].sum() == len(df)
    with pytest.raises(ValueError):
        walk_forward(s, px.iloc[:400], 21, 0.0)
