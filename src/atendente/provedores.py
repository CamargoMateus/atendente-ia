"""Provedores de modelo: Anthropic (Claude) e OpenRouter (inclui modelos gratuitos).

A busca e o prompt são idênticos nos dois casos. O que muda aqui é só o formato
da chamada HTTP, o que mantém o resto do sistema independente de fornecedor.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

ANTHROPIC = "anthropic"
OPENROUTER = "openrouter"

MODELO_ANTHROPIC = "claude-opus-5"
MODELO_OPENROUTER_PADRAO = "google/gemma-4-31b-it:free"

URL_MODELOS = "https://openrouter.ai/api/v1/models"
URL_CHAT = "https://openrouter.ai/api/v1/chat/completions"

# Identificação do app para o painel da OpenRouter (opcional, boa prática).
CABECALHOS_ATRIBUICAO = {
    "HTTP-Referer": "https://atendente-ia.streamlit.app",
    "X-Title": "Atendente IA sobre documentos",
}


@dataclass
class Saida:
    texto: str
    tokens_entrada: int
    tokens_saida: int
    modelo: str


def listar_modelos_gratuitos(timeout: int = 20) -> list[str]:
    """Modelos com sufixo :free na OpenRouter, do maior contexto para o menor.

    Consultado ao vivo porque a lista de gratuitos muda com frequência: fixar
    nomes no código deixaria o app quebrado alguns meses depois.
    """
    try:
        with urllib.request.urlopen(URL_MODELOS, timeout=timeout) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return [MODELO_OPENROUTER_PADRAO]

    gratuitos = [m for m in dados.get("data", []) if m.get("id", "").endswith(":free")]
    gratuitos.sort(key=lambda m: -(m.get("context_length") or 0))
    ids = [m["id"] for m in gratuitos]

    if MODELO_OPENROUTER_PADRAO in ids:  # padrão primeiro, o resto na ordem de contexto
        ids.remove(MODELO_OPENROUTER_PADRAO)
        ids.insert(0, MODELO_OPENROUTER_PADRAO)
    return ids or [MODELO_OPENROUTER_PADRAO]


def montar_payload_openrouter(
    instrucoes: str, mensagens: list[dict], modelo: str
) -> dict:
    """Formato compatível com OpenAI: o sistema vira a primeira mensagem."""
    return {
        "model": modelo,
        "max_tokens": 1500,
        "temperature": 0.2,
        "messages": [{"role": "system", "content": instrucoes}, *mensagens],
    }


def chamar_openrouter(
    instrucoes: str, mensagens: list[dict], api_key: str, modelo: str, timeout: int = 90
) -> Saida:
    payload = montar_payload_openrouter(instrucoes, mensagens, modelo)
    requisicao = urllib.request.Request(
        URL_CHAT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **CABECALHOS_ATRIBUICAO,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        detalhe = erro.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"OpenRouter respondeu {erro.code}: {detalhe}") from erro

    # Modelos gratuitos às vezes devolvem erro dentro de um HTTP 200.
    if "error" in corpo and not corpo.get("choices"):
        raise RuntimeError(f"OpenRouter: {corpo['error'].get('message', corpo['error'])}")

    escolha = corpo["choices"][0]["message"]
    uso = corpo.get("usage") or {}
    return Saida(
        texto=(escolha.get("content") or "").strip(),
        tokens_entrada=uso.get("prompt_tokens", 0),
        tokens_saida=uso.get("completion_tokens", 0),
        modelo=corpo.get("model", modelo),
    )


def chamar_anthropic(
    instrucoes: str, mensagens: list[dict], api_key: str, modelo: str = MODELO_ANTHROPIC
) -> Saida:
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key)
    resposta = cliente.messages.create(
        model=modelo,
        max_tokens=1500,
        system=[{"type": "text", "text": instrucoes, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low"},
        messages=mensagens,
    )

    if resposta.stop_reason == "refusal":
        texto = "Não consigo responder essa pergunta. Vou encaminhar para o time humano."
    else:
        texto = "".join(b.text for b in resposta.content if b.type == "text")

    return Saida(
        texto=texto,
        tokens_entrada=resposta.usage.input_tokens,
        tokens_saida=resposta.usage.output_tokens,
        modelo=modelo,
    )
