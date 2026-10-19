/* Estruturas pré-definidas e textos em linguagem simples — porta de estruturadas/presets.py.
   Os presets só preenchem a lista de pernas; o texto é gerado a partir das pernas atuais e do custo. */
(function (root) {
  "use strict";
  const E = root.Estr;
  const L = E.leg, S = E.structure, P = E.fmtPct;

  const builders = {
    booster: (k1 = 1.0, k2 = 1.125) => S("Booster", [L("stock"), L("call", 1, k1), L("call", -1, k2, "none", null, 2)], { preset: "booster" }),
    collar: (kp = 1.0, kc = 1.15) => S("Collar", [L("stock"), L("put", 1, kp), L("call", -1, kc)], { preset: "collar" }),
    collar_ki: (kp = 1.0, kc = 1.13, b = 1.43) => S("Collar Knock In", [L("stock"), L("put", 1, kp), L("call", -1, kc, "up_in", b)], { preset: "collar_ki" }),
    fko: (k = 1.10, b = 0.70) => S("Forward Knock Out", [L("stock"), L("put", 1, k, "down_out", b), L("call", -1, k, "down_out", b)], { preset: "fko" }),
    trava_alta: (k1 = 1.0, k2 = 1.2) => S("Trava de alta", [L("call", 1, k1), L("call", -1, k2)], { preset: "trava_alta" }),
    trava_baixa: (k1 = 1.0, k2 = 0.8) => S("Trava de baixa", [L("put", 1, k1), L("put", -1, k2)], { preset: "trava_baixa" }),
    straddle: (k = 1.0) => S("Straddle", [L("call", 1, k), L("put", 1, k)], { preset: "straddle" }),
    strangle: (kp = 0.95, kc = 1.05) => S("Strangle", [L("put", 1, kp), L("call", 1, kc)], { preset: "strangle" }),
    protecao_total: () => S("Proteção Total (BBDC4)", [
      L("stock"), L("put", 1, 1.041), L("call", -1, 1.041, "up_in", 1.381), L("call", 1, 1.0, "up_out", 1.381, 0.5),
    ], { preset: "protecao_total", ticker: "BBDC4", trade_date: "2025-11-19", expiry_date: "2026-11-25", option_cost: 0,
      notes: "Exemplo da lâmina de 19/11/2025. Custo das opções = 0 (estrutura sem custo)." }),
  };

  const r = (s, x, cost, branch = "none") => E.returnsFromPayoff(E.payoffAt(s, x, branch), cost, E.hasStock(s));
  const needCost = (s, cost) => (!E.hasStock(s) && !(cost > 0)
    ? ["Estrutura só com opções: informe o <b>custo líquido</b> (prêmio pago, em % do valor inicial) para calcular os retornos, ou use o modo Teórico."]
    : null);
  const rmaxTxt = (s, cost) => { const m = E.profileSummary(s, cost).return_max; return m == null ? "ilimitado" : P(m); };

  const describers = {
    booster(s, c) {
      const k1 = s.legs[1].strike, k2 = s.legs[2].strike, part = s.legs[0].ratio + s.legs[1].ratio;
      return [
        `<b>Na alta:</b> acima de ${P(k1)} do valor inicial você participa em <b>${E.fmtNum(part, part % 1 ? 2 : 0)}x</b> da alta até ${P(k2)} (alta de ${P(k2 - 1)}).`,
        `<b>Teto:</b> o retorno máximo é <b>${rmaxTxt(s, c)}</b>, para qualquer alta a partir de ${P(k2 - 1)} (as calls vendidas limitam o ganho).`,
        `<b>Na queda:</b> sem proteção — você acompanha a ação 1:1 (ex.: queda de 10% → ${P(r(s, 0.9, c))}; queda de 20% → ${P(r(s, 0.8, c))}).`,
      ];
    },
    collar(s, c) {
      const kp = s.legs[1].strike, kc = s.legs[2].strike;
      return [
        `<b>Na queda:</b> a put comprada protege abaixo de ${P(kp)}: retorno mínimo de <b>${P(r(s, Math.min(kp, 1) * 0.5, c))}</b>, por mais que a ação caia.`,
        `<b>Entre ${P(kp)} e ${P(kc)}:</b> você acompanha a variação da ação.`,
        `<b>Teto:</b> acima de ${P(kc)} o retorno fica limitado a <b>${P(r(s, kc * 1.5, c))}</b>.`,
      ];
    },
    collar_ki(s, c) {
      const kp = s.legs[1].strike, kc = s.legs[2].strike, b = s.legs[2].level;
      return [
        `<b>Se a ação nunca subir ${P(b - 1)} ou mais</b> (barreira em ${P(b)}): você participa 1:1 da alta, sem teto — até cerca de <b>${P(r(s, b - 1e-6, c))}</b> logo abaixo da barreira.`,
        `<b>Se tocar a barreira em algum momento:</b> a call vendida passa a existir e o retorno fica limitado a <b>${P(r(s, kc * 1.5, c, "all"))}</b> (strike ${P(kc)}).`,
        `<b>Na queda:</b> proteção da put em ${P(kp)} — retorno mínimo de <b>${P(r(s, Math.min(kp, 1) * 0.5, c))}</b>.`,
      ];
    },
    fko(s, c) {
      const b = s.legs[1].level;
      return [
        `<b>Se a ação nunca cair ${P(1 - b)} ou mais</b> (barreira em ${P(b)}): retorno <b>fixo de ${P(r(s, 1.0, c))}</b>, qualquer que seja o preço no vencimento.`,
        `<b>Se tocar a barreira:</b> a put e a call deixam de existir e você fica só com a ação: retorno = variação da ação (ex.: termina em −20% → ${P(r(s, 0.8, c, "all"))}; em +5% → ${P(r(s, 1.05, c, "all"))}).`,
      ];
    },
    trava_alta(s, c) {
      const k1 = s.legs[0].strike, k2 = s.legs[1].strike;
      return needCost(s, c) || [
        `Você paga ${P(c)} do valor inicial em prêmio.`,
        `<b>Abaixo de ${P(k1)}</b> no vencimento: perde 100% do prêmio.`,
        `<b>Acima de ${P(k2)}:</b> ganho máximo de <b>${P(r(s, k2 * 1.5, c))}</b> sobre o prêmio.`,
        `Ponto de equilíbrio: ação em ${P(k1 + c)}.`,
      ];
    },
    trava_baixa(s, c) {
      const k1 = s.legs[0].strike, k2 = s.legs[1].strike;
      return needCost(s, c) || [
        `Você paga ${P(c)} do valor inicial em prêmio.`,
        `<b>Acima de ${P(k1)}</b> no vencimento: perde 100% do prêmio.`,
        `<b>Abaixo de ${P(k2)}:</b> ganho máximo de <b>${P(r(s, k2 * 0.5, c))}</b> sobre o prêmio.`,
        `Ponto de equilíbrio: ação em ${P(k1 - c)}.`,
      ];
    },
    straddle(s, c) {
      const k = s.legs[0].strike;
      return needCost(s, c) || [
        `Você paga ${P(c)} do valor inicial e ganha com <b>movimentos fortes para qualquer lado</b>.`,
        `Pontos de equilíbrio: ação em ${P(k - c)} ou ${P(k + c)}.`,
        `Perda máxima: 100% do prêmio, se a ação terminar exatamente em ${P(k)}.`,
        `Ex.: ação +20% → ${P(r(s, 1.2, c))}; ação −20% → ${P(r(s, 0.8, c))}.`,
      ];
    },
    strangle(s, c) {
      const kp = s.legs[0].strike, kc = s.legs[1].strike;
      return needCost(s, c) || [
        `Você paga ${P(c)} e ganha com movimentos fortes; perde 100% do prêmio se a ação terminar entre ${P(kp)} e ${P(kc)}.`,
        `Pontos de equilíbrio: ${P(kp - c)} e ${P(kc + c)}.`,
        `Ex.: ação +20% → ${P(r(s, 1.2, c))}; ação −20% → ${P(r(s, 0.8, c))}.`,
      ];
    },
    protecao_total(s, c) {
      const k = s.legs[1].strike, b = s.legs[2].level, kuo = s.legs[3].strike, ratio = s.legs[3].ratio;
      return [
        `<b>Se a ação nunca subir ${P(b - 1)} ou mais</b> (barreira em ${P(b)}):<ul>
          <li>na queda ou até ${P(kuo)}: retorno <b>mínimo de ${P(r(s, 0.5, c))}</b> (proteção total + ganho mínimo do strike da put em ${P(k)});</li>
          <li>na alta: você recebe a alta da ação <b>mais ${P(ratio, 0)} da alta</b> acima de ${P(kuo)} (ex.: +4% → ${P(r(s, 1.04, c))}; +28% → ${P(r(s, 1.28, c))}), até cerca de <b>${P(r(s, b - 1e-6, c))}</b> logo abaixo da barreira.</li></ul>`,
        `<b>Se tocar a barreira em qualquer momento:</b> retorno <b>fixo de ${P(r(s, 1.0, c, "all"))}</b>, qualquer que seja o preço no vencimento.`,
      ];
    },
  };

  E.PRESETS = {
    booster: { name: "Booster", formula: "S_T + max(S_T − K1, 0) − 2·max(S_T − K2, 0)" },
    collar: { name: "Collar", formula: "min(max(S_T, Kp), Kc)" },
    collar_ki: { name: "Collar Knock In", formula: "S_T + max(Kp − S_T, 0) − 1{tocou B}·max(S_T − Kc, 0)" },
    fko: { name: "Forward Knock Out", formula: "sem toque em B: K (fixo); com toque: S_T" },
    trava_alta: { name: "Trava de alta", formula: "max(S_T − K1, 0) − max(S_T − K2, 0); retorno = valor/c − 1" },
    trava_baixa: { name: "Trava de baixa", formula: "max(K1 − S_T, 0) − max(K2 − S_T, 0); retorno = valor/c − 1" },
    straddle: { name: "Straddle", formula: "|S_T − K|; retorno = valor/c − 1" },
    strangle: { name: "Strangle", formula: "max(Kp − S_T, 0) + max(S_T − Kc, 0); retorno = valor/c − 1" },
    protecao_total: { name: "Proteção Total (BBDC4)", formula: "sem toque em B: S_T + max(K − S_T, 0) + 0,5·max(S_T − 1, 0); com toque: K (fixo)" },
  };
  Object.keys(E.PRESETS).forEach((k) => { E.PRESETS[k].build = builders[k]; E.PRESETS[k].describe = describers[k]; });

  const shape = (s) => s.legs.map((l) => `${l.kind}|${l.position}|${l.barrier}`).join(";");

  function describeGeneric(s, cost) {
    const nc = needCost(s, cost);
    if (nc) return nc;
    const prof = E.profileSummary(s, cost), lines = [];
    const scen = [-0.30, -0.20, -0.10, 0, 0.10, 0.20, 0.30, 0.50];
    const branches = E.events(s).length ? [["none", "Sem tocar barreira"], ["all", "Tocando a barreira"]] : [["none", ""]];
    branches.forEach(([b, lbl]) => {
      const parts = [];
      scen.forEach((v) => { const p = E.payoffAt(s, 1 + v, b); if (isFinite(p)) parts.push(`ação ${P(v, 0, true)} → <b>${P(E.returnsFromPayoff(p, cost, E.hasStock(s)))}</b>`); });
      if (parts.length) lines.push((lbl ? lbl + ": " : "") + parts.join("; ") + ".");
    });
    if (prof.gain_unlimited) lines.push("Ganho máximo: <b>ilimitado</b> na alta.");
    else if (prof.return_max != null) lines.push(`Retorno máximo no vencimento: <b>${P(prof.return_max)}</b>.`);
    if (prof.loss_unlimited) lines.push("Perda máxima: <b>ilimitada</b> na alta.");
    else if (prof.return_min != null) lines.push(`Pior retorno no vencimento: <b>${P(prof.return_min)}</b>.`);
    return lines;
  }

  /* Lista de frases (HTML) explicando a estrutura; usa o texto do preset se a forma não mudou. */
  E.describe = function (s, cost) {
    cost = cost == null ? s.option_cost : cost;
    const p = E.PRESETS[s.preset || ""];
    if (p && shape(p.build()) === shape(s)) {
      try { return p.describe(s, cost); } catch (e) { /* cai no genérico */ }
    }
    return describeGeneric(s, cost);
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
