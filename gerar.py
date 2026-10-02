"""Gera um carrossel completo: texto (IA ou banco), fundos e imagens dos slides.

Uso:
    python gerar.py            # gera 1 carrossel em saida/<data-hora>/
    python gerar.py --qtd 3    # gera 3 carrosséis
"""
import argparse
import json
import os
import random
import sys
import textwrap
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
FONTE_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTE_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
# Fonte própria (ex.: Montserrat ExtraBold): coloque em fontes/titulo.ttf e fontes/texto.ttf
if (BASE / "fontes/titulo.ttf").exists():
    FONTE_BOLD = str(BASE / "fontes/titulo.ttf")
if (BASE / "fontes/texto.ttf").exists():
    FONTE_REG = str(BASE / "fontes/texto.ttf")


def carregar_config():
    return yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- produtos

def lista_produtos(cfg):
    """Produtos ativos da lista `produtos`, com os campos que faltarem vindos de `ebook`."""
    padrao = cfg.get("ebook", {})
    lista = [p for p in cfg.get("produtos") or [] if p.get("ativo", True)]
    return [{**padrao, **p} for p in lista] or [padrao]


def escolher_produto(cfg):
    """Reveza os produtos em ordem: cada carrossel divulga o próximo da lista."""
    produtos = lista_produtos(cfg)
    arq = BASE / "conteudo/produto_atual.json"
    i = json.loads(arq.read_text()) if arq.exists() else -1
    i = (i + 1) % len(produtos)
    arq.write_text(json.dumps(i))
    return produtos[i]


