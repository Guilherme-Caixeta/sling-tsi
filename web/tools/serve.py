# -*- coding: utf-8 -*-
"""Servidor local para testar o PWA no iPad, sem cache atrapalhando.

O `python -m http.server` nao manda cabecalho de cache nenhum, e ai o
navegador decide sozinho guardar os arquivos — no Safari isso faz o app
continuar mostrando a versao antiga depois de uma alteracao. Aqui todo
arquivo sai com `Cache-Control: no-store`, entao cada recarregamento pega o
que esta no disco.

Uso:
    python web/tools/serve.py [porta]

Depois abra no iPad o endereco que aparece na tela, com o aparelho na mesma
rede Wi-Fi do computador.

Lembre-se: por `http://` o navegador nao libera o microfone (comandos de voz)
nem instala o service worker (modo offline). Para isso e preciso HTTPS.
"""

from __future__ import annotations

import socket
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent


class SemCache(SimpleHTTPRequestHandler):
    """Igual ao servidor padrao, mas pedindo para nao guardar nada."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, formato: str, *args) -> None:
        # so os erros interessam durante o teste
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(formato, *args)


def ip_da_rede() -> str:
    """Descobre o IP que o iPad enxerga (sem depender de DNS)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main() -> int:
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    manipulador = partial(SemCache, directory=str(WEB_DIR))
    servidor = ThreadingHTTPServer(("0.0.0.0", porta), manipulador)

    print(f"  servindo {WEB_DIR}")
    print(f"  neste computador : http://localhost:{porta}")
    print(f"  no iPad          : http://{ip_da_rede()}:{porta}")
    print("  (Ctrl+C para parar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  servidor parado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
