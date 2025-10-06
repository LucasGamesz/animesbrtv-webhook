import os
import json
import cloudscraper
from bs4 import BeautifulSoup
import requests

# ────────── CONFIG ──────────
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PROXY_URL   = os.getenv("PROXY_URL")  # Proxy principal (do GitHub Secrets)
DB_FILE     = "episodios_postados.json"
URL         = "https://animesbr.app"
LIMIT       = 5
ROLE_ID     = "1391784968786808873"  # ID do cargo que você quer pingar

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/"
}

# 💡 LISTA DE PROXIES GRATUITOS BRASILEIROS PARA TENTAR COMO FALLBACK
# ATENÇÃO: Substitua ESTA LISTA por endereços ativos que você encontrar!
# Formato: "http://IP:PORTA" ou "http://USUARIO:SENHA@IP:PORTA"
FALLBACK_PROXIES = [
    # Proxies de exemplo - AGORA CORRETAMENTE FORMATADOS COMO STRINGS!
    "http://177.136.44.194:54443",
    "http://187.19.201.217:8080",
    "http://177.11.67.162:8999",
    "http://45.182.177.81:9947",
    "http://31.97.93.252:3128",
    "http://187.103.105.20:8085",
    "http://189.50.45.105:1995",
    "http://187.84.176.20:8080",
    "http://170.247.200.69:8088",
    "http://191.252.204.220:8080",
    "http://186.215.87.194:30011",
    "http://177.82.99.173:7823",
    "http://189.48.37.164:8999",
    "http://187.103.105.18:8086",
    "http://201.8.204.194:8080",
    "http://168.195.214.41:8800",
    "http://45.70.4.89:8081",
    # Adicione mais proxies aqui...
]

# ────────── Carregar links já postados ──────────
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            # Tenta carregar o JSON. Se o arquivo estiver vazio, inicia um set vazio.
            content = f.read()
            if content:
                posted_links = set(json.loads(content))
            else:
                posted_links = set()
    except json.JSONDecodeError:
        # Lida com o JSON corrompido ou malformado (aquele JSONDecodeError)
        print(f"[ALERTA] Arquivo {DB_FILE} corrompido. Iniciando lista vazia.")
        posted_links = set()
else:
    posted_links = set()

# ────────── Scraper (com resiliência de Proxy) ──────────
def get_ultimos_episodios(limit=5):
    scraper = cloudscraper.create_scraper()
    
    # Monta a lista de proxies a serem testados
    proxies_to_test = []
    if PROXY_URL:
        proxies_to_test.append(PROXY_URL) # Tenta o proxy principal primeiro
        
    proxies_to_test.extend(FALLBACK_PROXIES) # Adiciona os de fallback
    
    r = None
    
    for current_proxy in proxies_to_test:
        
        # Monta o dicionário de proxies para a requisição
        proxies_dict = {
            "http": current_proxy,
            "https": current_proxy
        }
        
        print(f"[TESTE] Tentando com proxy: {current_proxy}")

        try:
            # Tenta fazer a requisição usando o proxy atual
            r = scraper.get(URL, headers=HEADERS, timeout=15, proxies=proxies_dict)
            r.raise_for_status()
            
            # Se chegou aqui, o proxy funcionou! Sai do loop
            print(f"[SUCESSO] Proxy '{current_proxy}' funcionando. Status: {r.status_code}")
            break 
            
        except Exception as e:
            # Se falhar (timeout ou 403), tenta o próximo proxy
            print(f"[ERRO] Falha com '{current_proxy}': {e}")
            r = None 
            continue
            
    # Se 'r' ainda for None após testar todos os proxies, a requisição falhou
    if r is None:
        print("[ERRO FATAL] Falha na requisição: Nenhum proxy da lista funcionou.")
        return []

    # --- Processamento dos dados (apenas se a requisição foi bem-sucedida) ---
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
        
        imagem_url = None
        if img_tag:
            # 1. Extrai 'data-src' ou 'src'
            imagem_url = img_tag.get('data-src') or img_tag.get('src')

            # 2. CORREÇÃO: Converte URL relativa para absoluta se necessário
            if imagem_url and imagem_url.startswith('//'):
                imagem_url = 'https:' + imagem_url
            elif imagem_url and not imagem_url.startswith('http'):
                 # Trata URLs relativas como /wp-content/... (improvável no seu caso, mas seguro)
                imagem_url = URL + imagem_url

        episodios.append({
            "link": link,
            "titulo_ep": titulo_ep,
            "nome_anime": nome_anime,
            "qualidade": qualidade,
            "data": data,
            "imagem": imagem_url
        })
    return episodios

# ────────── Função para enviar mensagem (com Debug) ──────────
def post_discord(ep):
    embed = {
        "title": f"{ep['nome_anime']} - {ep['titulo_ep']}",
        "description": f"**Tipo:** {ep['qualidade']}\n[👉 Assistir online]({ep['link']})",
        "color": 0xFF0000,  # vermelho
        "footer": {"text": f"Animesbr.tv • {ep['data']}"}
    }

    # Adiciona thumbnail apenas se for URL válida
    if ep['imagem'] and ep['imagem'].startswith("http"):
        embed["thumbnail"] = {"url": ep['imagem']}

    data = {
        "content": f"<@&{ROLE_ID}>",
        "embeds": [embed],
        "allowed_mentions": {"roles": [ROLE_ID]}
    }
    
    # Debug do JSON enviado
    print("[DEBUG] Enviando ao Discord:")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    r = requests.post(WEBHOOK_URL, json=data, timeout=10)
    
    # Debug da resposta (importante para o erro 400)
    print(f"[DEBUG] Resposta Discord: {r.status_code} {r.text}")

    if r.status_code == 204:
        print(f"[DISCORD] ✅ Enviado: {ep['titulo_ep']}")
        return True
    else:
        print(f"[DISCORD] ❌ Falha ao enviar: {r.status_code}")
        return False

# ────────── Loop principal ──────────
episodios = get_ultimos_episodios(LIMIT)
novo_postado = False

for ep in reversed(episodios):
    if ep["link"] and ep["link"] not in posted_links:
        # Só salva no JSON se o envio para o Discord for bem-sucedido (status 204)
        if post_discord(ep): 
            posted_links.add(ep["link"])
            novo_postado = True
    else:
        print(f"[BOT] Episódio já postado ou inválido: {ep['titulo_ep']}")

# ────────── Salvar JSON atualizado ──────────
if novo_postado:
    # Garante que o arquivo é criado com um JSON válido mesmo que não existisse
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(list(posted_links), f, ensure_ascii=False, indent=2)
