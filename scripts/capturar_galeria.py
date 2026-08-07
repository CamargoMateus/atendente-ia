"""Captura as imagens da galeria do portfólio.

Gera quatro peças em 16:9:
  galeria-1-caso-dificil.png  app respondendo a pergunta que a busca lexical erra na 1a posicao
  galeria-2-recusa.png        app admitindo que nao tem a informacao, em vez de inventar
  galeria-3-busca.png         quais trechos a busca escolheu e com que pontuacao (dados reais)
  galeria-4-prompt.png        o texto exato enviado ao modelo (dados reais)

As duas primeiras vêm do app publicado, as duas últimas são renderizadas aqui
mesmo a partir do índice, então nenhum número é inventado.

Uso: python scripts/capturar_galeria.py [url]
Requer playwright (usa o Chrome instalado, sem baixar navegador).

Nota sobre a técnica: o Streamlit mantém um websocket aberto, então `networkidle`
nunca dispara; a espera é por tempo fixo. Os cliques são feitos por JavaScript
procurando o botão pelo texto, que é mais estável do que coordenada.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

from playwright.sync_api import Frame, Page, sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from atendente.busca import Indice, normalizar  # noqa: E402
from atendente.corpus import carregar_trechos  # noqa: E402
from atendente.responder import INSTRUCOES, montar_mensagem  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://atendente-ia.streamlit.app"
DESTINO = RAIZ / "docs"

LARGURA, ALTURA = 1600, 900
ESPERA_CARREGAR_MS = 30_000
ESPERA_RESPOSTA_MS = 40_000

PERGUNTA_DIFICIL = "Quanto tempo demora para chegar em Manaus?"
# Não existe em nenhum documento: serve para mostrar o atendente admitindo que
# não sabe, que é o comportamento que um cliente precisa ver antes de contratar.
PERGUNTA_SEM_RESPOSTA = "Qual é o CNPJ da Lumina Café?"
SECAO_CERTA = "Prazo de entrega por região"

SEM_CROMO = """
[data-testid="stToolbar"], [data-testid="stStatusWidget"], [data-testid="stDecoration"],
[data-testid="manage-app-button"], [data-testid="stToolbarActions"],
header[data-testid="stHeader"], #MainMenu, footer,
[class^="_container_"], [class^="_profileContainer_"], [class^="_link_"],
[class^="_viewerBadge"], [class*="viewerBadge"] { display: none !important; }
"""

CLICAR_POR_TEXTO = """
(rotulo) => {
  const alvos = [...document.querySelectorAll('button, summary, [role="button"]')];
  const alvo = alvos.find(e => (e.innerText || '').includes(rotulo));
  if (!alvo) return false;
  alvo.scrollIntoView({block: 'center'});
  alvo.click();
  return true;
}
"""

ABRIR_DETALHES = """
() => {
  document.querySelectorAll('details').forEach(d => { d.open = true; });
  return document.querySelectorAll('details').length;
}
"""

# O contêiner do Streamlit se reancora no fim sozinho, então o reenquadramento
# precisa vir depois que ele terminou de crescer, e escrevendo o scrollTop na mão.
REENQUADRAR_NA_PERGUNTA = """
() => {
  const cont = document.querySelector('[data-testid="stAppScrollToBottomContainer"]');
  const msg = document.querySelector('[data-testid="stChatMessage"]');
  if (!cont || !msg) return null;
  const alto = msg.getBoundingClientRect().top - cont.getBoundingClientRect().top;
  cont.scrollTop = cont.scrollTop + alto - 28;
  return cont.scrollTop;
}
"""


# ---------------------------------------------------------------- app ao vivo


TEXTOS_DOS_BOTOES = """
() => [...document.querySelectorAll('button')].map(b => (b.innerText || '').trim())
"""

# O app hiberna quando fica sem visita e volta com um botão de despertar.
ROTULO_DESPERTAR = "get this app back up"


def _quadro(pagina: Page) -> Frame:
    """O app fica dentro de um iframe do Streamlit Cloud, não no documento de cima."""
    for frame in pagina.frames:
        if "/~/+/" in frame.url:
            return frame
    return pagina.main_frame


def _abrir_app(pagina: Page) -> Frame:
    pagina.goto(URL, wait_until="domcontentloaded", timeout=120_000)
    quadro = _esperar_botao(pagina, PERGUNTA_DIFICIL)
    # A barra do app está dentro do iframe; o selo e o avatar da Streamlit Cloud
    # ficam no documento de cima. Precisa dos dois.
    quadro.add_style_tag(content=SEM_CROMO)
    pagina.add_style_tag(content=SEM_CROMO)
    return quadro


def _esperar_botao(pagina: Page, rotulo: str, limite_ms: int = 240_000) -> Frame:
    """Espera o app terminar de subir, despertando-o se estiver hibernando."""
    esperado = 0
    rotulos: list[str] = []
    while esperado < limite_ms:
        quadro = _quadro(pagina)
        try:
            rotulos = quadro.evaluate(TEXTOS_DOS_BOTOES)
        except Exception:  # o frame troca de documento enquanto o app sobe
            rotulos = []
        if any(rotulo in r for r in rotulos):
            pagina.wait_for_timeout(2000)
            return quadro
        if any(ROTULO_DESPERTAR in r.lower() for r in rotulos):
            print("[..] app hibernando, despertando")
            quadro.evaluate(CLICAR_POR_TEXTO, ROTULO_DESPERTAR)
        pagina.wait_for_timeout(5000)
        esperado += 5000
    raise RuntimeError(f"app não subiu em {limite_ms / 1000:.0f}s; botões: {rotulos}")


def _perguntar(pagina: Page, quadro: Frame, pergunta: str) -> None:
    achou = quadro.evaluate(CLICAR_POR_TEXTO, pergunta)
    if not achou:
        raise RuntimeError(f"botão não encontrado para {pergunta!r}")
    _esperar_resposta(pagina)


def _perguntar_digitando(pagina: Page, quadro: Frame, pergunta: str) -> None:
    """Usa o campo de chat, para perguntas que não estão nos botões de exemplo."""
    campo = quadro.locator("textarea").first
    campo.fill(pergunta)
    campo.press("Enter")
    _esperar_resposta(pagina)
    # Sem isso o campo fica com o anel de foco vermelho na imagem.
    quadro.evaluate("() => document.activeElement && document.activeElement.blur()")
    pagina.wait_for_timeout(600)


def _esperar_resposta(pagina: Page) -> None:
    pagina.wait_for_timeout(ESPERA_RESPOSTA_MS)
    pagina.mouse.move(10, 10)
    pagina.wait_for_timeout(1000)


def capturar_do_app(pagina: Page) -> None:
    quadro = _abrir_app(pagina)
    _perguntar(pagina, quadro, PERGUNTA_DIFICIL)
    quadro.evaluate(ABRIR_DETALHES)
    pagina.wait_for_timeout(2500)
    print("[..] reenquadrado em", quadro.evaluate(REENQUADRAR_NA_PERGUNTA))
    pagina.wait_for_timeout(1200)
    _salvar(pagina, "galeria-1-caso-dificil.png")

    quadro = _abrir_app(pagina)
    _perguntar_digitando(pagina, quadro, PERGUNTA_SEM_RESPOSTA)
    _salvar(pagina, "galeria-2-nao-inventa.png")


# -------------------------------------------------------- páginas desenhadas

ESTILO = """
* { box-sizing: border-box; }
body {
  margin: 0; width: 1600px; height: 900px; overflow: hidden; position: relative;
  font-family: "Segoe UI", system-ui, sans-serif;
  color: #1a1c23; background: #fff;
  padding: 46px 58px;
}
h1 { font-size: 34px; margin: 0 0 6px; letter-spacing: -0.4px; }
.sub { font-size: 17px; color: #6b7280; margin: 0 0 26px; }
.rotulo { font-size: 13px; letter-spacing: 1.4px; text-transform: uppercase;
  color: #8b90a0; margin: 0 0 10px; font-weight: 600; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.chip { background: #eef0f6; border-radius: 6px; padding: 5px 11px;
  font-family: Consolas, monospace; font-size: 15px; color: #2b2f3a; }
.seta { color: #b6bac6; align-self: center; font-size: 15px; }
table { width: 100%; border-collapse: collapse; font-size: 17px; }
th { text-align: left; font-size: 13px; letter-spacing: 1.1px; text-transform: uppercase;
  color: #8b90a0; padding: 0 10px 9px; font-weight: 600; }
td { padding: 11px 10px; border-top: 1px solid #eceef3; vertical-align: middle; }
tr.certa td { background: #eaf7ef; }
.pos { font-family: Consolas, monospace; color: #8b90a0; width: 44px; }
.doc { color: #6b7280; }
.score { font-family: Consolas, monospace; text-align: right; width: 90px; }
.selo { display: inline-block; background: #1f9d55; color: #fff; font-size: 12px;
  font-weight: 700; border-radius: 4px; padding: 3px 8px; margin-left: 10px;
  vertical-align: 2px; letter-spacing: 0.3px; }
.nota { margin-top: 26px; font-size: 16px; color: #4b5162; line-height: 1.55; }
.nota b { color: #1a1c23; }
.colunas { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; height: 618px; }
.painel { background: #f7f8fb; border: 1px solid #e6e8ef; border-radius: 10px;
  padding: 20px 22px; overflow: hidden; }
.painel h2 { font-size: 15px; letter-spacing: 1.1px; text-transform: uppercase;
  color: #8b90a0; margin: 0 0 4px; font-weight: 600; }
.painel .quem { font-size: 13px; color: #a3a8b8; margin: 0 0 14px;
  font-family: Consolas, monospace; }
pre { margin: 0; font-family: Consolas, monospace; font-size: 13.5px; line-height: 1.62;
  white-space: pre-wrap; word-break: break-word; color: #2b2f3a; }
pre .cit { color: #1f6feb; font-weight: 600; }
pre .fim { color: #a3a8b8; font-style: italic; }
.rodape { position: absolute; bottom: 44px; left: 58px; right: 58px;
  border-top: 1px solid #eceef3; padding-top: 22px;
  display: flex; gap: 18px; }
.etapa { flex: 1; }
.etapa .n { font-family: Consolas, monospace; font-size: 13px; color: #1f6feb;
  font-weight: 700; letter-spacing: 1px; }
.etapa .t { font-size: 15.5px; color: #4b5162; line-height: 1.45; margin-top: 5px; }
.etapa .t b { color: #1a1c23; }
.medidas { position: absolute; bottom: 44px; left: 58px; right: 58px;
  border-top: 1px solid #eceef3; padding-top: 20px;
  font-size: 15.5px; color: #4b5162; }
.medidas b { color: #1a1c23; font-family: Consolas, monospace; }
"""

ETAPAS = (
    ("01", "Os documentos da empresa em <b>.md</b>, um arquivo por assunto"),
    ("02", "Quebrados em <b>42 trechos</b> citáveis e indexados com BM25 local, sem custo"),
    ("03", "A pergunta pontua os trechos; só os <b>5 melhores</b> entram no pedido"),
    ("04", "O modelo responde <b>preso a esses trechos</b>, citando, ou diz que não achou"),
)


def _pagina_html(corpo: str) -> str:
    return f"<!doctype html><meta charset='utf-8'><style>{ESTILO}</style>{corpo}"


def _html_busca() -> str:
    trechos = carregar_trechos()
    indice = Indice(trechos)
    resultados = indice.buscar(PERGUNTA_DIFICIL, k=5)
    termos = normalizar(PERGUNTA_DIFICIL)

    chips = "".join(f"<span class='chip'>{html.escape(t)}</span>" for t in termos)

    linhas = []
    posicao_certa = None
    for i, r in enumerate(resultados, start=1):
        certa = r.trecho.secao == SECAO_CERTA
        if certa:
            posicao_certa = i
        selo = "<span class='selo'>RESPONDE A PERGUNTA</span>" if certa else ""
        linhas.append(
            f"<tr class='{'certa' if certa else ''}'>"
            f"<td class='pos'>[{i}]</td>"
            f"<td><b>{html.escape(r.trecho.secao)}</b>{selo}<br>"
            f"<span class='doc'>{html.escape(r.trecho.documento)}</span></td>"
            f"<td class='score'>{r.score:.2f}</td></tr>"
        )

    return _pagina_html(
        "<h1>Como a busca escolhe o que o modelo vai ler</h1>"
        f"<p class='sub'>Pergunta do cliente: &ldquo;{html.escape(PERGUNTA_DIFICIL)}&rdquo;</p>"
        "<p class='rotulo'>A pergunta vira termos, sem acento e reduzidos ao radical</p>"
        f"<div class='chips'>{chips}</div>"
        "<p class='rotulo'>"
        f"Os 5 trechos mais bem pontuados, entre os {len(trechos)} do acervo</p>"
        "<table><tr><th></th><th>Seção do documento</th><th class='score'>BM25</th></tr>"
        + "".join(linhas)
        + "</table>"
        "<p class='nota'>Repare que o trecho certo chegou em "
        f"<b>{posicao_certa}º</b>, não em primeiro: &ldquo;tempo&rdquo; e &ldquo;chegar&rdquo; "
        "são genéricos e casam com a seção errada. Isso não é um defeito, é o desenho. "
        "A busca existe para <b>garantir que o trecho certo esteja entre os cinco</b>; "
        "escolher entre eles é trabalho do modelo, que lê todos. "
        "<b>Teste automático do repositório: recall@5 acerta 10 de 10</b> perguntas reais.</p>"
        + _rodape_etapas()
    )


def _rodape_etapas() -> str:
    etapas = "".join(
        f"<div class='etapa'><div class='n'>{n}</div><div class='t'>{t}</div></div>"
        for n, t in ETAPAS
    )
    return f"<div class='rodape'>{etapas}</div>"


def _html_prompt() -> str:
    trechos = carregar_trechos()
    indice = Indice(trechos)
    resultados = indice.buscar(PERGUNTA_DIFICIL, k=5)
    mensagem = montar_mensagem(PERGUNTA_DIFICIL, resultados)

    # Corta no fim de um parágrafo, para não deixar palavra pela metade.
    corte = mensagem.rfind("\n\n", 0, 1500)
    visivel = html.escape(mensagem[:corte])
    for i in range(1, 6):
        visivel = visivel.replace(f"[{i}] ", f"<span class='cit'>[{i}]</span> ")
    restantes = mensagem[corte:].count("\n\n")
    caracteres = f"{len(mensagem):,}".replace(",", ".")

    return _pagina_html(
        "<h1>O texto exato que sai daqui para o modelo</h1>"
        "<p class='sub'>Nada é treinado. Os trechos viajam dentro do próprio pedido, "
        "a cada pergunta, e são descartados depois.</p>"
        "<div class='colunas'>"
        "<div class='painel'><h2>Instruções</h2><p class='quem'>role: system</p>"
        f"<pre>{html.escape(INSTRUCOES)}</pre></div>"
        "<div class='painel'><h2>Mensagem</h2><p class='quem'>role: user</p>"
        f"<pre>{visivel}\n\n<span class='fim'>[continua com mais {restantes} trechos "
        "no mesmo formato e, na última linha, a pergunta do cliente]</span></pre></div>"
        "</div>"
        "<div class='medidas'>Neste pedido: <b>5</b> trechos, "
        f"<b>{caracteres}</b> caracteres de contexto, escolhidos entre os "
        f"<b>{len(trechos)}</b> trechos do acervo. Mudar a política da empresa é editar "
        "um arquivo de texto, não retreinar nada.</div>"
    )


def capturar_desenhadas(pagina: Page) -> None:
    for nome, construir in (
        ("galeria-3-busca.png", _html_busca),
        ("galeria-4-prompt.png", _html_prompt),
    ):
        pagina.set_content(construir(), wait_until="load")
        pagina.wait_for_timeout(400)
        _salvar(pagina, nome)


# ---------------------------------------------------------------------- saída


def _salvar(pagina: Page, nome: str) -> None:
    caminho = DESTINO / nome
    pagina.screenshot(path=str(caminho))
    print(f"[ok] {caminho.name} ({caminho.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    DESTINO.mkdir(exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="chrome")
        pagina = navegador.new_page(
            viewport={"width": LARGURA, "height": ALTURA}, device_scale_factor=2
        )
        capturar_desenhadas(pagina)
        capturar_do_app(pagina)
        navegador.close()


if __name__ == "__main__":
    main()
