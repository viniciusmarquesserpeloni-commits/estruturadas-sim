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

        print("Monte Carlo")
        t.go("#/monte-carlo")
        t.wait(READY + f" && {Q}('#m-vol canvas')", settle=2.0)
        t.shot("15_mc_kpis", f"[{Q}('#view .page-head'), {Q}('#view p.small'), {Q}('#view .kpi-strip').closest('.card')]", pad=6)
        t.shot("16_mc_vol", f"[{QA}('#view .section-title')].find(e => e.textContent.startsWith('Volatilidade')), "
                            f"{Q}('#m-vol').closest('.card')]", pad=6)
        t.shot("17_mc_cenarios", f"[{QA}('#view h3')].find(e => e.textContent.startsWith('Sensibilidade')).closest('.card')]", pad=6)
        t.shot("18_mc_distribuicao", f"[{Q}('#m-hist').closest('.grid')]", pad=6)
        t.js(f"{Q}('#m-calib').click()")
        t.wait("App.calib && App.calib.res && document.querySelector('#m-rel canvas')", timeout=300, settle=2.0)
        t.shot("19_calibracao", f"[{Q}('#m-calib-card').previousElementSibling, {Q}('#m-calib-card')]", pad=6)
        t.shot("20_saida_antecipada", f"[{QA}('#view .section-title')].find(e => e.textContent.startsWith('Saída')), "
                                      f"{Q}('#mc-exitdays').closest('.grid')]", pad=6)

        print("Exemplo 2: Proteção Total BBDC4 (lâmina)")
        t.js("App.setStructure(App.E.PRESETS.protecao_total.build(), 'protecao_total')")
        t.go("#/estrutura")
        t.wait(READY, settle=2.0)
        t.shot("21_pt_estrutura", f"[{Q}('#view .page-head'), {Q}('#s-editor').closest('.card'), {Q}('#s-kpis')]", pad=6)
        t.shot("22_pt_payoff", f"[{Q}('#s-payoff').closest('.grid')]", pad=6)
        t.go("#/backtest")
        t.wait(READY + f" && {Q}('#b-ts canvas')", settle=2.0)
        t.shot("23_pt_backtest", f"[{Q}('#view .kpi-strip').closest('.card')]", pad=6)
        t.go("#/ex-post")
        t.wait(f"{Q}('#x-chart canvas')", settle=2.5)
        t.shot("24_expost", f"[{Q}('#view .page-head'), {Q}('#x-trade').closest('.card'), {Q}('#x-body .kpi-strip')]", pad=6)
        t.shot("25_expost_grafico", f"[{Q}('#x-chart').closest('.card')]", pad=6)
        if t.js(f"!!{Q}('#x-exit-chart canvas')"):
            t.shot("26_expost_saida", f"[{Q}('#x-exit')]", pad=6)
        t.go("#/metodologia")
        time.sleep(1.5)
        t.shot("27_metodologia", f"[{Q}('#view h2'), {QA}('#view h3')][0]]", pad=6, extra_bottom=420)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
