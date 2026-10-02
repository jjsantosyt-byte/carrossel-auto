"""Publica um carrossel já gerado no Instagram e no TikTok pelas APIs oficiais.

As imagens precisam estar num endereço público (ex.: GitHub Pages), porque
Instagram e TikTok baixam as fotos por URL.

Variáveis de ambiente:
    URL_PUBLICA          ex.: https://seuusuario.github.io/carrossel-auto
    IG_USER_ID           id da conta profissional do Instagram
    IG_ACCESS_TOKEN      token de longa duração (Instagram API com login do Instagram)
    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN

Uso:
    python publicar.py --proximo          # publica o carrossel mais antigo ainda não publicado
    python publicar.py saida/2026-10-02_080000
    python publicar.py --proximo --teste  # só mostra o que seria enviado
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

BASE = Path(__file__).parent
IG_API = "https://graph.instagram.com/v23.0"
TT_API = "https://open.tiktokapis.com/v2"


def urls_publicas(pasta, post):
    base = os.environ["URL_PUBLICA"].rstrip("/")
    rel = pasta.resolve().relative_to(BASE.resolve()).as_posix()
    return [f"{base}/{rel}/{s}" for s in post["slides"]]


# ---------------------------------------------------------------- Instagram

def ig(metodo, caminho, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    r = requests.request(metodo, f"{IG_API}/{caminho}", params=params, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram {caminho}: {r.text}")
    return r.json()


def esperar_container_ig(cid):
    for _ in range(30):
        st = ig("GET", cid, fields="status_code")["status_code"]
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {cid} falhou: {st}")
        time.sleep(5)
    raise RuntimeError(f"Container {cid} demorou demais")


def publicar_instagram(urls, legenda):
    uid = os.environ["IG_USER_ID"]
    filhos = []
    for u in urls[:20]:  # carrossel aceita até 20 itens
        filhos.append(ig("POST", f"{uid}/media", image_url=u, is_carousel_item="true")["id"])
    for f in filhos:
        esperar_container_ig(f)
    carrossel = ig("POST", f"{uid}/media", media_type="CAROUSEL",
                   children=",".join(filhos), caption=legenda[:2200])["id"]
    esperar_container_ig(carrossel)
    return ig("POST", f"{uid}/media_publish", creation_id=carrossel)["id"]


# ---------------------------------------------------------------- TikTok

def token_tiktok():
    r = requests.post(f"{TT_API}/oauth/token/", data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
    }, timeout=30)
    dados = r.json()
    if "access_token" not in dados:
        raise RuntimeError(f"TikTok token: {dados}")
    if dados.get("refresh_token") and dados["refresh_token"] != os.environ["TIKTOK_REFRESH_TOKEN"]:
        print("AVISO: o TikTok enviou um refresh_token novo. Atualize o segredo TIKTOK_REFRESH_TOKEN.")
    return dados["access_token"]


def tt(token, caminho, corpo):
    r = requests.post(f"{TT_API}/{caminho}", json=corpo, timeout=60, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    dados = r.json()
    if dados.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok {caminho}: {dados['error']}")
    return dados["data"]


def publicar_tiktok(urls, hook, legenda):
    token = token_tiktok()
    criador = tt(token, "post/publish/creator_info/query/", {})
    opcoes = criador["privacy_level_options"]
    # App ainda não auditado pelo TikTok só pode postar como privado (SELF_ONLY).
    privacidade = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in opcoes else opcoes[0]
    dados = tt(token, "post/publish/content/init/", {
        "post_info": {
            "title": hook[:90],
            "description": legenda[:4000],
            "privacy_level": privacidade,
            "disable_comment": False,
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": urls[:35],
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    })
    pid = dados["publish_id"]
    for _ in range(30):
        st = tt(token, "post/publish/status/fetch/", {"publish_id": pid})
        if st["status"] == "PUBLISH_COMPLETE":
            return pid
        if st["status"] == "FAILED":
            raise RuntimeError(f"TikTok falhou: {st.get('fail_reason')}")
        time.sleep(5)
    return pid  # ainda processando; o TikTok termina sozinho


# ---------------------------------------------------------------- principal

def proximo_da_fila():
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    alvos = [k for k, v in cfg["publicar_em"].items() if v]
    for pasta in sorted((BASE / "saida").iterdir()):
        arq = pasta / "post.json"
        if arq.exists():
            post = json.loads(arq.read_text(encoding="utf-8"))
            if any(a not in post["publicado"] for a in alvos):
                return pasta, alvos
    return None, alvos


def esperar_imagens_no_ar(urls, limite=300):
    """O GitHub Pages leva 1 ou 2 minutos para publicar imagens novas. Espera elas aparecerem."""
    inicio = time.time()
    while time.time() - inicio < limite:
        if all(requests.head(u, timeout=20).status_code == 200 for u in urls):
            return
        time.sleep(15)
    raise RuntimeError("As imagens não apareceram no GitHub Pages: " + urls[0])


def publicar(pasta, alvos, teste=False):
    arq = pasta / "post.json"
    post = json.loads(arq.read_text(encoding="utf-8"))
    urls = urls_publicas(pasta, post)
    if teste:
        print(json.dumps({"alvos": alvos, "urls": urls, "legenda": post["legenda"]},
                         ensure_ascii=False, indent=2))
        return True
    esperar_imagens_no_ar(urls)
    ok = True
    for alvo in alvos:
        if alvo in post["publicado"]:
            continue
        try:
            if alvo == "instagram":
                post["publicado"]["instagram"] = publicar_instagram(urls, post["legenda"])
            elif alvo == "tiktok":
                post["publicado"]["tiktok"] = publicar_tiktok(urls, post["hook"], post["legenda"])
            print(f"Publicado no {alvo}: {post['publicado'][alvo]}")
        except Exception as e:
            ok = False
            print(f"ERRO no {alvo}: {e}", file=sys.stderr)
        arq.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", nargs="?")
    ap.add_argument("--proximo", action="store_true")
    ap.add_argument("--teste", action="store_true")
    a = ap.parse_args()
    if a.teste:
        os.environ.setdefault("URL_PUBLICA", "https://SEUUSUARIO.github.io/carrossel-auto")
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    if not cfg.get("ligado", True) and not a.teste:
        print("Desligado em config.yaml (ligado: false). Nada foi publicado."); sys.exit(0)
    if a.proximo:
        pasta, alvos = proximo_da_fila()
        if not pasta:
            sys.exit("Fila vazia: rode gerar.py primeiro.")
    else:
        pasta, alvos = Path(a.pasta), ["instagram", "tiktok"]
    sys.exit(0 if publicar(pasta, alvos, a.teste) else 1)
