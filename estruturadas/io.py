"""Importação/exportação de estruturas em JSON (para salvar lâminas como presets).

Formato (valores de strike/barreira em fração do valor inicial: 1.041 = 104,10%)::

    {
      "formato": "estruturadas-sim/v1",
      "nome": "Proteção Total (BBDC4)",
      "ticker": "BBDC4",
      "data_contratacao": "2025-11-19",
      "data_vencimento": "2026-11-25",
      "custo_opcoes": 0.0,
      "preset": "protecao_total",
      "observacoes": "...",
      "pernas": [
        {"tipo": "stock", "posicao": "comprada", "proporcao": 1.0},
        {"tipo": "put", "posicao": "comprada", "strike": 1.041,
         "barreira_tipo": "none", "barreira": null, "proporcao": 1.0}
      ]
    }
"""
from __future__ import annotations

import json
from pathlib import Path

from .legs import BARRIER_LABELS, KIND_LABELS, Leg, Structure

FORMAT = "estruturadas-sim/v1"

_KIND_ALIASES = {v.lower(): k for k, v in KIND_LABELS.items()} | {k: k for k in KIND_LABELS} | {"acao": "stock"}
_BARRIER_ALIASES = {v.lower(): k for k, v in BARRIER_LABELS.items()} | {k: k for k in BARRIER_LABELS}


def _position(value) -> int:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("comprada", "compra", "long", "+1", "1"):
            return 1
        if v in ("vendida", "venda", "short", "-1"):
            return -1
        raise ValueError(f"Posição inválida: {value!r}")
    return 1 if float(value) >= 0 else -1


def leg_to_dict(leg: Leg) -> dict:
    d = {"tipo": leg.kind, "posicao": "comprada" if leg.position > 0 else "vendida", "proporcao": leg.ratio}
    if leg.is_option:
        d.update({"strike": leg.strike, "barreira_tipo": leg.barrier, "barreira": leg.barrier_level})
    return d


def leg_from_dict(d: dict) -> Leg:
    kind = _KIND_ALIASES.get(str(d.get("tipo", d.get("kind", ""))).strip().lower())
    if kind is None:
        raise ValueError(f"Tipo de perna inválido: {d.get('tipo')!r}")
    barrier = _BARRIER_ALIASES.get(str(d.get("barreira_tipo", d.get("barrier", "none")) or "none").strip().lower())
    if barrier is None:
        raise ValueError(f"Tipo de barreira inválido: {d.get('barreira_tipo')!r}")
    return Leg(
        kind=kind,
        position=_position(d.get("posicao", d.get("position", 1))),
        strike=d.get("strike"),
        barrier=barrier,
        barrier_level=d.get("barreira", d.get("barrier_level")),
        ratio=float(d.get("proporcao", d.get("ratio", 1.0))),
    )


def structure_to_dict(s: Structure) -> dict:
    return {
        "formato": FORMAT,
        "nome": s.name,
        "ticker": s.ticker,
        "data_contratacao": s.trade_date,
        "data_vencimento": s.expiry_date,
        "custo_opcoes": s.option_cost,
        "preset": s.preset,
        "observacoes": s.notes,
        "pernas": [leg_to_dict(leg) for leg in s.legs],
    }


def structure_from_dict(d: dict) -> Structure:
    if "pernas" not in d or not isinstance(d["pernas"], list):
        raise ValueError("JSON inválido: campo 'pernas' ausente.")
    return Structure(
        name=d.get("nome") or "Estrutura importada",
        legs=[leg_from_dict(x) for x in d["pernas"]],
        ticker=d.get("ticker"),
        trade_date=d.get("data_contratacao"),
        expiry_date=d.get("data_vencimento"),
        option_cost=float(d.get("custo_opcoes") or 0.0),
        preset=d.get("preset"),
        notes=d.get("observacoes") or "",
    )


def dumps(s: Structure) -> str:
    return json.dumps(structure_to_dict(s), ensure_ascii=False, indent=2)


def loads(text: str | bytes) -> Structure:
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    return structure_from_dict(json.loads(text))


def save(s: Structure, path: str | Path) -> None:
    Path(path).write_text(dumps(s) + "\n", encoding="utf-8")


def load(path: str | Path) -> Structure:
    return loads(Path(path).read_text(encoding="utf-8"))
