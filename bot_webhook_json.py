import requests
import cloudscraper
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta

# -----------------------------
# CONFIGURAÇÃO DE PROXIES
# -----------------------------
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
    "http://186.250.202.104:8080"
]

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
MAIN_PROXY = os.getenv("PROXY_URL")

# -----------------------------
# FUNÇÃO REQUEST COM FALLBACK
# -----------------------------
def fazer_request(url):
    proxies = [{"http": MAIN_PROXY, "https": MAIN_PROXY}] if MAIN_PROXY else []
    proxies += [{"http": p, "https": p} for p in FALLBACK_PROXIES]

    scraper = cloudscraper.create_scraper()

    for proxy in proxies:
        try:
            print(f"Tentando proxy: {proxy['http']}")
            resp = scraper.get(url, proxies=proxy, timeout=12)
            if resp.status_code == 200:
                return resp
        except Exception:
            continue

    return None

# -----------------------------
# OBTER LINK CORRETO DA PÁGINA DO ANIME
# -----------------------------
def obter_link_pagina_anime(link_ep):
    resp = fazer_request(link_ep)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    temporadas_btn = soup.select_one("a.btn.tertiary-bg.mar span.ttu.dn.sm-dib.mal")

    if not temporadas_btn:
        return None

    a_tag = temporadas_btn.parent
    anime_link = a_tag.get("href")
    return anime_link if anime_link else None

# -----------------------------
# OBTER SINOPSE (SEGUNDO <p>)
# -----------------------------
def obter_sinopse(link_anime):
    if not link_anime:
        return None

    resp = fazer_request(link_anime)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    desc = soup.select_one(".description")

    if not desc:
        return None

    ps = desc.find_all("p")
    if len(ps) < 2:
        return None

    return ps[1].get_text(strip=True)

# -----------------------------
# ENVIAR EMBED
# -----------------------------
def enviar_discord(ep, sinopse):
    now = datetime.utcnow() - timedelta(hours=3)
    hora_atual = now.strftime("%d/%m/%Y • %H:%M")

    titulo = f"<:Animesbrapp:1439021183365288111> {ep['titulo']} ({ep['num']})"

    if sinopse:
        descricao = f"{sinopse}\n**❯ Assistir Online**\n[Clique aqui]({ep['link']})"
    else:
        descricao = f"**❯ Assistir Online**\n[Clique aqui]({ep['link']})"

    embed = {
        "embeds": [
            {
                "title": titulo,
                "description": descricao,
                "color": 0xFF0000,
                "footer": {
                    "text": f"Animesbr.tv • {hora_atual}"
                }
            }
        ]
    }

    requests.post(WEBHOOK_URL, json=embed)

# -----------------------------
# SALVAR JSON
# -----------------------------
def carregar_json():
    if not os.path.exists("episodios_postados.json"):
        return []
    with open("episodios_postados.json", "r", encoding="utf-8") as f:
        return json.load(f)

def salvar_json(data):
    with open("episodios_postados.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -----------------------------
# RASPAGEM PRINCIPAL
# -----------------------------
def buscar_episodios():
    url = "https://www.animesbr.app/ultimos-episodios"
    resp = fazer_request(url)
    if not resp:
        print("Falha ao acessar página de episódios.")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    items = soup.select(".item")
    episodios = []

    for item in items:
        titulo = item.select_one(".entry-title")
        num = item.select_one(".num-epi")
        link = item.get("href")

        if not titulo or not num or not link:
            continue

        episodios.append({
            "titulo": titulo.get_text(strip=True),
            "num": num.get_text(strip=True),
            "link": link
        })

    return episodios

# -----------------------------
# MAIN LOOP
# -----------------------------
def main():
    postados = carregar_json()
    novos = buscar_episodios()

    for ep in novos:
        chave = f"{ep['titulo']}|{ep['num']}"

        if chave in postados:
            continue

        link_anime = obter_link_pagina_anime(ep["link"])
        sinopse = obter_sinopse(link_anime)

        enviar_discord(ep, sinopse)

        postados.append(chave)
        salvar_json(postados)

    print("Finalizado.")

if __name__ == "__main__":
    main()
