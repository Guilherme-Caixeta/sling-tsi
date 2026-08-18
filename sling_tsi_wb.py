#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sling TSi — Peso & Balanço (Weight & Balance)

Replica em Python (Tkinter, sem dependencias externas) da secao "Peso & Balanco"
do planejador em https://slingaircraft.app/tsi/planejador

Calculos e constantes extraidos do proprio bundle da pagina (calcWBResult /
renderEnvelope). Visual replicado a partir do CSS do site (tema escuro #0d1117,
paineis #161b22, acento vermelho #e63329).

Uso:
    python sling_tsi_wb.py            # interface grafica
    python sling_tsi_wb.py --cli      # calculo em texto no terminal
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════
#  CONSTANTES TSi  — espelham as do site (todos os bracos em mm do datum)
# ══════════════════════════════════════════════════════════════════════
FUEL_DENSITY = 0.72          # kg/L
MAX_FUEL_L = 198.0           # L
MAX_BAG_KG = 35.0            # kg
MTOW_TSI = 950.0             # kg

ARM_EMPTY = 1909.0           # mm (default do perfil)
ARM_FUEL = 1800.0            # mm
ARM_FRONT_SEATS = 1902.0     # mm
ARM_REAR_SEATS = 2948.0      # mm
ARM_BAGGAGE = 3288.0         # mm

CG_FWD_MM = 1847.0           # limite dianteiro
CG_AFT_MM = 2043.0           # limite traseiro

MAC_LE_MM = 1602.0           # bordo de ataque da MAC
MAC_LEN_MM = 1339.0          # comprimento da MAC

# Envelope: (x = %MAC, y = kg)
WB_ENV_PTS = [
    (18, 490), (18, 840), (24, 950), (33, 950), (33, 700), (28, 490), (18, 490),
]
CHART_X_MIN, CHART_X_MAX = 16.0, 34.0
CHART_Y_MIN, CHART_Y_MAX = 400.0, 1000.0

# Defaults do perfil da aeronave
DEFAULT_CONS_LH = 28.0       # consumo em cruzeiro (L/h)
DEFAULT_DUR_H = 0.0          # duracao do voo (h)
DEFAULT_EMPTY_KG = 561.0
DEFAULT_EMPTY_CG_MM = 1909.0


# ══════════════════════════════════════════════════════════════════════
#  NUCLEO DE CALCULO
# ══════════════════════════════════════════════════════════════════════
@dataclass
class WBResult:
    total: float          # peso de decolagem (kg)
    cg_mm: float          # CG resultante (mm do datum)
    p_mac: float          # CG em % da MAC
    fuel_kg: float        # combustivel (kg)
    moment: float         # momento total (kg.mm)
    overweight: bool
    cg_oob: bool

    @property
    def ok(self) -> bool:
        return not self.overweight and not self.cg_oob


def calc_landing(res: "WBResult", cons_lh: float, dur_h: float) -> "WBResult":
    """Peso e CG ao fim do voo: queima `cons_lh * dur_h` litros do tanque.

    O braco do combustivel (1800 mm) fica a frente do CG tipico, entao o CG
    anda para tras conforme o tanque esvazia — por isso o limite aft costuma
    ser critico no pouso, nao na decolagem.
    """
    burn_kg = cons_lh * dur_h * FUEL_DENSITY
    fuel_kg = res.fuel_kg - burn_kg
    total = res.total - burn_kg
    moment = res.moment - burn_kg * ARM_FUEL
    cg_mm = moment / total if total > 0 else ARM_EMPTY
    return WBResult(
        total=total,
        cg_mm=cg_mm,
        p_mac=((cg_mm - MAC_LE_MM) / MAC_LEN_MM) * 100.0,
        fuel_kg=fuel_kg,
        moment=moment,
        overweight=total > MTOW_TSI,
        cg_oob=cg_mm < CG_FWD_MM or cg_mm > CG_AFT_MM,
    )


def calc_wb(empty_kg: float = DEFAULT_EMPTY_KG,
            empty_cg_mm: float = DEFAULT_EMPTY_CG_MM,
            pilot: float = 0.0,
            copilot: float = 0.0,
            pax3: float = 0.0,
            pax4: float = 0.0,
            baggage: float = 0.0,
            fuel_l: float = 0.0) -> WBResult:
    """Replica exata de calcWBResult() do planejador."""
    fuel_kg = fuel_l * FUEL_DENSITY
    total = empty_kg + pilot + copilot + pax3 + pax4 + baggage + fuel_kg
    moment = (empty_kg * empty_cg_mm
              + (pilot + copilot) * ARM_FRONT_SEATS
              + (pax3 + pax4) * ARM_REAR_SEATS
              + baggage * ARM_BAGGAGE
              + fuel_kg * ARM_FUEL)
    cg_mm = moment / total if total > 0 else ARM_EMPTY
    p_mac = ((cg_mm - MAC_LE_MM) / MAC_LEN_MM) * 100.0
    return WBResult(
        total=total,
        cg_mm=cg_mm,
        p_mac=p_mac,
        fuel_kg=fuel_kg,
        moment=moment,
        overweight=total > MTOW_TSI,
        cg_oob=cg_mm < CG_FWD_MM or cg_mm > CG_AFT_MM,
    )


# ══════════════════════════════════════════════════════════════════════
#  PERFIS SALVOS
# ══════════════════════════════════════════════════════════════════════
PROFILES_PATH = Path(__file__).with_name("perfis_wb.json")

# campos gravados em cada perfil (ordem = ordem na tela)
PROFILE_FIELDS = ("consumo", "duracao", "empty_kg", "empty_cg", "pilot",
                  "copilot", "pax3", "pax4", "baggage", "fuel")


def load_profiles() -> dict[str, dict[str, str]]:
    """Le perfis_wb.json. Arquivo ausente ou corrompido -> dicionario vazio."""
    try:
        data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def save_profiles(profiles: dict[str, dict[str, str]]) -> None:
    PROFILES_PATH.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
#  FOLHA DE IMPRESSAO — A4 retrato, preto e branco
# ══════════════════════════════════════════════════════════════════════
PRINT_CSS = """
@page { size: A4 portrait; margin: 14mm 13mm; }
* { box-sizing: border-box; }
html, body { background: #fff; color: #000; }
body { font-family: "Segoe UI", Arial, Helvetica, sans-serif; font-size: 9.5pt;
       margin: 0; line-height: 1.35; }
h1 { font-size: 15pt; letter-spacing: .10em; margin: 0; text-transform: uppercase; }
.sub { font-size: 8pt; color: #444; margin-top: 2pt; }
header { border-bottom: 1.5pt solid #000; padding-bottom: 5pt; margin-bottom: 10pt;
         display: flex; align-items: flex-end; justify-content: space-between; }
h2 { font-size: 8pt; letter-spacing: .16em; text-transform: uppercase;
     margin: 12pt 0 5pt; padding-bottom: 2pt; border-bottom: .75pt solid #000; }
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
.chart { text-align: center; margin-top: 6pt; }
footer { margin-top: 10pt; padding-top: 5pt; border-top: .5pt solid #000;
         font-size: 7.5pt; color: #333; display: flex;
         justify-content: space-between; }
.sig { margin-top: 16pt; display: flex; gap: 20pt; font-size: 8pt; color: #333; }
.sig div { flex: 1; border-top: .5pt solid #000; padding-top: 3pt; }
@media print { .noprint { display: none; } }
.noprint { margin: 10pt 0; }
.noprint button { font: inherit; padding: 6pt 14pt; cursor: pointer; }
"""


def envelope_svg(res: "WBResult", land: "WBResult | None" = None,
                 w: int = 520, h: int = 320) -> str:
    """Envelope de CG como SVG monocromático, pronto para impressão."""
    pad_l, pad_r, pad_t, pad_b = 44, 14, 14, 40
    dw, dh = w - pad_l - pad_r, h - pad_t - pad_b

    def tx(v: float) -> float:
        return pad_l + ((v - CHART_X_MIN) / (CHART_X_MAX - CHART_X_MIN)) * dw

    def ty(v: float) -> float:
        return pad_t + dh - ((v - CHART_Y_MIN) / (CHART_Y_MAX - CHART_Y_MIN)) * dh

    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
           'xmlns="http://www.w3.org/2000/svg" font-family="Arial, sans-serif">']
    out.append(f'<rect x="{pad_l}" y="{pad_t}" width="{dw}" height="{dh}" '
               'fill="#fff" stroke="#000" stroke-width=".75"/>')
    for x in (18, 20, 22, 24, 26, 28, 30, 32, 34):
        px = tx(x)
        out.append(f'<line x1="{px:.1f}" y1="{pad_t}" x2="{px:.1f}" '
                   f'y2="{h - pad_b}" stroke="#ccc" stroke-width=".5"/>')
        out.append(f'<text x="{px:.1f}" y="{h - pad_b + 11}" text-anchor="middle" '
                   f'font-size="7.5" fill="#000">{x}%</text>')
    for y in (400, 500, 600, 700, 800, 900, 950, 1000):
        py = ty(y)
        out.append(f'<line x1="{pad_l}" y1="{py:.1f}" x2="{w - pad_r}" '
                   f'y2="{py:.1f}" stroke="#ccc" stroke-width=".5"/>')
        out.append(f'<text x="{pad_l - 4}" y="{py + 2.5:.1f}" text-anchor="end" '
                   f'font-size="7.5" fill="#000">{y}</text>')

    mtow_y = ty(MTOW_TSI)
    out.append(f'<line x1="{pad_l}" y1="{mtow_y:.1f}" x2="{w - pad_r}" '
               f'y2="{mtow_y:.1f}" stroke="#000" stroke-width=".75" '
               'stroke-dasharray="5,3"/>')
    out.append(f'<text x="{w - pad_r - 3}" y="{mtow_y - 3:.1f}" text-anchor="end" '
               f'font-size="7.5" fill="#000">MTOW {MTOW_TSI:.0f} kg</text>')

    pts = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in WB_ENV_PTS)
    out.append(f'<polygon points="{pts}" fill="#e8e8e8" stroke="#000" '
               'stroke-width="1.5"/>')

    if res.total > 0:
        dx, dy = tx(res.p_mac), ty(res.total)
        if land is not None and land.total > 0:
            lx, ly = tx(land.p_mac), ty(land.total)
            out.append(f'<line x1="{dx:.1f}" y1="{dy:.1f}" x2="{lx:.1f}" '
                       f'y2="{ly:.1f}" stroke="#000" stroke-width=".75" '
                       'stroke-dasharray="4,2.5"/>')
            out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4.5" fill="#fff" '
                       'stroke="#000" stroke-width="1.5"/>')
            out.append(f'<text x="{min(max(lx, 52), w - 52):.1f}" '
                       f'y="{ly + 13:.1f}" text-anchor="middle" '
                       f'font-size="8" fill="#000">POU {land.p_mac:.1f}% / '
                       f'{land.total:.0f} kg</text>')
        out.append(f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="4.5" fill="#000"/>')
        out.append(f'<text x="{min(max(dx, 52), w - 52):.1f}" '
                   f'y="{dy - 8:.1f}" text-anchor="middle" '
                   f'font-size="8" fill="#000">DEC {res.p_mac:.1f}% / '
                   f'{res.total:.0f} kg</text>')

    out.append(f'<text x="{pad_l + dw / 2:.1f}" y="{h - 4}" text-anchor="middle" '
               'font-size="8" fill="#000">% MAC</text>')
    out.append(f'<text x="10" y="{pad_t + dh / 2:.1f}" text-anchor="middle" '
               f'font-size="8" fill="#000" transform="rotate(-90 10 '
               f'{pad_t + dh / 2:.1f})">Peso (kg)</text>')
    out.append("</svg>")
    return "".join(out)


def build_print_html(values: dict, res: "WBResult", land: "WBResult",
                     profile_name: str | None = None) -> str:
    """Folha A4 preto-e-branco com a composição de massa e o envelope."""
    esc = html.escape

    def fmt(x: float, casas: int = 1) -> str:
        return f"{x:.{casas}f}"

    def status(r) -> str:
        if r.overweight:
            return '<span class="badge ng">FORA — EXCESSO DE PESO</span>'
        if r.cg_oob:
            return '<span class="badge ng">FORA — CG ALÉM DO LIMITE</span>'
        return '<span class="badge">DENTRO DO ENVELOPE</span>'

    fuel_l = values["fuel"]
    burn_l = values["consumo"] * values["duracao"]
    linhas = [
        ("Peso Vazio", "perfil", values["empty_kg"], values["empty_cg"]),
        ("Piloto", "assento dianteiro", values["pilot"], ARM_FRONT_SEATS),
        ("Copiloto", "assento dianteiro", values["copilot"], ARM_FRONT_SEATS),
        ("Passageiro 3", "assento traseiro", values["pax3"], ARM_REAR_SEATS),
        ("Passageiro 4", "assento traseiro", values["pax4"], ARM_REAR_SEATS),
        ("Bagagem", f"máx. {MAX_BAG_KG:.0f} kg", values["baggage"], ARM_BAGGAGE),
        ("Combustível na Decolagem", f"{fuel_l:.0f} L × {FUEL_DENSITY} kg/L",
         fuel_l * FUEL_DENSITY, ARM_FUEL),
    ]

    corpo = []
    for nome, tag, kg, arm in linhas:
        mom = "&mdash;" if kg == 0 else fmt(kg * arm / 1000, 3)
        corpo.append(
            f"<tr><td>{esc(nome)}<span class='tag'>{esc(tag)}</span></td>"
            f"<td>{fmt(kg)}</td><td>{arm:.0f}</td><td>{mom}</td></tr>")
    corpo.append(
        f"<tr class='total'><td>TOTAL NA DECOLAGEM</td><td>{fmt(res.total)}</td>"
        f"<td>{res.cg_mm:.0f}</td><td>{fmt(res.cg_mm * res.total / 1000)}</td></tr>")
    corpo.append(
        f"<tr><td>Combustível no Pouso<span class='tag'>&minus; {burn_l:.0f} L "
        f"queimados</span></td><td>{fmt(land.fuel_kg)}</td><td>{ARM_FUEL:.0f}</td>"
        f"<td>{fmt(land.fuel_kg * ARM_FUEL / 1000, 3)}</td></tr>")
    corpo.append(
        f"<tr class='total'><td>TOTAL NO POUSO</td><td>{fmt(land.total)}</td>"
        f"<td>{land.cg_mm:.0f}</td>"
        f"<td>{fmt(land.cg_mm * land.total / 1000)}</td></tr>")

    titulo = "Sling TSi &mdash; Peso &amp; Balanço"
    perfil = f"Perfil: {esc(profile_name)}" if profile_name else "Perfil: &mdash;"
    quando = datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Peso e Balanço &mdash; Sling TSi</title>
<style>{PRINT_CSS}</style></head><body>
<div class="noprint"><button onclick="window.print()">Imprimir</button></div>
<header>
  <div><h1>{titulo}</h1><div class="sub">{perfil}</div></div>
  <div class="sub">Emitido em {quando}</div>
</header>

<h2>Aeronave &amp; Performance</h2>
<table><tr>
  <td style="text-align:left">Consumo<br><b>{values['consumo']:g} L/h</b></td>
  <td style="text-align:left">Duração do voo<br><b>{values['duracao']:g} h</b></td>
  <td style="text-align:left">Peso vazio<br><b>{fmt(values['empty_kg'])} kg</b></td>
  <td style="text-align:left">CG vazio<br><b>{values['empty_cg']:.0f} mm</b></td>
</tr></table>

<h2>Composição de Massa</h2>
<table>
<thead><tr><th>Item</th><th>Peso (kg)</th><th>Braço (mm)</th>
<th>Momento (kg&middot;m)</th></tr></thead>
<tbody>{''.join(corpo)}</tbody></table>

<div class="grid2">
  <div class="card"><div class="k">Peso na Decolagem</div>
    <div class="v">{fmt(res.total)} kg</div>
    <div class="d">MTOW {MTOW_TSI:.0f} kg</div></div>
  <div class="card"><div class="k">Na Decolagem</div>{status(res)}
    <div class="d">{res.cg_mm:.0f} mm &middot; {res.p_mac:.1f} %MAC</div></div>
  <div class="card"><div class="k">No Pouso</div>{status(land)}
    <div class="d">{land.cg_mm:.0f} mm &middot; {land.p_mac:.1f} %MAC</div></div>
</div>

<h2>Envelope de CG &mdash; Peso vs CG %MAC</h2>
<div class="chart">{envelope_svg(res, land if burn_l > 0 else None)}</div>

<div class="sig"><div>Piloto em comando</div><div>Data / assinatura</div></div>

<footer>
  <span>Limites CG {CG_FWD_MM:.0f}&ndash;{CG_AFT_MM:.0f} mm &middot;
  MTOW {MTOW_TSI:.0f} kg &middot; combustível {FUEL_DENSITY} kg/L</span>
  <span>Envelope aproximado &mdash; consulte o POH.</span>
</footer>
<script>window.addEventListener("load", function () {{
  setTimeout(function () {{ window.print(); }}, 350);
}});</script>
</body></html>"""


# ══════════════════════════════════════════════════════════════════════
#  PALETA / TEMA  (do CSS do site)
# ══════════════════════════════════════════════════════════════════════
C_BG = "#0d1117"
C_PANEL = "#161b22"
C_PANEL2 = "#1b212b"
C_LINE = "#2a313c"
C_TEXT = "#e6e9ef"
C_MUTED = "#8b93a3"
C_RED = "#e63329"
C_RED_DIM = "#b3271f"
C_FIELD = "#0f141b"
C_OK = "#2ea043"

C_FUEL_RED = "#d42020"        # acento do bloco de combustivel / envelope
C_PLOT_BG = "#111111"
C_GRID = "#2a313c"
C_TICK = "#6b7280"
C_AXIS_LBL = "#555555"
C_DOT_OK = "#22c55e"
C_DOT_NG = "#ef4444"
C_ENV_FILL = "#251313"        # rgba(212,32,32,.10) sobre #111
C_FUEL_BOX_BG = "#1a1116"     # rgba(212,32,32,.06) sobre o fundo
C_NOTE_BG = "#1b1216"         # rgba(230,51,41,.08) sobre o fundo
C_BADGE_OK_BG = "#182b1d"
C_BADGE_NG_BG = "#2b1614"


def _spaced(text: str, gap: str = " ") -> str:
    """Emula o letter-spacing dos titulos do site."""
    return gap.join(text)


# ══════════════════════════════════════════════════════════════════════
#  INTERFACE
# ══════════════════════════════════════════════════════════════════════
def run_gui(prefill: dict[str, float] | None = None) -> None:
    import tkinter as tk
    from tkinter import font as tkfont, messagebox

    prefill = prefill or {}

    root = tk.Tk()
    root.title("Sling TSi · Peso & Balanço")
    root.configure(bg=C_BG)
    root.minsize(820, 620)
    screen_h = root.winfo_screenheight()
    root.geometry(f"880x{min(1020, max(640, screen_h - 90))}+80+20")

    available = set(tkfont.families())

    def pick(*candidates: str) -> str:
        for name in candidates:
            if name in available:
                return name
        return candidates[-1]

    UI = pick("Saira", "Segoe UI", "Inter", "Helvetica")
    MONO = pick("JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New")

    f_h1 = (UI, 13, "bold")
    f_h2 = (UI, 8, "bold")
    f_lbl = (UI, 9)
    f_tag = (UI, 7)
    f_th = (UI, 7, "bold")
    f_num = (MONO, 10)
    f_num_b = (MONO, 10, "bold")
    f_big = (MONO, 17, "bold")
    f_badge = (UI, 9, "bold")
    f_hint = (UI, 8)

    # ── scroll container ────────────────────────────────────────────
    outer = tk.Canvas(root, bg=C_BG, highlightthickness=0)
    vbar = tk.Scrollbar(root, orient="vertical", command=outer.yview,
                        bg=C_PANEL, troughcolor=C_BG, borderwidth=0,
                        activebackground=C_LINE, highlightthickness=0)
    outer.configure(yscrollcommand=vbar.set)
    vbar.pack(side="right", fill="y")
    outer.pack(side="left", fill="both", expand=True)

    page = tk.Frame(outer, bg=C_BG)
    win = outer.create_window((0, 0), window=page, anchor="nw")

    def _on_page_config(_evt=None):
        outer.configure(scrollregion=outer.bbox("all"))

    def _on_outer_config(evt):
        outer.itemconfigure(win, width=evt.width)

    page.bind("<Configure>", _on_page_config)
    outer.bind("<Configure>", _on_outer_config)
    outer.bind_all("<MouseWheel>", lambda e: outer.yview_scroll(int(-e.delta / 120), "units"))

    wrap = tk.Frame(page, bg=C_BG)
    wrap.pack(fill="both", expand=True, padx=16, pady=14)

    def section(parent, title: str | None, bg: str = C_PANEL,
                border: str = C_LINE) -> tk.Frame:
        """Equivalente ao .sec do site: painel arredondado com titulo."""
        shell = tk.Frame(parent, bg=border, highlightthickness=0)
        shell.pack(fill="x", pady=(0, 14))
        box = tk.Frame(shell, bg=bg)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(box, bg=bg)
        inner.pack(fill="both", expand=True, padx=14, pady=13)
        if title:
            head = tk.Frame(inner, bg=bg)
            head.pack(fill="x", pady=(0, 11))
            tk.Frame(head, bg=C_RED, width=3, height=13).pack(side="left", padx=(0, 8))
            tk.Label(head, text=_spaced(title.upper()), font=f_h2, fg=C_MUTED,
                     bg=bg).pack(side="left")
        return inner

    # ── titlebar ────────────────────────────────────────────────────
    bar = tk.Frame(wrap, bg=C_BG)
    bar.pack(fill="x", pady=(4, 16))
    tk.Label(bar, text=_spaced("PESO & BALANÇO", " "), font=f_h1,
             fg=C_TEXT, bg=C_BG).pack(side="left")
    tk.Label(bar, text="—", font=f_h1, fg=C_RED, bg=C_BG).pack(side="left", padx=8)

    prof_shell = tk.Frame(bar, bg=C_LINE)
    prof_shell.pack(side="right")
    prof_mb = tk.Menubutton(prof_shell, text="Ler Perfis  ▾", font=(UI, 9),
                            fg=C_TEXT, bg=C_PANEL2, activebackground=C_LINE,
                            activeforeground=C_TEXT, relief="flat", padx=12,
                            pady=6, cursor="hand2")
    prof_mb.pack(padx=1, pady=1)
    prof_menu = tk.Menu(prof_mb, tearoff=0, bg=C_PANEL2, fg=C_TEXT,
                        activebackground=C_RED, activeforeground="#ffffff",
                        bd=0, font=(UI, 9))
    prof_mb.configure(menu=prof_menu)
    tk.Label(bar, text=_spaced("PERFIS SALVOS"), font=(UI, 8, "bold"),
             fg=C_MUTED, bg=C_BG).pack(side="right", padx=(0, 10))

    # ── state ───────────────────────────────────────────────────────
    v_cons = tk.StringVar(value=f"{DEFAULT_CONS_LH:g}")
    v_dur = tk.StringVar(value=f"{DEFAULT_DUR_H:g}")
    v_empty_kg = tk.StringVar(value=f"{DEFAULT_EMPTY_KG:g}")
    v_empty_cg = tk.StringVar(value=f"{DEFAULT_EMPTY_CG_MM:g}")
    v_pilot = tk.StringVar(value="")
    v_copil = tk.StringVar(value="")
    v_pax3 = tk.StringVar(value="")
    v_pax4 = tk.StringVar(value="")
    v_bag = tk.StringVar(value="")
    v_fuel = tk.StringVar(value="")

    FIELD_VARS = {
        "consumo": v_cons, "duracao": v_dur,
        "empty_kg": v_empty_kg, "empty_cg": v_empty_cg,
        "pilot": v_pilot, "copilot": v_copil,
        "pax3": v_pax3, "pax4": v_pax4,
        "baggage": v_bag, "fuel": v_fuel,
    }

    def ask_text(title: str, prompt: str, initial: str = "") -> str | None:
        """Caixa modal no tema da pagina; devolve None se cancelado."""
        dlg = tk.Toplevel(root, bg=C_PANEL)
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.transient(root)
        out: dict[str, str | None] = {"v": None}

        body = tk.Frame(dlg, bg=C_PANEL)
        body.pack(padx=18, pady=16)
        tk.Label(body, text=prompt, font=f_lbl, fg=C_MUTED, bg=C_PANEL,
                 anchor="w").pack(fill="x", pady=(0, 6))
        var = tk.StringVar(value=initial)
        ent = tk.Entry(body, textvariable=var, font=f_num, fg=C_TEXT, bg=C_FIELD,
                       insertbackground=C_RED, relief="flat", width=30,
                       highlightthickness=1, highlightbackground=C_LINE,
                       highlightcolor=C_RED)
        ent.pack(fill="x", ipady=5)

        def ok(*_a):
            out["v"] = var.get().strip()
            dlg.destroy()

        btns = tk.Frame(body, bg=C_PANEL)
        btns.pack(fill="x", pady=(14, 0))
        tk.Button(btns, text="Cancelar", font=(UI, 9), fg=C_MUTED, bg=C_PANEL2,
                  activebackground=C_LINE, activeforeground=C_TEXT, relief="flat",
                  padx=12, pady=5, cursor="hand2",
                  command=dlg.destroy).pack(side="right")
        tk.Button(btns, text="Salvar", font=(UI, 9, "bold"), fg="#ffffff",
                  bg=C_RED, activebackground=C_RED_DIM, activeforeground="#ffffff",
                  relief="flat", padx=14, pady=5, cursor="hand2",
                  command=ok).pack(side="right", padx=(0, 8))

        dlg.bind("<Return>", ok)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.update_idletasks()
        dlg.geometry("+%d+%d" % (
            root.winfo_rootx() + (root.winfo_width() - dlg.winfo_width()) // 2,
            root.winfo_rooty() + 140))
        ent.focus_set()
        ent.select_range(0, "end")
        dlg.grab_set()
        root.wait_window(dlg)
        return out["v"]

    active_profile: dict[str, str | None] = {"name": None}

    def set_active(name: str | None) -> None:
        active_profile["name"] = name
        prof_mb.configure(text="Ler Perfis  ▾" if name is None
                          else f"{name}  ▾")

    def apply_profile(name: str) -> None:
        data = load_profiles().get(name)
        if not data:
            return
        for key in PROFILE_FIELDS:
            FIELD_VARS[key].set(str(data.get(key, "")))
        set_active(name)
        render()

    def rebuild_profile_menu() -> None:
        prof_menu.delete(0, "end")
        names = sorted(load_profiles(), key=str.lower)
        if not names:
            prof_menu.add_command(label="(nenhum perfil salvo)", state="disabled")
            return
        for name in names:
            prof_menu.add_command(label=name,
                                  command=lambda n=name: apply_profile(n))

    prof_menu.configure(postcommand=rebuild_profile_menu)
    rebuild_profile_menu()

    def save_profile() -> None:
        name = ask_text("Salvar Perfil", "Nome do perfil:")
        if not name:
            return
        profiles = load_profiles()
        if name in profiles and not messagebox.askyesno(
                "Salvar Perfil",
                f"Já existe um perfil chamado “{name}”.\nSubstituir?",
                parent=root):
            return
        profiles[name] = {k: FIELD_VARS[k].get().strip() for k in PROFILE_FIELDS}
        try:
            save_profiles(profiles)
        except OSError as exc:
            messagebox.showerror("Salvar Perfil",
                                 f"Não foi possível gravar:\n{exc}", parent=root)
            return
        set_active(name)
        rebuild_profile_menu()
        lbl_save_msg.configure(text=f"✓ Perfil “{name}” salvo")
        root.after(2500, lambda: lbl_save_msg.configure(text=""))

    def print_sheet() -> None:
        """Gera a folha A4 e abre o diálogo de impressão do navegador."""
        values = {k: num(FIELD_VARS[k],
                         DEFAULT_EMPTY_KG if k == "empty_kg" else
                         DEFAULT_EMPTY_CG_MM if k == "empty_cg" else 0.0)
                  for k in PROFILE_FIELDS}
        res = calc_wb(values["empty_kg"], values["empty_cg"], values["pilot"],
                      values["copilot"], values["pax3"], values["pax4"],
                      values["baggage"], values["fuel"])
        land = calc_landing(res, values["consumo"], values["duracao"])
        page = Path(tempfile.gettempdir()) / "sling_tsi_wb_impressao.html"
        try:
            page.write_text(
                build_print_html(values, res, land, active_profile["name"]),
                encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Imprimir",
                                 "Não foi possível gerar a folha:" + chr(10)
                                 + str(exc), parent=root)
            return
        webbrowser.open(page.as_uri())
        lbl_save_msg.configure(text="✓ Folha A4 aberta no navegador")
        root.after(3500, lambda: lbl_save_msg.configure(text=""))

    def manage_profiles() -> None:
        win = tk.Toplevel(root, bg=C_BG)
        win.title("Gerenciar Perfis")
        win.transient(root)
        win.minsize(520, 280)

        head = tk.Frame(win, bg=C_BG)
        head.pack(fill="x", padx=16, pady=(14, 10))
        tk.Frame(head, bg=C_RED, width=3, height=13).pack(side="left", padx=(0, 8))
        tk.Label(head, text=_spaced("PERFIS SALVOS"), font=f_h2, fg=C_MUTED,
                 bg=C_BG).pack(side="left")

        body = tk.Frame(win, bg=C_BG)
        body.pack(fill="both", expand=True, padx=16)
        cv = tk.Canvas(body, bg=C_BG, highlightthickness=0, height=260)
        sb = tk.Scrollbar(body, orient="vertical", command=cv.yview, bg=C_PANEL,
                          troughcolor=C_BG, borderwidth=0,
                          activebackground=C_LINE, highlightthickness=0)
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        rows = tk.Frame(cv, bg=C_BG)
        rows_win = cv.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>",
                  lambda _e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(rows_win, width=e.width))
        cv.bind("<MouseWheel>",
                lambda e: cv.yview_scroll(int(-e.delta / 120), "units"))

        foot = tk.Frame(win, bg=C_BG)
        foot.pack(fill="x", padx=16, pady=(8, 14))
        status = tk.Label(foot, text="", font=f_hint, fg=C_OK, bg=C_BG)
        status.pack(side="left")
        tk.Button(foot, text="Fechar", font=(UI, 9), fg=C_MUTED, bg=C_PANEL2,
                  activebackground=C_LINE, activeforeground=C_TEXT, relief="flat",
                  padx=14, pady=6, cursor="hand2",
                  command=win.destroy).pack(side="right")

        def fit() -> None:
            """Altura da lista acompanha o conteudo; rolagem so quando precisa."""
            rows.update_idletasks()
            need = rows.winfo_reqheight()
            cv.configure(height=min(360, max(60, need)),
                         scrollregion=cv.bbox("all"))
            if need > 360:
                sb.pack(side="right", fill="y")
            else:
                sb.pack_forget()

        def flash(msg: str, ok: bool = True) -> None:
            status.configure(text=msg, fg=C_OK if ok else C_RED)
            win.after(3000, lambda: status.configure(text=""))

        def commit(profiles: dict) -> bool:
            try:
                save_profiles(profiles)
            except OSError as exc:
                messagebox.showerror(
                    "Gerenciar Perfis",
                    "Não foi possível gravar:" + chr(10) + str(exc),
                    parent=win)
                return False
            rebuild_profile_menu()
            refresh()
            return True

        def do_rename(old: str, new: str) -> None:
            new = new.strip()
            if not new:
                flash("O nome não pode ficar vazio.", ok=False)
                return
            if new == old:
                flash("Nome inalterado.")
                return
            profiles = load_profiles()
            if old not in profiles:
                refresh()
                return
            if new in profiles and not messagebox.askyesno(
                    "Gerenciar Perfis",
                    "Já existe um perfil chamado “" + new + "”."
                    + chr(10) + "Substituir?", parent=win):
                return
            renamed = {}
            for k, v in profiles.items():
                if k == old:
                    renamed[new] = v
                elif k != new:
                    renamed[k] = v
            if commit(renamed):
                if active_profile["name"] == old:
                    set_active(new)
                flash("“" + old + "” renomeado para “" + new
                      + "”.")

        def do_delete(name: str) -> None:
            if not messagebox.askyesno(
                    "Gerenciar Perfis",
                    "Excluir o perfil “" + name + "”?" + chr(10)
                    + "Esta ação não pode ser desfeita.",
                    parent=win):
                return
            profiles = load_profiles()
            profiles.pop(name, None)
            if commit(profiles):
                if active_profile["name"] == name:
                    set_active(None)
                flash("“" + name + "” excluído.")

        def refresh() -> None:
            for w in rows.winfo_children():
                w.destroy()
            profiles = load_profiles()
            if not profiles:
                tk.Label(rows, text="Nenhum perfil salvo ainda.", font=f_lbl,
                         fg=C_MUTED, bg=C_BG).pack(anchor="w", pady=8)
                fit()
                return
            for name in sorted(profiles, key=str.lower):
                shell = tk.Frame(rows, bg=C_LINE)
                shell.pack(fill="x", pady=(0, 6))
                inner = tk.Frame(shell, bg=C_PANEL)
                inner.pack(fill="x", padx=1, pady=1)
                var = tk.StringVar(value=name)
                tk.Button(inner, text="Excluir", font=(UI, 9), fg=C_RED,
                          bg=C_PANEL2, activebackground=C_BADGE_NG_BG,
                          activeforeground=C_RED, relief="flat", padx=12, pady=4,
                          cursor="hand2",
                          command=lambda n=name: do_delete(n)).pack(
                    side="right", padx=(0, 8), pady=7)
                tk.Button(inner, text="Salvar", font=(UI, 9, "bold"), fg="#ffffff",
                          bg=C_RED, activebackground=C_RED_DIM,
                          activeforeground="#ffffff", relief="flat", padx=12,
                          pady=4, cursor="hand2",
                          command=lambda n=name, v=var: do_rename(n, v.get())).pack(
                    side="right", padx=6, pady=7)
                ent = tk.Entry(inner, textvariable=var, font=f_lbl, fg=C_TEXT,
                               bg=C_FIELD, insertbackground=C_RED, relief="flat",
                               highlightthickness=1, highlightbackground=C_LINE,
                               highlightcolor=C_RED)
                ent.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=7,
                         ipady=3)
                ent.bind("<Return>",
                         lambda _e, n=name, v=var: do_rename(n, v.get()))
            fit()

        refresh()
        win.update_idletasks()
        win.geometry("+%d+%d" % (
            root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2,
            root.winfo_rooty() + 120))
        win.bind("<Escape>", lambda _e: win.destroy())

    def num(var: tk.StringVar, default: float = 0.0) -> float:
        """Equivalente a parseFloat(v)||default do JS."""
        try:
            val = float(str(var.get()).replace(",", "."))
        except (TypeError, ValueError):
            return default
        return val if val else default

    # ── Aeronave & Performance ──────────────────────────────────────
    sec_ac = section(wrap, "Aeronave & Performance")
    grid_ac = tk.Frame(sec_ac, bg=C_PANEL)
    grid_ac.pack(fill="x")
    for i in range(4):
        grid_ac.columnconfigure(i, weight=1, uniform="ac")

    def field(parent, col: int, label: str, var: tk.StringVar) -> tk.Entry:
        cell = tk.Frame(parent, bg=C_PANEL)
        cell.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 5, 0))
        tk.Label(cell, text=label, font=f_lbl, fg=C_MUTED, bg=C_PANEL,
                 anchor="w").pack(fill="x", pady=(0, 4))
        ent = tk.Entry(cell, textvariable=var, font=f_num, fg=C_TEXT, bg=C_FIELD,
                       insertbackground=C_RED, relief="flat", highlightthickness=1,
                       highlightbackground=C_LINE, highlightcolor=C_RED)
        ent.pack(fill="x", ipady=5)
        return ent

    field(grid_ac, 0, "Consumo de Combustível (L/h)", v_cons)
    field(grid_ac, 1, "Duração Vôo (h)", v_dur)
    field(grid_ac, 2, "Peso Vazio (kg)", v_empty_kg)
    field(grid_ac, 3, "CG Vazio (mm)", v_empty_cg)

    # ── Combustivel na decolagem (slider) ───────────────────────────
    fuel_sec = section(wrap, None, bg=C_FUEL_BOX_BG, border="#3a1c1e")
    head_fuel = tk.Frame(fuel_sec, bg=C_FUEL_BOX_BG)
    head_fuel.pack(fill="x", pady=(0, 8))
    tk.Label(head_fuel, text=_spaced("COMBUSTÍVEL NA DECOLAGEM"), font=f_h2,
             fg=C_MUTED, bg=C_FUEL_BOX_BG).pack(side="left")
    lbl_fuel_kg = tk.Label(head_fuel, text="· 0.0 kg", font=(MONO, 8),
                           fg=C_MUTED, bg=C_FUEL_BOX_BG)
    lbl_fuel_kg.pack(side="right")
    lbl_fuel_l = tk.Label(head_fuel, text="0 L", font=(MONO, 11, "bold"),
                          fg=C_FUEL_RED, bg=C_FUEL_BOX_BG)
    lbl_fuel_l.pack(side="right", padx=(0, 8))

    _sync_guard = {"on": False}

    # Slider desenhado em canvas para reproduzir o accent-color vermelho do site
    SL_H, KNOB = 20, 7
    slider = tk.Canvas(fuel_sec, height=SL_H, bg=C_FUEL_BOX_BG,
                       highlightthickness=0, cursor="hand2")
    slider.pack(fill="x")
    _slider_val = {"v": 0.0}

    def draw_slider() -> None:
        w = slider.winfo_width()
        if w <= 1:
            return
        x0, x1 = KNOB, w - KNOB
        cy = SL_H / 2
        frac = _slider_val["v"] / MAX_FUEL_L
        kx = x0 + frac * (x1 - x0)
        slider.delete("all")
        slider.create_rectangle(x0, cy - 3, x1, cy + 3, fill=C_FIELD,
                                outline=C_LINE)
        if kx > x0:
            slider.create_rectangle(x0, cy - 3, kx, cy + 3, fill=C_FUEL_RED,
                                    outline="")
        slider.create_oval(kx - KNOB, cy - KNOB, kx + KNOB, cy + KNOB,
                           fill=C_FUEL_RED, outline="#ffffff")

    def slider_from_event(evt) -> None:
        w = slider.winfo_width()
        x0, x1 = KNOB, w - KNOB
        frac = min(1.0, max(0.0, (evt.x - x0) / max(1, x1 - x0)))
        litres = int(round(frac * MAX_FUEL_L))
        _slider_val["v"] = float(litres)
        _sync_guard["on"] = True
        v_fuel.set("" if litres == 0 else str(litres))
        _sync_guard["on"] = False
        render()

    slider.bind("<Button-1>", slider_from_event)
    slider.bind("<B1-Motion>", slider_from_event)
    slider.bind("<Configure>", lambda _e: draw_slider())

    scale_row = tk.Frame(fuel_sec, bg=C_FUEL_BOX_BG)
    scale_row.pack(fill="x", pady=(3, 0))
    tk.Label(scale_row, text="0 L", font=f_tag, fg=C_MUTED,
             bg=C_FUEL_BOX_BG).pack(side="left")
    tk.Label(scale_row, text=f"{MAX_FUEL_L:.0f} L · máx.", font=f_tag,
             fg=C_MUTED, bg=C_FUEL_BOX_BG).pack(side="right")

    # ── Composicao de massa (tabela) ────────────────────────────────
    sec_mass = section(wrap, "Composição de Massa")
    table = tk.Frame(sec_mass, bg=C_PANEL)
    table.pack(fill="x")
    table.columnconfigure(0, weight=1)
    for c in (1, 2, 3):
        table.columnconfigure(c, minsize=110)

    for c, head in enumerate(("Item", "Peso (kg)", "Braço (mm)",
                              "Momento (kg·m)")):
        tk.Label(table, text=_spaced(head.upper()), font=f_th, fg=C_MUTED,
                 bg=C_PANEL, anchor="w" if c == 0 else "e").grid(
            row=0, column=c, sticky="ew", padx=8, pady=(0, 7))

    def rule(row: int) -> None:
        tk.Frame(table, bg=C_LINE, height=1).grid(row=row, column=0, columnspan=4,
                                                  sticky="ew")

    mom_labels: dict[str, tk.Label] = {}
    empty_kg_lbl = {}
    empty_arm_lbl = {}

    ROWS = [
        ("vazio", "Peso Vazio", "← perfil", None, None),
        ("pilot", "Piloto", "assento dianteiro", v_pilot, ARM_FRONT_SEATS),
        ("copil", "Copiloto", "assento dianteiro", v_copil, ARM_FRONT_SEATS),
        ("pax3", "Passageiro 3", "assento traseiro", v_pax3, ARM_REAR_SEATS),
        ("pax4", "Passageiro 4", "assento traseiro", v_pax4, ARM_REAR_SEATS),
        ("bag", "Bagagem", f"máx. {MAX_BAG_KG:.0f} kg", v_bag, ARM_BAGGAGE),
        ("fuel", "Combustível na Decolagem",
         f"máx. {MAX_FUEL_L:.0f} L · ×{FUEL_DENSITY} kg/L",
         v_fuel, ARM_FUEL),
    ]

    r = 1
    for key, name, tag, var, arm in ROWS:
        rule(r)
        r += 1
        lbl_cell = tk.Frame(table, bg=C_PANEL)
        lbl_cell.grid(row=r, column=0, sticky="w", padx=8, pady=6)
        tk.Label(lbl_cell, text=name, font=f_lbl, fg=C_TEXT, bg=C_PANEL).pack(side="left")
        tk.Label(lbl_cell, text=tag, font=f_tag, fg=C_MUTED,
                 bg=C_PANEL).pack(side="left", padx=(5, 0))

        if var is None:  # peso vazio: somente leitura, vem do perfil
            lb = tk.Label(table, text="505.0", font=f_num, fg=C_MUTED, bg=C_PANEL,
                          anchor="e")
            lb.grid(row=r, column=1, sticky="e", padx=8)
            empty_kg_lbl["l"] = lb
            la = tk.Label(table, text="1.873", font=f_num, fg=C_MUTED, bg=C_PANEL,
                          anchor="e")
            la.grid(row=r, column=2, sticky="e", padx=8)
            empty_arm_lbl["l"] = la
        else:
            ent = tk.Entry(table, textvariable=var, font=f_num, fg=C_TEXT,
                           bg=C_FIELD, insertbackground=C_RED, relief="flat",
                           justify="right", highlightthickness=1,
                           highlightbackground=C_LINE, highlightcolor=C_RED,
                           width=9)
            ent.grid(row=r, column=1, sticky="e", padx=8, pady=4, ipady=3)
            tk.Label(table, text=f"{arm:.0f}", font=f_num, fg=C_TEXT, bg=C_PANEL,
                     anchor="e").grid(row=r, column=2, sticky="e", padx=8)

        mom = tk.Label(table, text="—", font=f_num, fg=C_TEXT, bg=C_PANEL,
                       anchor="e")
        mom.grid(row=r, column=3, sticky="e", padx=8)
        mom_labels[key] = mom
        r += 1

    rule(r)
    r += 1
    total_bg = "#1c222b"
    tk.Label(table, text="TOTAL NA DECOLAGEM", font=(UI, 9, "bold"), fg=C_TEXT,
             bg=total_bg, anchor="w").grid(row=r, column=0, sticky="ew", padx=8,
                                           ipady=6)
    lbl_total_kg = tk.Label(table, text="— kg", font=f_num_b, fg=C_TEXT,
                            bg=total_bg, anchor="e")
    lbl_total_kg.grid(row=r, column=1, sticky="ew", padx=8, ipady=6)
    lbl_total_arm = tk.Label(table, text="—", font=f_num_b, fg=C_TEXT, bg=total_bg,
                             anchor="e")
    lbl_total_arm.grid(row=r, column=2, sticky="ew", padx=8, ipady=6)
    lbl_total_mom = tk.Label(table, text="—", font=f_num_b, fg=C_TEXT,
                             bg=total_bg, anchor="e")
    lbl_total_mom.grid(row=r, column=3, sticky="ew", padx=8, ipady=6)

    # ── combustivel restante e total no pouso ───────────────────────
    r += 1
    rule(r)
    r += 1
    land_cell = tk.Frame(table, bg=C_PANEL)
    land_cell.grid(row=r, column=0, sticky="w", padx=8, pady=6)
    tk.Label(land_cell, text="Combustível no Pouso", font=f_lbl, fg=C_TEXT,
             bg=C_PANEL).pack(side="left")
    lbl_burn_tag = tk.Label(land_cell, text="", font=f_tag, fg=C_MUTED, bg=C_PANEL)
    lbl_burn_tag.pack(side="left", padx=(5, 0))
    lbl_land_kg = tk.Label(table, text="—", font=f_num, fg=C_TEXT, bg=C_PANEL,
                           anchor="e")
    lbl_land_kg.grid(row=r, column=1, sticky="e", padx=8)
    tk.Label(table, text=f"{ARM_FUEL:.0f}", font=f_num, fg=C_TEXT, bg=C_PANEL,
             anchor="e").grid(row=r, column=2, sticky="e", padx=8)
    lbl_land_mom = tk.Label(table, text="—", font=f_num, fg=C_TEXT, bg=C_PANEL,
                            anchor="e")
    lbl_land_mom.grid(row=r, column=3, sticky="e", padx=8)

    r += 1
    rule(r)
    r += 1
    tk.Label(table, text="TOTAL NO POUSO", font=(UI, 9, "bold"), fg=C_TEXT,
             bg=total_bg, anchor="w").grid(row=r, column=0, sticky="ew", padx=8,
                                           ipady=6)
    lbl_ltot_kg = tk.Label(table, text="— kg", font=f_num_b, fg=C_TEXT,
                           bg=total_bg, anchor="e")
    lbl_ltot_kg.grid(row=r, column=1, sticky="ew", padx=8, ipady=6)
    lbl_ltot_arm = tk.Label(table, text="—", font=f_num_b, fg=C_TEXT, bg=total_bg,
                            anchor="e")
    lbl_ltot_arm.grid(row=r, column=2, sticky="ew", padx=8, ipady=6)
    lbl_ltot_mom = tk.Label(table, text="—", font=f_num_b, fg=C_TEXT, bg=total_bg,
                            anchor="e")
    lbl_ltot_mom.grid(row=r, column=3, sticky="ew", padx=8, ipady=6)

    # ── barra de resultado ──────────────────────────────────────────
    res_bar = tk.Frame(sec_mass, bg=C_PANEL)
    res_bar.pack(fill="x", pady=(14, 0))
    for i in range(3):
        res_bar.columnconfigure(i, weight=1, uniform="res")

    res_bar.rowconfigure(0, weight=1)

    def res_cell(col: int, caption: str):
        shell = tk.Frame(res_bar, bg=C_LINE)
        shell.grid(row=0, column=col, sticky="nsew",
                   padx=(0 if col == 0 else 5, 0))
        box = tk.Frame(shell, bg=C_PANEL2)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(box, text=_spaced(caption.upper()), font=(UI, 7, "bold"),
                 fg=C_MUTED, bg=C_PANEL2).pack(pady=(9, 4))
        val = tk.Label(box, text="—", font=f_big, fg=C_TEXT, bg=C_PANEL2)
        val.pack(pady=(0, 10))
        return val

    lbl_out_weight = res_cell(0, "Peso na Decolagem")

    def badge_cell(col: int, caption: str):
        shell = tk.Frame(res_bar, bg=C_LINE)
        shell.grid(row=0, column=col, sticky="nsew", padx=(5, 0))
        box = tk.Frame(shell, bg=C_PANEL2)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(box, text=_spaced(caption.upper()), font=(UI, 7, "bold"),
                 fg=C_MUTED, bg=C_PANEL2).pack(pady=(9, 4))
        badge = tk.Label(box, text="—", font=f_badge, fg=C_MUTED, bg=C_PANEL2,
                         padx=10, pady=3)
        badge.pack()
        detail = tk.Label(box, text="", font=(MONO, 8), fg=C_MUTED, bg=C_PANEL2)
        detail.pack(pady=(4, 9))
        return badge, detail

    lbl_badge, lbl_badge_det = badge_cell(1, "Na Decolagem")
    lbl_lbadge, lbl_lbadge_det = badge_cell(2, "No Pouso")

    def set_badge(badge, detail, r) -> None:
        """Pinta um badge a partir de um WBResult."""
        if r.total <= 0:
            badge.configure(text="—", fg=C_MUTED, bg=C_PANEL2)
            detail.configure(text="")
            return
        if r.overweight:
            badge.configure(text="⚠ EXCESSO DE PESO", fg=C_RED, bg=C_BADGE_NG_BG)
        elif r.cg_oob:
            badge.configure(text="⚠ CG FORA DOS LIMITES", fg=C_RED,
                            bg=C_BADGE_NG_BG)
        else:
            badge.configure(text="✓ Dentro do envelope", fg=C_OK,
                            bg=C_BADGE_OK_BG)
        detail.configure(text=f"{r.total:.1f} kg · {r.cg_mm:.0f} mm · "
                              f"{r.p_mac:.1f} %MAC")

    # ── Envelope de CG ──────────────────────────────────────────────
    sec_env = section(wrap, "Envelope de CG — Peso vs CG%MAC")
    CW, CH = 630, 400
    chart = tk.Canvas(sec_env, width=CW, height=CH, bg=C_PANEL,
                      highlightthickness=0)
    chart.pack()
    tk.Label(sec_env, text="Região vermelha = envelope de operação. "
                           "O ponto vermelho indica CG fora do limite. Envelope TSi "
                           "aproximado — consulte o POH para limites exatos.",
             font=f_hint, fg=C_MUTED, bg=C_PANEL, wraplength=CW,
             justify="left", anchor="w").pack(fill="x", pady=(10, 0))

    # ── salvar perfil ───────────────────────────────────────────────
    save_row = tk.Frame(wrap, bg=C_BG)
    save_row.pack(fill="x", pady=(0, 6))
    tk.Button(save_row, text="Salvar Perfil", font=(UI, 9, "bold"), fg="#ffffff",
              bg=C_RED, activebackground=C_RED_DIM, activeforeground="#ffffff",
              relief="flat", padx=18, pady=8, cursor="hand2",
              command=lambda: save_profile()).pack(side="left")
    tk.Button(save_row, text="Gerenciar Perfis", font=(UI, 9), fg=C_TEXT,
              bg=C_PANEL2, activebackground=C_LINE, activeforeground=C_TEXT,
              relief="flat", padx=16, pady=8, cursor="hand2",
              command=lambda: manage_profiles()).pack(side="left", padx=(8, 0))
    tk.Button(save_row, text="Imprimir (A4 P&B)", font=(UI, 9), fg=C_TEXT,
              bg=C_PANEL2, activebackground=C_LINE, activeforeground=C_TEXT,
              relief="flat", padx=16, pady=8, cursor="hand2",
              command=lambda: print_sheet()).pack(side="left", padx=(8, 0))
    lbl_save_msg = tk.Label(save_row, text="", font=f_hint, fg=C_OK, bg=C_BG)
    lbl_save_msg.pack(side="left", padx=12)

    PAD_L, PAD_R, PAD_T, PAD_B = 46, 18, 18, 50
    DW = CW - PAD_L - PAD_R
    DH = CH - PAD_T - PAD_B

    def to_x(v: float) -> float:
        return PAD_L + ((v - CHART_X_MIN) / (CHART_X_MAX - CHART_X_MIN)) * DW

    def to_y(v: float) -> float:
        return PAD_T + DH - ((v - CHART_Y_MIN) / (CHART_Y_MAX - CHART_Y_MIN)) * DH

    def draw_envelope(res: WBResult, land: WBResult | None = None) -> None:
        chart.delete("all")
        chart.create_rectangle(PAD_L, PAD_T, CW - PAD_R, CH - PAD_B,
                               fill=C_PLOT_BG, outline="")

        for x in (18, 20, 22, 24, 26, 28, 30, 32, 34):
            px = to_x(x)
            chart.create_line(px, PAD_T, px, CH - PAD_B, fill=C_GRID)
            chart.create_text(px, CH - PAD_B + 9, text=f"{x}%", fill=C_TICK,
                              font=(UI, 7), anchor="n")
        for y in (400, 500, 600, 700, 800, 900, 950, 1000):
            py = to_y(y)
            chart.create_line(PAD_L, py, CW - PAD_R, py, fill=C_GRID)
            chart.create_text(PAD_L - 5, py, text=str(y), fill=C_TICK,
                              font=(UI, 7), anchor="e")

        mtow_y = to_y(MTOW_TSI)
        if PAD_T <= mtow_y <= CH - PAD_B:
            chart.create_line(PAD_L, mtow_y, CW - PAD_R, mtow_y, fill="#7a2b2b",
                              dash=(5, 4))
            chart.create_text(CW - PAD_R - 4, mtow_y - 6,
                              text=f"MTOW {MTOW_TSI:.0f} kg", fill="#a83a3a",
                              font=(UI, 8), anchor="se")

        pts = []
        for x, y in WB_ENV_PTS:
            pts.extend((to_x(x), to_y(y)))
        chart.create_polygon(pts, fill=C_ENV_FILL, outline=C_FUEL_RED, width=1.5)

        if res.total > 0:
            dx, dy = to_x(res.p_mac), to_y(res.total)
            col = C_DOT_OK if res.ok else C_DOT_NG

            # trajetoria decolagem -> pouso (o CG recua conforme queima)
            if land is not None and land.total > 0:
                lx, ly = to_x(land.p_mac), to_y(land.total)
                lcol = C_DOT_OK if land.ok else C_DOT_NG
                chart.create_line(dx, dy, lx, ly, fill="#7c8698", width=1.2,
                                  dash=(4, 3))
                chart.create_oval(lx - 4.5, ly - 4.5, lx + 4.5, ly + 4.5,
                                  fill=C_PLOT_BG, outline=lcol, width=2)
                chart.create_text(min(max(lx, 50), CW - 50),
                                  min(ly + 12, CH - PAD_B - 6),
                                  text=f"POU  {land.p_mac:.1f}% / "
                                       f"{land.total:.0f} kg",
                                  fill=lcol, font=(UI, 8), anchor="n")

            chart.create_oval(dx - 7, dy - 7, dx + 7, dy + 7, fill="", outline=col)
            chart.create_oval(dx - 4.5, dy - 4.5, dx + 4.5, dy + 4.5, fill=col,
                              outline="#ffffff")
            tx = min(max(dx, 50), CW - 50)
            ty = max(dy - 12, PAD_T + 10)
            chart.create_text(tx, ty,
                              text=(f"DEC  " if land is not None else "")
                                   + f"{res.p_mac:.1f}% / {res.total:.0f} kg",
                              fill=col, font=(UI, 8), anchor="s")

        chart.create_text(PAD_L + DW / 2, CH - 4, text="% MAC", fill=C_AXIS_LBL,
                          font=(UI, 8), anchor="s")
        chart.create_text(12, PAD_T + DH / 2, text="Peso (kg)", fill=C_AXIS_LBL,
                          font=(UI, 8), angle=90)

    # ── render ──────────────────────────────────────────────────────
    def render(*_args) -> None:
        empty_kg = num(v_empty_kg, DEFAULT_EMPTY_KG)
        empty_cg = num(v_empty_cg, DEFAULT_EMPTY_CG_MM)

        empty_kg_lbl["l"].configure(text=f"{empty_kg:.1f}")
        empty_arm_lbl["l"].configure(text=f"{empty_cg / 1000:.3f}")

        pilot, copil = num(v_pilot), num(v_copil)
        pax3, pax4 = num(v_pax3), num(v_pax4)
        bag, fuel_l = num(v_bag), num(v_fuel)

        row_kg_arm = [
            ("vazio", empty_kg, empty_cg),
            ("pilot", pilot, ARM_FRONT_SEATS),
            ("copil", copil, ARM_FRONT_SEATS),
            ("pax3", pax3, ARM_REAR_SEATS),
            ("pax4", pax4, ARM_REAR_SEATS),
            ("bag", bag, ARM_BAGGAGE),
            ("fuel", fuel_l * FUEL_DENSITY, ARM_FUEL),
        ]
        for key, kg, arm in row_kg_arm:
            mom_labels[key].configure(
                text="—" if kg == 0 else f"{kg * arm / 1000:.3f}")

        res = calc_wb(empty_kg, empty_cg, pilot, copil, pax3, pax4, bag, fuel_l)

        lbl_total_kg.configure(text=f"{res.total:.1f} kg")
        lbl_total_arm.configure(
            text=f"{res.cg_mm:.0f}" if res.total > 0 else "—")
        lbl_total_mom.configure(
            text=f"{res.cg_mm * res.total / 1000:.1f}" if res.total > 0 else "—")
        lbl_out_weight.configure(text=f"{res.total:.1f} kg")

        # ── pouso: combustivel restante apos consumo x duracao ──────
        cons_lh, dur_h = num(v_cons, DEFAULT_CONS_LH), num(v_dur)
        land = calc_landing(res, cons_lh, dur_h)
        burn_l = cons_lh * dur_h
        lbl_burn_tag.configure(
            text="" if burn_l == 0 else
            f"− {burn_l:.0f} L queimados ({burn_l * FUEL_DENSITY:.1f} kg)")
        dry = land.fuel_kg < 0
        lbl_land_kg.configure(text=f"{land.fuel_kg:.1f}",
                              fg=C_RED if dry else C_TEXT)
        lbl_land_mom.configure(
            text="—" if land.fuel_kg == 0 else
            f"{land.fuel_kg * ARM_FUEL / 1000:.3f}",
            fg=C_RED if dry else C_TEXT)
        lbl_ltot_kg.configure(text=f"{land.total:.1f} kg")
        lbl_ltot_arm.configure(
            text=f"{land.cg_mm:.0f}" if land.total > 0 else "—",
            fg=C_RED if land.cg_oob else C_TEXT)
        lbl_ltot_mom.configure(
            text=f"{land.cg_mm * land.total / 1000:.1f}" if land.total > 0
            else "—")

        set_badge(lbl_badge, lbl_badge_det, res)
        set_badge(lbl_lbadge, lbl_lbadge_det, land)

        # slider <-> campo de combustivel
        _slider_val["v"] = min(MAX_FUEL_L, max(0.0, fuel_l))
        draw_slider()
        lbl_fuel_l.configure(text=f"{fuel_l:.0f} L")
        lbl_fuel_kg.configure(text=f"· {fuel_l * FUEL_DENSITY:.1f} kg")

        draw_envelope(res, land if burn_l > 0 else None)

    # todo campo da pagina recalcula — inclusive consumo e duracao, que so
    # afetam as linhas de pouso
    for v in FIELD_VARS.values():
        v.trace_add("write", render)

    # valores iniciais vindos da linha de comando
    def _fmt(x: float) -> str:
        return f"{x:g}"

    for key in PROFILE_FIELDS:
        if prefill.get(key):
            FIELD_VARS[key].set(_fmt(prefill[key]))

    # rolagem por teclado
    root.bind("<Prior>", lambda _e: outer.yview_scroll(-8, "units"))
    root.bind("<Next>", lambda _e: outer.yview_scroll(8, "units"))
    root.bind("<Up>", lambda _e: outer.yview_scroll(-2, "units"))
    root.bind("<Down>", lambda _e: outer.yview_scroll(2, "units"))

    render()
    root.mainloop()


# ══════════════════════════════════════════════════════════════════════
#  MODO TEXTO
# ══════════════════════════════════════════════════════════════════════
def run_cli(args: argparse.Namespace) -> None:
    res = calc_wb(args.empty_kg, args.empty_cg, args.pilot, args.copilot,
                  args.pax3, args.pax4, args.baggage, args.fuel)

    rows = [
        ("Peso Vazio", args.empty_kg, args.empty_cg),
        ("Piloto", args.pilot, ARM_FRONT_SEATS),
        ("Copiloto", args.copilot, ARM_FRONT_SEATS),
        ("Passageiro 3", args.pax3, ARM_REAR_SEATS),
        ("Passageiro 4", args.pax4, ARM_REAR_SEATS),
        ("Bagagem", args.baggage, ARM_BAGGAGE),
        (f"Combustivel Decolagem ({args.fuel:.0f} L)", res.fuel_kg, ARM_FUEL),
    ]
    land = calc_landing(res, args.consumo, args.duracao)

    print("\n  SLING TSi — PESO & BALANCO\n")
    print(f"  {'Item':<30}{'Peso (kg)':>11}{'Braco (mm)':>12}{'Momento (kg.m)':>16}")
    print("  " + "-" * 69)
    for name, kg, arm in rows:
        mom = "-" if kg == 0 else f"{kg * arm / 1000:.3f}"
        print(f"  {name:<30}{kg:>11.1f}{arm:>12.0f}{mom:>16}")
    print("  " + "-" * 69)
    print(f"  {'TOTAL NA DECOLAGEM':<30}{res.total:>11.1f}{res.cg_mm:>12.0f}"
          f"{res.cg_mm * res.total / 1000:>16.1f}")
    print("  " + "-" * 69)
    print(f"  {'Combustivel no Pouso':<30}{land.fuel_kg:>11.1f}{ARM_FUEL:>12.0f}"
          f"{land.fuel_kg * ARM_FUEL / 1000:>16.3f}")
    print("  " + "-" * 69)
    print(f"  {'TOTAL NO POUSO':<30}{land.total:>11.1f}{land.cg_mm:>12.0f}"
          f"{land.cg_mm * land.total / 1000:>16.1f}")

    print(f"\n  Peso de decolagem : {res.total:.1f} kg  (MTOW {MTOW_TSI:.0f} kg)")
    print(f"  CG                : {res.cg_mm:.0f} mm  "
          f"(limites {CG_FWD_MM:.0f}–{CG_AFT_MM:.0f} mm)")
    print(f"  CG %MAC           : {res.p_mac:.1f}%")
    print(f"  CG no pouso       : {land.cg_mm:.0f} mm · {land.p_mac:.1f}%MAC"
          f"{'  [!] FORA DOS LIMITES' if land.cg_oob else ''}")

    if res.overweight:
        status = f"[!] EXCESSO DE PESO (MTOW {MTOW_TSI:.0f} kg)"
    elif res.cg_oob:
        status = f"[!] CG FORA DOS LIMITES ({CG_FWD_MM:.0f}–{CG_AFT_MM:.0f} mm)"
    else:
        status = "[OK] Dentro do envelope"
    print(f"  Status            : {status}\n")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Sling TSi — Peso & Balanco (replica do planejador web)")
    p.add_argument("--cli", action="store_true", help="calcula no terminal, sem GUI")
    p.add_argument("--empty-kg", type=float, default=DEFAULT_EMPTY_KG,
                   help=f"peso vazio em kg (padrao {DEFAULT_EMPTY_KG:.0f})")
    p.add_argument("--empty-cg", type=float, default=DEFAULT_EMPTY_CG_MM,
                   help=f"CG vazio em mm (padrao {DEFAULT_EMPTY_CG_MM:.0f})")
    p.add_argument("--pilot", type=float, default=0.0, help="piloto, kg")
    p.add_argument("--copilot", type=float, default=0.0, help="copiloto, kg")
    p.add_argument("--pax3", type=float, default=0.0, help="passageiro 3, kg")
    p.add_argument("--pax4", type=float, default=0.0, help="passageiro 4, kg")
    p.add_argument("--baggage", type=float, default=0.0,
                   help=f"bagagem, kg (max {MAX_BAG_KG:.0f})")
    p.add_argument("--fuel", type=float, default=0.0,
                   help=f"combustivel na decolagem, litros (max {MAX_FUEL_L:.0f})")
    p.add_argument("--consumo", type=float, default=DEFAULT_CONS_LH,
                   help=f"consumo de combustivel em L/h (padrao {DEFAULT_CONS_LH:.0f})")
    p.add_argument("--duracao", type=float, default=DEFAULT_DUR_H,
                   help="duracao do voo em horas")
    args = p.parse_args()

    if args.cli:
        run_cli(args)
    else:
        run_gui({
            "consumo": args.consumo,
            "duracao": args.duracao,
            "empty_kg": args.empty_kg,
            "empty_cg": args.empty_cg,
            "pilot": args.pilot, "copilot": args.copilot,
            "pax3": args.pax3, "pax4": args.pax4,
            "baggage": args.baggage, "fuel": args.fuel,
        })
    return 0


if __name__ == "__main__":
    sys.exit(main())
