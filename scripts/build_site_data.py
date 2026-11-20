"""Gera os dados do site estático (site/data/): preços diários das ações, CDI e Selic.

Uso:
    python scripts/build_site_data.py              # todas as ações de scripts/tickers.py
    python scripts/build_site_data.py PETR4 VALE3  # só algumas (útil para testar)

Saída:
    site/data/index.json          meta + lista de ações disponíveis
    site/data/cdi.json            CDI diário (SGS 12) e Selic meta (SGS 432)
    site/data/precos/XXXX.json    datas, fechamento bruto e ajustado, máxima e mínima brutas

Filtro de qualidade (estruturadas.data.clean_history): saltos isolados com razão de desdobramento são
corrigidos, os demais saltos acima de 35% num dia são sinalizados, e o trecho inicial sem negociação
(preço repetido pelo Yahoo) é cortado. Os avisos de cada ação vão no index.json (campo "av").

Ações sem dados recentes (deslistadas, ticker alterado) são ignoradas com aviso.
O script falha (código 1) se menos da metade das ações vier — assim o deploy diário
não substitui o site por uma versão incompleta.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from estruturadas import data as sdata  # noqa: E402
from tickers import TICKERS  # noqa: E402

OUT = ROOT / "site" / "data"
START = "2008-01-01"
MIN_ROWS = 300
MAX_STALE_DAYS = 15


def _r(values, nd: int = 4) -> list:
    return [None if not np.isfinite(v) else round(float(v), nd) for v in values]


def download(symbols: list[str], tries: int = 3) -> dict[str, pd.DataFrame]:
    """Baixa OHLC + Adj Close em lote; refaz individualmente as que falharem."""
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    pending = list(symbols)
    for attempt in range(tries):
        if not pending:
            break
        batch = [sdata.normalize_ticker(t) for t in pending]
        try:
            raw = yf.download(batch, start=START, auto_adjust=False, actions=False, progress=False,
                              group_by="ticker", threads=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  aviso: download em lote falhou ({exc})", file=sys.stderr)
            raw = None
        still = []
        for t, sym in zip(pending, batch):
            df = None
            if raw is not None and not raw.empty:
                try:
                    df = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
                except KeyError:
                    df = None
            if df is None or df.dropna(how="all").empty:
                still.append(t)
            else:
                out[t] = df.dropna(how="all")
        pending = still
        if pending and attempt < tries - 1:
            time.sleep(5 * (attempt + 1))
    for t in pending:
        print(f"  aviso: sem dados para {t}", file=sys.stderr)
    return out


def prepare(ticker: str, raw: pd.DataFrame) -> pd.DataFrame | None:
    """Padroniza o que veio do Yahoo: Close, Adj Close, High e Low positivos, um pregão por linha."""
    df = raw.copy()
    df.index = pd.to_datetime(df.index).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    if len(df) < MIN_ROWS:
        print(f"  aviso: {ticker} tem só {len(df)} pregões; ignorada", file=sys.stderr)
        return None
    close = df["Close"].astype(float)
    adj = df["Adj Close"] if "Adj Close" in df else close
    adj = adj.where(np.isfinite(adj) & (adj > 0)).ffill().fillna(close)
    high = df["High"].where(df["High"] > 0).fillna(close)
    low = df["Low"].where(df["Low"] > 0).fillna(close)
    return pd.DataFrame({"Close": close, "Adj Close": adj.astype(float),
                         "High": np.maximum(high.to_numpy(float), close.to_numpy(float)),
                         "Low": np.minimum(low.to_numpy(float), close.to_numpy(float))}, index=df.index)


def price_payload(ticker: str, df: pd.DataFrame) -> dict:
    return {
        "ticker": ticker,
        "d": [d.strftime("%Y-%m-%d") for d in df.index],
        "c": _r(df["Close"].to_numpy(float)),
        "ca": _r(df["Adj Close"].to_numpy(float), 6),
        "h": _r(df["High"].to_numpy(float)),
        "l": _r(df["Low"].to_numpy(float)),
    }


def warnings_payload(av: dict) -> dict:
    """Avisos de qualidade no formato do index.json: c = saltos corrigidos [data, razão]; a = variações
    atípicas [data, variação]; ini = início original do histórico (quando o trecho inicial foi cortado)."""
    out = {}
    if av["corrigidos"]:
        out["c"] = [[d.strftime("%Y-%m-%d"), k] for d, k, _ in av["corrigidos"]]
    if av["atipicos"]:
        out["a"] = [[d.strftime("%Y-%m-%d"), round(v, 4)] for d, v in av["atipicos"]]
    if av["inicio_original"] is not None:
        out["ini"] = av["inicio_original"].strftime("%Y-%m-%d")
    return out


def main(argv: list[str]) -> int:
    wanted = [a.upper() for a in argv] or list(TICKERS)
    (OUT / "precos").mkdir(parents=True, exist_ok=True)

    print(f"Baixando {len(wanted)} ações desde {START}…")
    raw = download(wanted)
    frames = {t: f for t in wanted if t in raw and (f := prepare(t, raw[t])) is not None}
    if not frames:
        print("erro: nenhuma ação baixada", file=sys.stderr)
        return 1
    # filtro de qualidade: saltos isolados (com a mediana do mercado como referência) e início sem negociação
    market = sdata.market_abs_move({t: f["Adj Close"] for t, f in frames.items()})
    payloads, avisos = {}, {}
    for t, f in frames.items():
        clean, av = sdata.clean_history(f, market, min_rows=MIN_ROWS)
        payloads[t] = price_payload(t, clean)
        avisos[t] = warnings_payload(av)
        if avisos[t]:
            print(f"  dados {t}: {avisos[t]}", file=sys.stderr)
    last_global = max(pd.Timestamp(p["d"][-1]) for p in payloads.values())
    fresh = {}
    for t, p in payloads.items():
        if (last_global - pd.Timestamp(p["d"][-1])).days > MAX_STALE_DAYS:
            print(f"  aviso: {t} sem cotação recente (última {p['d'][-1]}); ignorada", file=sys.stderr)
            continue
        fresh[t] = p
    if len(fresh) < max(1, len(wanted) // 2):
        print(f"erro: só {len(fresh)} de {len(wanted)} ações com dados; abortando", file=sys.stderr)
        return 1

    index = []
    for t, p in sorted(fresh.items()):
        (OUT / "precos" / f"{t}.json").write_text(json.dumps(p, separators=(",", ":")), encoding="utf-8")
        close = pd.Series(p["ca"], dtype=float)
        entry = {"t": t, "n": TICKERS.get(t, t), "ini": p["d"][0], "fim": p["d"][-1],
                 "vol": round(sdata.historical_vol(close), 4)}
        if avisos.get(t):
            entry["av"] = avisos[t]
        index.append(entry)
    # remove arquivos de ações que saíram da lista
    for f in (OUT / "precos").glob("*.json"):
        if f.stem not in fresh:
            f.unlink()

    print("Consultando CDI e Selic no BCB…")
    cdi = sdata.fetch_cdi_daily(START, date.today())
    selic = sdata.fetch_selic_meta()
    if cdi is None or cdi.empty:
        print("  aviso: CDI indisponível; o site usará a taxa informada pelo usuário", file=sys.stderr)
    cdi_payload = {
        "d": [] if cdi is None else [d.strftime("%Y-%m-%d") for d in cdi.index],
        "r": [] if cdi is None else _r(cdi.to_numpy(float), 8),
        "selic_meta": selic,
    }
    (OUT / "cdi.json").write_text(json.dumps(cdi_payload, separators=(",", ":")), encoding="utf-8")

    meta = {
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dados_ate": last_global.strftime("%Y-%m-%d"),
        "inicio": START,
        "selic_meta": selic,
        "cdi_atual": sdata.latest_cdi_annual(cdi),  # CDI efetivo mais recente (a.a.): régua padrão do site
        "acoes": index,
    }
    (OUT / "index.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"OK: {len(index)} ações, dados até {meta['dados_ate']}, Selic meta {selic}, CDI atual {meta['cdi_atual']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
