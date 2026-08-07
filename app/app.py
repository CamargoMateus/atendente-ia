"""Atendente de IA: responde perguntas de clientes a partir dos documentos da empresa."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from atendente.busca import Indice  # noqa: E402
from atendente.corpus import carregar_trechos, resumo_do_corpus  # noqa: E402
from atendente.provedores import (  # noqa: E402
    ANTHROPIC,
    OPENROUTER,
    listar_modelos_gratuitos,
)
from atendente.responder import responder  # noqa: E402

PERGUNTAS_EXEMPLO = [
    "Comprei ontem e me arrependi, consigo devolver?",
    "Quanto tempo demora para chegar em Manaus?",
    "Posso pausar a assinatura no mês que vem?",
    "O café moído dura quanto tempo?",
    "Vocês parcelam? E tem desconto no Pix?",
    "Vocês atendem por telefone no domingo?",
]

st.set_page_config(page_title="Atendente IA", page_icon="💬", layout="centered")


@st.cache_resource
def preparar_indice():
    trechos = carregar_trechos()
    return trechos, Indice(trechos)


@st.cache_data(ttl=3600)
def modelos_gratuitos():
    return listar_modelos_gratuitos()


def segredo(nome: str) -> str:
    """st.secrets levanta exceção quando não há arquivo de secrets configurado."""
    try:
        return st.secrets.get(nome, "")
    except Exception:
        return ""


trechos, indice = preparar_indice()

st.title("💬 Atendente de IA")
st.markdown(
    "Um atendente que responde **somente com base nos documentos da empresa**, "
    "citando de onde tirou cada informação. O cenário aqui é uma loja de café por "
    "assinatura, mas a base pode ser trocada por manuais, contratos ou políticas "
    "de qualquer negócio."
)
st.caption(f"Base carregada: {resumo_do_corpus(trechos)}")

with st.sidebar:
    st.header("Configuração")
    escolha = st.radio(
        "Provedor do modelo",
        ["OpenRouter (modelos gratuitos)", "Anthropic (Claude)"],
        help="A busca nos documentos é a mesma nos dois casos. Muda só quem escreve a resposta.",
    )
    provedor = OPENROUTER if escolha.startswith("OpenRouter") else ANTHROPIC

    if provedor == OPENROUTER:
        modelo = st.selectbox("Modelo gratuito", modelos_gratuitos())
        chave = st.text_input(
            "Chave da OpenRouter",
            type="password",
            placeholder="sk-or-v1-...",
            help="Crie em openrouter.ai/keys. A chave fica só na sua sessão do navegador.",
        ) or segredo("OPENROUTER_API_KEY")
        st.caption(
            "Modelos gratuitos têm limite de requisições por minuto e por dia, "
            "e seguem menos à risca a instrução de citar a fonte."
        )
    else:
        modelo = None
        chave = st.text_input(
            "Chave da Anthropic",
            type="password",
            placeholder="sk-ant-...",
            help="A chave fica só na sua sessão do navegador.",
        ) or segredo("ANTHROPIC_API_KEY")

    st.markdown(
        "Sem chave o app roda em **modo busca**: mostra os trechos que seriam "
        "enviados ao modelo, com a pontuação de relevância."
    )
    st.divider()
    st.subheader("Documentos na base")
    for documento in sorted({t.documento for t in trechos}):
        st.markdown(f"- {documento}")
    st.divider()
    st.caption("Busca BM25 local, sem custo. Código aberto no GitHub.")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

st.subheader("Experimente")
colunas = st.columns(2)
pergunta_clicada = None
for i, exemplo in enumerate(PERGUNTAS_EXEMPLO):
    if colunas[i % 2].button(exemplo, key=f"ex{i}", width="stretch"):
        pergunta_clicada = exemplo


def mostrar_trechos(detalhes: list[dict]) -> None:
    for res in detalhes:
        st.markdown(f"**{res['citacao']}** · relevância {res['score']:.1f}")
        st.caption(res["texto"])


for mensagem in st.session_state.mensagens:
    with st.chat_message(mensagem["papel"]):
        st.markdown(mensagem["texto"])
        if mensagem.get("trechos"):
            with st.expander("Trechos consultados"):
                mostrar_trechos(mensagem["trechos"])

pergunta = st.chat_input("Escreva a dúvida do cliente...") or pergunta_clicada

if pergunta:
    st.session_state.mensagens.append({"papel": "user", "texto": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    resultados = indice.buscar(pergunta, k=5)
    detalhes = [
        {"citacao": r.trecho.citacao, "score": r.score, "texto": r.trecho.texto[:400]}
        for r in resultados
    ]

    with st.chat_message("assistant"):
        if not resultados:
            texto = (
                "Não encontrei nada sobre isso nos documentos da empresa. "
                "Vou encaminhar para o time humano."
            )
            st.markdown(texto)
            st.session_state.mensagens.append({"papel": "assistant", "texto": texto})
        elif not chave:
            texto = (
                "**Modo busca** (sem chave de API). Estes são os trechos que seriam "
                "enviados ao modelo para compor a resposta:"
            )
            st.markdown(texto)
            mostrar_trechos(detalhes)
            st.session_state.mensagens.append(
                {"papel": "assistant", "texto": texto, "trechos": detalhes}
            )
        else:
            with st.spinner("Consultando os documentos..."):
                try:
                    resposta = responder(
                        pergunta,
                        resultados,
                        api_key=chave,
                        provedor=provedor,
                        modelo=modelo,
                    )
                except Exception as erro:  # chave inválida, limite de uso, rede
                    texto = f"Não consegui gerar a resposta: {erro}"
                    st.error(texto)
                    st.session_state.mensagens.append({"papel": "assistant", "texto": texto})
                else:
                    st.markdown(resposta.texto)
                    with st.expander("Trechos consultados"):
                        mostrar_trechos(detalhes)
                    st.caption(
                        f"{resposta.modelo} · {resposta.tokens_entrada} tokens de "
                        f"entrada · {resposta.tokens_saida} de saída"
                    )
                    st.session_state.mensagens.append(
                        {"papel": "assistant", "texto": resposta.texto, "trechos": detalhes}
                    )
