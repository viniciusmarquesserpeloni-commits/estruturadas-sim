"""Estruturas pré-definidas: cada preset apenas preenche a lista de pernas.

Os textos explicativos são gerados a partir das pernas atuais e do custo
informado, então refletem edições feitas na tabela (desde que a "forma" da
estrutura continue a mesma do preset; caso contrário usa-se a descrição genérica).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .formatting import fmt_level, fmt_pct
from .legs import Leg, Structure, expiry_payoff, payoff_profile_summary, returns_from_payoff


@dataclass
class Preset:
    key: str
    name: str
    builder: Callable[..., Structure]
    describe: Callable[[Structure, float], str]
    formula: str  # fórmula do payoff (texto/markdown)


# ---------------------------------------------------------------------------
# Construtores
# ---------------------------------------------------------------------------

def booster(k1: float = 1.0, k2: float = 1.125) -> Structure:
    return Structure("Booster", [
        Leg("stock", +1),
        Leg("call", +1, k1),
        Leg("call", -1, k2, ratio=2.0),
    ], preset="booster", params={"k1": k1, "k2": k2})


def collar(kp: float = 1.0, kc: float = 1.15) -> Structure:
    return Structure("Collar", [
        Leg("stock", +1),
        Leg("put", +1, kp),
        Leg("call", -1, kc),
    ], preset="collar", params={"kp": kp, "kc": kc})


def collar_ki(kp: float = 1.0, kc: float = 1.13, b: float = 1.43) -> Structure:
    return Structure("Collar Knock In", [
        Leg("stock", +1),
        Leg("put", +1, kp),
        Leg("call", -1, kc, "up_in", b),
    ], preset="collar_ki", params={"kp": kp, "kc": kc, "b": b})


def forward_knock_out(k: float = 1.10, b: float = 0.70) -> Structure:
    return Structure("Forward Knock Out", [
        Leg("stock", +1),
        Leg("put", +1, k, "down_out", b),
        Leg("call", -1, k, "down_out", b),
    ], preset="fko", params={"k": k, "b": b})


def trava_alta(k1: float = 1.0, k2: float = 1.2) -> Structure:
    return Structure("Trava de alta", [
        Leg("call", +1, k1),
        Leg("call", -1, k2),
    ], preset="trava_alta", params={"k1": k1, "k2": k2})


def trava_baixa(k1: float = 1.0, k2: float = 0.8) -> Structure:
    return Structure("Trava de baixa", [
        Leg("put", +1, k1),
        Leg("put", -1, k2),
    ], preset="trava_baixa", params={"k1": k1, "k2": k2})


def straddle(k: float = 1.0) -> Structure:
    return Structure("Straddle", [
        Leg("call", +1, k),
        Leg("put", +1, k),
    ], preset="straddle", params={"k": k})


def strangle(kp: float = 0.95, kc: float = 1.05) -> Structure:
    return Structure("Strangle", [
        Leg("put", +1, kp),
        Leg("call", +1, kc),
    ], preset="strangle", params={"kp": kp, "kc": kc})


def protecao_total_bbdc4() -> Structure:
    """Lâmina "Proteção Total" em BBDC4 de 19/11/2025, vencimento 25/11/2026."""
    k, b = 1.041, 1.381
    return Structure("Proteção Total (BBDC4)", [
        Leg("stock", +1),
        Leg("put", +1, k, ratio=1.0),
        Leg("call", -1, k, "up_in", b, ratio=1.0),
        Leg("call", +1, 1.0, "up_out", b, ratio=0.5),
    ], ticker="BBDC4", trade_date="2025-11-19", expiry_date="2026-11-25",
        option_cost=0.0, preset="protecao_total",
        notes="Exemplo da lâmina de 19/11/2025. Custo das opções = 0 (estrutura sem custo).")


# ---------------------------------------------------------------------------
# Textos explicativos
# ---------------------------------------------------------------------------

def _r(structure: Structure, s: float, cost: float, branch: str = "none") -> float:
    p = expiry_payoff(structure, np.array([s]), branch)[0]
    return float(returns_from_payoff(p, cost, structure.has_stock))


def _shape(structure: Structure) -> list[tuple]:
    return [(leg.kind, leg.position, leg.barrier) for leg in structure.legs]


def _need_cost(structure: Structure, cost: float) -> str | None:
    if not structure.has_stock and cost <= 0:
        return ("Estrutura só com opções: informe o **custo líquido** (prêmio pago, em % do valor "
                "inicial) para calcular os retornos, ou use o modo Teórico.")
    return None


def describe_generic(structure: Structure, cost: float) -> str:
    msg = _need_cost(structure, cost)
    if msg:
        return msg
    prof = payoff_profile_summary(structure, cost)
    lines = []
    scen = [-0.30, -0.20, -0.10, 0.0, 0.10, 0.20, 0.30, 0.50]
    branches = [("none", "sem tocar barreira"), ("all", "tocando a barreira")] if structure.events else [("none", "")]
    for b, lbl in branches:
        parts = []
        for v in scen:
            p = expiry_payoff(structure, np.array([1 + v]), b)[0]
            if np.isfinite(p):
                r = float(returns_from_payoff(p, cost, structure.has_stock))
                parts.append(f"ação {fmt_pct(v, 0, sign=True)} → **{fmt_pct(r)}**")
        if parts:
            head = f"- {lbl.capitalize()}: " if lbl else "- "
            lines.append(head + "; ".join(parts) + ".")
    if prof["gain_unlimited"]:
        lines.append("- Ganho máximo: **ilimitado** na alta.")
    elif prof["return_max"] is not None:
        lines.append(f"- Retorno máximo no vencimento: **{fmt_pct(prof['return_max'])}**.")
    if prof["loss_unlimited"]:
        lines.append("- Perda máxima: **ilimitada** na alta.")
    elif prof["return_min"] is not None:
        lines.append(f"- Pior retorno no vencimento: **{fmt_pct(prof['return_min'])}**.")
    return "\n".join(lines)


def describe_booster(s: Structure, cost: float) -> str:
    k1, k2 = s.legs[1].strike, s.legs[2].strike
    part = s.legs[0].ratio + s.legs[1].ratio
    rmax = payoff_profile_summary(s, cost)["return_max"]
    return "\n".join([
        f"- **Na alta:** acima de {fmt_level(k1)} do valor inicial você participa em "
        f"**{part:g}x** da alta até {fmt_level(k2)} (alta de {fmt_pct(k2 - 1)}).",
        f"- **Teto:** o retorno máximo é **{fmt_pct(rmax) if rmax is not None else 'ilimitado'}**, "
        f"para qualquer alta a partir de {fmt_pct(k2 - 1)} (as calls vendidas limitam o ganho).",
        f"- **Na queda:** sem proteção — você acompanha a ação 1:1 "
        f"(ex.: queda de 10% → {fmt_pct(_r(s, 0.9, cost))}; queda de 20% → {fmt_pct(_r(s, 0.8, cost))}).",
    ])


def describe_collar(s: Structure, cost: float) -> str:
    kp, kc = s.legs[1].strike, s.legs[2].strike
    return "\n".join([
        f"- **Na queda:** a put comprada protege abaixo de {fmt_level(kp)}: retorno mínimo de "
        f"**{fmt_pct(_r(s, min(kp, 1) * 0.5, cost))}**, por mais que a ação caia.",
        f"- **Entre {fmt_level(kp)} e {fmt_level(kc)}:** você acompanha a variação da ação.",
        f"- **Teto:** acima de {fmt_level(kc)} o retorno fica limitado a **{fmt_pct(_r(s, kc * 1.5, cost))}**.",
    ])


def describe_collar_ki(s: Structure, cost: float) -> str:
    kp, kc, b = s.legs[1].strike, s.legs[2].strike, s.legs[2].barrier_level
    just_below = b - 1e-6
    return "\n".join([
        f"- **Se a ação nunca subir {fmt_pct(b - 1)} ou mais** (barreira em {fmt_level(b)}): você "
        f"participa 1:1 da alta, sem teto — até cerca de **{fmt_pct(_r(s, just_below, cost))}** logo abaixo da barreira.",
        f"- **Se tocar a barreira em algum momento:** a call vendida passa a existir e o retorno fica "
        f"limitado a **{fmt_pct(_r(s, kc * 1.5, cost, 'all'))}** (strike {fmt_level(kc)}).",
        f"- **Na queda:** proteção da put em {fmt_level(kp)} — retorno mínimo de "
        f"**{fmt_pct(_r(s, min(kp, 1) * 0.5, cost))}**.",
    ])


def describe_fko(s: Structure, cost: float) -> str:
    k, b = s.legs[1].strike, s.legs[1].barrier_level
    return "\n".join([
        f"- **Se a ação nunca cair {fmt_pct(1 - b)} ou mais** (barreira em {fmt_level(b)}): retorno "
        f"**fixo de {fmt_pct(_r(s, 1.0, cost))}**, qualquer que seja o preço no vencimento.",
        f"- **Se tocar a barreira:** a put e a call deixam de existir e você fica só com a ação: "
        f"retorno = variação da ação (ex.: termina em −20% → {fmt_pct(_r(s, 0.8, cost, 'all'))}; "
        f"em +5% → {fmt_pct(_r(s, 1.05, cost, 'all'))}).",
    ])


def describe_trava_alta(s: Structure, cost: float) -> str:
    msg = _need_cost(s, cost)
    if msg:
        return msg
    k1, k2 = s.legs[0].strike, s.legs[1].strike
    return "\n".join([
        f"- Você paga {fmt_pct(cost)} do valor inicial em prêmio.",
        f"- **Abaixo de {fmt_level(k1)}** no vencimento: perde 100% do prêmio.",
        f"- **Acima de {fmt_level(k2)}:** ganho máximo de **{fmt_pct(_r(s, k2 * 1.5, cost))}** sobre o prêmio.",
        f"- Ponto de equilíbrio: ação em {fmt_level(k1 + cost)}.",
    ])


def describe_trava_baixa(s: Structure, cost: float) -> str:
    msg = _need_cost(s, cost)
    if msg:
        return msg
    k1, k2 = s.legs[0].strike, s.legs[1].strike
    return "\n".join([
        f"- Você paga {fmt_pct(cost)} do valor inicial em prêmio.",
        f"- **Acima de {fmt_level(k1)}** no vencimento: perde 100% do prêmio.",
        f"- **Abaixo de {fmt_level(k2)}:** ganho máximo de **{fmt_pct(_r(s, k2 * 0.5, cost))}** sobre o prêmio.",
        f"- Ponto de equilíbrio: ação em {fmt_level(k1 - cost)}.",
    ])


def describe_straddle(s: Structure, cost: float) -> str:
    msg = _need_cost(s, cost)
    if msg:
        return msg
    k = s.legs[0].strike
    return "\n".join([
        f"- Você paga {fmt_pct(cost)} do valor inicial e ganha com **movimentos fortes para qualquer lado**.",
        f"- Pontos de equilíbrio: ação em {fmt_level(k - cost)} ou {fmt_level(k + cost)}.",
        f"- Perda máxima: 100% do prêmio, se a ação terminar exatamente em {fmt_level(k)}.",
        f"- Ex.: ação +20% → {fmt_pct(_r(s, 1.2, cost))}; ação −20% → {fmt_pct(_r(s, 0.8, cost))}.",
    ])


def describe_strangle(s: Structure, cost: float) -> str:
    msg = _need_cost(s, cost)
    if msg:
        return msg
    kp, kc = s.legs[0].strike, s.legs[1].strike
    return "\n".join([
        f"- Você paga {fmt_pct(cost)} e ganha com movimentos fortes; perde 100% do prêmio se a ação "
        f"terminar entre {fmt_level(kp)} e {fmt_level(kc)}.",
        f"- Pontos de equilíbrio: {fmt_level(kp - cost)} e {fmt_level(kc + cost)}.",
        f"- Ex.: ação +20% → {fmt_pct(_r(s, 1.2, cost))}; ação −20% → {fmt_pct(_r(s, 0.8, cost))}.",
    ])


def describe_protecao_total(s: Structure, cost: float) -> str:
    k, b = s.legs[1].strike, s.legs[2].barrier_level
    k_uo, ratio = s.legs[3].strike, s.legs[3].ratio
    just_below = b - 1e-6
    return "\n".join([
        f"- **Se a ação nunca subir {fmt_pct(b - 1)} ou mais** (barreira em {fmt_level(b)}):",
        f"  - na queda ou até {fmt_level(k_uo)}: retorno **mínimo de {fmt_pct(_r(s, 0.5, cost))}** "
        f"(proteção total + ganho mínimo do strike da put em {fmt_level(k)});",
        f"  - na alta: você recebe a alta da ação **mais {ratio:.0%} da alta** acima de {fmt_level(k_uo)} "
        f"(ex.: +4% → {fmt_pct(_r(s, 1.04, cost))}; +28% → {fmt_pct(_r(s, 1.28, cost))}), "
        f"até cerca de **{fmt_pct(_r(s, just_below, cost))}** logo abaixo da barreira.",
        f"- **Se tocar a barreira em qualquer momento:** retorno **fixo de {fmt_pct(_r(s, 1.0, cost, 'all'))}**, "
        f"qualquer que seja o preço no vencimento.",
    ])


PRESETS: dict[str, Preset] = {p.key: p for p in [
    Preset("booster", "Booster", booster, describe_booster,
           "Valor final = S_T + max(S_T − K1, 0) − 2·max(S_T − K2, 0)"),
    Preset("collar", "Collar", collar, describe_collar,
           "Valor final = S_T + max(Kp − S_T, 0) − max(S_T − Kc, 0) = min(max(S_T, Kp), Kc)"),
    Preset("collar_ki", "Collar Knock In", collar_ki, describe_collar_ki,
           "Valor final = S_T + max(Kp − S_T, 0) − 1{tocou B}·max(S_T − Kc, 0)"),
    Preset("fko", "Forward Knock Out", forward_knock_out, describe_fko,
           "Sem toque em B: valor final = K (fixo). Com toque: valor final = S_T"),
    Preset("trava_alta", "Trava de alta", trava_alta, describe_trava_alta,
           "Valor final = max(S_T − K1, 0) − max(S_T − K2, 0); retorno = valor/c − 1"),
    Preset("trava_baixa", "Trava de baixa", trava_baixa, describe_trava_baixa,
           "Valor final = max(K1 − S_T, 0) − max(K2 − S_T, 0); retorno = valor/c − 1"),
    Preset("straddle", "Straddle", straddle, describe_straddle,
           "Valor final = |S_T − K|; retorno = valor/c − 1"),
    Preset("strangle", "Strangle", strangle, describe_strangle,
           "Valor final = max(Kp − S_T, 0) + max(S_T − Kc, 0); retorno = valor/c − 1"),
    Preset("protecao_total", "Proteção Total (BBDC4)", protecao_total_bbdc4, describe_protecao_total,
           "Sem toque em B: S_T + max(K − S_T, 0) + 0,5·max(S_T − 1, 0). Com toque: K (fixo)"),
]}


def describe(structure: Structure, cost: float | None = None) -> str:
    """Texto em linguagem simples para a estrutura (preset ou customizada)."""
    cost = structure.option_cost if cost is None else cost
    preset = PRESETS.get(structure.preset or "")
    if preset is not None:
        ref = preset.builder()
        if _shape(ref) == _shape(structure):
            try:
                return preset.describe(structure, cost)
            except (ValueError, TypeError, IndexError):
                pass
    return describe_generic(structure, cost)
