"""Atendente de IA: responde perguntas de clientes a partir dos documentos da empresa."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from atendente.busca import Indice  # noqa: E402
from atendente.corpus import carregar_trechos, resumo_do_corpus  # noqa: E402
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
    chave = st.text_input(
        "Chave da API Anthropic",
        type="password",
        help="A chave fica só na sua sessão do navegador e não é gravada em lugar nenhum.",
        placeholder="sk-ant-...",
    )
    if not chave:
        # st.secrets levanta exceção quando não existe arquivo de secrets,
        # que é justamente o caso ao rodar localmente sem configuração.
        try:
            chave = st.secrets.get("ANTHROPIC_API_KEY", "")
        except Exception:
            chave = ""
    st.markdown(
        "Sem chave o app roda em **modo busca**: mostra os trechos que seriam "
        "enviados ao modelo, com a pontuação de relevância. Com chave, gera a "
        "resposta final citada."
    )
    st.divider()
    st.subheader("Documentos na base")
    for documento in sorted({t.documento for t in trechos}):
        st.markdown(f"- {documento}")
    st.divider()
    st.caption("Busca BM25 local + geração com Claude. Código aberto no GitHub.")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

st.subheader("Experimente")
colunas = st.columns(2)
pergunta_clicada = None
for i, exemplo in enumerate(PERGUNTAS_EXEMPLO):
    if colunas[i % 2].button(exemplo, key=f"ex{i}", width="stretch"):
        pergunta_clicada = exemplo

for mensagem in st.session_state.mensagens:
    with st.chat_message(mensagem["papel"]):
        st.markdown(mensagem["texto"])
        if mensagem.get("trechos"):
            with st.expander("Trechos consultados"):
                for res in mensagem["trechos"]:
                    st.markdown(f"**{res['citacao']}** · relevância {res['score']:.1f}")
                    st.caption(res["texto"])

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
                "**Modo busca** (sem chave da API). Estes são os trechos que seriam "
                "enviados ao modelo para compor a resposta:"
            )
            st.markdown(texto)
            for res in detalhes:
                st.markdown(f"**{res['citacao']}** · relevância {res['score']:.1f}")
                st.caption(res["texto"])
            st.session_state.mensagens.append(
                {"papel": "assistant", "texto": texto, "trechos": detalhes}
            )
        else:
            with st.spinner("Consultando os documentos..."):
                try:
                    resposta = responder(pergunta, resultados, api_key=chave)
                except Exception as erro:  # chave inválida, rede, limite de uso
                    texto = f"Não consegui gerar a resposta: {erro}"
                    st.error(texto)
                    st.session_state.mensagens.append({"papel": "assistant", "texto": texto})
                else:
                    st.markdown(resposta.texto)
                    with st.expander("Trechos consultados"):
                        for res in detalhes:
                            st.markdown(f"**{res['citacao']}** · relevância {res['score']:.1f}")
                            st.caption(res["texto"])
                    st.caption(
                        f"{resposta.tokens_entrada} tokens de entrada · "
                        f"{resposta.tokens_saida} de saída"
                    )
                    st.session_state.mensagens.append(
                        {"papel": "assistant", "texto": resposta.texto, "trechos": detalhes}
                    )
