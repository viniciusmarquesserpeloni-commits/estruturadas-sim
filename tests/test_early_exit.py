import numpy as np
import pandas as pd
import pytest

from estruturadas import presets
from estruturadas.backtest import run_historical, run_monte_carlo
from estruturadas.early_exit import (EarlyExitConfig, cdi_rate_series, rolling_vol, run_ex_post_exit,
                                     run_historical_exit, run_mc_exit, simulate_exit, structure_value)
from estruturadas.legs import Leg, Structure
from estruturadas.metrics import exit_by_cdi_regime, summarize_exit
from estruturadas.pricing import barrier_price, bs_price, bs_price_vec, make_mc_context, mc_price_leg

R, SIG, T = np.log1p(0.1375), 0.30, 1.0


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("H,K", [(1.35, 1.05), (1.35, 1.50), (0.70, 0.60), (0.70, 1.10)])
def test_barrier_in_out_parity_closed_form(kind, H, K):
    direction = "up" if H > 1 else "down"
    pin = barrier_price(kind, f"{direction}_in", 1.0, K, H, T, R, 0.02, SIG)
    pout = barrier_price(kind, f"{direction}_out", 1.0, K, H, T, R, 0.02, SIG)
    assert float(pin + pout) == pytest.approx(float(bs_price(kind, 1.0, K, T, R, 0.02, SIG)), abs=1e-12)
    assert pin >= -1e-12 and pout >= -1e-12


def test_bs_vec_matches_scalar():
    S = np.array([0.8, 1.0, 1.3])
    sig = np.array([0.2, 0.3, 0.5])
    for kind in ("call", "put"):
        expected = [float(bs_price(kind, s, 1.05, 0.7, R, 0.0, v)) for s, v in zip(S, sig)]
        np.testing.assert_allclose(bs_price_vec(kind, S, 1.05, 0.7, R, 0.0, sig), expected, atol=1e-12)


def test_closed_form_with_bgk_matches_daily_mc():
    # fórmula contínua com a barreira afastada (BGK) ≈ Monte Carlo com monitoramento diário
    ctx = make_mc_context(249, SIG, R, 0.0, 100_000, seed=3)
    n1 = np.ones(1)
    for leg in [Leg("call", 1, 1.041, "up_in", 1.381), Leg("call", 1, 1.0, "up_out", 1.381),
                Leg("put", 1, 1.10, "down_out", 0.70)]:
        p_mc, se = mc_price_leg(leg, ctx)
        p_cf = float(structure_value(Structure("x", [leg]), n1, n1, n1, 249 / 252, np.array([R]), np.array([SIG]))[0])
        assert abs(p_cf - p_mc) < 4 * se + 1e-4, (leg.label(), p_cf, p_mc, se)


def test_structure_value_after_barrier_hit_and_near_expiry():
    s = Structure("x", [Leg("call", 1, 1.0, "up_out", 1.3), Leg("call", 1, 1.0, "up_in", 1.3)])
    S, touched = np.array([1.1]), np.array([1.35])
    v = structure_value(s, S, touched, S, 0.5, np.array([R]), np.array([SIG]))
    assert v[0] == pytest.approx(float(bs_price("call", 1.1, 1.0, 0.5, R, 0.0, SIG)))  # UO morta, UI viva
    pt = presets.protecao_total_bbdc4()
    near = structure_value(pt, np.array([0.8, 1.2]), np.array([1.25, 1.25]), np.array([0.8, 0.8]), 1e-8,
                           np.array([R, R]), np.array([SIG, SIG]))
    np.testing.assert_allclose(near, [1.041, 1.2 + 0.1], atol=1e-6)  # converge para o payoff


def _stock_only(trend, N=20, cfg=None):
    s = Structure("ação", [Leg("stock", 1)])
    S = (1 + trend) ** np.arange(1, N + 1)[None, :]
    k = np.arange(N + 1)
    cdi_acc = (1.10 ** (k / 252) - 1)[None, :]
    rate, sigma = np.full((1, N), np.log1p(0.10)), np.full((1, N), 0.3)
    df = simulate_exit(s, S, S, S, cdi_acc, rate, sigma, 0.0, cfg or EarlyExitConfig(exit_spread=0.0),
                       np.array([S[0, -1] - 1]))
    return df.iloc[0], S[0]


