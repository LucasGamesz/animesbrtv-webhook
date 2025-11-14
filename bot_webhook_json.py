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
#  Obter sinopse da página do anime
# ───────────────────────────────────────────────
def obter_sinopse(link_ep):
    """Extrai o segundo <p> dentro de .description; se não tiver, pega o primeiro."""
    global WORKING_SCRAPER, WORKING_PROXY

    try:
        # https://www.animesbr.app/episodios/assistir-tougen-anki-episodio-18
        slug = link_ep.split("/episodios/assistir-")[-1].split("-episodio")[0]
        url_anime = f"https://www.animesbr.app/animes/{slug}"

        r = WORKING_SCRAPER.get(url_anime, headers=HEADERS, timeout=10, proxies=WORKING_PROXY)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        desc = soup.select_one("div.description")

        if not desc:
            return ""

        ps = desc.find_all("p")

        if len(ps) >= 2:
            return ps[1].get_text(strip=True)

        if len(ps) == 1:
            return ps[0].get_text(strip=True)

        return ""

    except Exception as e:
        print("[ERRO] Falha ao obter sinopse:", e)
        return ""


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
        titulo_el = art.select_one("h2.entry-title")
        titulo_raw = titulo_el.get_text(strip=True) if titulo_el else "Sem título"

        ep_info_el = art.select_one("span.num-epi")
        ep_info = ep_info_el.get_text(strip=True) if ep_info_el else "?"

        # título final atualizado
        titulo_final = f"<:Animesbrapp:1439021183365288111> {titulo_raw} ({ep_info})"

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
            "titulo": titulo_final,
            "ep_info": ep_info,
            "link": link,
            "imagem": imagem,
            "data": data_formatada,
        })

    return episodios


# ───────────────────────────────────────────────
#  ENVIAR PARA O DISCORD (com sinopse)
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

    # obter sinopse
    sinopse = obter_sinopse(ep["link"])
    if sinopse:
        descricao = sinopse + f"\n👉 [Assistir online]({ep['link']})"
    else:
        descricao = f"👉 [Assistir online]({ep['link']})"

    embed = {
        "title": ep["titulo"],
        "description": descricao[:4000],
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
