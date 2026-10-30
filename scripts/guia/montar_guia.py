"""Monta o guia em PDF (docs/guia/Guia_Simulador_Estruturadas.pdf) a partir de guia_template.html.

1. Gera os gráficos de payoff de cada preset (SVG) com o próprio motor Python e os prêmios ilustrativos.
2. Grava docs/guia/guia.html e imprime em PDF pelo Chrome headless (DevTools Protocol), duas vezes: a primeira
   descobre a página de cada seção (pypdf) e a segunda preenche o sumário.

Pré-requisitos: as telas em docs/guia/img (scripts/guia/capturar_telas.py), Google Chrome e pypdf. Uso:

    .venv/Scripts/python scripts/guia/montar_guia.py
"""
from __future__ import annotations

import base64
import json
import math
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from estruturadas import presets  # noqa: E402
from estruturadas.legs import expiry_payoff  # noqa: E402
from estruturadas.pricing import bs_price  # noqa: E402

from capturar_telas import CHROME, Tab  # noqa: E402

TEMPLATE = Path(__file__).with_name("guia_template.html")
OUT_DIR = ROOT / "docs" / "guia"
HTML = OUT_DIR / "guia.html"
PDF = OUT_DIR / "Guia_Simulador_Estruturadas.pdf"
PORT = 9334

BLUE, ORANGE, GRAY, GRID, MUTED, INK = "#2a78d6", "#eb6834", "#7d8f95", "#e9ece7", "#7d8f95", "#0e2a33"
SIGMA, CDI, T = 0.35, 0.1365, 63 / 252  # prêmio ilustrativo das estruturas só com opções


def fmt_pct(v: float, d: int = 2) -> str:
    return f"{v * 100:.{d}f}%".replace(".", ",")


def premium(key: str) -> float:
    r = math.log1p(CDI)
    c = lambda k: float(bs_price("call", 1.0, k, T, r, 0.0, SIGMA))  # noqa: E731
    p = lambda k: float(bs_price("put", 1.0, k, T, r, 0.0, SIGMA))  # noqa: E731
    return {"trava_alta": c(1.0) - c(1.2), "trava_baixa": p(1.0) - p(0.8), "straddle": c(1.0) + p(1.0),
            "strangle": p(0.95) + c(1.05)}.get(key, 0.0)


def payoff_svg(key: str, lo: float = 0.6, hi: float = 1.6, W: int = 340, H: int = 228) -> str:
    """Resultado no vencimento (% do valor inicial da ação) × variação da ação, nos dois ramos da barreira."""
    s = presets.PRESETS[key].builder()
    prem = premium(key)
    L, R, Tp, B = 42, 10, 12, 30
    ymin, ymax = -0.45, 0.65
    px = lambda x: L + (x - lo) / (hi - lo) * (W - L - R)  # noqa: E731
    py = lambda y: Tp + (ymax - y) / (ymax - ymin) * (H - Tp - B)  # noqa: E731
    levels = [1.0] + list(s.strikes) + [e[1] for e in s.events]
    inner = [lv for lv in levels if lo < lv < hi]
    xs = np.unique(np.concatenate([np.linspace(lo, hi, 801), inner, [lv - 1e-6 for lv in inner]]))
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Inter, Segoe UI, sans-serif">']
    for y in (-0.4, -0.2, 0.0, 0.2, 0.4, 0.6):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{py(y):.1f}" y2="{py(y):.1f}" stroke="{GRID if y else "#c7cfc8"}" stroke-width="1"/>')
        out.append(f'<text x="{L - 4}" y="{py(y) + 3:.1f}" text-anchor="end" font-size="11" fill="{MUTED}">{"+" if y > 0 else ""}{y * 100:.0f}%</text>')
    for x in (0.6, 0.8, 1.0, 1.2, 1.4, 1.6):
        out.append(f'<text x="{px(x):.1f}" y="{H - 13}" text-anchor="middle" font-size="11" fill="{MUTED}">{"+" if x > 1 else ""}{(x - 1) * 100:.0f}%</text>')
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 1}" text-anchor="middle" font-size="9.5" fill="{MUTED}">variação da ação até o vencimento</text>')
    for k in s.strikes:
        if lo < k < hi:
            out.append(f'<line x1="{px(k):.1f}" x2="{px(k):.1f}" y1="{Tp}" y2="{H - B}" stroke="{GRAY}" stroke-dasharray="1.5 3" stroke-width="1"/>')
    for _, level in s.events:
        if lo < level < hi:
            out.append(f'<line x1="{px(level):.1f}" x2="{px(level):.1f}" y1="{Tp}" y2="{H - B}" stroke="{ORANGE}" stroke-dasharray="5 4" stroke-width="1.3"/>')
            out.append(f'<text x="{px(level) + 3:.1f}" y="{Tp + 10}" font-size="10.5" fill="{ORANGE}">B {fmt_pct(level, 1)}</text>')

    def path(y, color, width=2.2, dash=None):
        segs, cur = [], []
        for x, v in zip(xs, y):
            if np.isfinite(v):
                cur.append(f"{px(x):.1f},{py(min(max(v, ymin), ymax)):.1f}")
            elif cur:
                segs.append(cur)
                cur = []
        if cur:
            segs.append(cur)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return "".join(f'<polyline points="{" ".join(sg)}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"{d}/>' for sg in segs)

    out.append(path(xs - 1.0, GRAY, 1.5, "5 4"))
    base = 1.0 if s.has_stock else 0.0
    if s.events:
        out.append(path(expiry_payoff(s, xs, "all") - base - prem, ORANGE, 2.7))
    out.append(path(expiry_payoff(s, xs, "none") - base - prem, BLUE, 2.9))
    out.append("</svg>")
    return "".join(out)


