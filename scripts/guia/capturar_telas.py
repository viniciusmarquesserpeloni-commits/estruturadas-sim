"""Captura as telas do site para o guia em PDF (Chrome headless via DevTools Protocol).

Pré-requisitos: site servido em http://localhost:8770 (python -m http.server 8770 --directory site), com os
dados de BBDC4 em site/data, e o Google Chrome instalado. Uso:

    .venv/Scripts/python scripts/guia/capturar_telas.py

As imagens vão para docs/guia/img/ (PNG, escala 2×).
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "guia" / "img"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
BASE = "http://localhost:8770/"
WIDTH, HEIGHT, SCALE = 1240, 900, 2


class Tab:
    def __init__(self, ws_url: str) -> None:
        self.ws = connect(ws_url, max_size=None, open_timeout=30)
        self.i = 0

    def cmd(self, method: str, **params):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv(timeout=180))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr: str):
        r = self.cmd("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS: {r['exceptionDetails'].get('exception', {}).get('description', r['exceptionDetails'])}")
        return r["result"].get("value")

    def wait(self, cond: str, timeout: float = 120.0, settle: float = 1.2) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.js(f"(() => {{ try {{ return !!({cond}); }} catch (e) {{ return false; }} }})()"):
                time.sleep(settle)
                return
            time.sleep(0.3)
        raise TimeoutError(cond)

    def go(self, route: str) -> None:
        self.js(f"location.hash = '{route}'")
        time.sleep(0.6)

    def rect(self, js_elems: str, pad: int = 10, extra_bottom: int = 0) -> dict:
        """Retângulo (coordenadas da página) que cobre os elementos devolvidos pela expressão JS."""
        r = self.js(f"""(() => {{
            const els = ({js_elems}).filter(Boolean);
            if (!els.length) return null;
            let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
            for (const e of els) {{ const b = e.getBoundingClientRect();
              x0 = Math.min(x0, b.left); y0 = Math.min(y0, b.top); x1 = Math.max(x1, b.right); y1 = Math.max(y1, b.bottom); }}
            return {{ x: x0 + scrollX, y: y0 + scrollY, w: x1 - x0, h: y1 - y0 }};
        }})()""")
        if not r:
            raise RuntimeError(f"elemento não encontrado: {js_elems}")
        return {"x": max(0, r["x"] - pad), "y": max(0, r["y"] - pad), "width": r["w"] + 2 * pad,
                "height": r["h"] + 2 * pad + extra_bottom, "scale": 1}

    def shot(self, name: str, js_elems: str, pad: int = 10, extra_bottom: int = 0) -> None:
        clip = self.rect(js_elems, pad, extra_bottom)
        self.js(f"window.scrollTo(0, {max(0, clip['y'] - 40)})")
        time.sleep(0.4)
        clip = self.rect(js_elems, pad, extra_bottom)
        data = self.cmd("Page.captureScreenshot", format="png", clip=clip, captureBeyondViewport=True)["data"]
        (OUT / f"{name}.png").write_bytes(base64.b64decode(data))
        print(f"  {name}.png  {clip['width']:.0f}×{clip['height']:.0f}")


# Números citados no guia, calculados pelo próprio motor do site no momento da captura e gravados em
# docs/guia/numeros.json (montar_guia.py troca {{N:chave}} no template por esses valores, já formatados em pt-BR).
NUM_HELPERS = r"""
window.__N = window.__N || {};
window.__H = (() => {
  const F = App.fmt, E = App.E;
  const p0 = (v) => F.pct(v, 0, false), p1 = (v) => F.pct(v, 1, false), p2 = (v) => F.pct(v, 2, false), s2 = (v) => F.pct(v, 2);
  const ci = (sm, k) => `${F.num(sm.ci[k][0] * 100, 0)}%–${F.num(sm.ci[k][1] * 100, 0)}%`;
  const rng = (rows, k) => { const v = rows.map((r) => r[k]).filter((x) => isFinite(x)); return `${F.num(Math.min(...v) * 100, 0)}%–${F.num(Math.max(...v) * 100, 0)}%`; };
  const hist = (pre) => {
    const c = App.ctx, sm = E.summarize(c.hist), o = {};
    o[pre + "n"] = F.int(sm.n); o[pre + "neff"] = F.int(sm.nEff); o[pre + "nefic"] = F.int(sm.n_ef_ic);
    for (const k of ["p_lucro", "p_cdi", "p_barreira", "p_perda", "p_cdi_epoca"]) if (isFinite(sm[k])) { o[pre + k] = p1(sm[k]); if (sm.ci && sm.ci[k]) o[pre + k + "_ic"] = ci(sm, k); }
    o[pre + "mediana"] = s2(sm.mediana); o[pre + "media"] = s2(sm.media); o[pre + "excesso"] = F.num(sm.excesso_cdi * 100, 2) + " p.p.";
    o[pre + "cdi_prazo"] = p2(sm.cdi_hoje); o[pre + "cvar5"] = s2(sm.cvar5);
    return o;
  };
  const mc = (pre) => {
    const c = App.ctx, sm = E.summarize(c.mc), o = {};
    o[pre + "n"] = F.int(sm.n);
    for (const k of ["p_lucro", "p_cdi", "p_barreira"]) if (isFinite(sm[k])) {
      o[pre + k] = p1(sm[k]);
      if (c.mc.partsSummary) o[pre + k + "_met"] = rng(c.mc.partsSummary, k);
      if (c.scen) o[pre + k + "_cen"] = rng(c.scen, k);
    }
    o[pre + "mediana"] = s2(sm.mediana); o[pre + "excesso"] = F.num(sm.excesso_cdi * 100, 2) + " p.p.";
    return o;
  };
  return { F, E, p0, p1, p2, s2, ci, rng, hist, mc };
})();
"""


def collect(t: "Tab", expr: str) -> None:
    """Avalia uma expressão JS (objeto chave → texto) e junta em window.__N."""
    t.js(NUM_HELPERS)
    t.js(f"Object.assign(window.__N, (() => {{ const H = window.__H, F = H.F, E = H.E, c = App.ctx; return ({expr}); }})())")


Q = "document.querySelector"
QA = "[...document.querySelectorAll"
READY = ("App.ctx && !App.ctx.loading && App.ctx.hist && App.ctx.mc && App.ctx.scen"
         " && (!App.state.adv.exitOn || (App.ctx.hexit && App.ctx.mcexit))")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlopen(BASE + "data/index.json", timeout=5)
    except Exception:  # noqa: BLE001
        sys.exit(f"Site fora do ar em {BASE}: rode python -m http.server 8770 --directory site")
    profile = tempfile.mkdtemp(prefix="guia-chrome-")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                             "--hide-scrollbars", "--no-first-run", "--disable-gpu", "--lang=pt-BR", "about:blank"])
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.3)
        t = Tab(page["webSocketDebuggerUrl"])
        t.cmd("Page.enable")
        t.cmd("Emulation.setDeviceMetricsOverride", width=WIDTH, height=HEIGHT, deviceScaleFactor=SCALE, mobile=False)
        t.cmd("Page.navigate", url=BASE + "#/estrutura")
        t.wait("window.App && App.ctx")
        t.js("localStorage.clear()")
        t.cmd("Page.navigate", url=BASE + "#/estrutura")
        t.wait(READY, settle=2.0)
        collect(t, """{
          dados_ate: F.date(App.data.index.dados_ate), cdi: H.p2(c.rateAnnual), pregoes: F.int(c.P.c.length),
          inicio: F.date(c.P.d[0]), prazo: F.int(c.n),
          vol_prazo: H.p1(c.volPrazo.sigma), vol_prazo_garch: H.p1(c.volPrazo.garch), vol_252: H.p1(c.volPrazo.realizada252),
          theo_net: F.pct(c.theo.net, 2), theo_put: H.p2(c.theo.legs.find((l) => l.leg.kind === 'put').unit),
          theo_call: H.p2(c.theo.legs.find((l) => l.leg.kind === 'call').unit),
        }""")
        print("Estrutura")
        # 1. Tela inicial: barra superior, abas e barra de parâmetros
        t.shot("01_tela_inicial", f"[{Q}('.topbar'), {Q}('#params'), {Q}('.page-head')]", pad=0)
        # 2. Autocompletar da ação
        t.js(f"(() => {{ const i = {Q}('#p-ticker'); i.focus(); i.value = 'BB'; i.dispatchEvent(new Event('input')); }})()")
        time.sleep(0.6)
        t.shot("02_acao", f"[{Q}('#params .pbar'), {Q}('#p-ac-list')]", pad=8)
        t.js(f"{Q}('#p-ticker').blur(); {Q}('#p-ac-list').classList.add('hidden'); {Q}('#p-ticker').value = App.state.ticker")
        time.sleep(0.5)
        # 3. Prazo, valor e custo
        t.shot("03_prazo", f"[{Q}('[data-term]').closest('.pfield')]", pad=8)
        t.shot("04_valor_custo", f"[{Q}('#p-invested').closest('.pfield'), {Q}('#p-cost').closest('.pfield')]", pad=8)
        # 4. Página Estrutura
        t.shot("05_composicao", f"[{Q}('#s-editor').closest('.card'), {Q}('#s-kpis')]", pad=6)
        t.shot("06_payoff_resumo", f"[{Q}('#s-payoff').closest('.grid')]", pad=6)
        t.shot("07_quadro_teorico", f"[{Q}('#s-quadro').closest('.grid')]", pad=6)
        t.js(f"{Q}('#sv-run').click()")
        t.wait(f"{Q}('#sv-out') && {Q}('#sv-out').textContent.includes('custo')", timeout=120)
        t.shot("08_solver", f"[{Q}('#s-solver').closest('.card')]", pad=6)
        collect(t, "{ solver: document.querySelector('#sv-out b').textContent.split('=')[1].trim() }")
        t.shot("09_exportar", f"[{Q}('.page-head')]", pad=6)
        # 5. Mais opções
        t.js(f"{Q}('#p-adv').click()")
        time.sleep(0.8)
        t.shot("10_mais_opcoes", f"[{Q}('#params .adv')]", pad=8)
        t.js(f"{Q}('#p-adv').click()")
        time.sleep(0.5)

        print("Backtest histórico")
        t.go("#/backtest")
        t.wait(READY + f" && {Q}('#b-ts canvas')", settle=2.0)
        t.shot("11_backtest_kpis", f"[{Q}('#view .page-head'), {Q}('#view .kpi-strip').closest('.card')]", pad=6)
        t.shot("12_backtest_janelas", f"[{Q}('#b-ts').closest('.card')]", pad=6)
        t.shot("13_backtest_distribuicao", f"[{Q}('#b-hist').closest('.grid')]", pad=6)
        t.shot("14_backtest_preco", f"[{Q}('#b-price').closest('.card')]", pad=6)
        collect(t, """Object.assign(H.hist('h_'), (() => {
          const hx = E.summarizeExit(c.hexit), mx = E.summarizeExit(c.mcexit);
          return { hx_p_saida: H.p1(hx.p_saida), hx_dias: F.int(hx.dias_mediana), hx_pctcdi: H.p0(hx.pct_cdi_mediana),
                   mx_p_saida: H.p1(mx.p_saida), mx_dias: F.int(mx.dias_mediana) };
        })())""")

        print("Monte Carlo")
        t.go("#/monte-carlo")
        t.wait(READY + f" && {Q}('#m-vol canvas')", settle=2.0)
        t.shot("15_mc_kpis", f"[{Q}('#view .page-head'), {Q}('#view p.small'), {Q}('#view .kpi-strip').closest('.card')]", pad=6)
        t.shot("16_mc_vol", f"[{QA}('#view .section-title')].find(e => e.textContent.startsWith('Volatilidade')), "
                            f"{Q}('#m-vol').closest('.card')]", pad=6)
        t.shot("17_mc_cenarios", f"[{QA}('#view h3')].find(e => e.textContent.startsWith('Sensibilidade')).closest('.card')]", pad=6)
        t.shot("18_mc_distribuicao", f"[{Q}('#m-hist').closest('.grid')]", pad=6)
        collect(t, """Object.assign(H.mc('m_'), (() => {
          const vp = E.volPanel(c.mc.garch, E.ohlcLogReturns(c.P).lr, c.mc.N), sc = (d, v = 1) => c.scen.find((r) => r.drift === d && r.volScale === v);
          return { vol_hoje: H.p1(vp.vol_hoje), vol_lp: H.p1(vp.vol_longo_prazo), vol_real63: H.p1(vp.vol_realizada),
                   meia_vida: F.int(vp.meia_vida), persist: F.num(vp.persistencia, 3), alpha: F.num(vp.alpha, 3),
                   gamma: F.num(vp.gamma, 3), beta: F.num(vp.beta, 3),
                   s_zero: H.p0(sc('zero').p_lucro), s_cdi: H.p0(sc('cdi').p_lucro), s_premio: H.p0(sc('cdi_premio').p_lucro),
                   s_bar_lo: H.p0(sc('cdi', 0.6).p_barreira), s_bar_hi: H.p0(sc('cdi', 1.3).p_barreira) };
        })())""")
        t.js(f"{Q}('#m-calib').click()")
        t.wait("App.calib && App.calib.res && document.querySelector('#m-rel canvas')", timeout=300, settle=2.0)
        t.shot("19_calibracao", f"[{Q}('#m-calib-card').previousElementSibling, {Q}('#m-calib-card')]", pad=6)
        collect(t, """(() => {
          const res = App.calib.res, o = { cal_n: F.int(res.rows.length), cal_ini: res.rows[0].data.slice(0, 4), cal_fim: res.rows[res.rows.length - 1].data.slice(0, 4) };
          for (const b of E.calibBrier(res)) { o['cal_' + b.chave] = F.pct(b.ganho, 1); o['cal_' + b.chave + '_t'] = F.num(b.t, 1);
            o['cal_' + b.chave + '_v'] = Math.abs(b.t) >= 2 ? 'significativo' : 'não distinguível de ruído'; }
          return o;
        })()""")
        t.shot("20_saida_antecipada", f"[{QA}('#view .section-title')].find(e => e.textContent.startsWith('Saída')), "
                                      f"{Q}('#mc-exitdays').closest('.grid')]", pad=6)

        # Estruturas para a página Comparar (3 meses), cada uma com o seu custo teórico (vol prevista e CDI de
        # hoje): o Collar Knock In do exemplo 1, uma versão com call e barreira mais altas e um Collar sem barreira
        t.js("""(() => {
          const c = App.ctx, a = App.state.adv, E = App.E;
          const theo = (s) => E.priceStructure(s, c.sigma, c.r, a.q, c.n, a.pricingPaths, a.pricingSeed, a.monitoring).net;
          const items = [[App.state.structure, 'Collar KI 100/106/112'], [E.PRESETS.collar_ki.build(1.0, 1.08, 1.18), 'Collar KI 100/108/118'],
                         [E.PRESETS.collar.build(1.0, 1.10), 'Collar 100/110']];
          window.__N.cmp_custos = items.map(([s, name]) => { const k = theo(s); App.addToCompare(s, k, name); return name + ': ' + App.fmt.pct(k, 2); }).join(' · ');
        })()""")

        print("Exemplo 2: Proteção Total BBDC4 (lâmina)")
        t.js("App.setStructure(App.E.PRESETS.protecao_total.build(), 'protecao_total')")
        t.go("#/estrutura")
        t.wait(READY, settle=2.0)
        t.shot("21_pt_estrutura", f"[{Q}('#view .page-head'), {Q}('#s-editor').closest('.card'), {Q}('#s-kpis')]", pad=6)
        t.shot("22_pt_payoff", f"[{Q}('#s-payoff').closest('.grid')]", pad=6)
        t.go("#/backtest")
        t.wait(READY + f" && {Q}('#b-ts canvas')", settle=2.0)
        t.shot("23_pt_backtest", f"[{Q}('#view .kpi-strip').closest('.card')]", pad=6)
        collect(t, "Object.assign(H.hist('pt_'), { pt_prazo: F.int(c.n) })")
        t.go("#/ex-post")
        t.wait(f"{Q}('#x-chart canvas')", settle=2.5)
        collect(t, """(() => {
          const st = App.state, ex = E.runExPost(st.structure, c.P, st.expost.trade, st.expost.expiry, c.cost, st.adv.monitoring, c.extra);
          const hit = ex.hits.find((h) => h.hit), note = document.querySelector('#x-exit .warn-note, #x-exit .disclaimer');
          return { xp_ate: F.date(ex.lastDate), xp_n: F.int(ex.nElapsed), xp_ret: F.pct(ex.ret, 2), xp_acao: F.pct(ex.stockRet, 2),
                   xp_rs: F.brl(st.invested * ex.ret), xp_bar: hit ? `barreira tocada em ${F.date(hit.date)}` : 'barreira não tocada',
                   xp_fim: ex.finished ? 'Resultado final' : 'Marcação intrínseca', xp_saida: note ? note.textContent.trim() : '' };
        })()""")
        t.shot("24_expost", f"[{Q}('#view .page-head'), {Q}('#x-trade').closest('.card'), {Q}('#x-body .kpi-strip')]", pad=6)
        t.shot("25_expost_grafico", f"[{Q}('#x-chart').closest('.card')]", pad=6)
        if t.js(f"!!{Q}('#x-exit-chart canvas')"):
            t.shot("26_expost_saida", f"[{Q}('#x-exit')]", pad=6)
        print("Comparar")
        t.js("App.update({ term: Object.assign({}, App.state.term, { mode: 'meses', months: 3 }) }); App.emit('params')")
        t.go("#/comparar")
        t.wait(f"{Q}('#c-payoff canvas') && !document.querySelector('#view').textContent.includes('calculando')", timeout=300, settle=2.0)
        t.shot("28_comparar", f"[{Q}('#view .page-head'), {QA}('#view h3')].find(e => e.textContent.startsWith('Indicadores')).closest('.card')]", pad=6)
        t.shot("29_comparar_payoff", f"[{Q}('#c-payoff').closest('.card')]", pad=6)
        t.go("#/metodologia")
        time.sleep(1.5)
        t.shot("27_metodologia", f"[{Q}('#view h2'), {QA}('#view h3')][0]]", pad=6, extra_bottom=420)
        nums = t.js("window.__N")
        (OUT.parent / "numeros.json").write_text(json.dumps(nums, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  numeros.json  {len(nums)} valores")
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
