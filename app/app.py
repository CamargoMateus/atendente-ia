"""Atendente de IA: responde perguntas de clientes a partir dos documentos da empresa."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from atendente.busca import Indice  # noqa: E402
from atendente.corpus import carregar_trechos, resumo_do_corpus  # noqa: E402
from atendente.provedores import ANTHROPIC, OPENROUTER  # noqa: E402
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


def segredo(nome: str) -> str:
    """Lê dos Secrets do Streamlit e, se não houver, da variável de ambiente.

    st.secrets levanta exceção quando não existe arquivo de secrets, que é o
    caso ao rodar localmente sem configuração.
    """
    try:
        valor = st.secrets.get(nome, "")
    except Exception:
        valor = ""
    return valor or os.environ.get(nome, "")


trechos, indice = preparar_indice()

st.title("💬 Atendente de IA")
st.markdown(
    "Um atendente que responde **somente com base nos documentos da empresa**, "
    "citando de onde tirou cada informação. O cenário aqui é uma loja de café por "
    "assinatura, mas a base pode ser trocada por manuais, contratos ou políticas "
    "de qualquer negócio."
)
st.caption(f"Base carregada: {resumo_do_corpus(trechos)}")

# A chave vive no servidor (Secrets do Streamlit ou variável de ambiente), nunca
# na interface: o visitante abre o link e usa, sem configurar nada.
chave_openrouter = segredo("OPENROUTER_API_KEY")
chave_anthropic = segredo("ANTHROPIC_API_KEY")
if chave_openrouter:
    provedor, chave, modelo = OPENROUTER, chave_openrouter, None
elif chave_anthropic:
    provedor, chave, modelo = ANTHROPIC, chave_anthropic, None
else:
    provedor, chave, modelo = OPENROUTER, "", None

with st.sidebar:
    st.header("Documentos na base")
    for documento in sorted({t.documento for t in trechos}):
        st.markdown(f"- {documento}")
    st.caption(
        "Troque estes arquivos pelos documentos da sua empresa e o atendente passa "
        "a responder sobre eles, sem nenhuma mudança no código."
    )
    st.divider()
    st.subheader("Como funciona")
    st.markdown(
        "1. A pergunta vira uma lista de palavras\n"
        "2. Uma busca BM25 pontua as 42 seções dos documentos\n"
        "3. As 5 mais relevantes vão para o modelo, junto da pergunta\n"
        "4. O modelo responde citando os trechos, ou diz que não encontrou"
    )
    st.caption("Busca local, sem custo. Resposta por modelo gratuito da OpenRouter.")
    st.divider()
    st.caption("Código aberto: github.com/CamargoMateus/atendente-ia")

if not chave:
    st.info(
        "**Modo busca.** A busca nos documentos está funcionando e mostra os trechos "
        "que respondem à pergunta, mas a redação final está desligada porque não há "
        "chave configurada no servidor. Para ligar, defina `OPENROUTER_API_KEY` nos "
        "Secrets do app."
    )

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
