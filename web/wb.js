/* ══════════════════════════════════════════════════════════════════
   Sling TSi — Peso & Balanceamento (PWA)

   Porte de "sling_tsi_wb.py": as constantes e as contas vem do proprio
   bundle do planejador (calcWBResult / renderEnvelope), com o envelope de
   CG desenhado em SVG e a folha A4 gerada para impressao.
   ══════════════════════════════════════════════════════════════════ */
'use strict';

// ── constantes TSi (todos os bracos em mm do datum) ────────────────
const FUEL_DENSITY = 0.72;      // kg/L
const MAX_FUEL_L = 198;         // L
const MAX_BAG_KG = 35;          // kg
const MTOW_TSI = 950;           // kg

const ARM_EMPTY = 1909;
const ARM_FUEL = 1800;
const ARM_FRONT_SEATS = 1902;
const ARM_REAR_SEATS = 2948;
const ARM_BAGGAGE = 3288;

const CG_FWD_MM = 1847;         // limite dianteiro
const CG_AFT_MM = 2043;         // limite traseiro

const MAC_LE_MM = 1602;         // bordo de ataque da MAC
const MAC_LEN_MM = 1339;        // comprimento da MAC

// envelope: [%MAC, kg]
const WB_ENV_PTS = [
  [18, 490], [18, 840], [24, 950], [33, 950], [33, 700], [28, 490], [18, 490],
];
const CHART_X_MIN = 16, CHART_X_MAX = 34;
const CHART_Y_MIN = 400, CHART_Y_MAX = 1000;

// defaults do perfil da aeronave
const DEFAULT_CONS_LH = 28;
const DEFAULT_DUR_H = 0;
const DEFAULT_EMPTY_KG = 561;
const DEFAULT_EMPTY_CG_MM = 1909;

const PROFILES_KEY = 'sling_tsi.perfis';
const PROFILES_SEED = 'data/perfis_wb.json';

// campos gravados em cada perfil (ordem = ordem na tela)
const PROFILE_FIELDS = ['consumo', 'duracao', 'empty_kg', 'empty_cg', 'pilot',
  'copilot', 'pax3', 'pax4', 'baggage', 'fuel', 'pilot_arm', 'copilot_arm'];

// ══════════════════════════════════════════════════════════════════
//  NUCLEO DE CALCULO
// ══════════════════════════════════════════════════════════════════
/** Equivalente a parseFloat(v)||default do planejador. */
function num(value, fallback) {
  const parsed = parseFloat(String(value === null || value === undefined ? '' : value)
    .replace(',', '.'));
  return Number.isFinite(parsed) && parsed !== 0 ? parsed : (fallback || 0);
}

function result(total, cgMm, fuelKg, moment) {
  return {
    total: total,
    cgMm: cgMm,
    pMac: ((cgMm - MAC_LE_MM) / MAC_LEN_MM) * 100,
    fuelKg: fuelKg,
    moment: moment,
    overweight: total > MTOW_TSI,
    cgOob: cgMm < CG_FWD_MM || cgMm > CG_AFT_MM,
    get ok() { return !this.overweight && !this.cgOob; },
  };
}

/** Replica exata de calcWBResult() do planejador. */
function calcWB(v) {
  const fuelKg = v.fuel * FUEL_DENSITY;
  const total = v.empty_kg + v.pilot + v.copilot + v.pax3 + v.pax4 +
    v.baggage + fuelKg;
  const moment = v.empty_kg * v.empty_cg +
    v.pilot * v.pilot_arm + v.copilot * v.copilot_arm +
    (v.pax3 + v.pax4) * ARM_REAR_SEATS +
    v.baggage * ARM_BAGGAGE + fuelKg * ARM_FUEL;
  const cgMm = total > 0 ? moment / total : ARM_EMPTY;
  return result(total, cgMm, fuelKg, moment);
}

/**
 * Peso e CG ao fim do voo: queima `consLh * durH` litros do tanque.
 *
 * O braco do combustivel (1800 mm) fica a frente do CG tipico, entao o CG
 * anda para tras conforme o tanque esvazia — por isso o limite traseiro
 * costuma ser critico no pouso, nao na decolagem.
 */
