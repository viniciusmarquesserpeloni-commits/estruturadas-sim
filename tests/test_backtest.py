import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from estruturadas import io as sio
from estruturadas import presets
from estruturadas.backtest import (block_bootstrap_paths, historical_windows, run_ex_post,
                                   run_historical, run_monte_carlo)
from estruturadas.data import (cdi_factor_on_index, count_trading_days, normalize_ticker,
                               parse_price_csv, previous_business_day, term_from_dates)
from estruturadas.legs import evaluate_paths
from estruturadas.metrics import comparison_table, default_variations, profitability_table, summarize

ROOT = Path(__file__).resolve().parents[1]


def synthetic(n=30, growth=0.01, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n)
    close = 100 * (1 + growth) ** np.arange(n)
    return pd.DataFrame({"Open": close, "High": close * 1.002, "Low": close * 0.998, "Close": close}, index=idx)


def test_windows_count_and_paths():
    prices = synthetic(30)
    w = historical_windows(prices, 5)
    assert w.close.shape == (25, 5)
    np.testing.assert_allclose(w.close, np.tile(1.01 ** np.arange(1, 6), (25, 1)))
    assert w.start_dates[0] == prices.index[0] and w.end_dates[-1] == prices.index[-1]
    with pytest.raises(ValueError):
        historical_windows(prices, 30)


def test_historical_expected_returns():
    prices = synthetic(30)
    res = run_historical(presets.collar(1.0, 1.15), prices, 5, cost=0.0)
    assert len(res.df) == 25
    assert res.n_effective == 5
    np.testing.assert_allclose(res.df["retorno"], 1.01**5 - 1)
    np.testing.assert_allclose(res.df["retorno_acao"], 1.01**5 - 1)

    # crescimento de 3% ao dia: Collar fica no teto de 15% depois de 5 dias
    res2 = run_historical(presets.collar(1.0, 1.15), synthetic(30, 0.03), 5, cost=0.0)
    np.testing.assert_allclose(res2.df["retorno"], 0.15)
    s = summarize(res2)
    assert s["p_lucro"] == 1.0 and s["p_max"] == 1.0 and s["n"] == 25


def test_historical_barrier_and_cdi():
    # FKO com barreira de baixa em 70%: uma queda forte no meio da série aciona algumas janelas
    prices = synthetic(40, 0.0)
    prices.iloc[20:, :] *= 0.6
    res = run_historical(presets.forward_knock_out(1.10, 0.70), prices, 5, cost=0.0,
                         cdi_factor=cdi_factor_on_index(prices.index, None, 0.10))
    hit = res.df["barreira_1"].to_numpy()
    assert hit.sum() == 5  # janelas que começam nos dias 15..19
    np.testing.assert_allclose(res.df.loc[~hit, "retorno"], 0.10)
    np.testing.assert_allclose(res.df.loc[hit, "retorno"], -0.40)
    np.testing.assert_allclose(res.df["retorno_cdi"], 1.10 ** (5 / 252) - 1)
    table = comparison_table({"Histórico": summarize(res)})
    assert "Barreira acionada (Baixa 70,00%)" in table.index


def test_monte_carlo_reproducible():
    prices = synthetic(300, 0.0005)
    rng = np.random.default_rng(0)
    prices["Close"] = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    prices["High"], prices["Low"] = prices["Close"] * 1.01, prices["Close"] * 0.99
    s = presets.protecao_total_bbdc4()
    a = run_monte_carlo(s, prices, 63, 0.0, "bootstrap", 2000, 20, seed=3)
    b = run_monte_carlo(s, prices, 63, 0.0, "bootstrap", 2000, 20, seed=3)
    pd.testing.assert_frame_equal(a.df, b.df)
    g = run_monte_carlo(s, prices, 63, 0.0, "gbm", 2000, drift="zero", seed=3)
    assert len(g.df) == 2000
    assert (g.df["retorno"] >= 0.041 - 1e-12).all()  # Proteção Total nunca rende menos que 4,10%
    intra = run_monte_carlo(s, prices, 63, 0.0, "gbm", 2000, drift="zero", seed=3, monitoring="intraday")
    assert intra.df["barreira_qualquer"].mean() >= g.df["barreira_qualquer"].mean()


