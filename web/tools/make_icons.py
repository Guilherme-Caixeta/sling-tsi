# -*- coding: utf-8 -*-
"""Gera os icones do PWA a partir de Logo.png.

O Logo.png tem o xadrez de transparencia *pintado* no arquivo (o alpha e
opaco em toda a imagem), entao a marca e separada pelo vermelho dominante e
as bordas suaves sao limpas do branco que ficou por tras delas.

Saidas em web/assets/:
    icon-192.png            atalho e favicon
    icon-512.png            instalacao do PWA e tela de inicio do iOS
    icon-maskable-512.png   marca menor, para o recorte do Android
    sling_tsi.png           logotipo do cabecalho (copia de "Sling TSI.png")

Uso:
    python web/tools/make_icons.py [caminho/para/Logo.png]
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent   # raiz do projeto
ASSETS = ROOT / "web" / "assets"

BG = (13, 17, 23)          # #0d1117: o iOS achata transparencia em preto
SHARE = 0.74               # quanto da largura a marca ocupa
SHARE_MASKABLE = 0.52      # area segura do icone adaptativo do Android


def cut_out_mark(path: Path) -> Image.Image:
    """Devolve so a marca vermelha, com alpha de verdade e ja recortada."""
    src = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    r, g, b = src[..., 0], src[..., 1], src[..., 2]

    alpha = np.clip(1.0 - np.minimum(g, b) / 255.0, 0.0, 1.0)
    alpha[(r - np.maximum(g, b)) < 12] = 0.0      # cinza do xadrez: fora
    alpha[alpha < 0.04] = 0.0

    safe = np.where(alpha > 0, alpha, 1.0)[..., None]
    color = np.clip((src - 255.0 * (1.0 - safe)) / safe, 0, 255)

    rgba = np.dstack([color, alpha * 255.0]).astype(np.uint8)
    mask = Image.fromarray((alpha * 255).astype(np.uint8), "L")
    return Image.fromarray(rgba, "RGBA").crop(mask.getbbox())


def compose(mark: Image.Image, side: int, share: float) -> Image.Image:
    limit = int(side * share)
    width, height = limit, max(1, round(mark.height * limit / mark.width))
    if height > limit:
        height, width = limit, max(1, round(mark.width * limit / mark.height))
    scaled = mark.resize((width, height), Image.LANCZOS)
    icon = Image.new("RGBA", (side, side), BG + (255,))
    icon.alpha_composite(scaled, ((side - width) // 2, (side - height) // 2))
    return icon


def build(logo_path: Path) -> None:
    mark = cut_out_mark(logo_path)
    ASSETS.mkdir(parents=True, exist_ok=True)

    compose(mark, 192, SHARE).save(ASSETS / "icon-192.png")
    compose(mark, 512, SHARE).save(ASSETS / "icon-512.png")
    compose(mark, 512, SHARE_MASKABLE).save(ASSETS / "icon-maskable-512.png")

    logo = ROOT / "Sling TSI.png"
    if logo.exists():
        shutil.copy(logo, ASSETS / "sling_tsi.png")

    for item in sorted(ASSETS.iterdir()):
        print(f"{item.name:24} {item.stat().st_size:>8,} bytes")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Logo.png")
