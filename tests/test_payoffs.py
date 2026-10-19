import numpy as np
import pytest

from estruturadas import presets
from estruturadas.legs import (Leg, Structure, evaluate_paths, expiry_payoff, payoff_profile_summary,
                               returns_from_payoff, validate)


def terminal_paths(s_T_values, n_days=5):
    """Caminhos que andam linearmente de 1 até S_T (sem tocar barreiras distantes)."""
    s_T = np.asarray(s_T_values, dtype=float)
    steps = np.linspace(0, 1, n_days + 1)[1:]
    return 1 + np.outer(s_T - 1, steps)


def ret(structure, close, high=None, low=None, monitoring="close", cost=0.0):
    ev = evaluate_paths(structure, close, high, low, monitoring)
    return returns_from_payoff(ev.payoff, cost, structure.has_stock)


def test_booster():
    s = presets.booster(1.0, 1.125)
    r = ret(s, terminal_paths([1.10, 1.30, 0.90]))
    np.testing.assert_allclose(r, [0.20, 0.25, -0.10], atol=1e-12)


def test_collar():
    s = presets.collar(1.0, 1.15)
    r = ret(s, terminal_paths([0.80, 1.10, 1.30]))
    np.testing.assert_allclose(r, [0.0, 0.10, 0.15], atol=1e-12)


def test_collar_knock_in():
    s = presets.collar_ki(1.0, 1.13, 1.43)
    touch = np.array([[1.10, 1.43, 1.30, 1.50]])
    no_touch_up = np.array([[1.10, 1.42, 1.30, 1.40]])
    no_touch_down = np.array([[0.95, 1.20, 0.90, 0.80]])
    paths = np.vstack([touch, no_touch_up, no_touch_down])
    np.testing.assert_allclose(ret(s, paths), [0.13, 0.40, 0.0], atol=1e-12)


def test_forward_knock_out():
    s = presets.forward_knock_out(1.10, 0.70)
    finals = np.array([0.75, 0.95, 1.10, 1.25, 1.60])
    no_touch = terminal_paths(finals)
    np.testing.assert_allclose(ret(s, no_touch), 0.10, atol=1e-12)
    touched = np.column_stack([np.full(len(finals), 0.65), finals])
    np.testing.assert_allclose(ret(s, touched), finals - 1, atol=1e-12)


def test_protecao_total_bbdc4():
    # A lâmina arredonda os valores para 4% / 6% / 42% / 57%; aqui usamos os exatos.
    # Com as pernas da lâmina, acima de 104,10% o valor final é S_T + 0,5·(S_T − 1):
    # S_T = 1,28 -> 1,42 (42,00%) e S_T = 1,38 -> 1,57 (57,00%). Os valores
    # "42,10%" e "57,10%" não são compatíveis com essas pernas; o arredondamento
    # da lâmina (42% / 57%) confere com o cálculo exato.
    s = presets.protecao_total_bbdc4()
    finals = [0.80, 1.00, 1.04, 1.28, 1.38]
    expected = [0.041, 0.041, 0.061, 0.420, 0.570]
    np.testing.assert_allclose(ret(s, terminal_paths(finals)), expected, atol=1e-12)
    # Barreira tocada (138,10%) em algum momento -> 4,10% fixo, qualquer que seja S_T.
    touched = np.column_stack([np.full(5, 1.40), finals])
    np.testing.assert_allclose(ret(s, touched), 0.041, atol=1e-12)


def test_intraday_monitoring():
    s = presets.collar_ki(1.0, 1.13, 1.43)
    close = np.array([[1.10, 1.40, 1.35]])
    high = np.array([[1.12, 1.45, 1.37]])  # máxima acima da barreira, fechamento abaixo
    low = close - 0.02
    ev_close = evaluate_paths(s, close, high, low, "close")
    ev_intra = evaluate_paths(s, close, high, low, "intraday")
    assert not ev_close.any_hit[0]
    assert ev_intra.any_hit[0]
    assert ret(s, close, high, low, "close")[0] == pytest.approx(0.35)
    assert ret(s, close, high, low, "intraday")[0] == pytest.approx(0.13)


def test_down_barrier_intraday_uses_low():
    s = presets.forward_knock_out(1.10, 0.70)
    close = np.array([[0.80, 0.72, 0.90]])
    low = np.array([[0.78, 0.69, 0.88]])
    assert not evaluate_paths(s, close, None, low, "close").any_hit[0]
    assert evaluate_paths(s, close, None, low, "intraday").any_hit[0]


def test_options_only_return_base():
    s = presets.trava_alta(1.0, 1.2)
    r = ret(s, terminal_paths([0.9, 1.1, 1.5]), cost=0.05)
    np.testing.assert_allclose(r, [-1.0, 1.0, 3.0], atol=1e-12)
    with pytest.raises(ValueError):
        returns_from_payoff(np.array([0.1]), 0.0, has_stock=False)


def test_cost_and_extra_cost():
    s = presets.collar(1.0, 1.15)
    r = ret(s, terminal_paths([1.10]), cost=0.02)
    assert r[0] == pytest.approx(1.10 / 1.02 - 1)
    ev = evaluate_paths(s, terminal_paths([1.10]))
    assert returns_from_payoff(ev.payoff, 0.0, True, extra_cost=0.005)[0] == pytest.approx(0.095)


def test_expiry_profile_branches():
    s = presets.protecao_total_bbdc4()
    grid = np.array([0.8, 1.2, 1.5])
    none = expiry_payoff(s, grid, "none")
    assert np.isnan(none[2])  # acima da barreira sem tocar é inviável
    np.testing.assert_allclose(expiry_payoff(s, grid, "all"), 1.041)


def test_profile_summary_and_validation():
    s = presets.booster()
    prof = payoff_profile_summary(s, 0.0)
    assert prof["return_max"] == pytest.approx(0.25)
    assert not prof["loss_unlimited"]

    naked = Structure("call vendida", [Leg("stock", 1), Leg("call", -1, 1.1, ratio=2)])
    assert payoff_profile_summary(naked)["loss_unlimited"]
    assert any("ILIMITADA" in m for _, m in validate(naked, 0.0))

    bad = Structure("ruim", [Leg("stock", 1), Leg("call", -1, 1.1, "up_in", 0.9), Leg("put", 1, 1.0, ratio=0)])
    msgs = [m for lvl, m in validate(bad, 0.0) if lvl == "erro"]
    assert any("barreira de alta" in m for m in msgs)
    assert any("proporção" in m for m in msgs)
    assert any(lvl == "erro" for lvl, _ in validate(presets.straddle(), 0.0))


@pytest.mark.parametrize("key", list(presets.PRESETS))
def test_all_presets_describe(key):
    s = presets.PRESETS[key].builder()
    cost = 0.0 if s.has_stock else 0.05
    txt = presets.describe(s, cost)
    assert isinstance(txt, str) and len(txt) > 20
