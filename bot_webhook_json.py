import os
import json
import cloudscraper
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timedelta, timezone
import re
from io import BytesIO
from PIL import Image

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
#  Converte "X horas atrás" → data real UTC-3
# ───────────────────────────────────────────────
def calcular_data(tempo_str):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    num = re.findall(r"\d+", tempo_str)

    if not num:
        return agora

    n = int(num[0])

    if "minuto" in tempo_str:
        return agora - timedelta(minutes=n)
    if "hora" in tempo_str:
        return agora - timedelta(hours=n)
    if "dia" in tempo_str:
        return agora - timedelta(days=n)

    return agora


# ───────────────────────────────────────────────
#  Corta imagem para proporção 16:9
# ───────────────────────────────────────────────
def cortar_16_9(img_bytes):
    try:
        img = Image.open(BytesIO(img_bytes))
        w, h = img.size

        target_ratio = 16/9
        current_ratio = w / h

        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            offset = (w - new_w) // 2
            img = img.crop((offset, 0, offset + new_w, h))
        else:
            new_h = int(w / target_ratio)
            offset = (h - new_h) // 2
            img = img.crop((0, offset, w, offset + new_h))

        output = BytesIO()
        img.save(output, format="JPEG", quality=95)
        return output.getvalue()

    except Exception as e:
        print("[ERRO] Falha ao ajustar imagem:", e)
        return img_bytes


# ───────────────────────────────────────────────
#  Extrair episódios da página inicial
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
            r.encoding = "utf-8"

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
        titulo_raw = art.select_one("h2.entry-title").get_text(strip=True)
        ep_info = art.select_one("span.num-epi").get_text(strip=True)

        # título final reformulado
        titulo_final = f"{titulo_raw} ({ep_info})"

        link = art.select_one("a.lnk-blk")["href"]

        img_el = art.select_one(".post-thumbnail img")
        imagem = img_el["src"] if img_el else None
        if imagem and imagem.startswith("//"):
            imagem = "https:" + imagem

        tempo_str = art.select_one(".entry-meta .time").get_text(strip=True)
        data_real = calcular_data(tempo_str)

        episodios.append({
            "titulo": titulo_final,
            "link": link,
            "imagem": imagem,
            "data": data_real.strftime("%d/%m/%Y %H:%M"),
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
            img_data = WORKING_SCRAPER.get(ep["imagem"], headers=HEADERS, timeout=10).content
            img_data = cortar_16_9(img_data)
            files["file"] = ("poster.jpg", img_data)
        except Exception as e:
            print("[ERRO] Falha ao baixar imagem:", e)

    embed = {
        "title": ep["titulo"],
        "description": f"👉 [Assistir online]({ep['link']})",
        "color": 0xFF0000,
        "footer": {"text": f"Animesbr.tv • {ep['data']}"}
    }

    if files:
        embed["image"] = {"url": "attachment://poster.jpg"}

    payload = {
        "content": f"<@&{ROLE_ID}>",
        "embeds": [embed],
        "allowed_mentions": {"roles": [ROLE_ID]}
    }

    r = requests.post(
        WEBHOOK_URL,
        data={"payload_json": json.dumps(payload, ensure_ascii=False)},
        files=files
    )

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
        if post_discord(ep):
            posted_links.add(ep["link"])
            novo = True
    else:
        print(f"[BOT] Já postado: {ep['titulo']}")

if novo:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted_links), f, ensure_ascii=False, indent=2)
