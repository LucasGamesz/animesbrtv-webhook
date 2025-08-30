import os
import requests, certifi
from bs4 import BeautifulSoup
import json

# ────────── CONFIG ──────────
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DB_FILE     = "episodios_postados.json"
URL         = "https://animesbr.tv"
HEADERS     = {"User-Agent": "AnimesBRBot/1.0"}
LIMIT       = 5
ROLE_ID     = "1391784968786808873"  # ID do cargo que você quer pingar

# ────────── Carregar links já postados ──────────
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f:
        posted_links = set(json.load(f))
else:
    posted_links = set()

# ────────── Scraper ──────────
def get_ultimos_episodios(limit=5):
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15, verify=certifi.where())
        r.raise_for_status()
    except Exception as e:
        print(f"[ERRO] Falha na requisição: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    artigos = soup.select('article.item.se.episodes')[:limit]
    episodios = []

    for artigo in artigos:
        data_div   = artigo.find('div', class_='data')
        a_tag      = data_div.find('h3').find('a') if data_div else None
        link       = a_tag['href'] if a_tag else None
        titulo_ep  = a_tag.get_text(strip=True) if a_tag else "Episódio"
        nome_tag   = data_div.find('span', class_='serie') if data_div else None
        nome_anime = nome_tag.get_text(strip=True) if nome_tag else "Novo Anime"
        qual_tag   = artigo.find('span', class_='quality')
        qualidade  = qual_tag.get_text(strip=True) if qual_tag else "Desconhecida"
        spans      = data_div.find_all('span') if data_div else []
        data       = spans[0].get_text(strip=True) if spans else "Data não disponível"
        poster_div = artigo.find('div', class_='poster')
        img_tag    = poster_div.find('img') if poster_div else None
        imagem_url = img_tag['src'] if img_tag else None

        episodios.append({
            "link": link,
            "titulo_ep": titulo_ep,
            "nome_anime": nome_anime,
            "qualidade": qualidade,
            "data": data,
            "imagem": imagem_url
        })
    return episodios

# ────────── Função para enviar mensagem ──────────
def post_discord(ep):
    data = {
        "content": f"<@&{ROLE_ID}>",  # ping do cargo
        "embeds": [{
            "title": f"{ep['nome_anime']} - {ep['titulo_ep']}",
            "description": f"**Tipo:** {ep['qualidade']}\n[👉 Assistir online]({ep['link']})",
            "color": 0xFF0000,  # vermelho
            "thumbnail": {"url": ep['imagem']} if ep['imagem'] else {},
            "footer": {"text": f"Animesbr.tv • {ep['data']}"}
        }],
        "allowed_mentions": {"roles": [ROLE_ID]}  # permite pingar o cargo
    }
    r = requests.post(WEBHOOK_URL, json=data, timeout=10)
    if r.status_code == 204:
        print(f"[DISCORD] ✅ Enviado: {ep['titulo_ep']}")
    else:
        print(f"[DISCORD] ❌ Falha ao enviar: {r.status_code}")

# ────────── Loop principal ──────────
episodios = get_ultimos_episodios(LIMIT)
novo_postado = False

for ep in reversed(episodios):
    if ep["link"] and ep["link"] not in posted_links:
        post_discord(ep)
        posted_links.add(ep["link"])
        novo_postado = True
    else:
        print(f"[BOT] Episódio já postado ou inválido: {ep['titulo_ep']}")

# ────────── Salvar JSON atualizado ──────────
if novo_postado:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted_links), f, ensure_ascii=False, indent=2)
