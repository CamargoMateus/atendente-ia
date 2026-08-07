"""Carrega os documentos e quebra em trechos citáveis.

Cada trecho corresponde a uma seção (título de nível 2) do documento, que é a
unidade que o atendente cita na resposta: "Prazos e frete > Valor do frete".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PASTA_DADOS = RAIZ / "dados"


@dataclass(frozen=True)
class Trecho:
    documento: str
    secao: str
    texto: str

    @property
    def citacao(self) -> str:
        return f"{self.documento} > {self.secao}"


def _titulo_do_arquivo(caminho: Path, primeira_linha: str) -> str:
    if primeira_linha.startswith("# "):
        return primeira_linha[2:].strip()
    return caminho.stem.replace("-", " ").capitalize()


PALAVRAS_POR_PASSAGEM = 90


def _dividir_em_passagens(corpo: str) -> list[str]:
    """Quebra uma seção longa em passagens, sem cortar parágrafo ou lista no meio.

    Seção inteira como um bloco só prejudica o ranking (o BM25 penaliza texto
    longo) e deixa a citação vaga. Blocos menores dão pontuação mais justa ao
    trecho que realmente responde a pergunta.
    """
    blocos = [b.strip() for b in re.split(r"\n\s*\n", corpo) if b.strip()]
    passagens: list[str] = []
    atual: list[str] = []
    palavras = 0

    for bloco in blocos:
        n = len(bloco.split())
        if atual and palavras + n > PALAVRAS_POR_PASSAGEM:
            passagens.append("\n\n".join(atual))
            atual, palavras = [], 0
        atual.append(bloco)
        palavras += n

    if atual:
        passagens.append("\n\n".join(atual))
    return passagens


def carregar_trechos(pasta: Path | None = None) -> list[Trecho]:
    """Lê os .md da pasta de dados e devolve as passagens indexáveis."""
    pasta = pasta or PASTA_DADOS
    trechos: list[Trecho] = []

    for arquivo in sorted(pasta.glob("*.md")):
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
        if not linhas:
            continue
        documento = _titulo_do_arquivo(arquivo, linhas[0])

        secao_atual = "Introdução"
        buffer: list[str] = []

        def fechar() -> None:
            corpo = "\n".join(buffer).strip()
            for passagem in _dividir_em_passagens(corpo):
                trechos.append(Trecho(documento=documento, secao=secao_atual, texto=passagem))

        for linha in linhas[1:]:
            if linha.startswith("## "):
                fechar()
                secao_atual = linha[3:].strip()
                buffer = []
            else:
                buffer.append(linha)
        fechar()

    return trechos


def formatar_para_prompt(trechos: list[Trecho]) -> str:
    """Monta o bloco de contexto que vai no prompt, com as citações explícitas."""
    partes = []
    for i, t in enumerate(trechos, start=1):
        partes.append(f"[{i}] {t.citacao}\n{t.texto}")
    return "\n\n".join(partes)


def resumo_do_corpus(trechos: list[Trecho]) -> str:
    documentos = sorted({t.documento for t in trechos})
    palavras = sum(len(re.findall(r"\w+", t.texto)) for t in trechos)
    return f"{len(documentos)} documentos · {len(trechos)} seções · {palavras} palavras"
