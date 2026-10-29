"""Fase 1 da revisão metodológica: CDI de hoje e ajuste de regime, intervalos de confiança, drift
controlado, bootstrap com máxima/mínima, grade de cenários e CVaR."""
import numpy as np
import pandas as pd
import pytest

from estruturadas import presets
from estruturadas.backtest import (bootstrap_drift_daily, bootstrap_ohlc_paths, drift_annual, ohlc_log_returns,
                                   regime_factor, run_historical, run_monte_carlo, run_scenarios)
from estruturadas.data import latest_cdi_annual
from estruturadas.early_exit import EarlyExitConfig, run_historical_exit
from estruturadas.metrics import block_bootstrap_ci, cvar, summarize, summarize_exit
from estruturadas.rng import Mulberry32


def _prices(n=900, seed=3, vol=0.02):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    c = 40 * np.exp(np.cumsum(rng.normal(0.0004, vol, n)))
    h = c * (1 + np.abs(rng.normal(0, 0.008, n)))
    lo = c * (1 - np.abs(rng.normal(0, 0.008, n)))
    return pd.DataFrame({"Open": c, "High": h, "Low": lo, "Close": c}, index=idx)


def _cf(n, annual):
    return np.cumprod(np.r_[1.0, np.full(n - 1, (1 + annual) ** (1 / 252))])


def test_regime_factor_is_one_when_cdi_equals_reference():
    px = _prices()
    cf = _cf(len(px), 0.12)
    np.testing.assert_allclose(regime_factor(cf, 63, 0.12), 1.0, atol=1e-12)
    s = presets.collar_ki(1.0, 1.06, 1.12)
    a = run_historical(s, px, 63, 0.0, cdi_factor=cf, cdi_ref=0.12, regime_adjust=False)
    b = run_historical(s, px, 63, 0.0, cdi_factor=cf, cdi_ref=0.12, regime_adjust=True)
    np.testing.assert_allclose(a.df["retorno"], b.df["retorno"], atol=1e-12)
    assert b.meta["regime_adjust"] and not a.meta["regime_adjust"]
    # sem série de CDI o ajuste é desligado
    c = run_historical(s, px, 63, 0.0, cdi_factor=None, cdi_ref=0.12, regime_adjust=True)
    assert not c.meta["regime_adjust"]


def test_fixed_floor_structure_loses_against_todays_cdi():
    # épocas de CDI baixo (5%) inflam estruturas com piso fixo; contra o CDI de hoje (14%) elas perdem
    px = _prices()
    cf = _cf(len(px), 0.05)
    s = presets.protecao_total_bbdc4()
    res = run_historical(s, px, 249, 0.0, cdi_factor=cf, cdi_ref=0.14, regime_adjust=True)
    sm = summarize(res)
    assert sm["p_cdi"] < sm["p_cdi_epoca"]
    assert sm["cdi_hoje"] == pytest.approx(1.14 ** (249 / 252) - 1)


def test_block_bootstrap_ci_properties():
    rng = np.random.default_rng(1)
    x = (np.cumsum(rng.normal(size=2000)) > 0).astype(float)  # indicador muito autocorrelacionado
    lo, hi = block_bootstrap_ci(x, 63)
    assert lo <= x.mean() <= hi
    assert block_bootstrap_ci(x, 63) == (lo, hi)  # determinístico (seed fixa)
    lo1, hi1 = block_bootstrap_ci(x, 1)
    assert (hi1 - lo1) < (hi - lo)  # ignorar a sobreposição subestima a incerteza
    assert block_bootstrap_ci(np.ones(500), 20) == (1.0, 1.0)


def test_mulberry32_range_and_determinism():
    a, b = Mulberry32(2026), Mulberry32(2026)
    xs = [a.uni() for _ in range(1000)]
    assert xs == [b.uni() for _ in range(1000)]
    assert min(xs) >= 0 and max(xs) < 1 and 0.45 < np.mean(xs) < 0.55
    assert all(0 <= Mulberry32(7).int(10) < 10 for _ in range(50))


