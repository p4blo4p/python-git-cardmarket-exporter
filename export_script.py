
import os
import csv
import time
import argparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURACIÓN DE ARGUMENTOS ---
parser = argparse.ArgumentParser(description='Cardmarket Exporter Pro')
parser.add_argument('--year', help='Año filtro (ej. 2025)')
parser.add_argument('--include-purchases', action='store_true', help='Exportar Compras')
parser.add_argument('--include-sales', action='store_true', help='Exportar Ventas')
args = parser.parse_args()

# --- VARIABLES DE ENTORNO (CRÍTICAS) ---
CM_PHPSESSID = os.environ.get('CM_PHPSESSID', '').strip()

# El User-Agent es la "huella" de tu navegador. 
# Si no lo pones, usamos uno genérico que suele fallar.
CM_USER_AGENT = os.environ.get('CM_USER_AGENT', '').strip()

CSV_FILE = 'cardmarket_export.csv'

def get_headers(ua):
    return {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

def load_existing_data():
    existing_ids = set()
    rows = []
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('Order ID'):
                        existing_ids.add(row.get('Order ID'))
                        rows.append(row)
        except: pass
    return existing_ids, rows

def scrape_section(session, url, start_dt, existing_ids, ua):
    print(f"[*] Accediendo a: {url}")
    new_data = []
    page_num = 1
    headers = get_headers(ua)
    
    while True:
        paginated_url = f"{url}?site={page_num}"
        try:
            response = session.get(paginated_url, headers=headers, timeout=15)
            if 'Logout' not in response.text:
                print(f"[!] Sesión invalidada en página {page_num}. Cardmarket ha detectado el cambio de navegador.")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            table_body = soup.select_one('div.table-body')
            if not table_body: break
                
            rows = table_body.select('div.row')
            if not rows: break

            page_duplicates = 0
            for row in rows:
                id_el = row.select_one('.col-orderId')
                if not id_el: continue
                order_id = id_el.get_text(strip=True)

                if order_id in existing_ids:
                    page_duplicates += 1
                    continue

                date_el = row.select_one('.col-date')
                date_str = date_el.get_text(strip=True) if date_el else ""
                
                try:
                    row_dt = datetime.strptime(date_str.split(' ')[0], '%d.%m.%y')
                    if start_dt and row_dt < start_dt:
                        print(f"[*] Filtro de fecha alcanzado.")
                        return new_data
                except: pass

                status = row.select_one('.col-status').get_text(strip=True) if row.select_one('.col-status') else ""
                user = row.select_one('.col-user').get_text(strip=True) if row.select_one('.col-user') else ""
                total = row.select_one('.col-total').get_text(strip=True) if row.select_one('.col-total') else ""

                new_data.append({
                    'Order ID': order_id, 'Date': date_str, 'User': user, 
                    'Status': status, 'Total': total, 
                    'Type': 'Purchase' if 'Received' in url else 'Sale'
                })
                existing_ids.add(order_id)

            print(f"[*] Página {page_num}: {len(new_data)} nuevos.")
            if page_duplicates == len(rows): break
            if not soup.select_one('a[aria-label="Next Page"]'): break
            page_num += 1
            time.sleep(2)
        except Exception as e:
            print(f"[!] Error: {e}")
            break
    return new_data

def run():
    if not CM_PHPSESSID:
        print("[!] ERROR: No has configurado CM_PHPSESSID.")
        return
    
    ua = CM_USER_AGENT
    if not ua:
        ua = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'
        print("[?] ADVERTENCIA: No has puesto CM_USER_AGENT. Usando uno genérico (puede fallar).")

    existing_ids, all_rows = load_existing_data()
    start_dt = datetime(int(args.year), 1, 1) if args.year else None

    with requests.Session() as s:
        s.cookies.set('PHPSESSID', CM_PHPSESSID, domain='.cardmarket.com', path='/')
        
        print("[*] Verificando sesión...")
        headers = get_headers(ua)
        check = s.get("https://www.cardmarket.com/en/Magic", headers=headers, timeout=10)
        
        if 'Logout' in check.text:
            print("[+] SESIÓN ACTIVA. El User-Agent coincide correctamente.")
        else:
            print("[!] ERROR: Sesión incorrecta o expirada.")
            print("[!] RECUERDA: El CM_USER_AGENT en Termux debe ser IDÉNTICO al de tu móvil.")
            with open('debug_error.html', 'w', encoding='utf-8') as f: f.write(check.text)
            return

        new_items = []
        if args.include_purchases:
            new_items.extend(scrape_section(s, "https://www.cardmarket.com/en/Magic/Orders/Received", start_dt, existing_ids, ua))
        if args.include_sales:
            new_items.extend(scrape_section(s, "https://www.cardmarket.com/en/Magic/Sales/Sent", start_dt, existing_ids, ua))

        if new_items:
            all_rows.extend(new_items)
            keys = ['Order ID', 'Date', 'User', 'Status', 'Total', 'Type']
            with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(all_rows)
            print(f"[+] Guardado con éxito en {CSV_FILE}.")
        else:
            print("[*] No hay nada nuevo que descargar.")

if __name__ == "__main__":
    run()