function calcLanding(res, consLh, durH) {
  const burnKg = consLh * durH * FUEL_DENSITY;
  const fuelKg = res.fuelKg - burnKg;
  const total = res.total - burnKg;
  const moment = res.moment - burnKg * ARM_FUEL;
  const cgMm = total > 0 ? moment / total : ARM_EMPTY;
  return result(total, cgMm, fuelKg, moment);
}

// ══════════════════════════════════════════════════════════════════
//  PERFIS
// ══════════════════════════════════════════════════════════════════
function loadProfiles() {
  try {
    const raw = JSON.parse(localStorage.getItem(PROFILES_KEY));
    if (raw && typeof raw === 'object') return raw;
  } catch (err) { /* segue com os de fabrica */ }
  return null;
}

function saveProfiles(profiles) {
  try {
    localStorage.setItem(PROFILES_KEY, JSON.stringify(profiles));
    return true;
  } catch (err) {
    return false;
  }
}

/** Na primeira visita valem os perfis que vieram com o aplicativo. */
async function seedProfiles() {
  if (loadProfiles()) return;
  try {
    const response = await fetch(PROFILES_SEED, { cache: 'no-cache' });
    if (response.ok) saveProfiles(await response.json());
  } catch (err) { /* sem semente: comeca vazio */ }
}

// ══════════════════════════════════════════════════════════════════
//  ENVELOPE DE CG  — as mesmas formas do canvas Tkinter
// ══════════════════════════════════════════════════════════════════
const SVG_NS = 'http://www.w3.org/2000/svg';
const CW = 630, CH = 400;
const PAD_L = 46, PAD_R = 18, PAD_T = 18, PAD_B = 50;
const DW = CW - PAD_L - PAD_R, DH = CH - PAD_T - PAD_B;

const toX = (v) => PAD_L + ((v - CHART_X_MIN) / (CHART_X_MAX - CHART_X_MIN)) * DW;
const toY = (v) => PAD_T + DH - ((v - CHART_Y_MIN) / (CHART_Y_MAX - CHART_Y_MIN)) * DH;

function svgEl(tag, attrs, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    node.setAttribute(key, String(value));
  }
  if (text !== undefined) node.textContent = text;
  return node;
}

