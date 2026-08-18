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
import sys
from dataclasses import dataclass

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
    from tkinter import font as tkfont

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
        ("fuel", "Combustível",
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
    tk.Label(table, text="TOTAL", font=(UI, 9, "bold"), fg=C_TEXT, bg=total_bg,
             anchor="w").grid(row=r, column=0, sticky="ew", padx=8, ipady=6)
    lbl_total_kg = tk.Label(table, text="— kg", font=f_num_b, fg=C_TEXT,
                            bg=total_bg, anchor="e")
    lbl_total_kg.grid(row=r, column=1, sticky="ew", padx=8, ipady=6)
    tk.Label(table, text="—", font=f_num_b, fg=C_TEXT, bg=total_bg,
             anchor="e").grid(row=r, column=2, sticky="ew", padx=8, ipady=6)
    lbl_total_mom = tk.Label(table, text="—", font=f_num_b, fg=C_TEXT,
                             bg=total_bg, anchor="e")
    lbl_total_mom.grid(row=r, column=3, sticky="ew", padx=8, ipady=6)

    # ── barra de resultado ──────────────────────────────────────────
    res_bar = tk.Frame(sec_mass, bg=C_PANEL)
    res_bar.pack(fill="x", pady=(14, 0))
    res_bar.columnconfigure(0, weight=1, uniform="res")
    res_bar.columnconfigure(1, weight=1, uniform="res")

    def res_cell(col: int, caption: str):
        shell = tk.Frame(res_bar, bg=C_LINE)
        shell.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 5, 0))
        box = tk.Frame(shell, bg=C_PANEL2)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(box, text=_spaced(caption.upper()), font=(UI, 7, "bold"),
                 fg=C_MUTED, bg=C_PANEL2).pack(pady=(9, 4))
        val = tk.Label(box, text="—", font=f_big, fg=C_TEXT, bg=C_PANEL2)
        val.pack(pady=(0, 10))
        return val

    lbl_out_weight = res_cell(0, "Peso Decolagem")

    shell_badge = tk.Frame(res_bar, bg=C_LINE)
    shell_badge.grid(row=0, column=1, sticky="ew", padx=(5, 0))
    badge_box = tk.Frame(shell_badge, bg=C_PANEL2)
    badge_box.pack(fill="both", expand=True, padx=1, pady=1)
    tk.Label(badge_box, text=_spaced("STATUS"), font=(UI, 7, "bold"), fg=C_MUTED,
             bg=C_PANEL2).pack(pady=(9, 4))
    lbl_badge = tk.Label(badge_box, text="—", font=f_badge, fg=C_MUTED,
                         bg=C_PANEL2, padx=10, pady=3)
    lbl_badge.pack(pady=(0, 11))

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

    PAD_L, PAD_R, PAD_T, PAD_B = 46, 18, 18, 50
    DW = CW - PAD_L - PAD_R
    DH = CH - PAD_T - PAD_B

    def to_x(v: float) -> float:
        return PAD_L + ((v - CHART_X_MIN) / (CHART_X_MAX - CHART_X_MIN)) * DW

    def to_y(v: float) -> float:
        return PAD_T + DH - ((v - CHART_Y_MIN) / (CHART_Y_MAX - CHART_Y_MIN)) * DH

    def draw_envelope(res: WBResult) -> None:
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
            chart.create_oval(dx - 7, dy - 7, dx + 7, dy + 7, fill="", outline=col)
            chart.create_oval(dx - 4.5, dy - 4.5, dx + 4.5, dy + 4.5, fill=col,
                              outline="#ffffff")
            tx = min(max(dx, 50), CW - 50)
            ty = max(dy - 12, PAD_T + 10)
            chart.create_text(tx, ty,
                              text=f"{res.p_mac:.1f}% / {res.total:.0f} kg",
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
        lbl_total_mom.configure(
            text=f"{res.cg_mm * res.total / 1000:.1f}" if res.total > 0 else "—")
        lbl_out_weight.configure(text=f"{res.total:.1f} kg")

        if res.total <= 0:
            lbl_badge.configure(text="—", fg=C_MUTED, bg=C_PANEL2)
        elif res.overweight:
            lbl_badge.configure(
                text=f"⚠ EXCESSO DE PESO (MTOW {MTOW_TSI:.0f} kg)",
                fg=C_RED, bg=C_BADGE_NG_BG)
        elif res.cg_oob:
            lbl_badge.configure(
                text=f"⚠ CG FORA DOS LIMITES ({CG_FWD_MM:.0f}–"
                     f"{CG_AFT_MM:.0f} mm)",
                fg=C_RED, bg=C_BADGE_NG_BG)
        else:
            lbl_badge.configure(text="✓ Dentro do envelope", fg=C_OK,
                                bg=C_BADGE_OK_BG)

        # slider <-> campo de combustivel
        _slider_val["v"] = min(MAX_FUEL_L, max(0.0, fuel_l))
        draw_slider()
        lbl_fuel_l.configure(text=f"{fuel_l:.0f} L")
        lbl_fuel_kg.configure(text=f"· {fuel_l * FUEL_DENSITY:.1f} kg")

        draw_envelope(res)

    for v in (v_empty_kg, v_empty_cg, v_pilot, v_copil, v_pax3, v_pax4, v_bag,
              v_fuel):
        v.trace_add("write", render)

    # valores iniciais vindos da linha de comando
    def _fmt(x: float) -> str:
        return f"{x:g}"

    for key, var in (("empty_kg", v_empty_kg), ("empty_cg", v_empty_cg),
                     ("pilot", v_pilot), ("copilot", v_copil),
                     ("pax3", v_pax3), ("pax4", v_pax4),
                     ("baggage", v_bag), ("fuel", v_fuel)):
        if prefill.get(key):
            var.set(_fmt(prefill[key]))

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
        (f"Combustivel ({args.fuel:.0f} L)", res.fuel_kg, ARM_FUEL),
    ]

    print("\n  SLING TSi — PESO & BALANCO\n")
    print(f"  {'Item':<24}{'Peso (kg)':>11}{'Braco (mm)':>12}{'Momento (kg.m)':>16}")
    print("  " + "-" * 63)
    for name, kg, arm in rows:
        mom = "-" if kg == 0 else f"{kg * arm / 1000:.3f}"
        print(f"  {name:<24}{kg:>11.1f}{arm:>12.0f}{mom:>16}")
    print("  " + "-" * 63)
    print(f"  {'TOTAL':<24}{res.total:>11.1f}{'':>12}"
          f"{res.cg_mm * res.total / 1000:>16.1f}")

    print(f"\n  Peso de decolagem : {res.total:.1f} kg  (MTOW {MTOW_TSI:.0f} kg)")
    print(f"  CG                : {res.cg_mm:.0f} mm  "
          f"(limites {CG_FWD_MM:.0f}–{CG_AFT_MM:.0f} mm)")
    print(f"  CG %MAC           : {res.p_mac:.1f}%")

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
                   help=f"combustivel, litros (max {MAX_FUEL_L:.0f})")
    args = p.parse_args()

    if args.cli:
        run_cli(args)
    else:
        run_gui({
            "empty_kg": args.empty_kg,
            "empty_cg": args.empty_cg,
            "pilot": args.pilot, "copilot": args.copilot,
            "pax3": args.pax3, "pax4": args.pax4,
            "baggage": args.baggage, "fuel": args.fuel,
        })
    return 0


if __name__ == "__main__":
    sys.exit(main())
