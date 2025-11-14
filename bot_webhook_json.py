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
    "http://186.208.248.46:8080",
    "http://138.0.207.3:8085",
    "http://206.62.64.34:8080",
    "http://191.252.204.220:8080",
    "http://200.174.198.32:8888",
    "http://45.231.101.97:9999",
    "http://189.89.154.130:3128",
    "http://177.184.199.36:80",
    "http://191.7.197.9:8080",
    "http://206.42.15.142:8090",
    "http://186.250.202.104:8080",
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
# Converter "X horas atrás" → data real (UTC−3)
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

    return agora


# ───────────────────────────────────────────────
# Extrair episódios
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
            r = scraper.get(URL, headers=HEADERS, timeout=10, proxies=prox_dict)
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

        # Limpar caracteres bugados
        titulo_raw = titulo_raw.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