function drawEnvelope(svg, res, land) {
  svg.textContent = '';
  svg.appendChild(svgEl('rect', {
    x: PAD_L, y: PAD_T, width: DW, height: DH, fill: '#111111',
  }));

  for (const x of [18, 20, 22, 24, 26, 28, 30, 32, 34]) {
    const px = toX(x);
    svg.appendChild(svgEl('line', {
      x1: px, y1: PAD_T, x2: px, y2: PAD_T + DH, stroke: '#2a313c',
    }));
    svg.appendChild(svgEl('text', {
      x: px, y: PAD_T + DH + 14, 'text-anchor': 'middle',
      'font-size': 10, fill: '#6b7280',
    }, `${x}%`));
  }
  for (const y of [400, 500, 600, 700, 800, 900, 950, 1000]) {
    const py = toY(y);
    svg.appendChild(svgEl('line', {
      x1: PAD_L, y1: py, x2: PAD_L + DW, y2: py, stroke: '#2a313c',
    }));
    svg.appendChild(svgEl('text', {
      x: PAD_L - 5, y: py + 3.5, 'text-anchor': 'end',
      'font-size': 10, fill: '#6b7280',
    }, String(y)));
  }

  const mtowY = toY(MTOW_TSI);
  svg.appendChild(svgEl('line', {
    x1: PAD_L, y1: mtowY, x2: PAD_L + DW, y2: mtowY,
    stroke: '#7a2b2b', 'stroke-dasharray': '5,4',
  }));
  svg.appendChild(svgEl('text', {
    x: PAD_L + 4, y: mtowY - 6, 'text-anchor': 'start',
    'font-size': 11, fill: '#a83a3a',
  }, `MTOW ${MTOW_TSI} kg`));

  const points = WB_ENV_PTS.map(([x, y]) => `${toX(x)},${toY(y)}`).join(' ');
  svg.appendChild(svgEl('polygon', {
    points: points, fill: '#251313', stroke: '#d42020', 'stroke-width': 1.5,
  }));

  if (res.total > 0) {
    const dx = toX(res.pMac), dy = toY(res.total);
    const color = res.ok ? '#22c55e' : '#ef4444';

    // trajetoria decolagem -> pouso (o CG recua conforme queima)
    if (land && land.total > 0) {
      const lx = toX(land.pMac), ly = toY(land.total);
      const lcolor = land.ok ? '#22c55e' : '#ef4444';
      svg.appendChild(svgEl('line', {
        x1: dx, y1: dy, x2: lx, y2: ly, stroke: '#7c8698',
        'stroke-width': 1.2, 'stroke-dasharray': '4,3',
      }));
      svg.appendChild(svgEl('circle', {
        cx: lx, cy: ly, r: 4.5, fill: '#111111', stroke: lcolor,
        'stroke-width': 2,
      }));
      svg.appendChild(svgEl('text', {
        x: Math.min(Math.max(lx, 80), CW - 80),
        y: Math.min(ly + 20, PAD_T + DH - 6),
        'text-anchor': 'middle', 'font-size': 11, fill: lcolor,
      }, `POU  ${land.pMac.toFixed(1)}% / ${land.total.toFixed(0)} kg`));
    }

    svg.appendChild(svgEl('circle', {
      cx: dx, cy: dy, r: 7, fill: 'none', stroke: color,
    }));
    svg.appendChild(svgEl('circle', {
      cx: dx, cy: dy, r: 4.5, fill: color, stroke: '#ffffff',
    }));
    svg.appendChild(svgEl('text', {
      x: Math.min(Math.max(dx, 80), CW - 80),
      y: Math.max(dy - 12, PAD_T + 12),
      'text-anchor': 'middle', 'font-size': 11, fill: color,
    }, `${land ? 'DEC  ' : ''}${res.pMac.toFixed(1)}% / ${res.total.toFixed(0)} kg`));
  }

  svg.appendChild(svgEl('text', {
    x: PAD_L + DW / 2, y: CH - 6, 'text-anchor': 'middle',
    'font-size': 11, fill: '#555555',
  }, '% MAC'));
  svg.appendChild(svgEl('text', {
    x: 14, y: PAD_T + DH / 2, 'text-anchor': 'middle', 'font-size': 11,
    fill: '#555555', transform: `rotate(-90 14 ${PAD_T + DH / 2})`,
  }, 'Peso (kg)'));
}

