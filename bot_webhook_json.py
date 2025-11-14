import os
import json
import cloudscraper
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timezone, timedelta

# ────────── CONFIG ──────────
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PROXY_URL = os.getenv("PROXY_URL")

DB_FILE = "episodios_postados.json"
URL = "https://www.animesbr.app"
LIMIT = 5
ROLE_ID = "1391784968786808873"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.google.com/"
}

FALLBACK_PROXIES = [
    "http://177.136.44.194:54443",
    "http://187.19.201.217:8080",
    "http://177.11.67.162:8999",
]

# ────────── CARREGAR DB ──────────
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            posted_links = set(json.load(f))
    except:
        posted_links = set()
else:
    posted_links = set()

WORKING_SCRAPER = None
WORKING_PROXY = None


# ─────────────────────────────────────────────────────
#  NOVO PARSER → COMPATÍVEL COM O HTML ATUAL
# ─────────────────────────────────────────────────────
def get_ultimos_episodios(limit=5):
    global WORKING_SCRAPER
    global WORKING_PROXY

    scraper = cloudscraper.create_scraper()

    proxies_to_test = []
    if PROXY_URL:
        proxies_to_test.append(PROXY_URL)
    proxies_to_test.extend(FALLBACK_PROXIES)

    r = None
    for current_proxy in proxies_to_test:
        try:
            proxies_dict = {"http": current_proxy, "https": current_proxy}
            print(f"[TESTE] Proxy: {current_proxy}")

            r = scraper.get(URL, headers=HEADERS, timeout=15, proxies=proxies_dict)
            r.raise_for_status()
            r.encoding = r.apparent_encoding

            WORKING_SCRAPER = scraper
            WORKING_PROXY = proxies_dict
            break
        except:
            r = None
            continue

    if r is None:
        print("[ERRO] Nenhum proxy funcionou.")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    # NOVO SELETOR
    artigos = soup.select("#widget_list_episodes-2 ul.post-lst li article.post.episodes")
    artigos = artigos[:limit]

    episodios = []

    tz_sp = timezone(timedelta(hours=-3))
    footer_time = datetime.now(timezone.utc).astimezone(tz_sp).strftime("%d/%m/%Y %H:%M")

    for artigo in artigos:

        # Título: "Anime Episódio X"
        titulo_el = artigo.select_one("h2.entry-title")
        titulo_raw = titulo_el.get_text(strip=True) if titulo_el else "Sem título"

        # Extrair só o nome do anime (remover "Episódio X")
        nome_anime = titulo_raw.rsplit(" Episódio", 1)[0].strip()

        # Temporada e episódio
        ep_info = artigo.select_one("span.num-epi")
        ep_info = ep_info.get_text(strip=True) if ep_info else ""

        # Link
        link_tag = artigo.select_one("a.lnk-blk")
        link = link_tag["href"] if link_tag else None

        # Imagem
        img = artigo.select_one(".post-thumbnail img")
        img_url = None
        if img:
            img_url = img.get("src")
            if img_url.startswith("//"):
                img_url = "https:" + img_url

        # Tempo (ex: "6 horas atrás")
        tempo = artigo.select_one(".entry-meta .time")
        tempo = tempo.get_text(strip=True) if tempo else ""

        episodios.append({
            "link": link,
            "titulo": titulo_raw,
            "nome_anime": nome_anime,
            "ep_info": ep_info,
            "qualidade": "HD",
            "data": footer_time,
            "imagem": img_url,
            "tempo": tempo,
        })

    return episodios


# ────────── ENVIAR PRO DISCORD ──────────
def post_discord(ep):
    global WORKING_SCRAPER

    files = {}
    image_url = ep.get("imagem")

    if image_url:
        try:
            img = WORKING_SCRAPER.get(image_url, headers=HEADERS, timeout=10)
            if img.status_code == 200:
                files["file"] = ("poster.jpg", img.content)
        except:
            pass

    payload = {
        "content": f"<@&{ROLE_ID}> **Novo Episódio!**",
        "embeds": [
            {
                "title": ep["titulo"],
                "url": ep["link"],
                "description": f"**{ep['nome_anime']}**\n{ep['ep_info']}\n⏳ {ep['tempo']}",
                "image": {"url": "attachment://poster.jpg"} if files else {}
            }
        ]
    }

    requests.post(WEBHOOK_URL, json=payload, files=files)


# ────────── MAIN LOOP ──────────
def main():
    global posted_links

    episodios = get_ultimos_episodios(LIMIT)
    novos = [e for e in episodios if e["link"] and e["link"] not in posted_links]

    for ep in novos:
        print(f"[POSTANDO] {ep['titulo']}")
        post_discord(ep)
        posted_links.add(ep["link"])

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted_links), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
