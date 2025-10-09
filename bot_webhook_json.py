import os
import json
import cloudscraper
from bs4 import BeautifulSoup
import requests

# ────────── CONFIG ──────────
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PROXY_URL   = os.getenv("PROXY_URL")  # proxy brasileiro opcional
DB_FILE     = "episodios_postados.json"
URL         = "https://animesbr.app"
LIMIT       = 5
ROLE_ID     = "1391784968786808873"  # ID do cargo que você quer pingar

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/"
}

PROXIES = None
if PROXY_URL:
    PROXIES = {
        "http": PROXY_URL,
        "https": PROXY_URL
    }

# ────────── Carregar links já postados ──────────
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
        posted_links = set(json.load(f))
else:
    posted_links = set()

# ────────── Scraper ──────────
def get_ultimos_episodios(limit=5):
    scraper = cloudscraper.create_scraper()
    try:
        r = scraper.get(URL, headers=HEADERS, timeout=15, proxies=PROXIES)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERRO] Falha na requisição: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    artigos = soup.select('article.item.se.episodes')[:limit]
    episodios = []

    for artigo in artigos:
        data_div   = artigo.find('div', class_='data')
        a_tag      = artigo.select_one('div.season_m a')
        link       = a_tag['href'] if a_tag else None
        titulo_ep  = a_tag.get_text(strip=True) if a_tag else "Episódio"
        nome_tag   = artigo.select_one('span.serie')
        nome_anime = nome_tag.get_text(strip=True) if nome_tag else ""
        qual_tag   = artigo.find('span', class_='quality')
        qualidade  = qual_tag.get_text(strip=True) if qual_tag else "Desconhecida"

        # Corrigido para pegar o src da imagem (e não data-src)
        poster_div = artigo.find('div', class_='poster')
        img_tag    = poster_div.find('img') if poster_div else None
        imagem_url = img_tag.get('src') or img_tag.get('data-src') if img_tag else None

        episodios.append({
            "link": link,
            "titulo_ep": titulo_ep,
            "nome_anime": nome_anime,
            "qualidade": qualidade,
            "imagem": imagem_url
        })
    return episodios

# ────────── Função para enviar mensagem ──────────
def post_discord(ep):
    data = {
        "content": f"<@&{ROLE_ID}>",
        "embeds": [{
            "title": f"{ep['nome_anime']} - {ep['titulo_ep']}".strip(" -"),
            "description": f"**Qualidade:** {ep['qualidade']}\n[👉 Assistir online]({ep['link']})",
            "color": 0xFF0000,
            "thumbnail": {"url": ep['imagem']} if ep['imagem'] else {},
            "footer": {"text": "AnimesBR • Atualização automática"}
        }],
        "allowed_mentions": {"roles": [ROLE_ID]}
    }

    try:
        r = requests.post(WEBHOOK_URL, json=data, timeout=10)
        if r.status_code == 204:
            print(f"[DISCORD] ✅ Enviado: {ep['titulo_ep']}")
            return True
        else:
            print(f"[DISCORD] ❌ Falha ao enviar ({r.status_code}): {ep['titulo_ep']}")
            return False
    except Exception as e:
        print(f"[DISCORD] ❌ Erro: {e}")
        return False

# ────────── Loop principal ──────────
episodios = get_ultimos_episodios(LIMIT)
novo_postado = False

for ep in reversed(episodios):
    if ep["link"] and ep["link"] not in posted_links:
        if post_discord(ep):
            posted_links.add(ep["link"])
            novo_postado = True
    else:
        print(f"[BOT] Episódio já postado ou inválido: {ep['titulo_ep']}")

# ────────── Salvar JSON atualizado ──────────
if novo_postado:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted_links), f, ensure_ascii=False, indent=2)