// ══════════════════════════════════════════════════════════════════
//  FOLHA A4  — preto e branco, pronta para imprimir
// ══════════════════════════════════════════════════════════════════
const PRINT_CSS = `
@page { size: A4 portrait; margin: 14mm 13mm; }
* { box-sizing: border-box; }
html, body { background: #fff; color: #000; }
/* a folha inteira sai a 92%: com um perfil carregado ela fica cheia, e essa
   sobra e o que garante uma pagina so mesmo com o cabecalho e o rodape que o
   navegador acrescenta ao imprimir */
body { font-family: "Segoe UI", Arial, Helvetica, sans-serif; font-size: 9.5pt;
       margin: 0; line-height: 1.35; zoom: .92; }
h1 { font-size: 15pt; letter-spacing: .10em; margin: 0; text-transform: uppercase; }
.sub { font-size: 8pt; color: #444; margin-top: 2pt; }
header { border-bottom: 1.5pt solid #000; padding-bottom: 5pt; margin-bottom: 10pt;
         display: flex; align-items: flex-end; justify-content: space-between; }
h2 { font-size: 8pt; letter-spacing: .16em; text-transform: uppercase;
     margin: 9pt 0 4pt; padding-bottom: 2pt; border-bottom: .75pt solid #000; }
table { width: 100%; border-collapse: collapse; }
th { font-size: 7.5pt; letter-spacing: .06em; text-transform: uppercase;
     text-align: right; padding: 3pt 5pt; border-bottom: .75pt solid #000; }
th:first-child, td:first-child { text-align: left; }
td { padding: 3.5pt 5pt; border-bottom: .5pt solid #bbb;
     text-align: right; font-variant-numeric: tabular-nums; }
tr.total td { font-weight: 700; border-top: .75pt solid #000;
              border-bottom: .75pt solid #000; background: #eee; }
.tag { font-size: 7pt; color: #555; margin-left: 4pt; }
.grid2 { display: flex; gap: 8pt; margin-top: 8pt; }
.card { flex: 1; border: .75pt solid #000; padding: 6pt 8pt; }
.card .k { font-size: 7pt; letter-spacing: .1em; text-transform: uppercase;
           color: #444; }
.card .v { font-size: 13pt; font-weight: 700; font-variant-numeric: tabular-nums; }
.card .d { font-size: 8pt; color: #333; font-variant-numeric: tabular-nums; }
.badge { display: inline-block; font-size: 8.5pt; font-weight: 700; padding: 2pt 6pt;
         border: 1pt solid #000; margin: 2pt 0; }
.badge.ng { background: #000; color: #fff; }
.chart { text-align: center; margin-top: 4pt; page-break-inside: avoid;
         break-inside: avoid; }
.chart svg { max-width: 100%; height: auto; }
footer { margin-top: 8pt; padding-top: 5pt; border-top: .5pt solid #000;
         font-size: 7.5pt; color: #333; display: flex;
         justify-content: space-between; }
.sig { margin-top: 12pt; display: flex; gap: 20pt; font-size: 8pt; color: #333;
       page-break-inside: avoid; break-inside: avoid; }
.sig div { flex: 1; border-top: .5pt solid #000; padding-top: 3pt; }
@media print { .noprint { display: none; } }
.noprint { margin: 10pt 0; }
.noprint button { font: inherit; padding: 6pt 14pt; cursor: pointer; }
`;

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[ch]);
}

/**
 * Envelope de CG monocromatico, para a folha impressa.
 *
 * Menor que o da tela de proposito: com um perfil carregado a folha fica
 * cheia, e o grafico e a primeira coisa que empurraria tudo para a segunda
 * pagina — ainda mais quando o navegador imprime com cabecalho e rodape.
 */
