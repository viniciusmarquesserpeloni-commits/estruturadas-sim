import numpy as np
import pytest

from estruturadas import presets
from estruturadas.legs import Leg
from estruturadas.pricing import (bs_price, make_mc_context, mc_price_leg, price_structure,
                                  solve_zero_cost)

SIGMA, R, Q, N = 0.30, np.log1p(0.12), 0.0, 252


def test_put_call_parity():
    T = N / 252
    for K in (0.8, 1.0, 1.2):
        c = bs_price("call", 1.0, K, T, R, Q, SIGMA)
        p = bs_price("put", 1.0, K, T, R, Q, SIGMA)
        assert c - p == pytest.approx(1.0 * np.exp(-Q * T) - K * np.exp(-R * T), abs=1e-12)


def test_bs_known_value():
    # Hull: S=42, K=40, r=10%, sigma=20%, T=0,5 -> call 4,76; put 0,81
    assert bs_price("call", 42, 40, 0.5, 0.10, 0.0, 0.20) == pytest.approx(4.7594, abs=1e-3)
    assert bs_price("put", 42, 40, 0.5, 0.10, 0.0, 0.20) == pytest.approx(0.8086, abs=1e-3)


def test_in_out_parity_vs_bs():
    ctx = make_mc_context(N, SIGMA, R, Q, n_paths=50_000, seed=7)
    K, B = 1.05, 1.35
    p_in, se_in = mc_price_leg(Leg("call", 1, K, "up_in", B), ctx)
    p_out, se_out = mc_price_leg(Leg("call", 1, K, "up_out", B), ctx)
    p_van, se_van = mc_price_leg(Leg("call", 1, K), ctx)
    bs = float(bs_price("call", 1.0, K, N / 252, R, Q, SIGMA))
    # in + out = vanilla caminho a caminho; o vanilla MC deve bater com BS em 3 erros padrão
    assert p_in + p_out == pytest.approx(p_van, abs=1e-12)
    assert abs(p_in + p_out - bs) < 3 * se_van


def test_intraday_shift_increases_knock_in_probability():
    leg = Leg("call", 1, 1.05, "up_in", 1.30)
    p_close, _ = mc_price_leg(leg, make_mc_context(N, SIGMA, R, n_paths=20_000, seed=1, monitoring="close"))
    p_intra, _ = mc_price_leg(leg, make_mc_context(N, SIGMA, R, n_paths=20_000, seed=1, monitoring="intraday"))
    assert p_intra > p_close


def test_price_structure_vanilla_uses_bs():
    res = price_structure(presets.collar(1.0, 1.15), SIGMA, R, Q, N)
    assert all(lp.method == "BS" for lp in res.legs)
    assert res.net_stderr == 0.0


@pytest.mark.parametrize("builder,legs,param,bounds", [
    (lambda: presets.collar(1.0, 1.15), 2, "strike", None),  # Kc do Collar dado Kp
    (lambda: presets.forward_knock_out(1.10, 0.70), [1, 2], "strike", (0.8, 1.6)),  # K do FKO dado B
])
def test_zero_cost_solver(builder, legs, param, bounds):
    res = solve_zero_cost(builder(), legs, param, SIGMA, R, Q, N, n_paths=20_000, bounds=bounds)
    assert res.converged, res.message
    assert abs(res.cost) < 1e-6


def test_zero_cost_solver_ratio_protecao_total():
    s = presets.protecao_total_bbdc4()
    res = solve_zero_cost(s, 3, "ratio", SIGMA, R, Q, N, n_paths=20_000)
    assert res.converged, res.message
    assert abs(res.cost) < 1e-6
    assert res.value > 0


def test_zero_cost_solver_no_solution():
    s = presets.straddle()  # só compras: custo sempre positivo
    res = solve_zero_cost(s, 0, "strike", SIGMA, R, Q, N)
    assert not res.converged
    assert "Não há solução" in res.message