def gerar_pagina_links(cfg):
    """Cria links/index.html: a página para pôr na bio, com um botão por produto."""
    botoes = "\n".join(
        f'<a href="{p["link"]}">{p["nome"]}</a>' for p in lista_produtos(cfg))
    cor = cfg["marca"]["cor_destaque"]
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{cfg["marca"]["arroba"]}</title><style>
body{{margin:0;background:#111;color:#fff;font-family:system-ui,sans-serif;text-align:center;padding:40px 16px}}
a{{display:block;max-width:420px;margin:14px auto;padding:18px;border-radius:40px;
background:{cor};color:#111;font-weight:700;text-decoration:none}}
</style></head><body><h1>{cfg["marca"]["arroba"]}</h1>
{botoes}
</body></html>"""
    (BASE / "links").mkdir(exist_ok=True)
    (BASE / "links/index.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------- conteúdo

def roteiro_do_banco(cfg, prod):
    banco_todo = yaml.safe_load((BASE / "conteudo/banco.yaml").read_text(encoding="utf-8"))
    # roteiros marcados com `produto:` só saem para aquele produto; os sem marca servem para todos
    idx = [i for i, r in enumerate(banco_todo) if r.get("produto") in (None, prod["nome"])]
    usados_arq = BASE / "conteudo/usados.json"
    usados = json.loads(usados_arq.read_text()) if usados_arq.exists() else []
    livres = [i for i in idx if i not in usados]
    if not livres:  # roteiros desse produto esgotados: recomeça o ciclo deles
        usados = [u for u in usados if u not in idx]
        livres = idx
    banco = banco_todo
    escolha = random.choice(livres)
    usados_arq.write_text(json.dumps(usados + [escolha]))
    return banco[escolha]


def roteiro_da_ia(cfg, prod):
    """Pede um roteiro novo ao Claude. Precisa da variável ANTHROPIC_API_KEY."""
    import anthropic

    historico_arq = BASE / "conteudo/hooks_usados.json"
    historico = json.loads(historico_arq.read_text()) if historico_arq.exists() else []
    n = cfg["slides"]["quantidade_conteudo"]
    prompt = f"""Você escreve carrosséis virais para Instagram e TikTok em português do Brasil.
Nicho: {prod['nicho']}. O carrossel termina divulgando o produto "{prod['nome']}".

Crie UM carrossel novo:
- hook: frase curta (máx 12 palavras) que faz a pessoa parar de rolar. Use número, curiosidade ou dor.
- slides: exatamente {n} itens, cada um com "titulo" (máx 6 palavras) e "texto" (máx 22 palavras), entregando valor real.
- legenda: 1 a 2 frases pedindo salvar/comentar/compartilhar.
- hashtags: 4 a 6 hashtags relevantes numa string.
Não repita estes hooks já usados: {historico[-30:]}

Responda APENAS com JSON: {{"hook": "...", "slides": [{{"titulo": "...", "texto": "..."}}], "legenda": "...", "hashtags": "..."}}"""
    cliente = anthropic.Anthropic()
    resp = cliente.messages.create(
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = resp.content[0].text
    roteiro = json.loads(texto[texto.find("{"): texto.rfind("}") + 1])
    historico_arq.write_text(json.dumps(historico + [roteiro["hook"]], ensure_ascii=False))
    return roteiro


# ---------------------------------------------------------------- fundos

def cortar_para(img, w, h):
    img = img.convert("RGB")
    escala = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * escala) + 1, int(img.height * escala) + 1), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def fundo_degrade(w, h):
    paletas = [((40, 30, 90), (150, 50, 190)), ((10, 70, 110), (0, 190, 170)),
               ((90, 20, 30), (230, 80, 50)), ((30, 30, 40), (110, 110, 130))]
    c1, c2 = random.choice(paletas)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    # círculos desfocados para dar profundidade
    camada = Image.new("RGB", (w, h), (0, 0, 0))
    dc = ImageDraw.Draw(camada)
    for _ in range(4):
        r = random.randint(200, 450)
        x, y = random.randint(0, w), random.randint(0, h)
        dc.ellipse([x - r, y - r, x + r, y + r], fill=tuple(min(255, c + 60) for c in c2))
    camada = camada.filter(ImageFilter.GaussianBlur(120))
    return Image.blend(img, camada, 0.35)


def fundos_pexels(cfg, prod, qtd):
    chave = os.environ.get("PEXELS_API_KEY")
    if not chave:
        return []
    busca = prod.get("busca_fundo") or prod["nicho"]
    if isinstance(busca, list):
        busca = random.choice(busca)
    r = requests.get("https://api.pexels.com/v1/search",
                     params={"query": busca,
                             "orientation": "portrait", "per_page": 40},
                     headers={"Authorization": chave}, timeout=30)
    r.raise_for_status()
    fotos = r.json()["photos"]
    if not fotos:
        return []
    fotos = random.sample(fotos, min(qtd, len(fotos)))
    return [Image.open(BytesIO(requests.get(f["src"]["large2x"], timeout=60).content)) for f in fotos]


def fundos_pixabay(cfg, prod, qtd):
    chave = os.environ.get("PIXABAY_API_KEY")
    if not chave:
        return []
    busca = prod.get("busca_fundo") or prod["nicho"]
    if isinstance(busca, list):
        busca = random.choice(busca)
    r = requests.get("https://pixabay.com/api/", params={
        "key": chave, "q": busca, "image_type": "photo", "orientation": "vertical",
        "safesearch": "true", "per_page": 50}, timeout=30)
    r.raise_for_status()
    fotos = r.json()["hits"]
    if not fotos:
        return []
    fotos = random.sample(fotos, min(qtd, len(fotos)))
    return [Image.open(BytesIO(requests.get(f["largeImageURL"], timeout=60).content)) for f in fotos]


def escolher_fundos(cfg, prod, qtd):
    w, h = cfg["slides"]["largura"], cfg["slides"]["altura"]
    imgs = []
    if cfg["fonte_fundo"] == "pasta":
        arquivos = [p for p in (BASE / "fundos").iterdir()
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
        random.shuffle(arquivos)
        imgs = [Image.open(p) for p in arquivos[:qtd]]
    elif cfg["fonte_fundo"] in ("pixabay", "pexels"):
        busca = fundos_pixabay if cfg["fonte_fundo"] == "pixabay" else fundos_pexels
        try:
            imgs = busca(cfg, prod, qtd)
        except Exception as e:  # sem internet ou chave inválida: usa degradê
            print(cfg["fonte_fundo"], "falhou, usando degradê:", e)
    imgs = [cortar_para(i, w, h) for i in imgs]
    while len(imgs) < qtd:
        imgs.append(imgs[len(imgs) % len(imgs)] if imgs and len(imgs) >= 3 else fundo_degrade(w, h))
    return imgs


# ---------------------------------------------------------------- desenho

def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def escurecer(img, nivel):
    preto = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, preto, nivel)
    # degradê extra embaixo para o texto ficar legível
    grad = Image.linear_gradient("L").resize(img.size)
    return Image.composite(preto, img, grad.point(lambda p: int(p * 0.5)))


def caber_texto(draw, texto, fonte_path, largura_max, tam_max, tam_min, max_linhas):
    """Acha o maior tamanho de fonte em que o texto cabe."""
    for tam in range(tam_max, tam_min - 1, -4):
        fonte = ImageFont.truetype(fonte_path, tam)
        chars = max(8, int(largura_max / (tam * 0.58)))
        linhas = textwrap.wrap(texto, chars)
        if len(linhas) <= max_linhas and all(draw.textlength(l, font=fonte) <= largura_max for l in linhas):
            return fonte, linhas
    fonte = ImageFont.truetype(fonte_path, tam_min)
    return fonte, textwrap.wrap(texto, max(8, int(largura_max / (tam_min * 0.58))))


def escrever(draw, linhas, fonte, x, y, cor, destaque=None, espaco=1.18, centro=False, largura=0):
    """Escreve linhas com sombra. Palavras entre *asteriscos* ficam na cor de destaque."""
    alt = int(fonte.size * espaco)
    for i, linha in enumerate(linhas):
        cx = x
        if centro:
            cx = x + (largura - draw.textlength(linha.replace("*", ""), font=fonte)) / 2
        for parte_i, parte in enumerate(linha.split("*")):
            c = destaque if (parte_i % 2 == 1 and destaque) else cor
            draw.text((cx + 4, y + i * alt + 4), parte, font=fonte, fill=(0, 0, 0))
            draw.text((cx, y + i * alt), parte, font=fonte, fill=c)
            cx += draw.textlength(parte, font=fonte)
    return y + len(linhas) * alt


def rodape(draw, cfg, w, h, num, total, seta=True):
    f = ImageFont.truetype(FONTE_REG, 30)
    draw.text((70, h - 90), cfg["marca"]["arroba"], font=f, fill=(230, 230, 230))
    txt = f"{num}/{total}" + ("   arraste →" if seta else "")
    draw.text((w - 70 - draw.textlength(txt, font=f), h - 90), txt, font=f, fill=(230, 230, 230))


def slide_hook(fundo, cfg, hook, total):
    w, h = fundo.size
    img = escurecer(fundo, cfg["marca"]["escurecer_fundo"])
    d = ImageDraw.Draw(img)
    destaque = hex_rgb(cfg["marca"]["cor_destaque"])
    d.rectangle([70, 300, 230, 316], fill=destaque)
    fonte, linhas = caber_texto(d, hook.upper(), FONTE_BOLD, w - 140, 110, 56, 6)
    escrever(d, linhas, fonte, 70, 360, hex_rgb(cfg["marca"]["cor_texto"]), destaque)
    rodape(d, cfg, w, h, 1, total)
    return img


def slide_conteudo(fundo, cfg, item, num, total):
    w, h = fundo.size
    img = escurecer(fundo, cfg["marca"]["escurecer_fundo"] + 0.1)
    d = ImageDraw.Draw(img)
    destaque = hex_rgb(cfg["marca"]["cor_destaque"])
    branco = hex_rgb(cfg["marca"]["cor_texto"])
    # número em destaque
    fn = ImageFont.truetype(FONTE_BOLD, 64)
    d.ellipse([70, 260, 190, 380], fill=destaque)
    n = str(num - 1)
    d.text((130 - d.textlength(n, font=fn) / 2, 280), n, font=fn, fill=(20, 20, 20))
    ft, lt = caber_texto(d, item["titulo"].upper(), FONTE_BOLD, w - 140, 84, 48, 3)
    y = escrever(d, lt, ft, 70, 440, destaque)
    fx, lx = caber_texto(d, item["texto"], FONTE_REG, w - 140, 52, 34, 7)
    escrever(d, lx, fx, 70, y + 50, branco, espaco=1.35)
    rodape(d, cfg, w, h, num, total)
    return img


def slide_cta(fundo, cfg, eb, total):
    w, h = fundo.size
    img = escurecer(fundo, 0.7)
    d = ImageDraw.Draw(img)
    destaque = hex_rgb(cfg["marca"]["cor_destaque"])
    branco = hex_rgb(cfg["marca"]["cor_texto"])
    f1 = ImageFont.truetype(FONTE_REG, 46)
    escrever(d, [eb.get("chamada_topo", "Quer o passo a passo completo?")], f1, 0, 300, branco, centro=True, largura=w)
    fn, ln = caber_texto(d, eb["nome"].upper(), FONTE_BOLD, w - 160, 104, 60, 3)
    y = escrever(d, ln, fn, 0, 400, destaque, centro=True, largura=w)
    if eb.get("preco"):
        fp = ImageFont.truetype(FONTE_BOLD, 60)
        y = escrever(d, [f"por apenas {eb['preco']}"], fp, 0, y + 40, branco, centro=True, largura=w)
    # botão
    fb = ImageFont.truetype(FONTE_BOLD, 54)
    txt = eb["chamada_link"].upper()
    bw = d.textlength(txt, font=fb) + 120
    bx, by = (w - bw) / 2, y + 90
    d.rounded_rectangle([bx, by, bx + bw, by + 120], radius=60, fill=destaque)
    d.text((bx + 60, by + 30), txt, font=fb, fill=(20, 20, 20))
    rodape(d, cfg, w, h, total, total, seta=False)
    return img


# ---------------------------------------------------------------- principal

def gerar_carrossel(cfg, pasta_saida=None):
    prod = escolher_produto(cfg)
    if cfg["fonte_conteudo"] == "ia":
        roteiro = roteiro_da_ia(cfg, prod)
    else:
        roteiro = roteiro_do_banco(cfg, prod)
    itens = roteiro["slides"]
    total = len(itens) + 2
    fundos = escolher_fundos(cfg, prod, total)

    pasta = pasta_saida or BASE / "saida" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    while pasta.exists():
        pasta = pasta.with_name(pasta.name + "b")
    pasta.mkdir(parents=True, exist_ok=True)
    slides = [slide_hook(fundos[0], cfg, roteiro["hook"], total)]
    slides += [slide_conteudo(fundos[i + 1], cfg, it, i + 2, total) for i, it in enumerate(itens)]
    slides.append(slide_cta(fundos[-1], cfg, prod, total))
    arquivos = []
    for i, s in enumerate(slides, 1):
        p = pasta / f"slide_{i:02d}.jpg"
        s.save(p, quality=92)
        arquivos.append(p.name)

    legenda = (f"{roteiro['hook']}\n\n{roteiro.get('legenda', '')}\n\n"
               f"📘 {prod['nome']}: {prod['chamada_link'].lower()}\n\n"
               f"{roteiro.get('hashtags', '')}").strip()
    (pasta / "post.json").write_text(json.dumps(
        {"hook": roteiro["hook"], "produto": prod["nome"], "link": prod["link"], "legenda": legenda, "slides": arquivos, "publicado": {}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("Carrossel gerado em", pasta)
    return pasta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--qtd", type=int, default=1)
    args = ap.parse_args()
    cfg = carregar_config()
    if not cfg.get("ligado", True) and os.environ.get("GITHUB_ACTIONS"):
        print("Desligado em config.yaml (ligado: false). Nada foi gerado."); sys.exit(0)
    gerar_pagina_links(cfg)
    for _ in range(args.qtd):
        gerar_carrossel(cfg)
