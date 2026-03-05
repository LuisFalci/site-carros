import json
import time
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- Configurações ---
URL_BASE = "https://centercarjf.com.br"
URL_PAGINA_INICIAL = f"{URL_BASE}/veiculos/carros"
ARQUIVO_JSON = "estoque_carros_detalhado.json"
TEMPO_ESPERA_HORAS = 1

def carregar_json():
    """Lê o arquivo JSON existente."""
    if os.path.exists(ARQUIVO_JSON):
        with open(ARQUIVO_JSON, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def salvar_json(dados):
    """Salva a lista atualizada no arquivo JSON."""
    with open(ARQUIVO_JSON, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def configurar_driver():
    """Configura o WebDriver do Chrome."""
    chrome_options = Options()
    # Descomente para rodar em background:
    # chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--start-maximized")
    servico = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=servico, options=chrome_options)

def pegar_links_da_vitrine(driver):
    """Navega por todas as páginas da vitrine e coleta os links dos carros."""
    driver.get(URL_PAGINA_INICIAL)
    links_totais = set()
    pagina_atual = 1

    while True:
        print(f"Lendo página {pagina_atual}...")
        
        try:
            # Aguarda a presença dos links dos carros
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".dmi-card a"))
            )
            time.sleep(2) # Pausa para renderização do Angular
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            cards = soup.find_all('div', class_='dmi-card')
            
            for card in cards:
                tag_a = card.find('a')
                if tag_a and 'href' in tag_a.attrs:
                    link = tag_a['href']
                    if link.startswith('/'):
                        link = f"{URL_BASE}{link}"
                    links_totais.add(link)
            
            # --- Lógica de Paginação ---
            try:
                # Procura pelo botão ">" (Próximo)
                botao_proximo = driver.find_element(By.XPATH, "//ul[contains(@class, 'paginacao')]//a[contains(text(), '>')]")
                
                # Move até o botão para garantir visibilidade e clica
                driver.execute_script("arguments[0].scrollIntoView();", botao_proximo)
                time.sleep(1)
                botao_proximo.click()
                
                pagina_atual += 1
                time.sleep(2)
            except:
                print("Fim das páginas alcançado.")
                break
                
        except Exception as e:
            print(f"Erro na navegação da vitrine: {e}")
            break

    return list(links_totais)

def extrair_detalhes_do_carro(driver, url):
    """Acessa a página do carro e extrai informações detalhadas e o preço correto."""
    print(f" -> Extraindo: {url}")
    driver.get(url)
    
    try:
        # Aguarda um dado técnico essencial aparecer
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Quilometragem')]"))
        )
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        carro_dados = {
            "url": url,
            "data_coleta": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # --- NOVO: Extração do Preço ---
        # Buscamos a div que contém as classes de preço informadas
        preco_div = soup.find('div', class_=lambda x: x and 'font-semibold' in x and ('text-2xl' in x or 'md:text-3xl' in x))
        if preco_div:
            # get_text() com strip=True junta o "R$" do span com o valor da div
            carro_dados["preco"] = preco_div.get_text(strip=True)
        else:
            # Backup caso a classe mude: busca por qualquer div que contenha "R$"
            fallback = soup.find('div', string=lambda t: t and "R$" in t)
            carro_dados["preco"] = fallback.parent.get_text(strip=True) if fallback else "N/A"

        # Título
        tag_h1 = soup.find('h1')
        if tag_h1:
            carro_dados["nome_principal"] = tag_h1.text.strip()

        # Especificações Técnicas
        labels_esperadas = [
            "Quilometragem", "Combustível", "Motor", "Câmbio", 
            "Carroceria", "Cor", "Portas", "Ano Modelo", 
            "Ano Fabricação", "Marca", "Modelo", "Versão"
        ]
        
        for label in labels_esperadas:
            elemento_label = soup.find(string=lambda text: text and text.strip() == label)
            if elemento_label:
                # O valor é o elemento irmão (sibling) da label encontrada
                parent = elemento_label.parent
                valor = parent.find_next_sibling()
                if valor:
                    carro_dados[label] = valor.text.strip()

        return carro_dados
    except Exception as e:
        print(f"    [Erro] Falha nos detalhes de {url}: {e}")
        return None

def executar_monitoramento():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando ciclo de monitoramento...")
    
    carros_salvos = carregar_json()
    # Criamos um dicionário para facilitar a atualização por URL
    estoque_dict = {carro['url']: carro for carro in carros_salvos}
    
    driver = configurar_driver()
    
    try:
        # 1. Coleta todos os links que estão ativos no site agora
        links_ativos_no_site = set(pegar_links_da_vitrine(driver))
        print(f"Total de veículos ativos no site: {len(links_ativos_no_site)}")
        
        # 2. Marcar como VENDIDO quem está no JSON mas não está mais no site
        for url, dados_carro in estoque_dict.items():
            if url not in links_ativos_no_site:
                if dados_carro.get("status") != "vendido":
                    print(f" [VENDIDO] Detectado: {dados_carro.get('nome_principal')}")
                    dados_carro["status"] = "vendido"
            else:
                # Se voltou ao site, volta a ficar disponível
                dados_carro["status"] = "disponivel"
        
        # 3. Identificar novos carros para extrair detalhes
        links_novos = [l for l in links_ativos_no_site if l not in estoque_dict]
        
        if not links_novos:
            print("Nenhuma novidade encontrada.")
        else:
            print(f"{len(links_novos)} novos carros detectados. Extraindo...")
            for link in links_novos:
                dados = extrair_detalhes_do_carro(driver, link)
                if dados:
                    dados["status"] = "disponivel" # Carro novo chega como disponível
                    estoque_dict[link] = dados
                    # Salva o dicionário convertido de volta para lista
                    salvar_json(list(estoque_dict.values()))
            
        # Salva ao final para garantir a atualização dos status de vendidos
        salvar_json(list(estoque_dict.values()))
        print(f"Ciclo finalizado com sucesso.")
            
    except Exception as e:
        print(f"Erro crítico: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    print("=== Robô Center Car JF Ativado ===")
    while True:
        executar_monitoramento()
        print(f"Próxima varredura em {TEMPO_ESPERA_HORAS} hora(s)...")
        time.sleep(TEMPO_ESPERA_HORAS * 3600)