def test_trigger_delay_grace_and_spread():
    row, S = _stock_only(0.01)
    assert row.gatilho and row.dia_gatilho == 1 and row.dia_saida == 2  # gatilho no dia 1, desmontagem no dia 2
    assert row.retorno_final == pytest.approx(S[1] - 1)
    row, S = _stock_only(0.01, cfg=EarlyExitConfig(exit_spread=0.0, delay=0))
    assert row.dia_saida == 1 and row.retorno_final == pytest.approx(0.01)
    row, S = _stock_only(0.01, cfg=EarlyExitConfig(exit_spread=0.0, min_days=5))
    assert row.dia_gatilho == 5 and row.dia_saida == 6
    row, S = _stock_only(0.01, cfg=EarlyExitConfig(exit_spread=0.03))
    assert row.dia_gatilho == 4  # 1,01^4 − 1 − 3% = 1,06% > 150% do CDI de 4 dias


def test_no_trigger_and_delay_past_maturity():
    row, S = _stock_only(-0.005)
    assert not row.gatilho and row.dia_saida == 20 and row.retorno_final == pytest.approx(S[-1] - 1)
    row, S = _stock_only(0.01, cfg=EarlyExitConfig(exit_spread=0.0, min_days=19, delay=1))
    assert row.gatilho and not row.saida_antecipada and row.dia_saida == 20


def test_helpers_rolling_vol_and_rate():
    close = 100 * np.exp(np.cumsum(np.r_[0, np.full(99, 0.01)]))
    np.testing.assert_allclose(rolling_vol(close, 63), 0.0, atol=1e-12)  # retornos constantes: vol zero
    f = np.cumprod(np.r_[1, np.full(10, 1.0004)])
    np.testing.assert_allclose(cdi_rate_series(f), 252 * np.log(1.0004))


def _synthetic(n=600, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    c = 50 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, n)))
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c}, index=idx)


def test_historical_mc_and_expost_run():
    px = _synthetic()
    cf = np.cumprod(np.r_[1, np.full(len(px) - 1, 1.0004)])
    s = presets.protecao_total_bbdc4()
    h = run_historical(s, px, 120, 0.0, cdi_factor=cf)
    ee = run_historical_exit(s, px, 120, 0.0, EarlyExitConfig(), cf, h.df["retorno"].to_numpy())
    assert len(ee.df) == len(h.df)
    early = ee.df["saida_antecipada"]
    assert (ee.df.loc[~early, "retorno_final"] == ee.df.loc[~early, "retorno_vencimento"]).all()
    assert (ee.df.loc[early, "dia_saida"] < 120).all()
    sm = summarize_exit(ee)
    assert 0 <= sm["p_saida"] <= 1 and sm["dias_medio"] <= 120
    assert not exit_by_cdi_regime(ee).empty
    m = run_monte_carlo(s, px, 120, 0.0, n_paths=3000, cdi_annual=0.10)
    em = run_mc_exit(s, m.meta["paths_exit"], 120, 0.0, EarlyExitConfig(), m.df["retorno"].to_numpy(),
                     m.meta["sigma"], 0.10)
    assert len(em.df) == 2000
    x = run_ex_post_exit(s, px, px.index[100], 120, 0.0, EarlyExitConfig(), cf)
    assert len(x.dates) == 120 and np.isnan(x.ret[-1])  # último pregão = apuração (vale o payoff)


def test_calibration_starts_at_price_paid():
    px = _synthetic()
    cf = np.cumprod(np.r_[1, np.full(len(px) - 1, 1.0004)])
    s = presets.collar(1.0, 1.15)
    # no dia 1, com a ação parada, a marcação calibrada fica perto do preço pago (− spread)
    x = run_ex_post_exit(s, px, px.index[200], 120, 0.0, EarlyExitConfig(exit_spread=0.0), cf)
    first_move = px["Close"].iloc[201] / px["Close"].iloc[200] - 1
    assert abs(x.ret[0]) < abs(first_move) + 0.01
