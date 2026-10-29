"""Dados de mercado: preços (yfinance ou CSV), Selic/CDI (API SGS do BCB) e calendário.

Este módulo não depende do Streamlit; o cache (``st.cache_data``) é aplicado no app.
"""
from __future__ import annotations

import io
from datetime import date, timedelta

import numpy as np
import pandas as pd

SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
SGS_SELIC_META = 432  # Selic meta (% a.a.)
SGS_CDI_DAILY = 12  # CDI (% a.d.)
TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# Preços
# ---------------------------------------------------------------------------

def normalize_ticker(ticker: str) -> str:
    """'petr4' -> 'PETR4.SA'. Mantém tickers que já têm sufixo ou índices (^BVSP)."""
    t = (ticker or "").strip().upper()
    if not t:
        raise ValueError("Informe o código da ação.")
    if "." in t or t.startswith("^"):
        return t
    return f"{t}.SA"


def adjust_ohlc(df: pd.DataFrame, adjusted: bool = True) -> pd.DataFrame:
    """Retorna Open/High/Low/Close; se ``adjusted``, multiplica OHLC pelo fator
    Adj Close / Close (ajuste por proventos e eventos)."""
    out = df[[c for c in ("Open", "High", "Low", "Close") if c in df.columns]].copy()
    if adjusted and "Adj Close" in df.columns:
        factor = (df["Adj Close"] / df["Close"]).replace([np.inf, -np.inf], np.nan).ffill().fillna(1.0)
        for col in out.columns:
            out[col] = out[col] * factor
    return out


def clean_prices(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None) if getattr(df.index, "tz", None) else pd.to_datetime(df.index)
    df.index = df.index.normalize()
    df.index.name = "Date"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    for col in ("High", "Low"):
        if col not in df.columns:
            df[col] = df["Close"]
        df[col] = df[col].fillna(df["Close"])
    if "Open" not in df.columns:
        df["Open"] = df["Close"]
    return df[["Open", "High", "Low", "Close"]].astype(float)


def load_prices_yf(ticker: str, start: date | str, end: date | str | None = None,
                   adjusted: bool = True) -> pd.DataFrame:
    """Baixa OHLC diário pelo yfinance. ``end`` é inclusivo."""
    import yfinance as yf

    sym = normalize_ticker(ticker)
    end_excl = (pd.Timestamp(end) + pd.Timedelta(days=1)) if end is not None else None
    raw = yf.download(sym, start=pd.Timestamp(start), end=end_excl, auto_adjust=False,
                      actions=False, progress=False, multi_level_index=False, threads=False)
    if raw is None or raw.empty:
        raise ValueError(f"Nenhum dado encontrado para {sym} no período.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return clean_prices(adjust_ohlc(raw, adjusted))


def parse_price_csv(content: bytes | str) -> pd.DataFrame:
    """Lê CSV com colunas Date, Close[, High, Low, Open]. Aceita ',' ou ';' e
    decimais com vírgula. Datas em AAAA-MM-DD ou DD/MM/AAAA."""
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    first = text.splitlines()[0] if text else ""
    sep = ";" if first.count(";") > first.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
    cols = {c.strip().lower(): c for c in df.columns}
    aliases = {"date": ["date", "data"], "close": ["close", "fechamento", "adj close", "preco", "preço"],
               "high": ["high", "maxima", "máxima"], "low": ["low", "minima", "mínima"],
               "open": ["open", "abertura"]}
    found = {}
    for key, names in aliases.items():
        for n in names:
            if n in cols:
                found[key] = cols[n]
                break
    if "date" not in found or "close" not in found:
        raise ValueError("O CSV precisa das colunas Date e Close (ou Data e Fechamento).")

    def num(s: pd.Series) -> pd.Series:
        s = s.astype(str).str.strip()
        if sep == ";" or s.str.contains(r",\d+$", regex=True).any():
            s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        return pd.to_numeric(s, errors="coerce")

    raw_dates = df[found["date"]].astype(str).str.strip()
    dayfirst = raw_dates.str.match(r"^\d{1,2}/\d{1,2}/\d{4}").any()
    out = pd.DataFrame(index=pd.to_datetime(raw_dates, dayfirst=dayfirst, errors="coerce"))
    for key in ("open", "high", "low", "close"):
        if key in found:
            out[key.capitalize()] = num(df[found[key]]).to_numpy()
    out = out[out.index.notna()]
    return clean_prices(out)


def historical_vol(close: pd.Series, window: int = TRADING_DAYS) -> float:
    """Vol histórica anualizada dos últimos ``window`` pregões (desvio dos log-retornos)."""
    lr = np.log(close.astype(float)).diff().dropna()
    lr = lr.iloc[-window:]
    if len(lr) < 2:
        return float("nan")
    return float(lr.std(ddof=1) * np.sqrt(TRADING_DAYS))


# ---------------------------------------------------------------------------
# Selic / CDI (API SGS do Banco Central)
# ---------------------------------------------------------------------------

def _sgs_get(code: int, params: dict, timeout: float = 15.0) -> list[dict]:
    import requests

    url = SGS_URL.format(code=code)
    if "ultimos" in params:
        url += f"/ultimos/{params.pop('ultimos')}"
    resp = requests.get(url, params={"formato": "json", **params}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(str(data))
    return data


def fetch_selic_meta() -> float | None:
    """Selic meta mais recente em fração ao ano (0,1375 = 13,75% a.a.); None se falhar."""
    try:
        data = _sgs_get(SGS_SELIC_META, {"ultimos": 1})
        return float(data[-1]["valor"]) / 100.0
    except Exception:
        return None


def fetch_cdi_daily(start: date | str, end: date | str) -> pd.Series | None:
    """Taxa CDI diária (fração ao dia) indexada por data; consulta em blocos de 5 anos
    (a API limita séries diárias a 10 anos por consulta). None se falhar."""
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    frames = []
    try:
        cur = start
        while cur <= end:
            stop = min(cur + pd.DateOffset(years=5) - pd.Timedelta(days=1), end)
            data = _sgs_get(SGS_CDI_DAILY, {"dataInicial": cur.strftime("%d/%m/%Y"),
                                            "dataFinal": stop.strftime("%d/%m/%Y")})
            if data:
                frames.append(pd.DataFrame(data))
            cur = stop + pd.Timedelta(days=1)
    except Exception:
        return None
    if not frames:
        return None
    df = pd.concat(frames)
    s = pd.Series(pd.to_numeric(df["valor"], errors="coerce").to_numpy() / 100.0,
                  index=pd.to_datetime(df["data"], format="%d/%m/%Y"), name="cdi")
    return s[~s.index.duplicated()].sort_index().dropna()


def latest_cdi_annual(cdi_daily: pd.Series | None) -> float | None:
    """CDI efetivo mais recente em taxa anual base 252: (1 + CDI do último dia)^252 − 1."""
    if cdi_daily is None or cdi_daily.empty:
        return None
    return float((1 + float(cdi_daily.iloc[-1])) ** TRADING_DAYS - 1)


def cdi_factor_on_index(index: pd.DatetimeIndex, cdi_daily: pd.Series | None,
                        fallback_annual: float) -> np.ndarray:
    """Fator acumulado do CDI em cada data da série de preços (começa em 1).

    O CDI de cada pregão é o publicado para aquela data; datas sem dado usam a
    última taxa conhecida ou, na falta, a taxa anual de fallback."""
    fallback_daily = (1 + fallback_annual) ** (1 / TRADING_DAYS) - 1
    if cdi_daily is None or cdi_daily.empty:
        rates = np.full(len(index), fallback_daily)
    else:
        rates = cdi_daily.reindex(index.union(cdi_daily.index)).ffill().reindex(index)
        rates = rates.fillna(fallback_daily).to_numpy(dtype=float, copy=True)
    rates[0] = 0.0  # o primeiro pregão é a base
    return np.cumprod(1 + rates)


# ---------------------------------------------------------------------------
# Calendário de pregões (para datas futuras, fora da série)
# ---------------------------------------------------------------------------

def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def b3_holidays(year: int) -> list[date]:
    """Aproximação dos feriados da B3: nacionais, Carnaval (seg e ter), Sexta-feira
    Santa, Corpus Christi, Consciência Negra (desde 2024), 24/12 e 31/12."""
    e = _easter(year)
    fixed = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 24), (12, 25), (12, 31)]
    days = [date(year, m, d) for m, d in fixed]
    if year >= 2024:
        days.append(date(year, 11, 20))
    days += [e - timedelta(days=48), e - timedelta(days=47), e - timedelta(days=2), e + timedelta(days=60)]
    return sorted(days)


