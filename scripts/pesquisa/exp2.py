"""Prazos curtos (63/126 pregões): IC, sensibilidade ao drift e teste de calibração walk-forward
dos estimadores de vol (incondicional x realizada 63d x EWMA x GARCH)."""
import json, numpy as np
from scipy.optimize import minimize
from scipy.special import ndtr
from numpy.lib.stride_tricks import sliding_window_view as swv
D = "site/data/"  # rodar da raiz do projeto
rng = np.random.default_rng(7)

def load(t, start="2010-01-01"):
    p = json.load(open(D + f"precos/{t}.json")); d = np.array(p["d"]); c = np.array(p["ca"], float)
    m = d >= start; return d[m], c[m]
cdi = json.load(open(D + "cdi.json")); cdi_d = dict(zip(cdi["d"], cdi["r"]))

STRUCT = {63: dict(kp=1.0, kc=1.06, b=1.12), 126: dict(kp=1.0, kc=1.10, b=1.20)}
def collar_ki(paths, kp, kc, b):
    S = paths[:, -1]; hit = paths.max(1) >= b
    return np.maximum(S, kp) - np.where(hit, np.maximum(S - kc, 0), 0) - 1, hit

def block_ci(ind, L, B=1500):
    n = len(ind); nb = int(np.ceil(n / L)); out = np.empty(B)
    for k in range(B):
        st = rng.integers(0, n - L + 1, nb); out[k] = ind[(st[:, None] + np.arange(L)).ravel()[:n]].mean()
    return np.percentile(out, [2.5, 97.5])

def garch_fit(r):
    r = r - r.mean()
    def filt(p):
        w, a, b = p; h = np.empty_like(r); h[0] = r.var()
        for t in range(1, len(r)): h[t] = w + a * r[t-1]**2 + b * h[t-1]
        return h
    def nll(p):
        w, a, b = p
        if w <= 0 or a < 0 or b < 0 or a + b >= 0.999: return 1e10
        h = filt(p); return 0.5 * np.sum(np.log(h) + r**2 / h)
    v = r.var(); p = minimize(nll, [v*0.05, 0.08, 0.9], method="Nelder-Mead", options=dict(maxiter=3000)).x
    return p

def garch_avg_var(p, r_hist, n):
    """variância diária média prevista para os próximos n dias."""
    w, a, b = p; r = r_hist - r_hist.mean(); h = r.var()
    for x in r[-500:]: h = w + a * x**2 + b * h  # aquece com últimos 500 dias
    lr = w / (1 - a - b); k = np.arange(n); return np.mean(lr + (a + b)**k * (h - lr))

Z = rng.standard_normal((4000, 126)); Z = np.vstack([Z, -Z])
def gbm(sig_ann, mu_ann, n):
    dt = 1/252; inc = (np.log(1+mu_ann) - 0.5*sig_ann**2)*dt + sig_ann*np.sqrt(dt)*Z[:, :n]
    return np.exp(np.cumsum(inc, 1))

for t in ["BBDC4", "PETR4", "VALE3"]:
    d, c = load(t); lr = np.diff(np.log(c))
    cdi_f = np.cumprod([1 + cdi_d.get(x, 0) for x in d])
    print(f"\n######## {t}  vol incondicional {lr.std()*np.sqrt(252):.0%}  vol 63d hoje {lr[-63:].std()*np.sqrt(252):.0%}")
    for N, sp in STRUCT.items():
        w = swv(c, N + 1); paths = w[:, 1:] / w[:, :1]
        cdi_win = cdi_f[N:] / cdi_f[:-N] - 1
        r, hit = collar_ki(paths, **sp)
        il, ic, ih = (r > 1e-9).astype(float), (r > cdi_win).astype(float), hit.astype(float)
        print(f"--- N={N} Collar KI {sp}: janelas {len(r)}, não sobrepostas ≈{len(r)//N}")
        for lbl, ind in [("P(lucro)", il), ("P(>CDI)", ic), ("P(barreira)", ih)]:
            lo, hi = block_ci(ind, N); print(f"   HIST {lbl:12s} {ind.mean():.0%}  IC95% [{lo:.0%}, {hi:.0%}]")
        sig = lr[-63:].std()*np.sqrt(252)
        for mu_lbl, mu in [("drift 0", 0.0), ("drift CDI", 0.1365), ("drift CDI+5", 0.1865), ("drift -10%", -0.10)]:
            r2, h2 = collar_ki(gbm(sig, mu, N), **sp); cdiN = 1.1365**(N/252) - 1
            print(f"   GBM σ={sig:.0%} {mu_lbl:12s} P(lucro)={np.mean(r2>1e-9):.0%} P(>CDI)={np.mean(r2>cdiN):.0%} P(barreira)={h2.mean():.0%}")
        for s_alt in [0.20, 0.30, 0.40, 0.50]:
            r2, h2 = collar_ki(gbm(s_alt, 0.1365, N), **sp)
            print(f"   GBM σ={s_alt:.0%} drift CDI    P(lucro)={np.mean(r2>1e-9):.0%} P(>CDI)={np.mean(r2>1.1365**(N/252)-1):.0%} P(barreira)={h2.mean():.0%}")

    # ---------- walk-forward: calibração das previsões (N=63) ----------
    N = 63; sp = STRUCT[N]; start = 504
    dates = range(start, len(c) - N, 5)
    preds = {k: [] for k in ["incond", "real63", "ewma", "garch"]}; outs = []
    params = None; last_fit = -10**9
    for i in dates:
        r_hist = lr[:i]
        if i - last_fit >= 252: params = garch_fit(r_hist); last_fit = i
        # EWMA lambda 0.94
        lam = 0.94; e = r_hist[-250:]; wts = lam ** np.arange(len(e))[::-1]; ew = np.sqrt(np.sum(wts*e**2)/np.sum(wts)*252)
        vols = dict(incond=r_hist.std()*np.sqrt(252), real63=r_hist[-63:].std()*np.sqrt(252), ewma=ew,
                    garch=np.sqrt(garch_avg_var(params, r_hist, N)*252))
        cdi_t = cdi_f[i+N]/cdi_f[i]-1  # CDI do período (conhecido aprox. no início)
        path = c[i+1:i+N+1]/c[i]; rr, hh = collar_ki(path[None, :], **sp)
        outs.append((rr[0] > 1e-9, hh[0], rr[0] > cdi_t))
        for k, v in vols.items():
            r2, h2 = collar_ki(gbm(v, (1+cdi_t)**(252/N)-1, N), **sp)
            preds[k].append((np.mean(r2 > 1e-9), h2.mean(), np.mean(r2 > cdi_t)))
    o = np.array(outs, float)
    print(f"--- Walk-forward N=63, {len(o)} datas (a cada 5 pregões), drift=CDI; Brier (menor = melhor) e média prevista x realizada")
    for j, lbl in enumerate(["P(lucro)", "P(barreira)", "P(>CDI)"]):
        line = f"   {lbl:12s} realizado {o[:, j].mean():.0%} |"
        for k, v in preds.items():
            p = np.array(v)[:, j]; line += f" {k}: prev {p.mean():.0%} Brier {np.mean((p-o[:, j])**2):.3f} |"
        print(line)
    # baseline: frequência climatológica
    print("   Brier 'chute constante' (freq. histórica):", [f"{np.mean((o[:, j].mean()-o[:, j])**2):.3f}" for j in range(3)])
