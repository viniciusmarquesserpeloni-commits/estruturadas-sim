"""Gerador pseudoaleatório mulberry32, idêntico ao do motor JS (``E.rng`` em pricing.js).

Usado onde Python e JS precisam produzir exatamente os mesmos números (intervalos de confiança por
block bootstrap), para que os dois motores mostrem o mesmo resultado e possam ser testados um contra o outro.
"""
from __future__ import annotations

import numpy as np

_M = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & _M


class Mulberry32:
    def __init__(self, seed: int) -> None:
        self.a = (int(seed) & _M) or 0x9E3779B9

    def uni(self) -> float:
        """Uniforme em [0, 1), igual a ``E.rng(seed).uni()``."""
        self.a = (self.a + 0x6D2B79F5) & _M
        a = self.a
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & _M) ^ t
        return ((t ^ (t >> 14)) & _M) / 4294967296.0

    def int(self, n: int) -> int:
        """Inteiro em [0, n), igual a ``E.rng(seed).int(n)``."""
        return int(self.uni() * n)


def uniforms(seed: int, n: int) -> np.ndarray:
    """Os ``n`` primeiros ``uni()`` de ``Mulberry32(seed)``, vetorizados (o estado do mulberry32 é um
    contador: a_i = a_0 + i·0x6D2B79F5, então cada sorteio pode ser calculado de forma independente)."""
    a0 = (int(seed) & _M) or 0x9E3779B9
    i = np.arange(1, n + 1, dtype=np.uint64)
    a = ((a0 + i * np.uint64(0x6D2B79F5)) & np.uint64(_M)).astype(np.uint32)
    with np.errstate(over="ignore"):
        t = (a ^ (a >> np.uint32(15))) * (a | np.uint32(1))
        t = (t + (t ^ (t >> np.uint32(7))) * (t | np.uint32(61))) ^ t
        t = t ^ (t >> np.uint32(14))
    return t.astype(np.float64) / 4294967296.0


def integers(seed: int, n: int, high: int) -> np.ndarray:
    """Os ``n`` primeiros ``int(high)`` de ``Mulberry32(seed)`` (= ``E.rng(seed).int(high)`` em sequência)."""
    return np.floor(uniforms(seed, n) * high).astype(np.int64)