def test_drift_options_and_bootstrap_expected_return():
    assert drift_annual("cdi", 0.13) == 0.13
    assert drift_annual("cdi_premio", 0.13, 0.05) == pytest.approx(0.18)
    assert drift_annual("zero", 0.13) == 0.0 and drift_annual("historico", 0.13) is None
    assert drift_annual("personalizado", 0.13, custom=0.2) == 0.2
    px = _prices(n=2500, vol=0.018)
    lr, up, dn = ohlc_log_returns(px)
    N, mu = 63, 0.13
    close, high, low = bootstrap_ohlc_paths(lr, 20000, N, 20, 5, bootstrap_drift_daily(lr, mu), 1.0, up, dn)
    st = close[:, -1]
    target = (1 + mu) ** (N / 252)
    assert abs(st.mean() - target) < 4 * st.std() / np.sqrt(len(st))
    assert (high >= close - 1e-12).all() and (low <= close + 1e-12).all()


def test_mc_intraday_with_sampled_high_low_and_cvar():
    px = _prices(n=1500)
    s = presets.collar_ki(1.0, 1.06, 1.12)
    a = run_monte_carlo(s, px, 63, 0.0, n_paths=4000, cdi_annual=0.12, monitoring="close")
    b = run_monte_carlo(s, px, 63, 0.0, n_paths=4000, cdi_annual=0.12, monitoring="intraday")
    assert b.df["barreira_qualquer"].mean() >= a.df["barreira_qualquer"].mean()
    assert b.meta["paths_exit_high"].shape == b.meta["paths_exit"].shape
    sm = summarize(a)
    assert sm["cvar5"] <= sm["p5"] + 1e-12 and sm["ci"] == {}  # MC: sem IC de sorteio
    assert cvar([1, 2, 3, 4], 0.5) == 1.5


def test_scenario_grid_monotonicity():
    px = _prices(n=1500)
    s = presets.collar_ki(1.0, 1.06, 1.12)
    g = run_scenarios(s, px, 63, 0.0, cdi_annual=0.12, n_paths=3000)
    assert len(g) == 9
    for drift in ("zero", "cdi", "cdi_premio"):
        sub = g[g.drift == drift].sort_values("vol_scale")
        assert sub["p_barreira"].is_monotonic_increasing  # mais vol, mais toque na barreira de alta
    for vs in (0.8, 1.0, 1.2):
        sub = g[g.vol_scale == vs].set_index("drift")
        assert sub.loc["zero", "p_lucro"] <= sub.loc["cdi", "p_lucro"] <= sub.loc["cdi_premio", "p_lucro"]


def test_early_exit_regime_adjusted_and_ci():
    px = _prices()
    cf = _cf(len(px), 0.12)
    s = presets.collar_ki(1.0, 1.06, 1.12)
    h = run_historical(s, px, 63, 0.0, cdi_factor=cf, cdi_ref=0.12, regime_adjust=True)
    a = run_historical_exit(s, px, 63, 0.0, EarlyExitConfig(), cf, h.df["retorno"].to_numpy(), cdi_ref=0.12,
                            regime_adjust=True)
    b = run_historical_exit(s, px, 63, 0.0, EarlyExitConfig(), cf, h.df["retorno"].to_numpy())
    pd.testing.assert_frame_equal(a.df, b.df)  # CDI da época = CDI de hoje: mesmo resultado
    sm = summarize_exit(a)
    lo, hi = sm["ci"]["p_saida"]
    assert lo <= sm["p_saida"] <= hi


def test_latest_cdi_annual():
    s = pd.Series([0.0004, 0.00050788], index=pd.to_datetime(["2026-10-20", "2026-10-21"]))
    assert latest_cdi_annual(s) == pytest.approx(1.00050788 ** 252 - 1)
    assert latest_cdi_annual(None) is None