def _holiday_array(start: date, end: date) -> np.ndarray:
    hs = [h for y in range(start.year, end.year + 1) for h in b3_holidays(y)]
    return np.array(hs, dtype="datetime64[D]")


def previous_business_day(d: date | str, index: pd.DatetimeIndex | None = None) -> pd.Timestamp:
    """Pregão anterior a ``d`` (D−1), pela série quando possível, senão pelo calendário."""
    d = pd.Timestamp(d).normalize()
    if index is not None and len(index) and d <= index[-1] + pd.Timedelta(days=1):
        prior = index[index < d]
        if len(prior):
            return prior[-1]
    hol = _holiday_array((d - pd.Timedelta(days=10)).date(), d.date())
    return pd.Timestamp(np.busday_offset(np.datetime64(d.date(), "D"), -1, roll="forward", holidays=hol))


def count_trading_days(trade_date: date | str, end_date: date | str,
                       index: pd.DatetimeIndex | None = None) -> int:
    """Nº de pregões em (trade_date, end_date]. Usa as datas da série de preços onde
    houver dados e o calendário aproximado da B3 para o trecho futuro."""
    t0, t1 = pd.Timestamp(trade_date).normalize(), pd.Timestamp(end_date).normalize()
    if t1 <= t0:
        return 0
    n = 0
    last = t0
    if index is not None and len(index):
        in_range = index[(index > t0) & (index <= t1)]
        n += len(in_range)
        last = max(t0, min(t1, index[-1]))
    if t1 > last:
        hol = _holiday_array(last.date(), t1.date())
        n += int(np.busday_count(np.datetime64((last + pd.Timedelta(days=1)).date(), "D"),
                                 np.datetime64((t1 + pd.Timedelta(days=1)).date(), "D"), holidays=hol))
    return n


def term_from_dates(trade_date, expiry_date, index: pd.DatetimeIndex | None = None) -> tuple[int, pd.Timestamp]:
    """Prazo em pregões entre a contratação e a apuração (fechamento de D−1 do vencimento)."""
    obs = previous_business_day(expiry_date, index)
    return count_trading_days(trade_date, obs, index), obs
