"""Gráficos Plotly com rótulos em pt-BR e formato numérico brasileiro (1.234,56)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .backtest import BacktestResult, ExPostResult
from .formatting import fmt_brl, fmt_level
from .legs import Structure, event_label, expiry_payoff, returns_from_payoff

BLUE = "#2a78d6"  # estrutura / barreira não tocada / histórico / lucro
ORANGE = "#eb6834"  # barreira tocada / Monte Carlo
RED = "#e34948"  # perda
GRAY = "#898781"  # só a ação / referências
AQUA = "#1baf7a"  # CDI

BASE_LAYOUT = dict(
    separators=",.",  # decimal "," e milhar "."
    hovermode="x unified",
    margin=dict(l=10, r=10, t=90, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def _layout(fig: go.Figure, title: str, xtitle: str, ytitle: str, height: int = 430, **kw) -> go.Figure:
    fig.update_layout(title=dict(text=title, x=0, xanchor="left", y=0.98, yanchor="top"), xaxis_title=xtitle,
                      yaxis_title=ytitle, height=height, **BASE_LAYOUT)
    fig.update_layout(**kw)
    return fig


def payoff_chart(structure: Structure, cost: float, extra_cost: float = 0.0) -> go.Figure:
    """Retorno da estrutura no vencimento vs variação da ação (ramos com e sem toque)."""
    levels = [1.0] + structure.strikes + [e[1] for e in structure.events]
    hi = max(1.5, max(levels) + 0.25)
    lo = max(0.0, min(0.5, min(levels) - 0.25))
    s = np.unique(np.concatenate([np.linspace(lo, hi, 801), np.array(levels), np.array(levels) - 1e-6]))
    x = s - 1
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=x, name="Só a ação", line=dict(color=GRAY, width=2, dash="dash"),
                             hovertemplate="%{y:.2%}"))
    branches = [("none", "Barreira não tocada", BLUE), ("all", "Barreira tocada", ORANGE)] \
        if structure.events else [("none", "Estrutura", BLUE)]
    for b, name, color in branches:
        p = expiry_payoff(structure, s, b)
        r = np.where(np.isfinite(p), returns_from_payoff(np.nan_to_num(p), cost, structure.has_stock, extra_cost),
                     np.nan)
        fig.add_trace(go.Scatter(x=x, y=r, name=name, line=dict(color=color, width=2.5),
                                 hovertemplate="%{y:.2%}", connectgaps=False))
    for i, k in enumerate(structure.strikes):  # alterna o lado do rótulo para não sobrepor
        fig.add_vline(x=k - 1, line=dict(color=GRAY, width=1, dash="dot"),
                      annotation_text=f"K {fmt_level(k)}",
                      annotation_position="top left" if i % 2 == 0 else "top right",
                      annotation_font_color=GRAY)
    for ev in structure.events:
        fig.add_vline(x=ev[1] - 1, line=dict(color=ORANGE, width=1.5, dash="dash"),
                      annotation_text=f"Barreira {fmt_level(ev[1])}", annotation_position="bottom right",
                      annotation_font_color=ORANGE)
    fig.add_hline(y=0, line=dict(color=GRAY, width=1))
    _layout(fig, "Retorno no vencimento × variação da ação", "Variação da ação no vencimento",
            "Retorno da estrutura")
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(tickformat=".0%")
    return fig


def histogram_chart(results: dict[str, BacktestResult], cdi: float | None = None) -> go.Figure:
    """Histograma dos retornos (frequência relativa), sobrepostos."""
    colors = [BLUE, ORANGE, AQUA]
    fig = go.Figure()
    all_r = np.concatenate([res.df["retorno"].to_numpy() for res in results.values()])
    lo, hi = np.percentile(all_r, 0.5), np.percentile(all_r, 99.5)
    span = max(hi - lo, 1e-3)
    size = span / 60
    for (name, res), color in zip(results.items(), colors):
        fig.add_trace(go.Histogram(
            x=res.df["retorno"], name=name, histnorm="probability", opacity=0.6,
            marker=dict(color=color, line=dict(color="rgba(0,0,0,0)", width=0)),
            xbins=dict(start=lo - size, end=hi + size, size=size),
            hovertemplate="Retorno %{x:.1%}<br>Frequência %{y:.1%}<extra>" + name + "</extra>"))
    fig.add_vline(x=0, line=dict(color=GRAY, width=1.5), annotation_text="0%", annotation_position="top")
    if cdi is not None and np.isfinite(cdi):
        fig.add_vline(x=cdi, line=dict(color=AQUA, width=1.5, dash="dash"),
                      annotation_text="CDI", annotation_position="top right", annotation_font_color=AQUA)
    _layout(fig, "Distribuição dos retornos", "Retorno da estrutura no período", "Frequência relativa",
            barmode="overlay", bargap=0.02, hovermode="closest")
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(tickformat=".0%")
    return fig


def windows_timeseries_chart(res: BacktestResult) -> go.Figure:
    """Retorno de cada janela pela data de início: cor = lucro/perda, símbolo = barreira."""
    df = res.df
    profit = df["retorno"] > 1e-9
    hit = df["barreira_qualquer"].to_numpy()
    fig = go.Figure()
    combos = [(True, False, "Lucro", BLUE, "circle"), (False, False, "Sem lucro", RED, "circle"),
              (True, True, "Lucro (barreira acionada)", BLUE, "x"),
              (False, True, "Sem lucro (barreira acionada)", RED, "x")]
    for is_profit, is_hit, name, color, symbol in combos:
        m = (profit == is_profit).to_numpy() & (hit == is_hit)
        if not m.any():
            continue
        sub = df.loc[m]
        fig.add_trace(go.Scattergl(
            x=sub["data_inicio"], y=sub["retorno"], mode="markers", name=name,
            marker=dict(color=color, size=5 if symbol == "circle" else 6, symbol=symbol, opacity=0.75),
            customdata=np.stack([sub["data_fim"].dt.strftime("%d/%m/%Y"), sub["retorno_acao"]], axis=1),
            hovertemplate=("Início %{x|%d/%m/%Y} → fim %{customdata[0]}<br>Estrutura %{y:.2%}"
                           "<br>Ação %{customdata[1]:.2%}<extra>" + name + "</extra>")))
    fig.add_hline(y=0, line=dict(color=GRAY, width=1))
    _layout(fig, "Retorno de cada janela pela data de início", "Data de início da janela",
            "Retorno da estrutura", hovermode="closest")
    fig.update_xaxes(tickformat="%m/%Y")
    fig.update_yaxes(tickformat=".0%")
    return fig


def price_chart(prices: pd.DataFrame, ticker: str, structure: Structure | None = None,
                window: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> go.Figure:
    """Preço da ação no período, com destaque opcional de uma janela (e seus níveis)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices.index, y=prices["Close"], name="Fechamento",
                             line=dict(color=BLUE, width=1.5), hovertemplate="R$ %{y:,.2f}"))
    if window is not None:
        start, end = window
        fig.add_vrect(x0=start, x1=end, fillcolor=ORANGE, opacity=0.12, line_width=0)
        if structure is not None and start in prices.index:
            s0 = float(prices.loc[start, "Close"])
            for k in structure.strikes:
                fig.add_shape(type="line", x0=start, x1=end, y0=k * s0, y1=k * s0,
                              line=dict(color=GRAY, width=1, dash="dot"))
            for ev in structure.events:
                fig.add_shape(type="line", x0=start, x1=end, y0=ev[1] * s0, y1=ev[1] * s0,
                              line=dict(color=ORANGE, width=1.5, dash="dash"))
    _layout(fig, f"Preço de {ticker}", "Data", "Preço (R$)", height=380, showlegend=False)
    fig.update_xaxes(tickformat="%m/%Y")
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
    return fig


