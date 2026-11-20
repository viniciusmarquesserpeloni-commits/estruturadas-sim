"""Comparação lado a lado de estruturas."""
import numpy as np
import pandas as pd

from estruturadas import compare as cmp
from estruturadas import presets
from estruturadas.backtest import run_historical, run_monte_carlo
from estruturadas.metrics import summarize


def _prices(n=900, seed=3):
    rng = np.random.default_rng(seed)
    close = 20 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n)))
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame({"Close": close, "High": close * 1.01, "Low": close * 0.99}, index=idx)


def test_best_indices_ties_and_all_equal():
    assert cmp.best_indices([0.5, 0.7, 0.7], True) == [1, 2]
    assert cmp.best_indices([0.5, 0.5], True) == []
    assert cmp.best_indices([-0.1, -0.3, np.nan], False) == [1]
    assert cmp.best_indices([0.1, 0.2], None) == []
    assert cmp.best_indices([0.1, np.nan], True) == []


def test_unique_name():
    assert cmp.unique_name("Collar", []) == "Collar"
    assert cmp.unique_name("Collar", ["Collar"]) == "Collar (2)"
    assert cmp.unique_name("Collar", ["Collar", "Collar (2)"]) == "Collar (3)"


def test_compare_table_two_structures():
    px = _prices()
    items = []
    for s, cost in ((presets.collar(1.0, 1.15), 0.0), (presets.collar_ki(1.0, 1.06, 1.12), 0.0)):
        h = summarize(run_historical(s, px, 63, cost))
        m = summarize(run_monte_carlo(s, px, 63, cost, method="gbm", n_paths=2000))
        items.append(cmp.CompareItem(s.name, s, cost, h, m))
    df = cmp.compare_table(items)
    assert list(df.columns) == ["Indicador", "Collar", "Collar Knock In"]
    assert len(df) == 3 + len(cmp.ROWS)
    row = df[df["Indicador"] == "Histórico · P(barreira acionada)"].iloc[0]
    assert row["Collar"] == "sem barreira" and "%" in row["Collar Knock In"]
    # IC 95% só nas linhas do histórico
    assert "(" in df[df["Indicador"] == "Histórico · P(lucro > 0)"].iloc[0]["Collar"]
    assert "(" not in df[df["Indicador"] == "Monte Carlo · P(lucro > 0)"].iloc[0]["Collar"].replace("★ ", "")
    # retorno máximo do collar = strike da call (15%)
    assert df[df["Indicador"] == "Retorno máximo no vencimento"].iloc[0]["Collar"] == "15,00%"
    # valores numéricos coerentes com os resumos
    vals = dict((lbl, v) for lbl, v, _ in cmp.compare_values(items))
    assert np.isclose(vals["Monte Carlo · P(lucro > 0)"][0], items[0].mc["p_lucro"])
