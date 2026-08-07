"""Mostra, com dado real, cada etapa entre a pergunta do cliente e a resposta.

Serve para explicar o sistema a quem não programa: imprime o arquivo no disco,
o pedaço como objeto, a conta da busca e o JSON exato que trafega na internet.

Uso: python scripts/passo_a_passo.py "sua pergunta aqui"
"""

import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from atendente.busca import B, K1, Indice, normalizar
from atendente.corpus import PASTA_DADOS, carregar_trechos
from atendente.provedores import MODELO_OPENROUTER_PADRAO, montar_payload_openrouter
from atendente.responder import INSTRUCOES, montar_mensagem

PERGUNTA_PADRAO = "Comprei ontem e me arrependi, consigo devolver?"


def titulo(n: int, texto: str) -> None:
    print(f"\n{'=' * 78}\nETAPA {n}: {texto}\n{'=' * 78}")


def main() -> None:
    pergunta = " ".join(sys.argv[1:]) or PERGUNTA_PADRAO

    titulo(0, "OS ARQUIVOS, NO DISCO")
    for arquivo in sorted(PASTA_DADOS.glob("*.md")):
        print(f"  {arquivo}  ({arquivo.stat().st_size} bytes)")

    exemplo = sorted(PASTA_DADOS.glob("*.md"))[0]
    print(f"\n  Primeiras 8 linhas de {exemplo.name}, exatamente como estão gravadas:\n")
    for i, linha in enumerate(exemplo.read_text(encoding="utf-8").splitlines()[:8], 1):
        print(f"    {i:>2}| {linha}")

    titulo(1, "QUEM CORTA O ARQUIVO EM PEDAÇOS (é o Python, não a IA)")
    print("  Regra: toda linha que começa com '## ' inicia um pedaço novo.")
    print(f"\n  Linhas com '## ' encontradas em {exemplo.name}:")
    for i, linha in enumerate(exemplo.read_text(encoding="utf-8").splitlines(), 1):
        if linha.startswith("## "):
            print(f"    linha {i:>2} -> pedaço '{linha[3:]}'")

    trechos = carregar_trechos()
    titulo(2, "O QUE É UM PEDAÇO: um objeto com três campos")
    t = trechos[1]
    print(f"  documento = {t.documento!r}")
    print(f"  secao     = {t.secao!r}")
    print(f"  texto     = {t.texto[:110]!r}...")
    print(f"\n  Total de pedaços na memória: {len(trechos)}")

    titulo(3, "A PERGUNTA DO CLIENTE VIRA UMA LISTA DE PALAVRAS (ainda sem IA)")
    print(f"  Digitado:  {pergunta!r}")
    termos = normalizar(pergunta)
    print(f"  Vira:      {termos}")

    indice = Indice(trechos)
    resultados = indice.buscar(pergunta, k=5)

    titulo(4, "A CONTA DA BUSCA, PEDAÇO POR PEDAÇO")
    melhor = resultados[0]
    posicao = trechos.index(melhor.trecho)
    freq: Counter = indice.frequencias[posicao]
    tamanho = indice.tamanhos[posicao]
    print(f"  Pedaço campeão: {melhor.trecho.citacao}")
    print(f"  Ele tem {tamanho} palavras (a média dos pedaços é {indice.media_tamanho:.0f}).\n")
    print("  palavra da pergunta | aparece? | raridade | pontos que soma")
    print("  " + "-" * 62)
    total = 0.0
    for termo in termos:
        vezes = freq.get(termo, 0)
        if vezes:
            idf = indice.idf.get(termo, 0.0)
            norm = 1 - B + B * (tamanho / indice.media_tamanho)
            pontos = idf * (vezes * (K1 + 1)) / (vezes + K1 * norm)
            total += pontos
            print(f"  {termo:<19} | {vezes}x       | {idf:>6.2f}   | {pontos:>6.2f}")
        else:
            print(f"  {termo:<19} | não      |    -     |   0.00")
    print("  " + "-" * 62)
    print(f"  {'TOTAL':<19} |          |          | {total:>6.2f}")

    print("\n  Ranking final (os 5 que serão enviados):")
    for i, r in enumerate(resultados, 1):
        print(f"    [{i}] {r.score:>5.2f}  {r.trecho.citacao}")

    titulo(5, "O JSON EXATO QUE SAI PELA INTERNET (POST para a OpenRouter)")
    mensagens = [{"role": "user", "content": montar_mensagem(pergunta, resultados)}]
    payload = montar_payload_openrouter(INSTRUCOES, mensagens, MODELO_OPENROUTER_PADRAO)
    bruto = json.dumps(payload, ensure_ascii=False, indent=2)
    print(f"  Endereço: https://openrouter.ai/api/v1/chat/completions")
    print(f"  Tamanho do corpo: {len(bruto)} caracteres\n")
    linhas = bruto.splitlines()
    for linha in linhas[:14]:
        print("  " + (linha[:150] + "…" if len(linha) > 150 else linha))
    print(f"  ... (mais {len(linhas) - 14} linhas com os 5 trechos e a pergunta) ...")

    titulo(6, "O QUE A IA RECEBE, EM RESUMO")
    print(f"  system : {len(INSTRUCOES)} caracteres de instruções (as regras anti-invenção)")
    print(f"  user   : {len(mensagens[0]['content'])} caracteres = 5 trechos + a pergunta")
    print("\n  A IA NÃO recebe: os arquivos inteiros, a pasta, nem os outros 37 pedaços.")
    print("  A IA NÃO guarda nada: na próxima pergunta, tudo é enviado de novo.")


if __name__ == "__main__":
    main()