function envelopeSvgPrint(res, land) {
  const w = 450, h = 278;
  const padL = 44, padR = 14, padT = 14, padB = 40;
  const dw = w - padL - padR, dh = h - padT - padB;
  const tx = (v) => padL + ((v - CHART_X_MIN) / (CHART_X_MAX - CHART_X_MIN)) * dw;
  const ty = (v) => padT + dh - ((v - CHART_Y_MIN) / (CHART_Y_MAX - CHART_Y_MIN)) * dh;

  const out = [`<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" ` +
    'xmlns="http://www.w3.org/2000/svg" font-family="Arial, sans-serif">'];
  out.push(`<rect x="${padL}" y="${padT}" width="${dw}" height="${dh}" ` +
    'fill="#fff" stroke="#000" stroke-width=".75"/>');

  for (const x of [18, 20, 22, 24, 26, 28, 30, 32, 34]) {
    const px = tx(x);
    out.push(`<line x1="${px.toFixed(1)}" y1="${padT}" x2="${px.toFixed(1)}" ` +
      `y2="${h - padB}" stroke="#ccc" stroke-width=".5"/>`);
    out.push(`<text x="${px.toFixed(1)}" y="${h - padB + 11}" text-anchor="middle" ` +
      `font-size="7.5" fill="#000">${x}%</text>`);
  }
  for (const y of [400, 500, 600, 700, 800, 900, 950, 1000]) {
    const py = ty(y);
    out.push(`<line x1="${padL}" y1="${py.toFixed(1)}" x2="${w - padR}" ` +
      `y2="${py.toFixed(1)}" stroke="#ccc" stroke-width=".5"/>`);
    out.push(`<text x="${padL - 4}" y="${(py + 2.5).toFixed(1)}" text-anchor="end" ` +
      `font-size="7.5" fill="#000">${y}</text>`);
  }

  const mtowY = ty(MTOW_TSI);
  out.push(`<line x1="${padL}" y1="${mtowY.toFixed(1)}" x2="${w - padR}" ` +
    `y2="${mtowY.toFixed(1)}" stroke="#000" stroke-width=".75" stroke-dasharray="5,3"/>`);
  out.push(`<text x="${padL + 3}" y="${(mtowY - 3).toFixed(1)}" text-anchor="start" ` +
    `font-size="7.5" fill="#000">MTOW ${MTOW_TSI} kg</text>`);

  const pts = WB_ENV_PTS.map(([x, y]) => `${tx(x).toFixed(1)},${ty(y).toFixed(1)}`).join(' ');
  out.push(`<polygon points="${pts}" fill="#e8e8e8" stroke="#000" stroke-width="1.5"/>`);

  if (res.total > 0) {
    const dx = tx(res.pMac), dy = ty(res.total);
    if (land && land.total > 0) {
      const lx = tx(land.pMac), ly = ty(land.total);
      out.push(`<line x1="${dx.toFixed(1)}" y1="${dy.toFixed(1)}" x2="${lx.toFixed(1)}" ` +
        `y2="${ly.toFixed(1)}" stroke="#000" stroke-width=".75" stroke-dasharray="4,2.5"/>`);
      out.push(`<circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="4.5" fill="#fff" ` +
        'stroke="#000" stroke-width="1.5"/>');
      out.push(`<text x="${Math.min(Math.max(lx, 66), w - 66).toFixed(1)}" ` +
        `y="${(ly + 13).toFixed(1)}" text-anchor="middle" font-size="8" fill="#000">` +
        `POU ${land.pMac.toFixed(1)}% / ${land.total.toFixed(0)} kg</text>`);
    }
    out.push(`<circle cx="${dx.toFixed(1)}" cy="${dy.toFixed(1)}" r="4.5" fill="#000"/>`);
    out.push(`<text x="${Math.min(Math.max(dx, 66), w - 66).toFixed(1)}" ` +
      `y="${(dy - 8).toFixed(1)}" text-anchor="middle" font-size="8" fill="#000">` +
      `DEC ${res.pMac.toFixed(1)}% / ${res.total.toFixed(0)} kg</text>`);
  }

  out.push(`<text x="${(padL + dw / 2).toFixed(1)}" y="${h - 4}" text-anchor="middle" ` +
    'font-size="8" fill="#000">% MAC</text>');
  out.push(`<text x="10" y="${(padT + dh / 2).toFixed(1)}" text-anchor="middle" ` +
    `font-size="8" fill="#000" transform="rotate(-90 10 ${(padT + dh / 2).toFixed(1)})">` +
    'Peso (kg)</text>');
  out.push('</svg>');
  return out.join('');
}

