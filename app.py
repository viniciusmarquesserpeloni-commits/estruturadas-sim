"""Simulador de Operações Estruturadas — interface Streamlit.

Rodar:  streamlit run app.py
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from estruturadas import charts, data
from estruturadas import io as sio
from estruturadas import presets
from estruturadas.backtest import (DRIFT_LABELS, MC_METHOD_LABELS, SCENARIO_DRIFTS, SCENARIO_VOLS, run_ex_post,
                                   run_historical, run_monte_carlo, run_scenarios)
from estruturadas.early_exit import (VOL_MODE_LABELS, EarlyExitConfig, run_ex_post_exit, run_historical_exit,
                                     run_mc_exit)
from estruturadas.formatting import fmt_brl, fmt_level, fmt_num, fmt_pct
from estruturadas.legs import (BARRIER_LABELS, KIND_LABELS, MONITORING_LABELS, Leg, Structure, has_errors,
                               payoff_profile_summary, validate)
from estruturadas.metrics import (comparison_table, default_variations, exit_by_cdi_regime, exit_table,
                                  profitability_table, summarize, summarize_exit)
from estruturadas.pricing import (PARAM_LABELS, PARAMS, annual_to_continuous, default_bounds, price_structure,
                                  solve_zero_cost)

st.set_page_config(page_title="Simulador de Estruturadas", page_icon="📈", layout="wide")

MIN_LAMINA = 30_000.0
KIND_FROM_LABEL = {v: k for k, v in KIND_LABELS.items()}
BARRIER_FROM_LABEL = {v: k for k, v in BARRIER_LABELS.items()}
POS_FROM_LABEL = {"Comprada": 1, "Vendida": -1}
CUSTOM_KEY = "custom"
METODOLOGIA = (Path(__file__).parent / "METODOLOGIA.md").read_text(encoding="utf-8")

def md_brl(x) -> str:
    """R$ formatado para textos Markdown (escapa o $, que o Streamlit trata como LaTeX)."""
    return fmt_brl(x).replace("$", r"\$")


DISCLAIMER = ("Ferramenta educacional. Não é recomendação de investimento. Passado não garante futuro. "
              "Retornos brutos de IR.")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cached_prices(ticker: str, start: date, end: date, adjusted: bool) -> pd.DataFrame:
    return data.load_prices_yf(ticker, start, end, adjusted)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cached_selic() -> float | None:
    return data.fetch_selic_meta()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _cached_cdi_strict(start: date, end: date) -> pd.Series:
    s = data.fetch_cdi_daily(start, end)
    if s is None:
        raise ConnectionError("CDI indisponível no BCB")  # exceção não entra no cache: tenta de novo na próxima
    return s


def cached_cdi(start: date, end: date) -> pd.Series | None:
    try:
        return _cached_cdi_strict(start, end)
    except ConnectionError:
        return None


@st.cache_data(show_spinner=False, max_entries=64)
def cached_pricing(struct_json: str, sigma: float, r: float, q: float, n_days: int, n_paths: int,
                   seed: int, monitoring: str) -> dict:
    s = sio.loads(struct_json)
    res = price_structure(s, sigma, r, q, n_days, n_paths, seed, monitoring)
    return {
        "net": res.net_cost, "net_se": res.net_stderr, "n_paths": res.n_paths,
        "legs": [{"Perna": lp.leg.label(), "Método": lp.method, "Preço unitário": lp.unit_price,
                  "Contribuição ao custo": lp.signed_price, "Erro padrão": lp.stderr} for lp in res.legs],
    }


@st.cache_data(show_spinner=False, max_entries=16)
def cached_historical(struct_json: str, prices: pd.DataFrame, n_days: int, cost: float, monitoring: str,
                      extra_cost: float, cdi_factor: np.ndarray, cdi_ref: float, regime_adjust: bool):
    return run_historical(sio.loads(struct_json), prices, n_days, cost, monitoring, extra_cost, cdi_factor,
                          cdi_ref, regime_adjust)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_mc(struct_json: str, prices: pd.DataFrame, n_days: int, cost: float, method: str, n_paths: int,
              block: int, drift: str, cdi_annual: float, seed: int, monitoring: str, extra_cost: float,
              premium: float, custom: float | None):
    return run_monte_carlo(sio.loads(struct_json), prices, n_days, cost, method, n_paths, block, drift,
                           cdi_annual, seed, monitoring, extra_cost, premium=premium, custom=custom)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_scen(struct_json: str, prices: pd.DataFrame, n_days: int, cost: float, method: str, block: int,
                cdi_annual: float, seed: int, monitoring: str, extra_cost: float, premium: float):
    return run_scenarios(sio.loads(struct_json), prices, n_days, cost, method, block, cdi_annual, seed, monitoring,
                         extra_cost, premium)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_hexit(struct_json: str, prices: pd.DataFrame, n_days: int, cost: float, cfg: dict, cdi_factor: np.ndarray,
                 ret_hold: np.ndarray, monitoring: str, extra_cost: float, cdi_ref: float, regime_adjust: bool):
    return run_historical_exit(sio.loads(struct_json), prices, n_days, cost, EarlyExitConfig(**cfg), cdi_factor,
                               ret_hold, monitoring, extra_cost, cdi_ref, regime_adjust)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_mcexit(struct_json: str, paths: np.ndarray, n_days: int, cost: float, cfg: dict, ret_hold: np.ndarray,
                  sigma: float, cdi_annual: float, monitoring: str, extra_cost: float, high, low):
    return run_mc_exit(sio.loads(struct_json), paths, n_days, cost, EarlyExitConfig(**cfg), ret_hold, sigma, cdi_annual,
                       monitoring, extra_cost, high, low)


# ---------------------------------------------------------------------------
# Estado da estrutura (tabela editável)
# ---------------------------------------------------------------------------

def structure_to_df(s: Structure) -> pd.DataFrame:
    rows = []
    for leg in s.legs:
        rows.append({
            "Tipo": KIND_LABELS[leg.kind],
            "Posição": "Comprada" if leg.position > 0 else "Vendida",
            "Strike (%)": None if leg.strike is None else round(leg.strike * 100, 6),
            "Barreira": BARRIER_LABELS[leg.barrier],
            "Barreira (%)": None if leg.barrier_level is None else round(leg.barrier_level * 100, 6),
            "Proporção": leg.ratio,
        })
    df = pd.DataFrame(rows, columns=["Tipo", "Posição", "Strike (%)", "Barreira", "Barreira (%)", "Proporção"])
    df.index = pd.RangeIndex(1, len(df) + 1, name="Perna")
    return df


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def df_to_structure(df: pd.DataFrame, base: Structure) -> Structure:
    legs = []
    for _, row in df.iterrows():
        kind = KIND_FROM_LABEL.get(row.get("Tipo"))
        if kind is None:
            continue
        strike = _num(row.get("Strike (%)"))
        level = _num(row.get("Barreira (%)"))
        ratio = _num(row.get("Proporção"))
        legs.append(Leg(kind=kind, position=POS_FROM_LABEL.get(row.get("Posição"), 1),
                        strike=None if strike is None else strike / 100,
                        barrier=BARRIER_FROM_LABEL.get(row.get("Barreira"), "none"),
                        barrier_level=None if level is None else level / 100,
                        ratio=1.0 if ratio is None else ratio))
    return base.copy(legs=legs)


def load_structure(s: Structure, reset_meta: bool = True) -> None:
    """Coloca uma estrutura na tabela (chamar antes de criar os widgets afetados)."""
    st.session_state.base_structure = s
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
    st.session_state.pop("solver_result", None)
    if not reset_meta:
        return
    if s.ticker:
        st.session_state.ticker = s.ticker
    st.session_state.cost_informed = round(100 * s.option_cost, 6)
    if s.trade_date and s.expiry_date:
        td, ed = pd.Timestamp(s.trade_date).date(), pd.Timestamp(s.expiry_date).date()
        st.session_state.trade_date = td
        st.session_state.expiry_date = ed
        st.session_state.expost_trade = td
        st.session_state.expost_expiry = ed


def on_preset_change() -> None:
    key = st.session_state.preset_select
    if key == CUSTOM_KEY:
        s = Structure("Estrutura customizada", [Leg("stock", 1)])
    else:
        s = presets.PRESETS[key].builder()
    load_structure(s)


def init_state() -> None:
    if "base_structure" not in st.session_state:
        # padrão: estrutura típica de 3 meses; a lâmina Proteção Total BBDC4 segue disponível como preset
        st.session_state.preset_select = "collar_ki"
        st.session_state.ticker = "BBDC4"
        st.session_state.cost_informed = 0.0
        st.session_state.term_mode = "Meses"
        load_structure(presets.collar_ki(1.0, 1.06, 1.12))


init_state()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

sb = st.sidebar
sb.title("📈 Estruturadas")
sb.caption(DISCLAIMER)

sb.header("1. Estrutura")
preset_options = list(presets.PRESETS) + [CUSTOM_KEY]
sb.selectbox("Preset", preset_options, key="preset_select", on_change=on_preset_change,
             format_func=lambda k: "Customizada (em branco)" if k == CUSTOM_KEY else presets.PRESETS[k].name,
             help="Os presets apenas preenchem a tabela de pernas (aba Estrutura), que pode ser editada livremente.")
uploaded_json = sb.file_uploader("Importar lâmina/estrutura (JSON)", type=["json"])
if uploaded_json is not None:
    upload_id = f"{uploaded_json.name}-{uploaded_json.size}"
    if st.session_state.get("json_loaded_id") != upload_id:
        try:
            imported = sio.loads(uploaded_json.getvalue())
            st.session_state.json_loaded_id = upload_id
            load_structure(imported)
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            sb.error(f"Não foi possível ler o JSON: {exc}")

sb.header("2. Ação e histórico")
sb.text_input("Código da ação (B3)", key="ticker", help="Ex.: PETR4, VALE3, BBDC4 (o sufixo .SA é adicionado).")
c1, c2 = sb.columns(2)
hist_start = c1.date_input("Histórico desde", value=date(2010, 1, 1), min_value=date(1995, 1, 1),
                           format="DD/MM/YYYY")
hist_end = c2.date_input("até", value=date.today(), format="DD/MM/YYYY")
price_kind = sb.radio("Preço", ["Ajustado por proventos", "Bruto (sem ajuste)"], horizontal=False,
                      help="As lâminas ajustam strikes e barreiras em eventos corporativos; o preço ajustado "
                           "é a aproximação padrão.")
with sb.expander("Usar arquivo CSV em vez do Yahoo Finance"):
    uploaded_csv = st.file_uploader("CSV com colunas Date, Close[, High, Low]", type=["csv", "txt"])

ticker = (st.session_state.ticker or "").strip().upper()
prices: pd.DataFrame | None = None
price_error = None
try:
    if uploaded_csv is not None:
        prices = data.parse_price_csv(uploaded_csv.getvalue())
        prices = prices.loc[(prices.index >= pd.Timestamp(hist_start)) & (prices.index <= pd.Timestamp(hist_end))]
        ticker = ticker or "CSV"
    else:
        with st.spinner(f"Baixando preços de {data.normalize_ticker(ticker)}…"):
            prices = cached_prices(ticker, hist_start, hist_end, price_kind.startswith("Ajustado"))
    if prices is None or len(prices) < 30:
        raise ValueError("Histórico muito curto (menos de 30 pregões).")
except Exception as exc:  # noqa: BLE001
    price_error = str(exc)
    prices = None

sb.header("3. Prazo")
term_mode = sb.radio("Definir prazo por", ["Meses", "Dias úteis", "Datas"], key="term_mode", horizontal=True)
obs_date = None
if term_mode == "Meses":
    vertice = sb.radio("Vértice", ["3 meses", "6 meses", "9 meses", "12 meses", "Outro"], horizontal=True)
    if vertice == "Outro":
        months = sb.number_input("Meses (1 mês = 21 dias úteis)", min_value=1, max_value=120, value=3, step=1)
    else:
        months = int(vertice.split()[0])
    n_days = int(months * 21)
elif term_mode == "Dias úteis":
    n_days = int(sb.number_input("Dias úteis (pregões)", min_value=1, max_value=2520, value=252, step=1))
else:
    if "trade_date" not in st.session_state:
        st.session_state.trade_date = date.today()
        st.session_state.expiry_date = (pd.Timestamp.today() + pd.DateOffset(years=1)).date()
    d1, d2 = sb.columns(2)
    trade_d = d1.date_input("Contratação", key="trade_date", format="DD/MM/YYYY")
    expiry_d = d2.date_input("Vencimento", key="expiry_date", format="DD/MM/YYYY")
    if expiry_d <= trade_d:
        sb.error("O vencimento deve ser posterior à contratação.")
        n_days = 1
    else:
        n_days, obs_date = data.term_from_dates(trade_d, expiry_d, None if prices is None else prices.index)
        n_days = max(int(n_days), 1)
    sb.caption("Valor inicial = fechamento da contratação; apuração no fechamento de D−1 do vencimento "
               "(liquidação em D+1, apenas informativa).")
sb.caption(f"Prazo: **{n_days} pregões** (≈ {n_days / 21:.1f} meses)"
           + (f" · apuração em {obs_date:%d/%m/%Y}" if obs_date is not None else ""))

sb.header("4. Valor e custos")
invested = sb.number_input("Valor investido (R$)", min_value=0.0, value=MIN_LAMINA, step=1_000.0, format="%.2f")
if invested < MIN_LAMINA:
    sb.caption(f"ℹ️ As lâminas costumam indicar aplicação mínima de {md_brl(MIN_LAMINA)} (apenas referência).")
cost_mode = sb.radio("Custo das opções", ["Informado", "Teórico"], horizontal=True,
                     help="Informado: custo líquido cotado pela mesa (0 = estrutura sem custo). "
                          "Teórico: calculado pelo app (Black-Scholes / Monte Carlo neutro ao risco).")
sb.number_input("Custo líquido das opções (% do valor inicial)", key="cost_informed", step=0.10, format="%.4f",
                disabled=cost_mode != "Informado",
                help="Cotação da mesa. Positivo = débito (você paga); negativo = crédito; 0 = sem custo. "
                     "Estruturas só com opções exigem > 0.")
extra_cost_pct = sb.number_input("Custos/taxas adicionais (% do valor investido)", min_value=0.0, value=0.0,
                                 step=0.05, format="%.2f")
extra_cost = extra_cost_pct / 100

hist_vol = data.historical_vol(prices["Close"]) if prices is not None else float("nan")
selic = cached_selic()
with sb.expander("Parâmetros de precificação", expanded=cost_mode == "Teórico"):
    vol_default = round(100 * hist_vol, 2) if np.isfinite(hist_vol) else 30.0
    vol_pct = st.number_input("Volatilidade (% a.a.)", min_value=1.0, max_value=300.0, value=float(vol_default),
                              step=0.5, help="Padrão: vol histórica anualizada dos últimos 252 pregões.")
    cdi_now = data.latest_cdi_annual(cached_cdi(date.today() - timedelta(days=20), date.today()))
    rate_default = (round(100 * cdi_now, 2) if cdi_now is not None
                    else round(100 * selic - 0.10, 2) if selic is not None else 10.0)
    rate_pct = st.number_input("CDI de referência (% a.a.)", min_value=0.0, max_value=100.0,
                               value=float(rate_default), step=0.25,
                               help="Padrão: CDI efetivo mais recente (série 12 do BCB). Use o DI futuro do vencimento, "
                                    "se souber. É a régua de P(> CDI de hoje), o ajuste de regime, o drift do Monte "
                                    "Carlo e a taxa do modo Teórico.")
    if cdi_now is None:
        st.caption("⚠️ Não foi possível consultar o CDI no BCB; informe manualmente.")
    q_pct = st.number_input("Dividend yield (% a.a.)", min_value=0.0, max_value=50.0, value=0.0, step=0.25)
    pricing_paths = st.select_slider("Caminhos do MC (barreiras)", [20_000, 50_000, 100_000, 200_000], value=50_000)
    pricing_seed = st.number_input("Seed do MC de precificação", value=42, step=1)
sigma, rate_annual, q = vol_pct / 100, rate_pct / 100, q_pct / 100
r_cont = annual_to_continuous(rate_annual)

sb.header("5. Barreiras")
monitoring = sb.radio("Monitoramento", list(MONITORING_LABELS), format_func=MONITORING_LABELS.get,
                      help="Fechamento diário: usa o Close de cada pregão. Intradiário: usa a máxima (barreiras "
                           "de alta) e a mínima (de baixa) no histórico; no Monte Carlo aplica a correção de "
                           "Broadie-Glasserman-Kou.")

sb.header("6. Monte Carlo (backtest)")
mc_method = sb.radio("Método", list(MC_METHOD_LABELS), format_func=MC_METHOD_LABELS.get)
mc_drift = sb.selectbox("Retorno esperado da ação", list(DRIFT_LABELS), format_func=DRIFT_LABELS.get,
                        help="Padrão: CDI (visão neutra). A média histórica é estatisticamente pouco confiável "
                             "(erro padrão ≈ σ/√anos).")
mc_premium = sb.number_input("Prêmio sobre o CDI (p.p. a.a.)", value=5.0, step=1.0) / 100 if mc_drift == "cdi_premio" else 0.05
mc_custom = sb.number_input("Retorno esperado (% a.a.)", value=15.0, step=1.0) / 100 if mc_drift == "personalizado" else None
regime_adjust = sb.checkbox("Ajustar histórico ao CDI de hoje", value=True,
                            help="Re-ancora cada janela histórica no CDI de hoje, preservando o excesso de retorno "
                                 "da ação sobre o CDI da época (\"e se eu contratasse agora?\").")
mc_block = sb.slider("Tamanho do bloco (dias)", 1, 120, 20) if mc_method == "bootstrap" else 20
mc_paths = sb.select_slider("Nº de caminhos", [1_000, 5_000, 10_000, 20_000, 50_000], value=10_000)
mc_seed = sb.number_input("Seed", value=42, step=1)

sb.header("7. Saída antecipada")
exit_on = sb.toggle("Simular saída antecipada", value=True,
                    help="Desmontagem antes do vencimento quando a estrutura rende acima do gatilho (% do CDI).")
exit_cfg = None
if exit_on:
    x1, x2 = sb.columns(2)
    exit_trigger = x1.number_input("Gatilho (% do CDI)", min_value=1.0, value=150.0, step=10.0)
    exit_spread = x2.number_input("Spread de saída (%)", min_value=0.0, value=1.0, step=0.25,
                                  help="Desconto sobre a marcação na desmontagem, em % do valor inicial (estimativa).")
    x3, x4 = sb.columns(2)
    exit_delay = x3.number_input("Pregões até desmontar", min_value=0, value=1, step=1,
                                 help="Tempo até o OK do investidor; a desmontagem usa o valor desse dia.")
    exit_min = x4.number_input("Carência (pregões)", min_value=0, value=0, step=1)
    exit_vol_mode = sb.selectbox("Vol da marcação", list(VOL_MODE_LABELS), format_func=VOL_MODE_LABELS.get)
    exit_vol_add = sb.number_input("Adicional de vol (pontos)", min_value=0.0, value=3.0, step=0.5)
    exit_calibrate = sb.checkbox("Calibrar ao preço pago na contratação", value=True,
                                 help="Soma à marcação a diferença entre o preço pago e o modelo no dia 0, "
                                      "amortizada até o vencimento.")
    exit_cfg = dict(trigger=exit_trigger / 100, exit_spread=exit_spread / 100, delay=int(exit_delay),
                    min_days=int(exit_min), vol_mode=exit_vol_mode, vol_add=exit_vol_add / 100,
                    calibrate=bool(exit_calibrate))


# ---------------------------------------------------------------------------
# Corpo
# ---------------------------------------------------------------------------

st.title("Simulador de Operações Estruturadas")
st.caption("Probabilidade de sair no lucro em estruturas com opções sobre ações da B3, com base no histórico "
           "de preços. " + DISCLAIMER)

if price_error:
    st.error(f"Não foi possível carregar os preços: {price_error}")

tab_struct, tab_hist, tab_mc, tab_ex, tab_method = st.tabs(
    ["Estrutura", "Backtest histórico", "Monte Carlo", "Ex-post", "Metodologia e limitações"])

base: Structure = st.session_state.base_structure

# ----------------------------- Aba Estrutura -------------------------------
with tab_struct:
    st.subheader(base.name)
    if base.notes:
        st.caption(base.notes)
    st.markdown("**Composição da estratégia** — strikes e barreiras em % do valor inicial; "
                "proporção = quantidade de opções por ação.")
    edited = st.data_editor(
        structure_to_df(base), key=f"legs_editor_{st.session_state.editor_version}", num_rows="dynamic",
        hide_index=False,
        column_config={
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=list(KIND_LABELS.values()), required=True,
                                                     default="Call"),
            "Posição": st.column_config.SelectboxColumn("Posição", options=list(POS_FROM_LABEL), required=True,
                                                        default="Comprada"),
            "Strike (%)": st.column_config.NumberColumn("Preço de exercício (%)", format="%.2f", min_value=0.0,
                                                        step=0.01),
            "Barreira": st.column_config.SelectboxColumn("Tipo de barreira", options=list(BARRIER_LABELS.values()),
                                                         required=True, default=BARRIER_LABELS["none"]),
            "Barreira (%)": st.column_config.NumberColumn("Valor da barreira (%)", format="%.2f", min_value=0.0,
                                                          step=0.01),
            "Proporção": st.column_config.NumberColumn("Proporção", format="%.4f", min_value=0.0, step=0.01,
                                                       default=1.0),
        })
    structure = df_to_structure(edited, base)

informed_cost = float(st.session_state.get("cost_informed", 0.0) or 0.0) / 100
pre_issues = validate(structure, informed_cost if cost_mode == "Informado" else None)
struct_ok = not has_errors(pre_issues)
struct_json = sio.dumps(structure)

theo = None
if struct_ok and structure.option_legs:
    try:
        with st.spinner("Calculando custo teórico…"):
            theo = cached_pricing(struct_json, sigma, r_cont, q, n_days, int(pricing_paths), int(pricing_seed),
                                  monitoring)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Falha no cálculo do custo teórico: {exc}")

if cost_mode == "Informado" or not structure.option_legs:
    cost = informed_cost if structure.option_legs else 0.0
else:
    cost = theo["net"] if theo else 0.0

issues = validate(structure, cost)
struct_ok = not has_errors(issues)
ready = struct_ok and prices is not None

with tab_struct:
    for level, msg in issues:
        (st.error if level == "erro" else st.warning)(msg)

    if struct_ok:
        prof = payoff_profile_summary(structure, cost)
        m = st.columns(4)
        m[0].metric("Custo das opções usado", fmt_pct(cost), help="Em % do valor inicial (+ = débito).")
        m[1].metric("Retorno máximo", "Ilimitado" if prof["gain_unlimited"] else fmt_pct(
            None if prof["return_max"] is None else prof["return_max"] - extra_cost))
        m[2].metric("Pior retorno", "Ilimitado" if prof["loss_unlimited"] else fmt_pct(
            None if prof["return_min"] is None else prof["return_min"] - extra_cost))
        m[3].metric("Prazo", f"{n_days} pregões", help=f"Valor investido: {md_brl(invested)}")

        if theo:
            with st.expander(f"Custo teórico: {fmt_pct(theo['net'])}"
                             + (f" (± {fmt_pct(theo['net_se'], 3)} de erro padrão do MC)" if theo["net_se"] else ""),
                             expanded=cost_mode == "Teórico"):
                if cost_mode == "Informado":
                    diff = informed_cost - theo["net"]
                    st.markdown(f"Custo informado: **{fmt_pct(informed_cost)}** · teórico: **{fmt_pct(theo['net'])}** "
                                f"· diferença: **{fmt_pct(diff)}** do valor inicial. A diferença reflete a "
                                "remuneração da estrutura e diferenças de volatilidade/taxa em relação à mesa.")
                legs_df = pd.DataFrame(theo["legs"])
                for c in ("Preço unitário", "Contribuição ao custo", "Erro padrão"):
                    legs_df[c] = legs_df[c].map(lambda v: fmt_pct(v, 3))
                st.dataframe(legs_df, hide_index=True)
                st.caption(f"Vol {fmt_pct(sigma)} a.a. · taxa {fmt_pct(rate_annual)} a.a. "
                           f"(contínua {fmt_pct(r_cont)}) · q {fmt_pct(q)} · {n_days} pregões · "
                           f"MC com {fmt_num(theo['n_paths'], 0)} caminhos (antitéticos, seed fixa). "
                           "Referência teórica: pode divergir do preço da mesa.")

        st.markdown("#### Resumo em linguagem simples")
        st.markdown(presets.describe(structure, cost))
        st.caption("Retornos no vencimento, brutos de IR, sobre o valor investido"
                   + (" (ação + custo das opções)." if structure.has_stock else " (prêmio pago).")
                   + (f" Já descontados {fmt_pct(extra_cost)} de custos adicionais." if extra_cost else ""))

        st.plotly_chart(charts.payoff_chart(structure, cost, extra_cost))

        st.markdown("#### Quadro de rentabilidade no vencimento")
        default_rows = "; ".join(fmt_num(100 * v, 0 if abs(100 * v - round(100 * v)) < 1e-9 else 2)
                                 for v in default_variations(structure))
        rows_txt = st.text_input("Variações da ação (%) separadas por ponto e vírgula", value=default_rows,
                                 key=f"rows_{st.session_state.editor_version}")
        try:
            variations = [float(x.strip().replace(",", ".")) / 100 for x in rows_txt.split(";") if x.strip()]
        except ValueError:
            st.warning("Não entendi a lista de variações; usando a padrão.")
            variations = default_variations(structure)
        qt = profitability_table(structure, cost, variations, extra_cost)
        num_qt = profitability_table(structure, cost, variations, extra_cost, formatted=False)
        for col in num_qt.columns[1:]:
            qt[f"{col} (R$)"] = [fmt_brl(invested * x) if np.isfinite(x) else "—" for x in num_qt[col]]
        st.dataframe(qt, hide_index=True)
        if structure.events:
            st.caption("“—” = cenário impossível (ex.: terminar acima de uma barreira de alta sem tê-la tocado, "
                       "com monitoramento diário).")

        with st.expander("Solver de custo zero"):
            st.caption("Encontra o valor de um parâmetro que zera o custo líquido teórico (ou atinge um custo alvo), "
                       "usando os parâmetros de precificação da barra lateral.")
            opt_idx = [i for i, leg in enumerate(structure.legs) if leg.is_option]
            if not opt_idx:
                st.info("A estrutura não tem opções.")
            else:
                sc = st.columns([3, 2, 1, 1, 1])
                sel = sc[0].multiselect("Perna(s) — várias = mesmo valor (ex.: put e call do FKO)", opt_idx,
                                        default=[opt_idx[-1]],
                                        format_func=lambda i: f"{i + 1}: {structure.legs[i].label()}")
                param = sc[1].selectbox("Parâmetro", PARAMS, format_func=PARAM_LABELS.get)
                scale = 1.0 if param == "ratio" else 100.0
                lo0, hi0 = default_bounds(structure.legs[sel[0]] if sel else structure.legs[opt_idx[0]], param)
                lo = sc[2].number_input("Mín.", value=float(round(lo0 * scale, 4)), key=f"slo_{param}")
                hi = sc[3].number_input("Máx.", value=float(round(hi0 * scale, 4)), key=f"shi_{param}")
                target = sc[4].number_input("Custo alvo (%)", value=0.0, step=0.1)
                if st.button("Resolver", type="primary", disabled=not sel):
                    with st.spinner("Resolvendo…"):
                        res = solve_zero_cost(structure, sel, param, sigma, r_cont, q, n_days, int(pricing_paths),
                                              int(pricing_seed), monitoring, (lo / scale, hi / scale), target / 100)
                    st.session_state.solver_result = (res, list(sel), param, structure)
                if "solver_result" in st.session_state:
                    res, s_sel, s_param, s_struct = st.session_state.solver_result
                    if res.converged:
                        shown = f"{res.value:.4f}" if s_param == "ratio" else fmt_level(res.value, 4)
                        st.success(f"{PARAM_LABELS[s_param]} = **{shown}** → custo {fmt_pct(res.cost, 4)}"
                                   + (f" (± {fmt_pct(res.stderr, 3)})" if res.stderr else ""))

                        def _apply(r=res, legs_sel=s_sel, p=s_param, s=s_struct):
                            from estruturadas.pricing import _with_param
                            load_structure(_with_param(s, legs_sel, p, r.value), reset_meta=False)

                        st.button("Aplicar à tabela", on_click=_apply)
                        if cost_mode == "Informado":
                            st.caption("Dica: mude o custo para “Teórico” (ou informe o custo alvo) para usar o "
                                       "custo resolvido nos backtests.")
                    else:
                        st.warning(res.message)

        st.download_button("⬇️ Baixar estrutura (JSON)", struct_json.encode("utf-8"),
                           file_name=f"{structure.name.lower().replace(' ', '_')}.json", mime="application/json")

# ----------------------------- Backtests -----------------------------------
hist_res = mc_res = hexit_res = mcexit_res = scen_res = None
cdi_factor = None
run_err = None
if ready:
    try:
        with st.spinner("Rodando backtest histórico e Monte Carlo…"):
            cdi = cached_cdi(prices.index[0].date(), prices.index[-1].date())
            cdi_factor = data.cdi_factor_on_index(prices.index, cdi, rate_annual)
            if n_days < len(prices):
                hist_res = cached_historical(struct_json, prices, n_days, cost, monitoring, extra_cost, cdi_factor,
                                             rate_annual, regime_adjust and cdi is not None)
            mc_res = cached_mc(struct_json, prices, n_days, cost, mc_method, int(mc_paths), int(mc_block), mc_drift,
                               rate_annual, int(mc_seed), monitoring, extra_cost, mc_premium, mc_custom)
            scen_res = cached_scen(struct_json, prices, n_days, cost, mc_method, int(mc_block), rate_annual,
                                   int(mc_seed), monitoring, extra_cost, mc_premium)
        if exit_cfg is not None:
            with st.spinner("Marcando a estrutura dia a dia (saída antecipada)…"):
                if hist_res is not None:
                    hexit_res = cached_hexit(struct_json, prices, n_days, cost, exit_cfg, cdi_factor,
                                             hist_res.df["retorno"].to_numpy(), monitoring, extra_cost, rate_annual,
                                             bool(hist_res.meta.get("regime_adjust")))
                if mc_res is not None:
                    mcexit_res = cached_mcexit(struct_json, mc_res.meta["paths_exit"], n_days, cost, exit_cfg,
                                               mc_res.df["retorno"].to_numpy(), mc_res.meta["sigma"], rate_annual,
                                               monitoring, extra_cost, mc_res.meta["paths_exit_high"],
                                               mc_res.meta["paths_exit_low"])
    except Exception as exc:  # noqa: BLE001
        run_err = str(exc)


def _not_ready(container) -> bool:
    if prices is None:
        container.info("Carregue os preços da ação (barra lateral) para rodar o backtest.")
        return True
    if not struct_ok:
        container.warning("Corrija a estrutura na aba **Estrutura** para rodar o backtest.")
        return True
    if run_err:
        container.error(f"Erro ao rodar o backtest: {run_err}")
        return True
    return False


def _band(s: dict, key: str, scen=None) -> str:
    """Faixa de incerteza: IC 95% (histórico) ou mínimo–máximo entre os cenários (Monte Carlo)."""
    ci = s.get("ci", {}).get(key)
    if ci:
        return f"IC 95%: {fmt_num(100 * ci[0], 0)}–{fmt_num(100 * ci[1], 0)}%"
    if scen is not None and key in scen and scen[key].notna().any():
        return f"cenários: {fmt_num(100 * scen[key].min(), 0)}–{fmt_num(100 * scen[key].max(), 0)}%"
    return ""


def _kpis(container, s: dict, scen=None) -> None:
    """Indicadores na ordem da revisão: P(lucro) → P(> CDI de hoje) → P(barreira), com faixas."""
    k = container.columns(6)
    k[0].metric("P(lucro > 0)", fmt_pct(s["p_lucro"], 1), help=_band(s, "p_lucro", scen) or None)
    k[1].metric("P(retorno > CDI de hoje)", fmt_pct(s["p_cdi"], 1), help=_band(s, "p_cdi", scen) or None)
    k[2].metric("P(barreira acionada)", fmt_pct(s["p_barreira"], 1) if np.isfinite(s["p_barreira"]) else "—",
                help=_band(s, "p_barreira", scen) or None)
    k[3].metric("P(perda)", fmt_pct(s["p_perda"], 1), help=_band(s, "p_perda", scen) or None)
    k[4].metric("Retorno mediano", fmt_pct(s["mediana"]), help=f"Em R\\$: {md_brl(invested * s['mediana'])}")
    k[5].metric("CVaR 5%", fmt_pct(s["cvar5"]), help="Média dos 5% piores resultados")
    bands = [f"{lbl} {_band(s, key, scen).split(': ', 1)[1]}" for key, lbl in
             (("p_lucro", "P(lucro)"), ("p_cdi", "P(> CDI de hoje)"), ("p_barreira", "P(barreira)"))
             if _band(s, key, scen)]
    if bands:
        container.caption(("IC 95% (block bootstrap; janelas sobrepostas): " if s.get("ci") else
                           "Faixa entre os 9 cenários de premissa: ") + " · ".join(bands))


def _side_by_side() -> pd.DataFrame:
    sums = {}
    if hist_res is not None:
        sums["Janelas históricas"] = summarize(hist_res)
    if mc_res is not None:
        sums[f"Monte Carlo ({MC_METHOD_LABELS[mc_method]})"] = summarize(mc_res)
    return comparison_table(sums)


def _exit_section(kind: str) -> None:
    """Saída antecipada: indicadores, distribuição do dia de saída, tabela e quebra por nível de CDI."""
    st.markdown(f"#### Saída antecipada — gatilho de {fmt_num(exit_cfg['trigger'] * 100, 0)}% do CDI"
                if exit_cfg else "#### Saída antecipada")
    if exit_cfg is None:
        st.caption("Desativada na barra lateral (7. Saída antecipada).")
        return
    res = hexit_res if kind == "hist" else mcexit_res
    base = hist_res if kind == "hist" else mc_res
    if res is None or base is None:
        return
    sm, bs = summarize_exit(res), summarize(base)
    k = st.columns(5)
    k[0].metric("P(saída antecipada)", fmt_pct(sm["p_saida"], 1), help=f"Gatilho atingido em {fmt_pct(sm['p_gatilho'], 1)}")
    k[1].metric("Dia mediano da saída", "—" if np.isnan(sm["dias_mediana"]) else f"{sm['dias_mediana']:.0f} pregões")
    k[2].metric("Retorno médio com saída", fmt_pct(sm["media"]), help=f"No vencimento: {fmt_pct(sm['media_venc'])}")
    k[3].metric("P(> CDI) com saída", fmt_pct(sm["p_cdi"], 1), help=f"No vencimento: {fmt_pct(bs['p_cdi'], 1)}")
    k[4].metric("% do CDI mediano", fmt_pct(sm["pct_cdi_mediana"], 0), help="Do período efetivamente investido")
    sums = {}
    if hexit_res is not None:
        sums["Histórico"] = summarize_exit(hexit_res)
    if mcexit_res is not None:
        sums[f"Monte Carlo ({len(mcexit_res.df)} caminhos)"] = summarize_exit(mcexit_res)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.exit_days_chart({**({"Histórico": hexit_res} if hexit_res is not None else {}),
                                            **({"Monte Carlo": mcexit_res} if mcexit_res is not None else {})}, n_days),
                    key=f"exitdays_{kind}")
    c2.dataframe(exit_table(sums), key=f"exittable_{kind}")
    st.caption(f"Desmontagem {exit_cfg['delay']} pregão(ões) após o gatilho, spread de saída "
               f"{fmt_pct(exit_cfg['exit_spread'])}, marcação com {VOL_MODE_LABELS[exit_cfg['vol_mode']].lower()} "
               f"({fmt_num(exit_cfg['vol_add'] * 100, 1)} pts), "
               + ("calibrada ao preço pago." if exit_cfg["calibrate"] else "sem calibração (modelo puro).")
               + " Retornos comparados ao CDI do período efetivamente investido.")
    if kind == "hist":
        reg = exit_by_cdi_regime(res)
        if not reg.empty:
            shown = reg.copy()
            for c in ("P(saída antecipada)", "P(> CDI) com saída", "Retorno médio com saída", "Retorno médio no vencimento"):
                shown[c] = shown[c].map(lambda v: fmt_pct(v, 1))
            shown["Dia mediano da saída"] = shown["Dia mediano da saída"].map(lambda v: "—" if np.isnan(v) else f"{v:.0f}")
            st.markdown(f"**Por nível de juros no início da janela** (CDI atual: {fmt_pct(rate_annual)} a.a.)")
            st.dataframe(shown, hide_index=True)
            st.caption("Com juros altos, a parte de renda fixa da estrutura vale menos e a régua de % do CDI sobe mais "
                       "rápido: a saída antecipada fica mais rara e mais tardia.")


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(sep=";", decimal=",", index=False, date_format="%d/%m/%Y").encode("utf-8-sig")


with tab_hist:
    if not _not_ready(st):
        if hist_res is None:
            st.warning(f"Histórico insuficiente ({len(prices)} pregões) para janelas de {n_days} pregões.")
        else:
            hs = summarize(hist_res)
            st.markdown(f"**{ticker}** · {fmt_num(hs['n'], 0)} janelas de {n_days} pregões entre "
                        f"{prices.index[0]:%d/%m/%Y} e {prices.index[-1]:%d/%m/%Y} · amostra efetiva "
                        f"(não sobrepostas): **{fmt_num(hs['n_effective'], 0)}** · monitoramento: "
                        f"{MONITORING_LABELS[monitoring].lower()}")
            _kpis(st, hs)
            st.caption(("Caminhos re-ancorados no **CDI de hoje** "
                        f"({fmt_pct(rate_annual)} a.a.), preservando o excesso de retorno da ação sobre o CDI de cada época. "
                        if hist_res.meta.get("regime_adjust") else "Ajuste ao CDI de hoje desligado: CDI da época. ")
                       + f"Amostra efetiva ≈ {hs['n_effective']} janelas independentes. Em testes fora da amostra, a "
                         "probabilidade de direção não foi mais precisa que a frequência histórica: use para comparar "
                         "estruturas e dimensionar o risco de barreira.")
            if hs["barreiras"]:
                st.caption("Barreira acionada em: " + " · ".join(
                    f"{lbl}: **{fmt_pct(v, 1)}** das janelas" for lbl, v in hs["barreiras"].items()))
            st.plotly_chart(charts.windows_timeseries_chart(hist_res))
            cdi_ref = hs["cdi_medio"]
            st.plotly_chart(charts.histogram_chart(
                {"Janelas históricas": hist_res, **({"Monte Carlo": mc_res} if mc_res is not None else {})},
                cdi_ref))
            st.caption("Linha do CDI = CDI médio das janelas históricas.")
            st.markdown("#### Métricas: histórico × Monte Carlo")
            st.dataframe(_side_by_side())
            _exit_section("hist")

            st.markdown("#### Preço da ação e janela em destaque")
            starts = hist_res.df["data_inicio"]
            opts = list(range(len(starts)))
            worst = int(hist_res.df["retorno"].idxmin())
            pick = st.select_slider("Janela (data de início)", options=opts, value=worst,
                                    format_func=lambda i: f"{starts.iloc[i]:%d/%m/%Y}")
            row = hist_res.df.iloc[pick]
            st.caption(f"Janela {row['data_inicio']:%d/%m/%Y} → {row['data_fim']:%d/%m/%Y}: estrutura "
                       f"**{fmt_pct(row['retorno'])}** ({md_brl(invested * row['retorno'])}), ação "
                       f"{fmt_pct(row['retorno_acao'])}, barreira {'acionada' if row['barreira_qualquer'] else 'não acionada'}. "
                       "Padrão: a pior janela.")
            st.plotly_chart(charts.price_chart(prices, ticker, structure, (row["data_inicio"], row["data_fim"])))
            out = hist_res.df.copy()
            out["resultado_rs"] = invested * out["retorno"]
            st.download_button("⬇️ Baixar janelas (CSV)", _csv(out), file_name=f"janelas_{ticker}.csv",
                               mime="text/csv")

with tab_mc:
    if not _not_ready(st) and mc_res is not None:
        ms = summarize(mc_res)
        desc = (f"bootstrap em blocos de {mc_block} dias dos log-retornos diários" if mc_method == "bootstrap"
                else f"GBM com σ histórica de {fmt_pct(mc_res.meta['sigma'])} a.a. e drift "
                     f"{DRIFT_LABELS[mc_drift].lower()}")
        st.markdown(f"**{fmt_num(ms['n'], 0)} caminhos** de {n_days} pregões · {desc} · seed {mc_seed}"
                    + (" · barreira com correção BGK (intradiário)" if monitoring == "intraday" else ""))
        _kpis(st, ms, scen_res)
        if scen_res is not None:
            st.markdown("#### Sensibilidade às premissas (retorno esperado × vol)")
            lbl = {"zero": "Zero", "cdi": f"CDI ({fmt_pct(rate_annual, 1)})", "cdi_premio": f"CDI + {fmt_num(100 * mc_premium, 0)} p.p."}
            cols3 = st.columns(3)
            for col, (key, title) in zip(cols3, (("p_lucro", "P(lucro > 0)"), ("p_cdi", "P(> CDI de hoje)"),
                                                 ("p_barreira", "P(barreira acionada)"))):
                tab = scen_res.pivot(index="drift", columns="sigma", values=key).reindex(list(SCENARIO_DRIFTS))
                tab.index = [lbl[d] for d in tab.index]
                tab.columns = [f"vol {fmt_pct(c, 0)}" for c in tab.columns]
                col.markdown(f"**{title}**")
                col.dataframe(tab.map(lambda v: fmt_pct(v, 1) if np.isfinite(v) else "—"), key=f"scen_{key}")
            st.caption("Cenário central: retorno esperado = CDI e vol de base (histórica do período). 5.000 caminhos "
                       "por cenário, com os mesmos números aleatórios.")
        if ms["barreiras"]:
            st.caption("Barreira acionada em: " + " · ".join(
                f"{lbl}: **{fmt_pct(v, 1)}** dos caminhos" for lbl, v in ms["barreiras"].items()))
        c_left, c_right = st.columns(2)
        c_left.plotly_chart(charts.histogram_chart({"Monte Carlo": mc_res}, (1 + rate_annual) ** (n_days / 252) - 1))
        c_right.plotly_chart(charts.mc_paths_chart(mc_res, structure))
        st.caption(f"CDI do período no MC: taxa de {fmt_pct(rate_annual)} a.a. composta por {n_days} pregões.")
        st.markdown("#### Métricas: histórico × Monte Carlo")
        st.dataframe(_side_by_side())
        _exit_section("mc")
        out = mc_res.df.copy()
        out["resultado_rs"] = invested * out["retorno"]
        st.download_button("⬇️ Baixar caminhos simulados (CSV)", _csv(out), file_name=f"monte_carlo_{ticker}.csv",
                           mime="text/csv")

with tab_ex:
    st.markdown("Aplica a estrutura no caminho **realizado** de uma operação real (datas de contratação e "
                "vencimento).")
    if "expost_trade" not in st.session_state:
        st.session_state.expost_trade = st.session_state.get("trade_date", date(2025, 11, 19))
        st.session_state.expost_expiry = st.session_state.get("expiry_date", date(2026, 11, 25))
    e1, e2 = st.columns(2)
    ex_trade = e1.date_input("Data de contratação", key="expost_trade", format="DD/MM/YYYY")
    ex_expiry = e2.date_input("Data de vencimento", key="expost_expiry", format="DD/MM/YYYY")
    if prices is None:
        st.info("Carregue os preços da ação para usar o modo ex-post.")
    elif not struct_ok:
        st.warning("Corrija a estrutura na aba **Estrutura**.")
    else:
        try:
            ex = run_ex_post(structure, prices, ex_trade, ex_expiry, cost, monitoring, extra_cost)
        except ValueError as exc:
            st.warning(str(exc))
            ex = None
        if ex is not None:
            if ex.finished:
                st.success(f"Operação encerrada: apuração em {ex.obs_date:%d/%m/%Y} (D−1 do vencimento "
                           f"{ex.expiry_date:%d/%m/%Y}).")
            else:
                st.warning(f"Vencimento ainda não chegou (apuração prevista em {ex.obs_date:%d/%m/%Y}). Situação "
                           f"**até {ex.last_date:%d/%m/%Y}**: marcação **intrínseca** — o payoff como se a apuração "
                           "fosse hoje, com o status das barreiras até agora. **Não** é o valor de mercado da "
                           "estrutura (que inclui o valor temporal das opções).")
            k = st.columns(4)
            k[0].metric("Retorno da estrutura", fmt_pct(ex.retorno), help="Bruto de IR.")
            k[1].metric("Resultado (R$)", fmt_brl(invested * ex.retorno))
            k[2].metric("Retorno só da ação", fmt_pct(ex.retorno_acao))
            k[3].metric("Pregões decorridos", f"{ex.n_days_elapsed}")
            if ex.hits:
                for lbl, (hit, when) in ex.hits.items():
                    if hit:
                        st.markdown(f"🔶 Barreira **{lbl}** tocada em **{when:%d/%m/%Y}**.")
                    else:
                        st.markdown(f"🔷 Barreira **{lbl}** não tocada"
                                    + (" até agora." if not ex.finished else " durante a operação."))
            st.caption(f"Valor inicial: fechamento de {ex.trade_date:%d/%m/%Y} = {md_brl(ex.s0_price)} "
                       f"({'ajustado por proventos' if price_kind.startswith('Ajustado') else 'bruto'}). "
                       "Com preço ajustado, valores em R\\$ podem diferir dos da lâmina, mas as variações "
                       "percentuais são comparáveis.")
            st.plotly_chart(charts.ex_post_chart(ex, structure, ticker))
            if exit_cfg is not None:
                st.markdown(f"#### Saída antecipada — gatilho de {fmt_num(exit_cfg['trigger'] * 100, 0)}% do CDI")
                cf_ex = cdi_factor if cdi_factor is not None else data.cdi_factor_on_index(
                    prices.index, cached_cdi(prices.index[0].date(), prices.index[-1].date()), rate_annual)
                n_total, _obs = data.term_from_dates(ex.trade_date, ex.expiry_date, prices.index)
                xx = run_ex_post_exit(structure, prices, ex.trade_date, n_total, cost, EarlyExitConfig(**exit_cfg),
                                      cf_ex, monitoring, extra_cost)
                if xx is not None:
                    live = np.flatnonzero(np.isfinite(xx.ret))
                    if xx.exit_date is not None:
                        st.success(f"Gatilho atingido em {xx.trigger_date:%d/%m/%Y}; com o OK do investidor, desmontagem "
                                   f"em {xx.exit_date:%d/%m/%Y} com retorno de **{fmt_pct(xx.exit_return)}** "
                                   f"({md_brl(invested * xx.exit_return)}).")
                    elif xx.trigger_date is not None:
                        st.info(f"Gatilho atingido em {xx.trigger_date:%d/%m/%Y}; desmontagem ainda não concluída.")
                    elif len(live):
                        j = live[-1]
                        st.warning(f"Gatilho ainda não atingido. Em {xx.dates[j]:%d/%m/%Y}: retorno de saída estimado de "
                                   f"**{fmt_pct(xx.ret[j])}** contra gatilho de **{fmt_pct(xx.threshold[j])}**.")
                    st.plotly_chart(charts.ex_post_exit_chart(xx, exit_cfg["trigger"]))
                    st.caption("Marcação a modelo (Black-Scholes e fórmulas de barreira): estimativa do valor de "
                               "desmontagem; o preço efetivo é o da mesa.")

with tab_method:
    st.markdown(METODOLOGIA)