def ex_post_chart(res: ExPostResult, structure: Structure, ticker: str) -> go.Figure:
    """Caminho realizado com strikes e barreiras (em R$) e marcos da operação."""
    p = res.path
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=p.index, y=p["preco"], name="Fechamento", line=dict(color=BLUE, width=2),
                             hovertemplate="R$ %{y:,.2f}"))
    if (p["maxima"] != p["nivel"]).any():
        fig.add_trace(go.Scatter(x=p.index, y=p["maxima"] * res.s0_price, name="Máxima",
                                 line=dict(color=BLUE, width=1, dash="dot"), opacity=0.5,
                                 hovertemplate="R$ %{y:,.2f}"))
        fig.add_trace(go.Scatter(x=p.index, y=p["minima"] * res.s0_price, name="Mínima",
                                 line=dict(color=BLUE, width=1, dash="dot"), opacity=0.5,
                                 hovertemplate="R$ %{y:,.2f}"))
    x0 = res.trade_date
    x1 = max(res.obs_date, p.index[-1])
    fig.add_shape(type="line", x0=x0, x1=x1, y0=res.s0_price, y1=res.s0_price,
                  line=dict(color=GRAY, width=1))
    fig.add_annotation(x=x0, y=res.s0_price, text=f"Valor inicial {fmt_brl(res.s0_price)}", showarrow=False, xanchor="left", yanchor="bottom",
                       font=dict(color=GRAY))
    for k in structure.strikes:
        y = k * res.s0_price
        fig.add_shape(type="line", x0=x0, x1=x1, y0=y, y1=y, line=dict(color=GRAY, width=1, dash="dot"))
        fig.add_annotation(x=x1, y=y, text=f"K {fmt_level(k)}", showarrow=False, xanchor="right",
                           yanchor="bottom", font=dict(color=GRAY))
    for ev in structure.events:
        y = ev[1] * res.s0_price
        fig.add_shape(type="line", x0=x0, x1=x1, y0=y, y1=y, line=dict(color=ORANGE, width=1.5, dash="dash"))
        fig.add_annotation(x=x1, y=y, text=f"Barreira {fmt_level(ev[1])}", showarrow=False, xanchor="right",
                           yanchor="bottom", font=dict(color=ORANGE))
        hit, when = res.hits.get(event_label(ev), (False, None))
        if hit and when is not None:
            fig.add_trace(go.Scatter(x=[when], y=[p.loc[when, "preco"]], mode="markers", name="Toque na barreira",
                                     marker=dict(color=ORANGE, size=12, symbol="x"),
                                     hovertemplate="Barreira tocada em %{x|%d/%m/%Y}<extra></extra>"))
    fig.add_vline(x=res.obs_date, line=dict(color=GRAY, width=1, dash="dash"))
    fig.add_annotation(x=res.obs_date, y=0, yref="paper", text="Apuração (D−1)", showarrow=False,
                       xanchor="right", yanchor="bottom", font=dict(color=GRAY))
    _layout(fig, f"{ticker}: caminho realizado desde a contratação", "Data", "Preço (R$)", height=450)
    fig.update_xaxes(tickformat="%d/%m/%Y")
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
    return fig


