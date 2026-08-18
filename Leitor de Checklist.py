#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sling TSi — Leitor de Checklist

Leitor de checklists de voo em Python (Tkinter) com sintese de voz e
reconhecimento de comandos em pt-BR pelo System.Speech do Windows.

O conteudo vem de Checklists-PB.json, na hierarquia
grupos -> subgrupos -> checklists -> itens.

Visual replicado do planejador Sling TSi (tema escuro #0d1117, paineis
#161b22, acento vermelho #e63329) — a mesma paleta de sling_tsi_wb.py, que o
menu inicial abre pelo botao "Peso & Balanceamento".

Comandos de voz (botao "Ouvir"):
    "check"    marca o item pendente e le ate o proximo
    "pular"    deixa o item pendente e segue adiante
    "repetir"  repete a ultima leitura

Uso:
    python "Leitor de Checklist.py"
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont
from typing import Any, Callable

try:                                  # o logo e opcional: sem Pillow o app roda igual
    from PIL import Image, ImageTk
except ImportError:                   # pragma: no cover
    Image = ImageTk = None            # type: ignore[assignment]


# ══════════════════════════════════════════════════════════════════════
#  ARQUIVOS E APLICATIVOS IRMAOS
# ══════════════════════════════════════════════════════════════════════
CHECKLIST_PATH = Path(__file__).with_name("Checklists-PB.json")
SETTINGS_PATH = Path(__file__).with_name("settings.json")
LOGO_PATH = Path(__file__).with_name("Sling TSI.png")
ICON_PATH = Path(__file__).with_name("logo.ico")
WB_APP_PATH = Path(__file__).with_name("sling_tsi_wb.py")

URL_REDEMET = "https://redemet-app.decea.mil.br/"
URL_AISWEB = "https://aisweb.decea.mil.br/"


# ══════════════════════════════════════════════════════════════════════
#  PALETA / TEMA  (identica a de sling_tsi_wb.py)
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

C_DOTS = "#39414e"            # guias pontilhadas entre desafio e resposta
C_RESPONSE = "#58a6ff"        # resposta esperada do item
C_CAUTION = "#d29922"         # ITEM_CAUTION
C_WARNING = C_RED             # ITEM_WARNING
C_LISTENING = "#3fb950"       # indicador de escuta ativa
C_NOTE_BG = "#1b1216"         # fundo do aviso, como as notas do planejador

PAD_X = 16                    # respiro lateral da pagina
WRAP_LENGTH = 900             # quebra de linha dos textos longos
LOGO_HEIGHT = 36              # altura do logotipo no cabecalho inicial


def _spaced(text: str, gap: str = " ") -> str:
    """Emula o letter-spacing dos titulos do site."""
    return gap.join(text)


# ══════════════════════════════════════════════════════════════════════
#  TIPOGRAFIA  — resolvida depois da criacao do root
# ══════════════════════════════════════════════════════════════════════
UI = "Segoe UI"
MONO = "Consolas"
F: dict[str, tuple] = {}


def setup_fonts() -> None:
    """Escolhe as familias disponiveis e monta a escala tipografica."""
    global UI, MONO
    available = set(tkfont.families())

    def pick(*candidates: str) -> str:
        for name in candidates:
            if name in available:
                return name
        return candidates[-1]

    UI = pick("Saira", "Segoe UI", "Inter", "Helvetica")
    MONO = pick("JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New")

    F.update({
        "h1": (UI, 13, "bold"),
        "h2": (UI, 8, "bold"),
        "lbl": (UI, 9),
        "tag": (UI, 7),
        "btn": (UI, 9),
        "btn_b": (UI, 9, "bold"),
        "list": (UI, 11),
        "list_tag": (UI, 8),
        "chev": (UI, 13),
        # o checklist e lido em voo: o corpo fica um ponto acima do resto
        "item": (UI, 11),
        "item_i": (UI, 11, "italic"),
        "resp": (MONO, 11),
        "hint": (UI, 8),
    })


# ══════════════════════════════════════════════════════════════════════
#  VOZ  — sintese e reconhecimento pelo System.Speech
# ══════════════════════════════════════════════════════════════════════
_speaking_process: subprocess.Popen[str] | None = None
_listening_process: subprocess.Popen[str] | None = None

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stop_speaking() -> None:
    global _speaking_process
    if _speaking_process is not None and _speaking_process.poll() is None:
        _speaking_process.terminate()
    _speaking_process = None


def stop_listening() -> None:
    global _listening_process
    if _listening_process is not None and _listening_process.poll() is None:
        _listening_process.terminate()
    _listening_process = None


def speak_text_pt_br(text: str, rate: int = 0) -> None:
    """Fala `text` em pt-BR; qualquer fala anterior e interrompida."""
    global _speaking_process
    stop_speaking()
    if not text:
        return

    script = f"""
Add-Type -AssemblyName System.Speech
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$text = [Console]::In.ReadToEnd()
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Rate = {rate}
$voice = $speaker.GetInstalledVoices() |
    Where-Object {{ $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'pt-BR' }} |
    Select-Object -First 1
if (-not $voice) {{
    $voice = $speaker.GetInstalledVoices() |
        Where-Object {{ $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'pt' }} |
        Select-Object -First 1
}}
if ($voice) {{
    $speaker.SelectVoice($voice.VoiceInfo.Name)
}}
$speaker.Speak($text)
$speaker.Dispose()
"""
    _speaking_process = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", script],
        stdin=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=_NO_WINDOW,
    )
    _speaking_process.stdin.write(text)   # type: ignore[union-attr]
    _speaking_process.stdin.close()       # type: ignore[union-attr]


