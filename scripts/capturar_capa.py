"""Captura a imagem de capa do app com uma conversa real acontecendo.

Uso: python scripts/capturar_capa.py [url]
Requer playwright (usa o Chrome instalado, sem baixar navegador).

Nota sobre a técnica: o Streamlit renderiza dentro de shadow DOM e mantém um
websocket aberto, então nem seletor de texto nem `networkidle` funcionam aqui.
Por isso a espera é por tempo fixo e o clique é por coordenada.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://atendente-ia.streamlit.app"
DESTINO = Path(__file__).resolve().parents[1] / "docs"

LARGURA, ALTURA = 1600, 900
BOTAO_PRIMEIRA_PERGUNTA = (770, 397)
ESPERA_CARREGAR_MS = 30_000
ESPERA_RESPOSTA_MS = 35_000

SEM_TOOLBAR = """
[data-testid="stToolbar"], [data-testid="stStatusWidget"], #MainMenu, footer,
[data-testid="manage-app-button"] { display: none !important; }
"""


def capturar() -> None:
    DESTINO.mkdir(exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="chrome")
        pagina = navegador.new_page(
            viewport={"width": LARGURA, "height": ALTURA}, device_scale_factor=2
        )
        pagina.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        pagina.wait_for_timeout(ESPERA_CARREGAR_MS)
        pagina.add_style_tag(content=SEM_TOOLBAR)

        pagina.mouse.click(*BOTAO_PRIMEIRA_PERGUNTA)
        pagina.wait_for_timeout(ESPERA_RESPOSTA_MS)
        pagina.mouse.move(10, 10)
        pagina.wait_for_timeout(1000)

        capa = DESTINO / "capa.png"
        pagina.screenshot(path=str(capa))
        print(f"[ok] {capa} ({capa.stat().st_size / 1024:.0f} KB)")
        navegador.close()


if __name__ == "__main__":
    capturar()
