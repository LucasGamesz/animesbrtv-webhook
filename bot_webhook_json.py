import os
import json
import cloudscraper
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timedelta, timezone
import re

# ────────── CONFIG ──────────
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PROXY_URL   = os.getenv("PROXY_URL")

DB_FILE = "episodios_postados.json"
URL = "https://animesbr.app"
LIMIT = 5
ROLE_ID = "1391784968786808873"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

FALLBACK_PROXIES = [
    "http://177.136.44.194:54443",
    "http://187.19.201.217:8080",
]

# ────────── DB ──────────
if os.path.exists(DB_FILE):
    try:
        posted_links = set(json.load(open(DB_FILE, "r", encoding="utf-8")))
    except:
        posted_links = set()
else:
    posted_links = set()

WORKING_SCRAPER = None
WORKING_PROXY   = None


# ───────────────────────────────────────────────
#  Função para converter "X horas atrás" → data real
# ───────────────────────────────────────────────
def calcular_data(tempo_str):
    agora = datetime.now(timezone(timedelta(hours=-3)))

    if "minuto" in tempo_str:
        n = int(re.findall(r"\d+", tempo_str)[0])
        return agora - timedelta(minutes=n)

    if "hora" in tempo_str:
        n = int(re.findall(r"\d+", tempo_str)[0])
        return agora - timedelta(hours=n)

    if "dia" in tempo_str:
        n = int(re.findall(r"\d+", tempo_str)[0])
        return agora - timedelta(days=n)

    return agora  # fallback


# ───────────────────────────────────────────────
#  Extrair episódios (formato atualizado do site)
# ───────────────────────────────────────────────
def get_ultimos_episodios(limit=5):
    global WORKING_SCRAPER, WORKING_PROXY

    scraper = cloudscraper.create_scraper()

    proxies_to_test = []
    if PROXY_URL:
        proxies_to_test.append(PROXY_URL)
    proxies_to_test.extend(FALLBACK_PROXIES)

    r = None
    for proxy in proxies_to_test:
        try:
            prox_dict = {"http": proxy, "https": proxy}
            print(f"[TESTE] Proxy: {proxy}")
            r = scraper.get(URL, headers=HEADERS, timeout=15, proxies=prox_dict)
            r.raise_for_status()
            r.encoding = r.apparent_encoding
            WORKING_SCRAPER = scraper
            WORKING_PROXY   = prox_dict
            break
        except:
            r = None
            continue

    if r is None:
        print("[ERRO] Nenhum proxy funcionou.")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    artigos = soup.select("#widget_list_episodes-2 ul.post-lst li article.post.episodes")[:limit]

    episodios = []

    for art in artigos:
        titulo_el = art.select_one("h2.entry-title")
        titulo_raw = titulo_el.get_text(strip=True) if titulo_el else "Sem título"

        ep_info = art.select_one("span.num-epi")
        ep_info = ep_info.get_text(strip=True) if ep_info else "Episódio ?"

        link_el = art.select_one("a.lnk-blk")
        link = link_el["href"] if link_el else None

        img_el = art.select_one(".post-thumbnail img")
        imagem = img_el["src"] if img_el else None
        if imagem and imagem.startswith("//"):
            imagem = "https:" + imagem

        tempo_el = art.select_one(".entry-meta .time")
        tempo_str = tempo_el.get_text(strip=True) if tempo_el else "0 minutos atrás"

        data_real = calcular_data(tempo_str)
        data_formatada = data_real.strftime("%d/%m/%Y %H:%M")

        episodios.append({
            "titulo": titulo_raw,
            "ep_info": ep_info,
            "link": link,
            "imagem": imagem,
            "data": data_formatada,
        })

    return episodios


# ───────────────────────────────────────────────
#  ENVIAR PARA O DISCORD
# ───────────────────────────────────────────────
def post_discord(ep):
    global WORKING_SCRAPER

    files = {}
    if ep["imagem"]:
        try:
            img = WORKING_SCRAPER.get(ep["imagem"], headers=HEADERS, timeout=10)
            if img.status_code == 200:
                files["file"] = ("poster.jpg", img.content)
        except:
            pass

    payload = {
        "content": f"<@&{ROLE_ID}>",
        "embeds": [
            {
                "title": ep["titulo"],             # Nome + Episódio igual ao site
                "description": (
                    f"**Número do EP:** {ep['ep_info']}\n"
                    f"👉 [Assistir online]({ep['link']})"
                ),
                "color": 0xFF0000,                 # Barrinha vermelha igual antes
                "image": {"url": "attachment://poster.jpg"} if files else {},
                "footer": {"text": f"Animesbr.tv • {ep['data']}"}
            }
        ],
        "allowed_mentions": {"roles": [ROLE_ID]}
    }

    r = requests.post(WEBHOOK_URL, json=payload, files=files)
    if r.status_code in (200, 204):
        print(f"[DISCORD] ✅ Enviado: {ep['titulo']}")
        return True
    else:
        print(f"[DISCORD] ❌ Erro {r.status_code}: {r.text}")
        return False


# ───────────────────────────────────────────────
#  LOOP PRINCIPAL
# ───────────────────────────────────────────────
episodios = get_ultimos_episodios(LIMIT)
novo = False

for ep in reversed(episodios):
    if ep["link"] and ep["link"] not in posted_links:
        if post_discord(ep):        # Só salva se realmente postou
            posted_links.add(ep["link"])
            novo = True
    else:
        print(f"[BOT] Já postado: {ep['titulo']}")

if novo:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted_links), f, ensure_ascii=False, indent=2)
