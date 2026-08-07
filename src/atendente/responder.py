"""Monta o prompt e gera a resposta do atendente, presa aos documentos."""

from __future__ import annotations

from dataclasses import dataclass

from .busca import Resultado
from .corpus import formatar_para_prompt
from .provedores import (
    ANTHROPIC,
    MODELO_ANTHROPIC,
    OPENROUTER,
    chamar_anthropic,
    chamar_openrouter,
    chamar_openrouter_com_reserva,
)

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
    modelo: str


def montar_mensagem(pergunta: str, resultados: list[Resultado]) -> str:
    """Texto exato que vai ao modelo: os trechos recuperados e depois a pergunta."""
    contexto = formatar_para_prompt([r.trecho for r in resultados])
    return (
        f"Trechos dos documentos da empresa:\n\n{contexto}\n\n"
        f"Pergunta do cliente: {pergunta}"
    )


def responder(
    pergunta: str,
    resultados: list[Resultado],
    api_key: str,
    provedor: str = ANTHROPIC,
    modelo: str | None = None,
    historico: list[dict] | None = None,
) -> Resposta:
    mensagens: list[dict] = list(historico or [])
    mensagens.append({"role": "user", "content": montar_mensagem(pergunta, resultados)})

    if provedor == OPENROUTER:
        if modelo:
            saida = chamar_openrouter(INSTRUCOES, mensagens, api_key=api_key, modelo=modelo)
        else:  # sem modelo escolhido, percorre a fila de reserva
            saida = chamar_openrouter_com_reserva(INSTRUCOES, mensagens, api_key=api_key)
    else:
        saida = chamar_anthropic(
            INSTRUCOES, mensagens, api_key=api_key, modelo=modelo or MODELO_ANTHROPIC
        )

    return Resposta(
        texto=saida.texto,
        citacoes=[r.trecho.citacao for r in resultados],
        tokens_entrada=saida.tokens_entrada,
        tokens_saida=saida.tokens_saida,
        modelo=saida.modelo,
    )
