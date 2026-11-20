"""Filtro de qualidade dos dados: saltos de preço (desdobramento não ajustado) e histórico sem negociação."""
import numpy as np
import pandas as pd
import pytest

from estruturadas.data import clean_history, has_warnings, market_abs_move, split_ratio, stale_start


def series(n=900, seed=4):
    rng = np.random.default_rng(seed)
    close = 20 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, n)))
    idx = pd.bdate_range("2015-01-02", periods=n)
    return pd.DataFrame({"Close": close, "Adj Close": close * 0.9, "High": close * 1.01, "Low": close * 0.99}, index=idx)


def calm_market(df, level=0.01):
    return pd.Series(level, index=df.index)


def test_split_ratio():
    assert split_ratio(np.log(1 / 2.953)) == 3 and split_ratio(np.log(2.04)) == 2 and split_ratio(-np.log(10.2)) == 10
    assert split_ratio(np.log(1.6)) is None and split_ratio(np.log(2.4)) is None


def test_salto_de_desdobramento_e_corrigido():
    df = series()
    bad = df.copy()
    bad.iloc[:300] *= 3.0  # histórico anterior 3× maior: queda de 66% no dia 300 (desdobramento 3:1 não ajustado)
    out, av = clean_history(bad, calm_market(bad))
    assert [(k, round(v, 2)) for _, k, v in av["corrigidos"]] == [(3, round(float(bad["Adj Close"].iloc[300] / bad["Adj Close"].iloc[299] - 1), 2))]
    assert av["corrigidos"][0][0] == df.index[300] and not av["atipicos"]
    pd.testing.assert_frame_equal(out, df)  # voltou à série verdadeira, em todas as colunas
    assert has_warnings(av)


def test_salto_em_dia_de_queda_geral_e_real():
    df = series()
    bad = df.copy()
    bad.iloc[300:] *= 0.5  # −50% no dia 300…
    market = calm_market(bad)
    market.iloc[300] = 0.14  # …mas o mercado inteiro caiu junto
    out, av = clean_history(bad, market)
    assert not has_warnings(av)
    pd.testing.assert_frame_equal(out, bad)


def test_salto_sem_razao_de_desdobramento_so_e_sinalizado():
    df = series()
    bad = df.copy()
    bad.iloc[:300] *= 1.7
    out, av = clean_history(bad, calm_market(bad))
    assert not av["corrigidos"] and len(av["atipicos"]) == 1 and av["atipicos"][0][0] == df.index[300]
    assert av["atipicos"][0][1] == pytest.approx(bad["Adj Close"].iloc[300] / bad["Adj Close"].iloc[299] - 1)
    pd.testing.assert_frame_equal(out, bad)


def test_sem_referencia_de_mercado_nada_e_corrigido():
    df = series()
    bad = df.copy()
    bad.iloc[:300] *= 2.0
    for market in (None, pd.Series(np.nan, index=bad.index)):
        out, av = clean_history(bad, market)
        assert not av["corrigidos"] and len(av["atipicos"]) == 1
        pd.testing.assert_frame_equal(out, bad)


def test_inicio_sem_negociacao_e_cortado():
    df = series()
    stale = df.copy()
    stale.iloc[:400] = stale["Close"].iloc[400]  # 400 pregões com o mesmo preço (máxima = mínima = fechamento)
    stale.iloc[:400, stale.columns.get_loc("Adj Close")] = stale["Adj Close"].iloc[400]
    assert stale_start(stale["Close"], stale["High"], stale["Low"]) >= 400
    out, av = clean_history(stale, calm_market(stale))
    assert av["inicio_original"] == df.index[0] and out.index[0] >= df.index[400] and len(out) >= 300
    assert stale_start(df["Close"], df["High"], df["Low"]) == 0
    # se o corte deixar menos que o mínimo de pregões, o histórico fica como está
    short, av2 = clean_history(stale, calm_market(stale), min_rows=800)
    assert av2["inicio_original"] is None and len(short) == len(stale)


def test_dias_parados_esparsos_nao_cortam():
    df = series()
    few = df.copy()
    for i in range(50, 850, 40):  # um dia parado a cada 40 (2,5%): feriado local, leilão…
        few.iloc[i] = few.iloc[i - 1]
    assert stale_start(few["Close"], few["High"], few["Low"]) == 0


def test_mediana_do_mercado():
    idx = pd.bdate_range("2020-01-01", periods=5)
    closes = {f"A{i}": pd.Series([10, 10.1, 9.0, 9.1, 9.2], index=idx) * (1 + i / 100) for i in range(12)}
    m = market_abs_move(closes)
    assert m.iloc[2] == pytest.approx(abs(np.log(9.0 / 10.1))) and np.isnan(m.iloc[0])
    assert market_abs_move({k: closes[k] for k in list(closes)[:3]}).isna().all()  # poucas ações: sem referência
