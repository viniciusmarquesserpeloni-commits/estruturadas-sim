import json, numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv
D = "site/data/"  # rodar da raiz do projeto
cdi=json.load(open(D+"cdi.json")); cd=dict(zip(cdi["d"],cdi["r"]))
CDI_NOW=0.1365
def collar_ki(P,kp,kc,b):
    S=P[:,-1]; h=P.max(1)>=b; return np.maximum(S,kp)-np.where(h,np.maximum(S-kc,0),0)-1
def prot(P):
    S=P[:,-1]; h=P.max(1)>=1.381; return np.where(h,1.041,np.maximum(S,1.041)+0.5*np.maximum(S-1,0))-1
cases=[(63,lambda P:collar_ki(P,1,1.06,1.12),"Collar KI 3m 100/106/112"),(126,lambda P:collar_ki(P,1,1.10,1.20),"Collar KI 6m 100/110/120"),(252,prot,"Proteção Total 12m")]
for t in ["BBDC4","PETR4"]:
    p=json.load(open(D+f"precos/{t}.json")); d=np.array(p["d"]); c=np.array(p["ca"],float); m=d>="2010-01-01"; d,c=d[m],c[m]
    f=np.cumprod([1+cd.get(x,0) for x in d])
    for N,fn,name in cases:
        P=swv(c,N+1); P=P[:,1:]/P[:,:1]
        F=swv(f,N+1); F=F[:,1:]/F[:,:1]           # CDI acumulado do período em cada dia
        k=np.arange(1,N+1); now=(1+CDI_NOW)**(k/252)
        Padj=P*now/F                               # troca o CDI da época pelo CDI de hoje (mantém o excesso sobre o CDI)
        cdi_per=F[:,-1]-1; cdi_now=now[-1]-1
        r=fn(P); ra=fn(Padj)
        print(f"{t} {name:26s} | CDI da época: P(>CDI)={np.mean(r>cdi_per):.0%} | CDI de hoje, caminho bruto: {np.mean(r>cdi_now):.0%} | CDI de hoje, caminho ajustado: {np.mean(ra>cdi_now):.0%} | CDI médio época {np.mean((1+cdi_per)**(252/N)-1):.1%}")
