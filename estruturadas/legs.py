"""Modelo de pernas e avaliação vetorizada de payoff.

Convenções
----------
* Tudo é normalizado pelo valor inicial: S0 = 1. Strikes e barreiras são frações
  de S0 (1.041 = 104,10% do valor inicial).
* Um caminho é uma matriz ``(n_caminhos, n_dias)`` com os preços dos dias 1..N
  divididos por S0. O último dia é a data de apuração (S_T).
* Barreira de alta é tocada quando o preço monitorado fica >= barreira; barreira
  de baixa quando fica <= barreira.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

KINDS = ("stock", "call", "put")
BARRIERS = ("none", "up_in", "up_out", "down_in", "down_out")
MONITORING = ("close", "intraday")

KIND_LABELS = {"stock": "Ação", "call": "Call", "put": "Put"}
BARRIER_LABELS = {
    "none": "Não se aplica",
    "up_in": "Knock Up and In",
    "up_out": "Knock Up and Out",
    "down_in": "Knock Down and In",
    "down_out": "Knock Down and Out",
}
POSITION_LABELS = {1: "Comprada", -1: "Vendida"}
MONITORING_LABELS = {"close": "Fechamento diário", "intraday": "Intradiário"}

_EPS = 1e-12


@dataclass
class Leg:
    """Uma linha da tabela "Composição da Estratégia" das lâminas."""

    kind: str
    position: int = 1
    strike: float | None = None
    barrier: str = "none"
    barrier_level: float | None = None
    ratio: float = 1.0

    def __post_init__(self) -> None:
        self.kind = str(self.kind).lower()
        self.barrier = str(self.barrier or "none").lower()
        self.position = 1 if int(np.sign(self.position)) >= 0 else -1
        self.ratio = float(self.ratio)
        if self.kind not in KINDS:
            raise ValueError(f"Tipo de perna inválido: {self.kind!r}")
        if self.barrier not in BARRIERS:
            raise ValueError(f"Tipo de barreira inválido: {self.barrier!r}")
        if self.kind == "stock":
            self.strike = None
            self.barrier = "none"
            self.barrier_level = None
        else:
            self.strike = None if self.strike is None else float(self.strike)
            if self.barrier == "none":
                self.barrier_level = None
            elif self.barrier_level is not None:
                self.barrier_level = float(self.barrier_level)

    @property
    def is_option(self) -> bool:
        return self.kind != "stock"

    @property
    def has_barrier(self) -> bool:
        return self.barrier != "none"

    @property
    def barrier_dir(self) -> str | None:
        return self.barrier.split("_")[0] if self.has_barrier else None

    @property
    def knock(self) -> str | None:
        return self.barrier.split("_")[1] if self.has_barrier else None

    @property
    def event(self) -> tuple[str, float] | None:
        """Chave do evento de barreira (direção, nível) usada para agrupar pernas."""
        if not self.has_barrier or self.barrier_level is None:
            return None
        return (self.barrier_dir, round(self.barrier_level, 10))

    def label(self) -> str:
        pos = POSITION_LABELS[self.position]
        if self.kind == "stock":
            return f"Ação {pos.lower()}"
        txt = f"{KIND_LABELS[self.kind]} {pos.lower()} K={self.strike:.2%}"
        if self.has_barrier:
            txt += f" ({BARRIER_LABELS[self.barrier]} {self.barrier_level:.2%})"
        if abs(self.ratio - 1) > 1e-12:
            txt += f" ×{self.ratio:g}"
        return txt


@dataclass
class Structure:
    """Estrutura = lista de pernas + metadados da lâmina."""

    name: str
    legs: list[Leg]
    ticker: str | None = None
    trade_date: str | None = None  # ISO (AAAA-MM-DD)
    expiry_date: str | None = None  # ISO (AAAA-MM-DD)
    option_cost: float = 0.0  # custo líquido das opções em fração de S0 (+ = débito)
    preset: str | None = None
    notes: str = ""
    params: dict = field(default_factory=dict)

    @property
    def has_stock(self) -> bool:
        return any(leg.kind == "stock" for leg in self.legs)

    @property
    def option_legs(self) -> list[Leg]:
        return [leg for leg in self.legs if leg.is_option]

    @property
    def events(self) -> list[tuple[str, float]]:
        evs = {leg.event for leg in self.legs if leg.event is not None}
        return sorted(evs, key=lambda e: (e[0], e[1]))

    @property
    def strikes(self) -> list[float]:
        return sorted({leg.strike for leg in self.option_legs if leg.strike is not None})

    def copy(self, **changes) -> "Structure":
        legs = [replace(leg) for leg in changes.pop("legs", self.legs)]
        return replace(self, legs=legs, params=dict(self.params), **changes)


def event_label(event: tuple[str, float]) -> str:
    direction, level = event
    return f"{'Alta' if direction == 'up' else 'Baixa'} {level:.2%}".replace(".", ",")


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

def validate(structure: Structure, cost: float | None = None) -> list[tuple[str, str]]:
    """Retorna uma lista de (nível, mensagem); nível é "erro" ou "aviso"."""
    issues: list[tuple[str, str]] = []
    if not structure.legs:
        return [("erro", "A estrutura não tem nenhuma perna.")]
    for i, leg in enumerate(structure.legs, start=1):
        if leg.ratio <= 0:
            issues.append(("erro", f"Perna {i}: a proporção deve ser maior que zero."))
        if leg.is_option:
            if leg.strike is None or not np.isfinite(leg.strike) or leg.strike <= 0:
                issues.append(("erro", f"Perna {i}: informe um preço de exercício válido."))
            if leg.has_barrier:
                b = leg.barrier_level
                if b is None or not np.isfinite(b) or b <= 0:
                    issues.append(("erro", f"Perna {i}: informe o valor da barreira."))
                elif leg.barrier_dir == "up" and b <= 1:
                    issues.append(("erro", f"Perna {i}: barreira de alta deve ser maior que 100% do valor inicial."))
                elif leg.barrier_dir == "down" and b >= 1:
                    issues.append(("erro", f"Perna {i}: barreira de baixa deve ser menor que 100% do valor inicial."))
    stock_ratio = sum(leg.ratio * leg.position for leg in structure.legs if leg.kind == "stock")
    if stock_ratio < 0:
        issues.append(("aviso", "Ação vendida a descoberto: o simulador trata o retorno sobre o valor inicial da ação."))
    if not structure.has_stock:
        if cost is not None and cost <= 0:
            issues.append(("erro", "Estruturas só com opções exigem custo líquido positivo (débito) para calcular o retorno."))
    if not any(i[0] == "erro" for i in issues):
        prof = payoff_profile_summary(structure)
        if prof["loss_unlimited"]:
            issues.append(("aviso", "Perda máxima ILIMITADA na alta (há calls vendidas sem cobertura)."))
    return issues


def has_errors(issues: list[tuple[str, str]]) -> bool:
    return any(level == "erro" for level, _ in issues)


# ---------------------------------------------------------------------------
# Avaliação em caminhos
# ---------------------------------------------------------------------------

@dataclass
class PathSummary:
    """Resumo suficiente de cada caminho para avaliar barreiras e payoff final."""

    s_T: np.ndarray
    run_max: np.ndarray  # máximo monitorado para barreiras de alta
    run_min: np.ndarray  # mínimo monitorado para barreiras de baixa


def summarize_paths(close, high=None, low=None, monitoring: str = "close") -> PathSummary:
    close = np.atleast_2d(np.asarray(close, dtype=float))
    if monitoring == "intraday" and high is not None:
        up_series = np.maximum(np.atleast_2d(np.asarray(high, dtype=float)), close)
    else:
        up_series = close
    if monitoring == "intraday" and low is not None:
        down_series = np.minimum(np.atleast_2d(np.asarray(low, dtype=float)), close)
    else:
        down_series = close
    return PathSummary(
        s_T=close[:, -1],
        run_max=np.nanmax(up_series, axis=1),
        run_min=np.nanmin(down_series, axis=1),
    )


def shifted_level(event: tuple[str, float], shift: float) -> float:
    """Correção de Broadie-Glasserman-Kou: aproxima monitoramento contínuo
    deslocando a barreira em direção ao preço (shift = 0,5826·σ·√Δt)."""
    direction, level = event
    return level * np.exp(-shift) if direction == "up" else level * np.exp(shift)


def event_hits(summary: PathSummary, events, barrier_shift: float = 0.0) -> dict:
    hits = {}
    for ev in events:
        lvl = shifted_level(ev, barrier_shift)
        if ev[0] == "up":
            hits[ev] = summary.run_max >= lvl - _EPS
        else:
            hits[ev] = summary.run_min <= lvl + _EPS
    return hits


def leg_payoff(leg: Leg, s_T: np.ndarray, active: np.ndarray | bool = True) -> np.ndarray:
    s_T = np.asarray(s_T, dtype=float)
    if leg.kind == "stock":
        raw = s_T
    elif leg.kind == "call":
        raw = np.maximum(s_T - leg.strike, 0.0)
    else:
        raw = np.maximum(leg.strike - s_T, 0.0)
    return leg.position * leg.ratio * raw * np.asarray(active, dtype=float)


def leg_active(leg: Leg, hits: dict, shape) -> np.ndarray:
    if not leg.has_barrier:
        return np.ones(shape, dtype=bool)
    hit = hits[leg.event]
    return hit if leg.knock == "in" else ~hit


@dataclass
class Evaluation:
    payoff: np.ndarray  # valor final (S0 = 1) da carteira no vencimento
    s_T: np.ndarray
    hits: dict  # evento -> array bool
    leg_payoffs: list[np.ndarray]

    @property
    def any_hit(self) -> np.ndarray:
        if not self.hits:
            return np.zeros_like(self.s_T, dtype=bool)
        return np.logical_or.reduce(list(self.hits.values()))


def evaluate_summary(structure: Structure, summary: PathSummary, barrier_shift: float = 0.0) -> Evaluation:
    hits = event_hits(summary, structure.events, barrier_shift)
    shape = summary.s_T.shape
    leg_pays = [leg_payoff(leg, summary.s_T, leg_active(leg, hits, shape)) for leg in structure.legs]
    payoff = np.sum(leg_pays, axis=0) if leg_pays else np.zeros(shape)
    return Evaluation(payoff=payoff, s_T=summary.s_T, hits=hits, leg_payoffs=leg_pays)


def evaluate_paths(structure: Structure, close, high=None, low=None,
                   monitoring: str = "close", barrier_shift: float = 0.0) -> Evaluation:
    """Avalia a estrutura numa matriz de caminhos (n_caminhos × n_dias)."""
    return evaluate_summary(structure, summarize_paths(close, high, low, monitoring), barrier_shift)


def first_hit_index(path_close, event, path_high=None, path_low=None, monitoring="close") -> int:
    """Índice (0-based) do primeiro dia em que o evento foi tocado num único caminho; -1 se nunca."""
    close = np.asarray(path_close, dtype=float)
    direction, level = event
    if direction == "up":
        series = np.maximum(path_high, close) if (monitoring == "intraday" and path_high is not None) else close
        touched = series >= level - _EPS
    else:
        series = np.minimum(path_low, close) if (monitoring == "intraday" and path_low is not None) else close
        touched = series <= level + _EPS
    return int(np.argmax(touched)) if touched.any() else -1


# ---------------------------------------------------------------------------
# Retornos
# ---------------------------------------------------------------------------

def returns_from_payoff(payoff, cost: float, has_stock: bool, extra_cost: float = 0.0) -> np.ndarray:
    """Converte o valor final em retorno sobre o capital investido.

    * com ação: investimento = S0 + custo das opções = 1 + c;
    * só opções: investimento = c (exige c > 0).
    ``extra_cost`` (fração do valor investido) é subtraído do retorno.
    """
    payoff = np.asarray(payoff, dtype=float)
    if has_stock:
        base = 1.0 + cost
        if base <= 0:
            raise ValueError("Custo das opções implica investimento não positivo.")
    else:
        if cost <= 0:
            raise ValueError("Estruturas só com opções exigem custo líquido positivo.")
        base = cost
    return payoff / base - 1.0 - extra_cost


# ---------------------------------------------------------------------------
# Perfil no vencimento (gráfico de payoff e quadro de rentabilidade)
# ---------------------------------------------------------------------------

def expiry_payoff(structure: Structure, s_T, branch: str = "none") -> np.ndarray:
    """Payoff no vencimento em função de S_T, num ramo de barreiras.

    branch = "none": nenhuma barreira tocada — S_T precisa estar do lado de
    dentro de todas as barreiras (senão o ponto é inviável e vira NaN);
    branch = "all": todas as barreiras tocadas em algum momento.
    """
    s_T = np.asarray(s_T, dtype=float)
    hit_value = branch == "all"
    hits = {ev: np.full(s_T.shape, hit_value) for ev in structure.events}
    pays = [leg_payoff(leg, s_T, leg_active(leg, hits, s_T.shape)) for leg in structure.legs]
    payoff = np.sum(pays, axis=0) if pays else np.zeros_like(s_T)
    if branch == "none":
        feasible = np.ones(s_T.shape, dtype=bool)
        for direction, level in structure.events:
            feasible &= (s_T < level) if direction == "up" else (s_T > level)
        payoff = np.where(feasible, payoff, np.nan)
    return payoff


def payoff_profile_summary(structure: Structure, cost: float = 0.0) -> dict:
    """Retorno máximo/mínimo no vencimento e se a perda/ganho é ilimitado."""
    levels = [1.0] + structure.strikes + [e[1] for e in structure.events]
    top = 3.0 * max(levels)
    grid = np.unique(np.concatenate([np.linspace(0, top, 6001), np.array(levels),
                                     np.array(levels) - 1e-9]))
    grid = grid[grid >= 0]
    branches = ["none", "all"] if structure.events else ["none"]
    pays = np.concatenate([expiry_payoff(structure, grid, b) for b in branches])
    far = np.array([top * 10, top * 20])
    gain_unlimited = loss_unlimited = False
    for b in branches:
        p = expiry_payoff(structure, far, b)
        if np.all(np.isfinite(p)):
            slope = p[1] - p[0]
            gain_unlimited |= slope > 1e-9
            loss_unlimited |= slope < -1e-9
    try:
        rets = returns_from_payoff(pays, cost, structure.has_stock) if (structure.has_stock or cost > 0) else None
    except ValueError:
        rets = None
    out = {
        "payoff_max": None if gain_unlimited else float(np.nanmax(pays)),
        "payoff_min": None if loss_unlimited else float(np.nanmin(pays)),
        "gain_unlimited": bool(gain_unlimited),
        "loss_unlimited": bool(loss_unlimited),
        "return_max": None,
        "return_min": None,
    }
    if rets is not None:
        out["return_max"] = None if gain_unlimited else float(np.nanmax(rets))
        out["return_min"] = None if loss_unlimited else float(np.nanmin(rets))
    return out