def mc_paths_chart(res: BacktestResult, structure: Structure, n_show: int = 100) -> go.Figure:
    """Amostra de caminhos simulados (nível em % do valor inicial) com strikes e barreiras."""
    paths = res.meta.get("paths_sample")
    fig = go.Figure()
    if paths is not None:
        n_days = paths.shape[1]
        x = np.arange(0, n_days + 1)
        for i, path in enumerate(paths[:n_show]):
            fig.add_trace(go.Scattergl(x=x, y=np.concatenate([[1.0], path]), mode="lines",
                                       line=dict(color=BLUE, width=1), opacity=0.18, showlegend=False,
                                       hoverinfo="skip"))
    for i, k in enumerate(structure.strikes):
        fig.add_hline(y=k, line=dict(color=GRAY, width=1, dash="dot"), annotation_text=f"K {fmt_level(k)}",
                      annotation_position="top left" if i % 2 == 0 else "bottom left",
                      annotation_font_color=GRAY)
    for ev in structure.events:
        fig.add_hline(y=ev[1], line=dict(color=ORANGE, width=1.5, dash="dash"),
                      annotation_text=f"Barreira {fmt_level(ev[1])}", annotation_font_color=ORANGE)
    _layout(fig, f"Amostra de {min(n_show, 0 if paths is None else len(paths))} caminhos simulados",
            "Pregões desde a contratação", "Nível (% do valor inicial)", hovermode=False, showlegend=False)
    fig.update_yaxes(tickformat=".0%")
    return fig


def exit_days_chart(results: dict, n_days: int) -> go.Figure:
    """Saída antecipada: fração das janelas/caminhos desmontados em cada mês (21 pregões) da operação."""
    colors = [BLUE, ORANGE]
    fig = go.Figure()
    nb = int(np.ceil(n_days / 21))
    labels = [f"{i + 1}º mês" for i in range(nb)]
    for (name, res), color in zip(results.items(), colors):
        df = res.df
        days = df.loc[df["saida_antecipada"], "dia_saida"].to_numpy()
        counts = np.bincount(np.minimum((days - 1) // 21, nb - 1), minlength=nb) / max(len(df), 1)
        fig.add_trace(go.Bar(x=labels, y=counts, name=name, marker_color=color,
                             hovertemplate="%{x}: %{y:.1%}<extra>" + name + "</extra>"))
    _layout(fig, "Quando acontece a saída antecipada", "Mês da operação", "Fração das simulações",
            barmode="group", hovermode="closest")
    fig.update_yaxes(tickformat=".0%")
    return fig


def ex_post_exit_chart(x, trigger: float) -> go.Figure:
    """Ex-post: retorno de saída estimado (marcação diária) × gatilho de % do CDI."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x.dates, y=x.ret, name="Retorno de saída (marcação)", line=dict(color=BLUE, width=2),
                             hovertemplate="%{y:.2%}"))
    fig.add_trace(go.Scatter(x=x.dates, y=x.threshold, name=f"Gatilho ({trigger:.0%} do CDI)".replace(".", ","),
                             line=dict(color=AQUA, width=1.5, dash="dash"), hovertemplate="%{y:.2%}"))
    for date, label, color in ((x.trigger_date, "Gatilho atingido", ORANGE), (x.exit_date, "Desmontagem", RED)):
        if date is not None:
            i = x.dates.index(date)
            fig.add_trace(go.Scatter(x=[date], y=[x.ret[i]], mode="markers", name=label,
                                     marker=dict(color=color, size=12, symbol="diamond")))
    _layout(fig, "Retorno de saída estimado × gatilho", "Data", "Retorno acumulado", height=380)
    fig.update_xaxes(tickformat="%d/%m/%Y")
    fig.update_yaxes(tickformat=".0%")
    return fig
