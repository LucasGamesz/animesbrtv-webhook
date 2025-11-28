import os
import json
import cloudscraper
from bs4 import BeautifulSoup
import requests
from datetime import datetime, timedelta, timezone

# ────────── CONFIG ──────────
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PROXY_URL   = os.getenv("PROXY_URL")

DB_FILE = "episodios_postados.json"
URL = "https://animebr.org"
LIMIT = 10
ROLE_ID = "1391784968786808873"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

FALLBACK_PROXIES = [
    "http://187.19.201.217:8080",    
    "http://179.189.200.197:3129",
    "http://186.227.112.65:8080",
    "http://201.65.173.179:8080",
    "http://191.252.204.220:8080",
    "http://179.97.120.240:3128",
    "http://186.250.29.225:8080",
    "http://186.208.81.214:3129",
    "http://177.10.44.190:8080",
    "http://187.94.16.59:39665",
    "http://177.19.167.242:80",
    "http://177.73.136.29:8080",
    "http://187.19.198.130:8080",
    "http://131.0.91.117:8080",
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
#  Obter link do anime via botão "Temporadas"
# ───────────────────────────────────────────────
def obter_link_anime(link_ep):
    global WORKING_SCRAPER, WORKING_PROXY

    try:
        r = WORKING_SCRAPER.get(link_ep, headers=HEADERS, timeout=10, proxies=WORKING_PROXY)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        btn = soup.select_one('.epsdsnv a[href*="/animes/"]')
        if btn:
            return btn["href"]

        return None

    except Exception as e:
        print("[ERRO] Falha ao obter link do anime via botão Temporadas:", e)
        return None


# ───────────────────────────────────────────────
#  Obter sinopse do anime via página oficial
# ───────────────────────────────────────────────
def obter_sinopse(link_ep):
    global WORKING_SCRAPER, WORKING_PROXY

    try:
        link_anime = obter_link_anime(link_ep)
        if not link_anime:
            print("[AVISO] Não foi possível encontrar o link do anime.")
            return ""

        r = WORKING_SCRAPER.get(link_anime, headers=HEADERS, timeout=10, proxies=WORKING_PROXY)
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

    # hora atual UTC-3
    agora_br = datetime.now(timezone(timedelta(hours=-3)))
    data_formatada = agora_br.strftime("%d/%m/%Y • %H:%M")

    for art in artigos:
        titulo_el = art.select_one("h2.entry-title")
        titulo_raw = titulo_el.get_text(strip=True) if titulo_el else "Sem título"

        ep_info_el = art.select_one("span.num-epi")
        ep_info = ep_info_el.get_text(strip=True) if ep_info_el else "?"

        titulo_final = f"<:Animesbrapp:1439021183365288111>  {titulo_raw} ({ep_info})"

        link_el = art.select_one("a.lnk-blk")
        link = link_el["href"] if link_el else None

        img_el = art.select_one(".post-thumbnail img")
        imagem = img_el["src"] if img_el else None
        if imagem and imagem.startswith("//"):
            imagem = "https:" + imagem

        episodios.append({
            "titulo": titulo_final,
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

    sinopse = obter_sinopse(ep["link"])

    if sinopse:
        descricao = sinopse + f"\n\n**❯ Assistir Online**\n[Clique aqui]({ep['link']})" 
    else:
        descricao = f"\n**❯ Assistir Online**\n[Clique aqui]({ep['link']})"
    
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