def start_listening(window: tk.Tk,
                    callbacks: dict[str, Callable[[], None]],
                    on_done: Callable[[], None]) -> None:
    """Escuta uma palavra da gramatica e despacha o callback na thread da UI."""
    global _listening_process
    stop_listening()

    script = """
Add-Type -AssemblyName System.Speech
$ptInfo = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
    Where-Object { $_.Culture.Name -eq 'pt-BR' -or $_.Culture.TwoLetterISOLanguageName -eq 'pt' } |
    Select-Object -First 1
if ($ptInfo) {
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($ptInfo.Culture)
} else {
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
}
$recognizer.SetInputToDefaultAudioDevice()
$gb = New-Object System.Speech.Recognition.GrammarBuilder
$gb.Culture = $recognizer.RecognizerInfo.Culture
$choices = New-Object System.Speech.Recognition.Choices
[void]$choices.Add('check')
[void]$choices.Add('pular')
[void]$choices.Add('repetir')
$gb.Append($choices)
$grammarObj = New-Object System.Speech.Recognition.Grammar($gb)
$recognizer.LoadGrammar($grammarObj)
$result = $recognizer.Recognize([System.TimeSpan]::FromSeconds(30))
if ($result) {
    Write-Output $result.Text.ToLower()
}
$recognizer.Dispose()
"""
    _listening_process = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", script],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=_NO_WINDOW,
    )
    proc = _listening_process

    def _thread_func() -> None:
        word = ""
        if proc.stdout:
            word = proc.stdout.readline().strip().lower()
        proc.wait()

        def _dispatch() -> None:
            if word in callbacks:
                callbacks[word]()
            on_done()

        window.after(0, _dispatch)

    threading.Thread(target=_thread_func, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════
#  DADOS  — checklists e preferencias
# ══════════════════════════════════════════════════════════════════════
def load_checklist() -> dict[str, Any]:
    with CHECKLIST_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_settings() -> dict[str, Any]:
    """Le settings.json. Arquivo ausente ou corrompido -> dicionario vazio."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict[str, Any]) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False),
                                 encoding="utf-8")
    except OSError:
        pass


# o nome do arquivo da lugar ao aviso de uso e a matricula nao vai para a tela
METADATA_SKIP = ("name", "aircraftInfo")

DISCLAIMER = ("Aplicativo desenvolvido para uso pessoal. Nenhuma das "
              "informações contidas aqui devem ser consideradas e substituem "
              "os documentos oficiais da Aeronave")


def metadata_text(data: dict[str, Any]) -> str:
    return "\n".join(str(value)
                     for key, value in data.get("metadata", {}).items()
                     if key not in METADATA_SKIP)


# ══════════════════════════════════════════════════════════════════════
#  APLICATIVOS EXTERNOS
# ══════════════════════════════════════════════════════════════════════
def open_url(url: str, status: tk.Label | None = None) -> None:
    try:
        webbrowser.open_new(url)
    except OSError as exc:
        flash(status, "Não foi possível abrir o navegador: " + str(exc), ok=False)


def open_weight_balance(status: tk.Label | None = None) -> None:
    """Abre sling_tsi_wb.py num processo proprio, no mesmo interpretador."""
    if not WB_APP_PATH.exists():
        flash(status, "sling_tsi_wb.py não encontrado nesta pasta.", ok=False)
        return

    # pythonw evita o console preto atras da janela do Tk no Windows
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    launcher = str(pythonw if pythonw.exists() else exe)

    try:
        subprocess.Popen([launcher, str(WB_APP_PATH)],
                         cwd=str(WB_APP_PATH.parent),
                         creationflags=_NO_WINDOW)
    except OSError as exc:
        flash(status, "Não foi possível abrir Peso & Balanceamento: " + str(exc),
              ok=False)
        return
    flash(status, "✓ Peso & Balanceamento aberto em outra janela")


# ══════════════════════════════════════════════════════════════════════
#  WIDGETS DE BASE  (equivalentes aos do planejador)
# ══════════════════════════════════════════════════════════════════════
def load_logo(height: int) -> Any:
    """Logotipo redimensionado para `height` px, ou None se nao der para usar.

    Sem Pillow (ou sem o arquivo) o cabecalho volta ao titulo em texto.
    """
    if Image is None or ImageTk is None or not LOGO_PATH.exists():
        return None
    try:
        img = Image.open(LOGO_PATH).convert("RGBA")
        w, h = img.size
        img = img.resize((max(1, round(w * height / h)), height),
                         Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except (OSError, ValueError):
        return None


def apply_icon(window: tk.Tk) -> None:
    """Icone da janela. `default` vale tambem para as caixas de dialogo."""
    if not ICON_PATH.exists():
        return
    try:
        window.iconbitmap(default=str(ICON_PATH))
    except tk.TclError:
        pass


def flash(label: tk.Label | None, text: str, ok: bool = True,
          delay: int = 3000) -> None:
    """Mensagem temporaria no rodape, verde quando deu certo."""
    if label is None or not label.winfo_exists():
        return
    label.configure(text=text, fg=C_OK if ok else C_RED)
    label.after(delay,
                lambda: label.winfo_exists() and label.configure(text=""))


def primary_button(parent: tk.Misc, text: str,
                   command: Callable[[], None]) -> tk.Button:
    return tk.Button(parent, text=text, font=F["btn_b"], fg="#ffffff", bg=C_RED,
                     activebackground=C_RED_DIM, activeforeground="#ffffff",
                     relief="flat", padx=16, pady=7, cursor="hand2",
                     command=command)


def ghost_button(parent: tk.Misc, text: str,
                 command: Callable[[], None]) -> tk.Button:
    return tk.Button(parent, text=text, font=F["btn"], fg=C_TEXT, bg=C_PANEL2,
                     activebackground=C_LINE, activeforeground=C_TEXT,
                     relief="flat", padx=14, pady=7, cursor="hand2",
                     command=command)


def list_button(parent: tk.Misc, text: str, command: Callable[[], None],
                tag: str = "") -> tk.Frame:
    """Linha de menu: moldura C_LINE sobre painel, com chevron vermelho."""
    shell = tk.Frame(parent, bg=C_LINE)
    inner = tk.Frame(shell, bg=C_PANEL)
    inner.pack(fill="both", expand=True, padx=1, pady=1)

    chev = tk.Label(inner, text="›", font=F["chev"], fg=C_RED, bg=C_PANEL,
                    cursor="hand2")
    chev.pack(side="right", padx=(8, 14))

    cell = tk.Frame(inner, bg=C_PANEL, cursor="hand2")
    cell.pack(side="left", fill="both", expand=True, padx=16, pady=12)
    name = tk.Label(cell, text=text, font=F["list"], fg=C_TEXT, bg=C_PANEL,
                    anchor="w", cursor="hand2")
    name.pack(side="left")

    parts: list[Any] = [inner, cell, name, chev]
    if tag:
        tag_label = tk.Label(cell, text=tag, font=F["list_tag"], fg=C_MUTED,
                             bg=C_PANEL, cursor="hand2")
        tag_label.pack(side="left", padx=(8, 0))
        parts.append(tag_label)

    def paint(bg: str, border: str) -> None:
        shell.configure(bg=border)
        for widget in parts:
            widget.configure(bg=bg)

    for widget in parts:
        widget.bind("<Enter>", lambda _e: paint(C_PANEL2, C_RED))
        widget.bind("<Leave>", lambda _e: paint(C_PANEL, C_LINE))
        widget.bind("<Button-1>", lambda _e: command())

    return shell


def section(parent: tk.Misc, title: str | None, bg: str = C_PANEL,
            border: str = C_LINE) -> tk.Frame:
    """Equivalente ao .sec do site: painel com moldura e titulo."""
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
        tk.Label(head, text=_spaced(title.upper()), font=F["h2"], fg=C_MUTED,
                 bg=bg).pack(side="left")
    return inner


def title_bar(window: tk.Tk, title: str,
              on_back: Callable[[], None] | None = None,
              image: Any = None) -> tk.Frame:
    """Cabecalho da pagina: voltar opcional e o titulo — em logotipo, quando
    `image` vem preenchido, senao espacado em texto com o travessao."""
    bar = tk.Frame(window, bg=C_BG)
    bar.pack(fill="x", padx=PAD_X, pady=(14, 14))
    if on_back is not None:
        ghost_button(bar, "‹  Voltar", on_back).pack(side="left", padx=(0, 14))

    if image is not None:
        logo = tk.Label(bar, image=image, bg=C_BG)
        logo.image = image        # type: ignore[attr-defined]  (segura o GC)
        logo.pack(side="left")
        return bar

    tk.Label(bar, text=_spaced(title.upper()), font=F["h1"], fg=C_TEXT,
             bg=C_BG).pack(side="left")
    tk.Label(bar, text="—", font=F["h1"], fg=C_RED,
             bg=C_BG).pack(side="left", padx=8)
    return bar


def scroll_area(window: tk.Tk) -> tuple[tk.Frame, tk.Canvas]:
    """Canvas rolavel ocupando o resto da janela; devolve (conteudo, canvas)."""
    outer = tk.Canvas(window, bg=C_BG, highlightthickness=0)
    vbar = tk.Scrollbar(window, orient="vertical", command=outer.yview,
                        bg=C_PANEL, troughcolor=C_BG, borderwidth=0,
                        activebackground=C_LINE, highlightthickness=0)
    outer.configure(yscrollcommand=vbar.set)
    vbar.pack(side="right", fill="y")
    outer.pack(side="left", fill="both", expand=True)

    page = tk.Frame(outer, bg=C_BG)
    win = outer.create_window((0, 0), window=page, anchor="nw")
    page.bind("<Configure>",
              lambda _e: outer.configure(scrollregion=outer.bbox("all")))
    outer.bind("<Configure>", lambda e: outer.itemconfigure(win, width=e.width))
    outer.bind_all("<MouseWheel>",
                   lambda e: outer.winfo_exists()
                   and outer.yview_scroll(int(-e.delta / 120), "units"))

    content = tk.Frame(page, bg=C_BG)
    content.pack(fill="both", expand=True, padx=PAD_X, pady=(0, 18))
    return content, outer


def clear_window(window: tk.Tk) -> None:
    stop_speaking()
    stop_listening()
    for widget in window.winfo_children():
        widget.destroy()


# ══════════════════════════════════════════════════════════════════════
#  LEITURA GUIADA  — avancar, pular e repetir
# ══════════════════════════════════════════════════════════════════════
def new_speech_state() -> dict[str, Any]:
    return {"last_text": "", "next_index": 0, "last_challenge_index": None,
            "canvas": None, "content": None, "search_start": 0}


def _first_unchecked(read_entries: list[dict[str, Any]],
                     start: int) -> int | None:
    for index, entry in enumerate(read_entries):
        if index < start:
            continue
        check_var = entry.get("check_var")
        if check_var is not None and not check_var.get():
            return index
    return None


def scroll_to(speech_state: dict[str, Any], widget: Any) -> None:
    """Centraliza `widget` na area visivel, se houver o que rolar."""
    canvas = speech_state.get("canvas")
    content = speech_state.get("content")
    if not isinstance(canvas, tk.Canvas) or not isinstance(content, tk.Frame):
        return
    if not isinstance(widget, tk.Widget) or not widget.winfo_exists():
        return

    canvas.update_idletasks()
    box = canvas.bbox("all")
    if not box:
        return
    content_height = box[3]
    canvas_height = canvas.winfo_height()
    if content_height <= canvas_height:
        return

    # o item mora dentro de um painel: mede a distancia real ate o topo da pagina
    offset = widget.winfo_rooty() - content.winfo_rooty()
    target_y = offset + widget.winfo_height() / 2 - canvas_height / 2
    target_y = max(0.0, min(target_y, float(content_height - canvas_height)))
    canvas.yview_moveto(target_y / content_height)


def read_next_items(read_entries: list[dict[str, Any]],
                    speech_state: dict[str, Any], rate: int = 0) -> None:
    """Marca o desafio pendente e le ate o proximo — o comando "check"."""
    if not read_entries:
        return

    previous_challenge_index = speech_state.get("last_challenge_index")
    if previous_challenge_index is not None:
        previous_check_var = read_entries[previous_challenge_index].get("check_var")
        if previous_check_var is not None:
            previous_check_var.set(1)

    first_unchecked_index = _first_unchecked(
        read_entries, speech_state.get("search_start", 0))

    if first_unchecked_index is None:
        text = "Checklist completo."
    else:
        start_index = speech_state.get("next_index", 0)
        if start_index > first_unchecked_index:
            start_index = first_unchecked_index

        entries_to_read = read_entries[start_index:first_unchecked_index + 1]
        text = ". ".join(entry["text"] for entry in entries_to_read
                         if entry.get("text"))
        speech_state["next_index"] = first_unchecked_index + 1
        speech_state["last_challenge_index"] = first_unchecked_index

    speech_state["last_text"] = text

    if first_unchecked_index is not None:
        scroll_to(speech_state, read_entries[first_unchecked_index].get("widget"))

    speak_text_pt_br(text, rate)


def skip_next_item(read_entries: list[dict[str, Any]],
                   speech_state: dict[str, Any], rate: int = 0) -> None:
    """Deixa o item pendente sem marcar e segue para o proximo desafio."""
    if not read_entries:
        return

    skipped_index = _first_unchecked(read_entries,
                                     speech_state.get("search_start", 0))
    if skipped_index is None:
        return

    # avanca o inicio da busca para que o item pulado nunca volte
    speech_state["search_start"] = skipped_index + 1

    next_index = _first_unchecked(read_entries, skipped_index + 1)
    if next_index is None:
        return

    # le o texto corrido entre o item pulado e o proximo desafio, e o desafio
    entries_to_read = read_entries[skipped_index + 1:next_index + 1]
    text = ". ".join(entry["text"] for entry in entries_to_read
                     if entry.get("text"))
    speech_state["next_index"] = next_index + 1
    speech_state["last_challenge_index"] = next_index
    speech_state["last_text"] = text

    scroll_to(speech_state, read_entries[next_index].get("widget"))
    speak_text_pt_br(text, rate)


def repeat_last_read(speech_state: dict[str, Any], rate: int = 0) -> None:
    speak_text_pt_br(speech_state.get("last_text", ""), rate)


# ══════════════════════════════════════════════════════════════════════
#  TELAS
# ══════════════════════════════════════════════════════════════════════
def show_main_menu(window: tk.Tk, data: dict[str, Any]) -> None:
    clear_window(window)
    window.title("Sling TSi · Aplicativos")

    title_bar(window, "Sling TSi", image=load_logo(LOGO_HEIGHT))

    content, _ = scroll_area(window)

    apps = section(content, "Escolha um aplicativo")
    status = tk.Label(content, text="", font=F["hint"], fg=C_OK, bg=C_BG,
                      anchor="w")

    entries: list[tuple[str, str, Callable[[], None]]] = [
        ("Checklist", "procedimentos normais e de emergência",
         lambda: show_groups(window, data)),
        ("Peso & Balanceamento", "envelope de CG",
         lambda: open_weight_balance(status)),
        ("RedeMet", "meteorologia aeronáutica · DECEA",
         lambda: open_url(URL_REDEMET, status)),
        ("AISweb", "cartas e publicações · DECEA",
         lambda: open_url(URL_AISWEB, status)),
    ]
    for label, tag, command in entries:
        list_button(apps, label, command, tag=tag).pack(fill="x", pady=(0, 8))

    status.pack(fill="x", pady=(2, 0))

    if data.get("metadata"):
        foot = tk.Frame(content, bg=C_BG)
        foot.pack(fill="x", pady=(10, 0))
        ghost_button(foot, "Sobre o aplicativo",
                     lambda: show_metadata(window, data)).pack(side="left")


def show_metadata(window: tk.Tk, data: dict[str, Any]) -> None:
    clear_window(window)
    window.title("Sling TSi · Sobre")

    title_bar(window, "Sobre", lambda: show_main_menu(window, data))
    content, _ = scroll_area(window)

    aviso = section(content, "Aviso", bg=C_NOTE_BG, border="#3a1c1e")
    tk.Label(aviso, text=DISCLAIMER, font=F["item"], fg=C_TEXT, bg=C_NOTE_BG,
             justify="left", anchor="w", wraplength=WRAP_LENGTH).pack(fill="x")

    about = section(content, "Metadados do arquivo")
    tk.Label(about, text=metadata_text(data), font=F["lbl"], fg=C_TEXT,
             bg=C_PANEL, justify="left", anchor="w",
             wraplength=WRAP_LENGTH).pack(fill="x")


def show_groups(window: tk.Tk, data: dict[str, Any]) -> None:
    clear_window(window)
    window.title("Sling TSi · Checklists")

    title_bar(window, "Checklists", lambda: show_main_menu(window, data))
    content, _ = scroll_area(window)

    groups = data.get("groups", [])
    panel = section(content, "Grupos")
    if not groups:
        tk.Label(panel, text="Nenhum grupo encontrado.", font=F["lbl"],
                 fg=C_MUTED, bg=C_PANEL).pack(anchor="w")
        return

    for group in groups:
        subgroups = group.get("groups", [])
        tag = "" if not subgroups else (
            "1 seção" if len(subgroups) == 1 else f"{len(subgroups)} seções")
        list_button(panel, group.get("title", ""),
                    lambda selected=group: show_subgroups(window, data, selected),
                    tag=tag).pack(fill="x", pady=(0, 8))


def show_subgroups(window: tk.Tk, data: dict[str, Any],
                   group: dict[str, Any]) -> None:
    clear_window(window)
    window.title(f"Sling TSi · {group.get('title', 'Seções')}")

    title_bar(window, group.get("title", "Seções"),
              lambda: show_groups(window, data))
    content, _ = scroll_area(window)

    subgroups = group.get("groups", [])
    panel = section(content, "Seções")
    if not subgroups:
        tk.Label(panel, text="Nenhuma seção encontrada.", font=F["lbl"],
                 fg=C_MUTED, bg=C_PANEL).pack(anchor="w")
        return

    for subgroup in subgroups:
        checklists = subgroup.get("checklists", [])
        tag = "" if not checklists else (
            "1 checklist" if len(checklists) == 1
            else f"{len(checklists)} checklists")
        list_button(panel, subgroup.get("title", ""),
                    lambda selected=subgroup: show_items(window, data, group,
                                                         selected),
                    tag=tag).pack(fill="x", pady=(0, 8))


def show_items(window: tk.Tk, data: dict[str, Any], group: dict[str, Any],
               subgroup: dict[str, Any]) -> None:
    clear_window(window)
    window.title(f"Sling TSi · {subgroup.get('title', 'Itens')}")

    title_bar(window, subgroup.get("title", "Itens"),
              lambda: show_subgroups(window, data, group))

    read_entries: list[dict[str, Any]] = []
    speech_state = new_speech_state()

    # ── controles de leitura ────────────────────────────────────────
    # em barra propria: titulo de checklist e longo e espremeria os botoes
    controls = tk.Frame(window, bg=C_BG)
    controls.pack(fill="x", padx=PAD_X, pady=(0, 12))

    speed_var = tk.IntVar(value=load_settings().get("speed", 0))
    speed_var.trace_add("write",
                        lambda *_a: save_settings({"speed": speed_var.get()}))

    primary_button(
        controls, "Check",
        lambda: read_next_items(read_entries, speech_state, speed_var.get()),
    ).pack(side="left", padx=(0, 8))
    for text, action in (
        ("Repetir", lambda: repeat_last_read(speech_state, speed_var.get())),
        ("Pular", lambda: skip_next_item(read_entries, speech_state,
                                         speed_var.get())),
    ):
        ghost_button(controls, text, action).pack(side="left", padx=(0, 8))

    ouvir_button = ghost_button(controls, "Ouvir", lambda: None)
    ouvir_button.pack(side="left", padx=(8, 0))

    tk.Scale(controls, from_=-10, to=10, orient="horizontal", variable=speed_var,
             length=130, bg=C_PANEL2, fg=C_MUTED, font=F["tag"],
             highlightthickness=0, bd=0, troughcolor=C_FIELD,
             activebackground=C_RED, sliderrelief="flat",
             sliderlength=16).pack(side="right")
    tk.Label(controls, text=_spaced("VELOCIDADE DA VOZ"), font=F["tag"],
             fg=C_MUTED, bg=C_BG).pack(side="right", padx=(0, 8))

    # ── escuta continua ─────────────────────────────────────────────
    is_listening = [False]
    voice_callbacks: dict[str, Callable[[], None]] = {
        "check": lambda: read_next_items(read_entries, speech_state,
                                         speed_var.get()),
        "pular": lambda: skip_next_item(read_entries, speech_state,
                                        speed_var.get()),
        "repetir": lambda: repeat_last_read(speech_state, speed_var.get()),
    }

    def _idle_button() -> None:
        ouvir_button.configure(text="Ouvir", fg=C_TEXT, bg=C_PANEL2)

    def _listen_loop() -> None:
        def _on_done() -> None:
            if not ouvir_button.winfo_exists():
                return
            if is_listening[0]:
                _listen_loop()
            else:
                _idle_button()

        start_listening(window, voice_callbacks, _on_done)

    def _on_ouvir() -> None:
        stop_speaking()
        if is_listening[0]:
            is_listening[0] = False
            stop_listening()
            _idle_button()
        else:
            is_listening[0] = True
            ouvir_button.configure(text="●  Ouvindo", fg=C_LISTENING, bg=C_FIELD)
            _listen_loop()

    ouvir_button.configure(command=_on_ouvir)

    # ── conteudo ────────────────────────────────────────────────────
    content, canvas = scroll_area(window)
    speech_state["canvas"] = canvas
    speech_state["content"] = content

    checklists = subgroup.get("checklists", [])
    if not checklists:
        panel = section(content, subgroup.get("title", "Itens"))
        tk.Label(panel, text="Nenhum item encontrado.", font=F["lbl"],
                 fg=C_MUTED, bg=C_PANEL).pack(anchor="w")
        return

    for checklist in checklists:
        checklist_title = str(checklist.get("title", ""))
        panel = section(content, checklist_title or None)

        if checklist_title:
            read_entries.append({"text": checklist_title, "check_var": None})

        for item in checklist.get("items", []):
            read_entry = add_item_row(panel, item)
            if read_entry:
                read_entries.append(read_entry)

    tk.Label(content, text="Diga “check” para avançar, “pular” para deixar o "
                           "item pendente ou “repetir” para ouvir de novo.",
             font=F["hint"], fg=C_MUTED, bg=C_BG, anchor="w", justify="left",
             wraplength=WRAP_LENGTH).pack(fill="x")


def add_item_row(parent: tk.Frame, item: dict[str, Any]) -> dict[str, Any] | None:
    """Desenha um item do checklist e devolve o que a leitura precisa saber."""
    item_type = item.get("type", "")
    prompt = item.get("prompt", "")
    left_padding = 26 if item.get("indent") == 1 else 0

    if item_type == "ITEM_SPACE":
        tk.Frame(parent, bg=C_LINE, height=1).pack(fill="x", pady=8)
        return None

    if item_type == "ITEM_CHALLENGE_RESPONSE":
        row = tk.Frame(parent, bg=C_PANEL)
        row.pack(fill="x", pady=1, padx=(left_padding, 0))
        row.columnconfigure(2, weight=1)

        check_var = tk.IntVar(value=0)
        check_box = tk.Checkbutton(row, variable=check_var, bg=C_PANEL, fg=C_RED,
                                   activebackground=C_PANEL, activeforeground=C_RED,
                                   selectcolor=C_FIELD, highlightthickness=0, bd=0,
                                   cursor="hand2")
        check_box.grid(row=0, column=0, sticky="w", padx=(0, 6))

        prompt_label = tk.Label(row, text=prompt, font=F["item"], fg=C_TEXT,
                                bg=C_PANEL, anchor="w")
        prompt_label.grid(row=0, column=1, sticky="w")

        dots_label = tk.Label(row, text="", font=F["item"], fg=C_DOTS, bg=C_PANEL,
                              anchor="e")
        dots_label.grid(row=0, column=2, sticky="ew", padx=6)

        expectation = item.get("expectation", "")
        expectation_label = tk.Label(row, text=expectation, font=F["resp"],
                                     fg=C_RESPONSE, bg=C_PANEL, anchor="e")
        expectation_label.grid(row=0, column=3, sticky="e")

        # item conferido esmaece, como as linhas ja resolvidas do planejador
        def on_check(*_args: Any) -> None:
            done = bool(check_var.get())
            prompt_label.configure(fg=C_MUTED if done else C_TEXT)
            expectation_label.configure(fg=C_MUTED if done else C_RESPONSE)

        check_var.trace_add("write", on_check)

        # a coluna dos pontos nunca pode entrar na largura pedida pela linha:
        # senao cada redesenho dispara outro <Configure> e o laco nao fecha
        dots_label.configure(width=1)
        dot_font = tkfont.Font(font=dots_label.cget("font"))
        last_width = {"px": -1}

        def update_dots(event: Any) -> None:
            if event.width == last_width["px"]:
                return
            last_width["px"] = event.width
            used_width = (check_box.winfo_width()
                          + prompt_label.winfo_reqwidth()
                          + expectation_label.winfo_reqwidth()
                          + 20)
            available_width = max(event.width - used_width,
                                  dot_font.measure("..."))
            dot_count = max(3, available_width // dot_font.measure("."))
            dots_label.configure(text="." * dot_count)

        row.bind("<Configure>", update_dots)
        return {"text": f"{prompt}. {expectation}", "check_var": check_var,
                "widget": row}

    # ── itens de texto: nota, atencao e advertencia ─────────────────
    text = prompt or item_type
    color = C_TEXT
    if item_type in ("ITEM_PLAINTEXT", "ITEM_NOTE"):
        color = C_MUTED
    elif item_type == "ITEM_CAUTION":
        color = C_CAUTION
    elif item_type in ("ITEM_WARNING", "ITEM_WARNIN"):
        color = C_WARNING

    tk.Label(parent, text=text, font=F["item_i"], fg=color, bg=C_PANEL,
             justify="left", anchor="w", wraplength=WRAP_LENGTH).pack(
        fill="x", pady=3, padx=(left_padding, 0))
    return {"text": text, "check_var": None}


# ══════════════════════════════════════════════════════════════════════
#  ENTRADA
# ══════════════════════════════════════════════════════════════════════
def main() -> int:
    try:
        data = load_checklist()
    except (OSError, ValueError) as exc:
        print(f"Nao foi possivel ler {CHECKLIST_PATH.name}: {exc}",
              file=sys.stderr)
        return 1

    window = tk.Tk()
    window.title("Sling TSi · Aplicativos")
    window.configure(bg=C_BG)
    apply_icon(window)
    window.minsize(880, 620)
    screen_h = window.winfo_screenheight()
    window.geometry(f"1120x{min(1020, max(640, screen_h - 90))}+80+20")

    setup_fonts()

    # rolagem por teclado, como no planejador
    window.bind("<Prior>",
                lambda _e: window.event_generate("<MouseWheel>", delta=960))
    window.bind("<Next>",
                lambda _e: window.event_generate("<MouseWheel>", delta=-960))

    show_main_menu(window, data)
    window.protocol("WM_DELETE_WINDOW",
                    lambda: (stop_speaking(), stop_listening(), window.destroy()))
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
