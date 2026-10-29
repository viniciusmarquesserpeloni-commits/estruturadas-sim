"""Gerador pseudoaleatório mulberry32, idêntico ao do motor JS (``E.rng`` em pricing.js).

Usado onde Python e JS precisam produzir exatamente os mesmos números (intervalos de confiança por
block bootstrap), para que os dois motores mostrem o mesmo resultado e possam ser testados um contra o outro.
"""
from __future__ import annotations

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