def fill(template: str, pages: dict[str, int] | None) -> str:
    html = template
    for key in presets.PRESETS:
        html = html.replace(f"{{{{SVG:{key}}}}}", payoff_svg(key))
        html = html.replace(f"{{{{PREMIO:{key}}}}}", fmt_pct(premium(key)) + " do valor da ação")
    return re.sub(r"\{\{P:(\w+)\}\}", lambda m: str(pages.get(m.group(1), "")) if pages else "", html)


# Trecho do início de cada seção (texto do corpo, não do sumário) para achar a página no PDF
MARKERS = {"s0": "Esteguiafoiescritoparaquem", "s1": "Umaoperaçãoestruturadacombina", "s2": "Elassópreenchematabeladepernas",
           "s3": "Osimuladoraplicaaestruturaamilhares", "s4": "Cadanúmerodosimuladorvemdeummétodo",
           "s5": "Osimuladorrodanonavegador", "s6": "UmclientecomR$30.000", "s6a": "UmclientecomR$30.000",
           "s6b": "Operaçãorealcontratadaem19/11/2025", "s7": "ComeceporP(lucro),masnãopare",
           "s8": "Janelassobrepostassãomuitocorrelacionadas"}


def section_pages(pdf: Path) -> dict[str, int]:
    from pypdf import PdfReader
    texts = [re.sub(r"\s+", "", p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    found = {}
    for key, marker in MARKERS.items():
        for i, txt in enumerate(texts):
            if marker in txt:
                found[key] = i + 1
                break
    return found


FOOTER = ('<div style="width:100%;font-family:Segoe UI,Arial,sans-serif;font-size:7.5px;color:#7d8f95;padding:0 16mm;'
          'display:flex;justify-content:space-between;"><span>Simulador de Operações Estruturadas · Guia completo · '
          'outubro de 2026</span><span>página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>')


def print_pdf(t: Tab, html: Path, pdf: Path) -> None:
    t.cmd("Page.navigate", url=html.resolve().as_uri())
    t.wait("document.readyState === 'complete' && document.fonts.status === 'loaded' && "
           "[...document.images].every((i) => i.complete && i.naturalWidth > 0)", timeout=60, settle=1.0)
    params = dict(printBackground=True, preferCSSPageSize=True, displayHeaderFooter=True,
                  headerTemplate="<div></div>", footerTemplate=FOOTER, generateDocumentOutline=True)
    try:
        data = t.cmd("Page.printToPDF", **params)["data"]
    except RuntimeError:
        params.pop("generateDocumentOutline")
        data = t.cmd("Page.printToPDF", **params)["data"]
    pdf.write_bytes(base64.b64decode(data))


def main() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    missing = sorted(set(re.findall(r'src="img/([\w.]+)"', template)) - {p.name for p in (OUT_DIR / "img").glob("*.png")})
    if missing:
        sys.exit(f"Faltam telas em docs/guia/img: {missing} (rode capturar_telas.py)")
    profile = tempfile.mkdtemp(prefix="guia-pdf-")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                             "--no-first-run", "--disable-gpu", "--allow-file-access-from-files", "about:blank"])
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2))
                page = next(x for x in tabs if x["type"] == "page")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.3)
        t = Tab(page["webSocketDebuggerUrl"])
        t.cmd("Page.enable")
        HTML.write_text(fill(template, None), encoding="utf-8")
        print_pdf(t, HTML, PDF)
        pages = section_pages(PDF)
        print("páginas das seções:", pages)
        HTML.write_text(fill(template, pages), encoding="utf-8")
        print_pdf(t, HTML, PDF)
        from pypdf import PdfReader
        n = len(PdfReader(str(PDF)).pages)
        print(f"OK: {PDF} ({n} páginas, {PDF.stat().st_size / 1024 / 1024:.1f} MB)")
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
