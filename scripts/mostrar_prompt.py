"""Imprime exatamente o que é enviado ao modelo para uma pergunta.

Serve para auditar o sistema sem gastar chamada de API: mostra os trechos que a
busca escolheu, a pontuação de cada um e o texto final do prompt.

Uso: python scripts/mostrar_prompt.py "quanto tempo demora para chegar em Manaus"
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from atendente.busca import Indice, normalizar
from atendente.corpus import carregar_trechos
from atendente.responder import INSTRUCOES, montar_mensagem

PERGUNTA_PADRAO = "Comprei ontem e me arrependi, consigo devolver?"


def main() -> None:
    pergunta = " ".join(sys.argv[1:]) or PERGUNTA_PADRAO
    trechos = carregar_trechos()
    indice = Indice(trechos)
    resultados = indice.buscar(pergunta, k=5)

    print("=" * 72)
    print("PERGUNTA:", pergunta)
    print("TERMOS APÓS NORMALIZAÇÃO E RADICAL:", normalizar(pergunta))
    print("=" * 72)
    print(f"\nTRECHOS ESCOLHIDOS PELA BUSCA (de {len(trechos)} no total):\n")
    for i, r in enumerate(resultados, start=1):
        print(f"  [{i}] {r.trecho.citacao}  (relevância {r.score:.2f})")

    print("\n" + "=" * 72)
    print("INSTRUÇÕES ENVIADAS (system prompt):")
    print("=" * 72)
    print(INSTRUCOES)

    print("\n" + "=" * 72)
    print("MENSAGEM ENVIADA (user):")
    print("=" * 72)
    print(montar_mensagem(pergunta, resultados))


if __name__ == "__main__":
    main()