def test_block_bootstrap_shape():
    lr = np.log(1.01) * np.ones(50)
    p = block_bootstrap_paths(lr, 10, 33, block=20, seed=1)
    assert p.shape == (10, 33)
    np.testing.assert_allclose(p[:, -1], 1.01**33)


def test_ex_post_finished_and_ongoing():
    prices = synthetic(60, 0.01)
    s = presets.collar_ki(1.0, 1.13, 1.43)
    t0, expiry = prices.index[5], prices.index[20]
    res = run_ex_post(s, prices, t0, expiry, 0.0)
    assert res.finished and res.obs_date == prices.index[19]
    assert res.n_days_elapsed == 14
    assert res.retorno == pytest.approx(1.01**14 - 1)
    assert not res.hits["Alta 143,00%"][0]

    ongoing = run_ex_post(s, prices, prices.index[40], prices.index[-1] + pd.Timedelta(days=60), 0.0)
    assert not ongoing.finished and ongoing.last_date == prices.index[-1]


def test_ex_post_barrier_date_intraday():
    prices = synthetic(30, 0.0)
    prices.iloc[10, prices.columns.get_loc("High")] = 150.0  # só a máxima toca 143%
    s = presets.collar_ki(1.0, 1.13, 1.43)
    t0, expiry = prices.index[0], prices.index[25]
    assert not run_ex_post(s, prices, t0, expiry, 0.0, "close").hits["Alta 143,00%"][0]
    hit, when = run_ex_post(s, prices, t0, expiry, 0.0, "intraday").hits["Alta 143,00%"]
    assert hit and when == prices.index[10]


def test_json_round_trip(tmp_path):
    s = presets.protecao_total_bbdc4()
    path = tmp_path / "x.json"
    sio.save(s, path)
    s2 = sio.load(path)
    rng = np.random.default_rng(1)
    paths = np.exp(np.cumsum(rng.normal(0, 0.02, (500, 60)), axis=1))
    np.testing.assert_array_equal(evaluate_paths(s, paths).payoff, evaluate_paths(s2, paths).payoff)
    assert s2.ticker == "BBDC4" and s2.expiry_date == "2026-11-25"


def test_bundled_preset_json_matches_builder():
    s = sio.load(ROOT / "presets" / "protecao_total_bbdc4.json")
    ref = presets.protecao_total_bbdc4()
    assert [vars(a) for a in s.legs] == [vars(b) for b in ref.legs]
    assert json.loads((ROOT / "presets" / "protecao_total_bbdc4.json").read_text("utf-8"))["formato"]


def test_profitability_table_bbdc4():
    s = presets.protecao_total_bbdc4()
    t = profitability_table(s, 0.0, [-0.20, -0.10, 0.0, 0.04, 0.28, 0.38, 0.48], formatted=False)
    np.testing.assert_allclose(t["Barreira não atingida"].iloc[:6], [0.041, 0.041, 0.041, 0.061, 0.42, 0.57])
    assert np.isnan(t["Barreira não atingida"].iloc[6])
    np.testing.assert_allclose(t["Barreira atingida"], 0.041)
    assert {0.04, 0.38, 0.48} <= set(default_variations(s))


def test_data_helpers():
    assert normalize_ticker(" petr4 ") == "PETR4.SA"
    assert normalize_ticker("VALE3.SA") == "VALE3.SA"
    assert normalize_ticker("^BVSP") == "^BVSP"
    csv = "Data;Fechamento;Máxima;Mínima\n02/01/2024;10,50;10,80;10,20\n03/01/2024;11,00;11,10;10,90\n"
    df = parse_price_csv(csv.encode("utf-8"))
    assert df["Close"].tolist() == [10.5, 11.0] and df.index[0] == pd.Timestamp("2024-01-02")
    df2 = parse_price_csv("Date,Close\n2024-01-02,10.5\n2024-01-03,11\n")
    assert df2["High"].tolist() == [10.5, 11.0]
    # calendário: 25/11/2026 (qua) -> apuração em 24/11/2026; 20/11/2026 é feriado
    assert previous_business_day("2026-11-25") == pd.Timestamp("2026-11-24")
    assert count_trading_days("2026-11-18", "2026-11-24") == 3  # 19, 23, 24
    idx = pd.bdate_range("2025-11-17", "2025-11-28")
    n, obs = term_from_dates("2025-11-19", "2025-11-26", idx)
    assert obs == pd.Timestamp("2025-11-25") and n == 4  # 20, 21, 24, 25 (série sem feriados)
