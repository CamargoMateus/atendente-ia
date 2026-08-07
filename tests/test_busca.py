"""Mede o recall da busca: a seção certa aparece entre os k trechos enviados ao modelo?

O critério é recall@k, não a primeira posição. Numa arquitetura RAG a busca
existe para garantir que o trecho correto chegue ao modelo; escolher entre os
trechos é trabalho do modelo, que lê todos eles. Perguntas como "quanto tempo
demora para chegar em Manaus" têm dois termos genéricos que casam com a seção
errada e um único termo raro que aponta a certa, e por isso não ficam em
primeiro lugar numa busca lexical.

Uso: python tests/test_busca.py  (da raiz do projeto)
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from atendente.busca import Indice
from atendente.corpus import carregar_trechos

K = 5  # mesmo k usado pelo app ao montar o contexto do modelo

# pergunta -> seção que precisa estar entre os k trechos recuperados
CASOS = {
    "Comprei ontem e me arrependi, consigo devolver?": "Prazo de arrependimento",
    "quanto tempo demora para chegar em manaus": "Prazo de entrega por região",
    "posso pausar a assinatura": "Pausar a assinatura",
    "o café moído dura quanto tempo": "Validade e armazenamento",
    "vocês parcelam a compra": "Parcelamento",
    "tem desconto no pix": "Pix",
    "vocês atendem por telefone": "Canais e horários",
    "meu pedido atrasou muito": "Pedido atrasado ou extraviado",
    "quero cancelar sem pagar multa": "Cancelamento",
    "vocês têm café descafeinado": "Cafés descafeinados",
}


def main() -> int:
    trechos = carregar_trechos()
    indice = Indice(trechos)
    falhas = []

    for pergunta, esperado in CASOS.items():
        top = [r.trecho.secao for r in indice.buscar(pergunta, k=K)]
        if esperado not in top:
            falhas.append(f"  {pergunta!r}\n    esperado: {esperado}\n    veio: {top}")

    print(f"corpus: {len(trechos)} trechos")
    if falhas:
        print(f"FALHOU {len(falhas)}/{len(CASOS)}:")
        print("\n".join(falhas))
        return 1

    print(f"ok: recall@{K} de {len(CASOS)}/{len(CASOS)} nas perguntas de teste")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
