"""Formatação numérica no padrão brasileiro (1.234,56)."""
from __future__ import annotations

import math


def _swap(txt: str) -> str:
    return txt.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_num(x, decimals: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return _swap(f"{x:,.{decimals}f}")


def fmt_pct(x, decimals: int = 2, sign: bool = False) -> str:
    """0.041 -> '4,10%'."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    fmt = f"{{:{'+' if sign else ''},.{decimals}f}}%"
    return _swap(fmt.format(100 * x))


def fmt_brl(x, decimals: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    txt = fmt_num(abs(x), decimals)
    return f"-R$ {txt}" if x < 0 else f"R$ {txt}"


def fmt_level(x, decimals: int = 2) -> str:
    """Nível em % do valor inicial (1.041 -> '104,10%')."""
    return fmt_pct(x, decimals)