/** Folha A4 preto-e-branco com a composicao de massa e o envelope. */
function buildPrintHtml(values, res, land, profileName) {
  const fmt = (x, n) => x.toFixed(n === undefined ? 1 : n);
  const status = (r) => {
    if (r.overweight) return '<span class="badge ng">FORA — EXCESSO DE PESO</span>';
    if (r.cgOob) return '<span class="badge ng">FORA — CG ALÉM DO LIMITE</span>';
    return '<span class="badge">DENTRO DO ENVELOPE</span>';
  };

  const fuelL = values.fuel;
  const burnL = values.consumo * values.duracao;
  const linhas = [
    ['Peso Vazio', 'perfil', values.empty_kg, values.empty_cg],
    ['Piloto', 'assento dianteiro', values.pilot, values.pilot_arm],
    ['Copiloto', 'assento dianteiro', values.copilot, values.copilot_arm],
    ['Passageiro 3', 'assento traseiro', values.pax3, ARM_REAR_SEATS],
    ['Passageiro 4', 'assento traseiro', values.pax4, ARM_REAR_SEATS],
    ['Bagagem', `máx. ${MAX_BAG_KG} kg`, values.baggage, ARM_BAGGAGE],
    ['Combustível na Decolagem', `${fuelL.toFixed(0)} L × ${FUEL_DENSITY} kg/L`,
      fuelL * FUEL_DENSITY, ARM_FUEL],
  ];

  const corpo = linhas.map(([nome, tag, kg, arm]) => {
    const mom = kg === 0 ? '&mdash;' : fmt(kg * arm / 1000, 3);
    return `<tr><td>${escapeHtml(nome)}<span class='tag'>${escapeHtml(tag)}</span></td>` +
      `<td>${fmt(kg)}</td><td>${arm.toFixed(0)}</td><td>${mom}</td></tr>`;
  });
  corpo.push(`<tr class='total'><td>TOTAL NA DECOLAGEM</td><td>${fmt(res.total)}</td>` +
    `<td>${res.cgMm.toFixed(0)}</td><td>${fmt(res.cgMm * res.total / 1000)}</td></tr>`);
  corpo.push(`<tr><td>Combustível no Pouso<span class='tag'>&minus; ${burnL.toFixed(0)} L ` +
    `queimados</span></td><td>${fmt(land.fuelKg)}</td><td>${ARM_FUEL}</td>` +
    `<td>${fmt(land.fuelKg * ARM_FUEL / 1000, 3)}</td></tr>`);
  corpo.push(`<tr class='total'><td>TOTAL NO POUSO</td><td>${fmt(land.total)}</td>` +
    `<td>${land.cgMm.toFixed(0)}</td>` +
    `<td>${fmt(land.cgMm * land.total / 1000)}</td></tr>`);

  const perfil = profileName ? `Perfil: ${escapeHtml(profileName)}` : 'Perfil: &mdash;';
  const quando = new Date().toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });

  return `<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Peso e Balanceamento &mdash; Sling TSi</title>
<style>${PRINT_CSS}</style></head><body>
<div class="noprint"><button onclick="window.print()">Imprimir</button></div>
<header>
  <div><h1>Sling TSi &mdash; Peso &amp; Balanceamento</h1><div class="sub">${perfil}</div></div>
  <div class="sub">Emitido em ${quando}</div>
</header>

<h2>Aeronave &amp; Performance</h2>
<table><tr>
  <td style="text-align:left">Consumo<br><b>${values.consumo} L/h</b></td>
  <td style="text-align:left">Duração do voo<br><b>${values.duracao} h</b></td>
  <td style="text-align:left">Peso vazio<br><b>${fmt(values.empty_kg)} kg</b></td>
  <td style="text-align:left">CG vazio<br><b>${values.empty_cg.toFixed(0)} mm</b></td>
</tr></table>

<h2>Composição de Massa</h2>
<table>
<thead><tr><th>Item</th><th>Peso (kg)</th><th>Braço (mm)</th>
<th>Momento (kg&middot;m)</th></tr></thead>
<tbody>${corpo.join('')}</tbody></table>

<div class="grid2">
  <div class="card"><div class="k">Peso na Decolagem</div>
    <div class="v">${fmt(res.total)} kg</div>
    <div class="d">MTOW ${MTOW_TSI} kg</div></div>
  <div class="card"><div class="k">Na Decolagem</div>${status(res)}
    <div class="d">${res.cgMm.toFixed(0)} mm &middot; ${res.pMac.toFixed(1)} %MAC</div></div>
  <div class="card"><div class="k">No Pouso</div>${status(land)}
    <div class="d">${land.cgMm.toFixed(0)} mm &middot; ${land.pMac.toFixed(1)} %MAC</div></div>
</div>

<h2>Envelope de CG &mdash; Peso vs CG %MAC</h2>
<div class="chart">${envelopeSvgPrint(res, burnL > 0 ? land : null)}</div>

<div class="sig"><div>Piloto em comando</div><div>Data / assinatura</div></div>

<footer>
  <span>Limites CG ${CG_FWD_MM}&ndash;${CG_AFT_MM} mm &middot;
  MTOW ${MTOW_TSI} kg &middot; combustível ${FUEL_DENSITY} kg/L</span>
  <span>Envelope aproximado &mdash; consulte o POH.</span>
</footer>
<script>window.addEventListener("load", function () {
  setTimeout(function () { window.print(); }, 350);
});<\/script>
</body></html>`;
}
