"""Gera a resposta do atendente com a API da Anthropic, presa aos documentos."""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from .busca import Resultado
from .corpus import formatar_para_prompt

MODELO = "claude-opus-5"

INSTRUCOES = """Você é o atendente virtual da Lumina Café, uma loja de café por assinatura.

Responda usando exclusivamente os trechos de documentos fornecidos. Regras:

1. Se a resposta não estiver nos trechos, diga que não tem essa informação e ofereça encaminhar para o time humano. Nunca invente prazo, valor, política ou dado de contato.
2. Cite a origem de cada informação no formato [n], usando o número do trecho.
3. Responda em português do Brasil, de forma direta e cordial, em no máximo dois parágrafos curtos.
4. Quando o cliente pedir algo que depende de dados da conta dele (número do pedido, status de entrega), explique o caminho para ele obter isso.
5. Não use travessão como pontuação."""


@dataclass
class Resposta:
    texto: str
    citacoes: list[str]
    tokens_entrada: int
    tokens_saida: int


def responder(
    pergunta: str,
    resultados: list[Resultado],
    api_key: str,
    historico: list[dict] | None = None,
) -> Resposta:
    """Chama o modelo com os trechos recuperados e devolve a resposta citada."""
    trechos = [r.trecho for r in resultados]
    contexto = formatar_para_prompt(trechos)

    mensagens: list[dict] = list(historico or [])
    mensagens.append(
        {
            "role": "user",
            "content": (
                f"Trechos dos documentos da empresa:\n\n{contexto}\n\n"
                f"Pergunta do cliente: {pergunta}"
            ),
        }
    )

    cliente = anthropic.Anthropic(api_key=api_key)
    resposta = cliente.messages.create(
        model=MODELO,
        max_tokens=1500,
        system=[{"type": "text", "text": INSTRUCOES, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low"},
        messages=mensagens,
    )

    if resposta.stop_reason == "refusal":
        return Resposta(
            texto="Não consigo responder essa pergunta. Encaminhe para o time humano.",
            citacoes=[],
            tokens_entrada=resposta.usage.input_tokens,
            tokens_saida=resposta.usage.output_tokens,
        )

    texto = "".join(b.text for b in resposta.content if b.type == "text")
    citacoes = [t.citacao for t in trechos]
    return Resposta(
        texto=texto,
        citacoes=citacoes,
        tokens_entrada=resposta.usage.input_tokens,
        tokens_saida=resposta.usage.output_tokens,
    )
