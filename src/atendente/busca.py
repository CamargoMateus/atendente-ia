"""Busca lexical BM25 sobre os trechos, sem dependência externa.

BM25 foi escolhido no lugar de embeddings porque o corpus é pequeno, as
perguntas usam o mesmo vocabulário dos documentos e não há custo nem chave de
API envolvidos na busca. Trocar por embeddings depois é substituir só este
módulo: a interface (`Indice.buscar`) permanece.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .corpus import Trecho

K1 = 1.5
B = 0.75

# Stopwords do português que só adicionam ruído ao ranking.
STOPWORDS = {
    "a", "à", "ao", "aos", "as", "às", "com", "como", "da", "das", "de", "do",
    "dos", "e", "é", "em", "essa", "esse", "esta", "este", "eu", "for", "foi",
    "ha", "há", "isso", "ja", "já", "la", "lhe", "mais", "mas", "me", "mesmo",
    "meu", "muito", "na", "nao", "não", "nas", "no", "nos", "num", "numa", "o",
    "os", "ou", "para", "pela", "pelo", "por", "posso", "pode", "qual", "quais",
    "quando", "que", "quem", "se", "sem", "ser", "seu", "sua", "tem", "tenho",
    "ter", "um", "uma", "vai", "voces", "vocês", "você", "voce",
}


# Sufixos removidos do maior para o menor. Sem isso a busca não liga a palavra
# do cliente ("me arrependi", "vocês parcelam") à do documento
# ("arrependimento", "parcelamento"), que é a falha clássica de busca lexical.
SUFIXOS = (
    "mentos", "mento", "coes", "cao", "adores", "ador", "antes", "ante",
    "aram", "eram", "iram", "ando", "endo", "indo", "amos", "emos", "imos",
    "aria", "eria", "iria", "adas", "ados", "idas", "idos", "ada", "ado",
    "ida", "ido", "ava", "iam", "vel", "am", "em", "ar", "er", "ir",
    "as", "es", "os", "is", "s",
)
TAMANHO_MINIMO_RADICAL = 4


def radical(palavra: str) -> str:
    """Reduz a palavra ao radical, cortando sufixo e vogal final."""
    for sufixo in SUFIXOS:
        if palavra.endswith(sufixo):
            candidato = palavra[: -len(sufixo)]
            if len(candidato) >= TAMANHO_MINIMO_RADICAL:
                palavra = candidato
                break
    if len(palavra) > TAMANHO_MINIMO_RADICAL and palavra[-1] in "aeo":
        palavra = palavra[:-1]
    return palavra


def normalizar(texto: str) -> list[str]:
    """Minúsculas, sem acento, sem pontuação, sem stopwords, reduzido ao radical."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    palavras = re.findall(r"[a-z0-9]+", sem_acento)
    return [radical(p) for p in palavras if p not in STOPWORDS]


@dataclass
class Resultado:
    trecho: Trecho
    score: float


class Indice:
    """Índice BM25 construído em memória a partir dos trechos."""

    def __init__(self, trechos: list[Trecho]) -> None:
        self.trechos = trechos
        # O título entra na indexação uma única vez. Repeti-lo para dar peso extra
        # fazia seções curtas de título genérico ("Tempo de resposta") vencerem a
        # seção longa que continha de fato o termo buscado ("Manaus").
        self.tokens = [normalizar(f"{t.secao} {t.texto}") for t in trechos]
        self.tamanhos = [len(toks) for toks in self.tokens]
        self.media_tamanho = (sum(self.tamanhos) / len(self.tamanhos)) if self.tamanhos else 0.0
        self.frequencias = [Counter(toks) for toks in self.tokens]

        documentos_por_termo: Counter[str] = Counter()
        for freq in self.frequencias:
            documentos_por_termo.update(freq.keys())

        total = len(trechos)
        self.idf = {
            termo: math.log(1 + (total - n + 0.5) / (n + 0.5))
            for termo, n in documentos_por_termo.items()
        }

    def buscar(self, pergunta: str, k: int = 4) -> list[Resultado]:
        termos = normalizar(pergunta)
        if not termos:
            return []

        resultados: list[Resultado] = []
        for i, freq in enumerate(self.frequencias):
            score = 0.0
            for termo in termos:
                if termo not in freq:
                    continue
                tf = freq[termo]
                norm = 1 - B + B * (self.tamanhos[i] / self.media_tamanho or 1)
                score += self.idf.get(termo, 0.0) * (tf * (K1 + 1)) / (tf + K1 * norm)
            if score > 0:
                resultados.append(Resultado(trecho=self.trechos[i], score=score))

        resultados.sort(key=lambda r: r.score, reverse=True)
        return resultados[:k]
