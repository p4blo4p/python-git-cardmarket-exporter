
import os
import csv
import time
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuración de argumentos
parser = argparse.ArgumentParser(description='Cardmarket Exporter Pro con Recuperación')
parser.add_argument('--start-date', help='YYYY-MM-DD')
parser.add_argument('--end-date', help='YYYY-MM-DD')
parser.add_argument('--year', help='Año (ej. 2025)')
parser.add_argument('--include-purchases', action='store_true', help='Exportar Compras')
parser.add_argument('--include-sales', action='store_true', help='Exportar Ventas')
args = parser.parse_args()

USER_NAME = os.environ.get('CM_USERNAME')
PASSWORD = os.environ.get('CM_PASSWORD')
CSV_FILE = 'cardmarket_export.csv'

def load_existing_data():
    """Carga los IDs existentes para evitar duplicados y retomar el trabajo."""
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
            print(f"INFO: Se cargaron {len(existing_ids)} registros existentes para recuperación.")
        except Exception as e:
            print(f"WARNING: No se pudo leer el CSV previo: {e}")
    return existing_ids, rows

def scrape_section(page, url, start_dt, end_dt, existing_ids):
    print(f"INFO: Navegando a {url}...")
    page.goto(url, wait_until="networkidle")
    
    # Intentar cerrar banners de cookies
    try:
        cookie_btn = page.query_selector('#cookie-allow-all-button')
        if cookie_btn: cookie_btn.click()
    except: pass

    new_data = []
    has_next = True
    page_num = 1

    while has_next:
        print(f"DEBUG: Procesando página {page_num}...")
        try:
            page.wait_for_selector('div.table-body', timeout=10000)
        except:
            print("ERROR: No se encontró la tabla de pedidos. ¿Quizás no hay registros?")
            break
            
        rows = page.query_selector_all('div.table-body > div.row')
        if not rows: break

        page_duplicates = 0
        for row in rows:
            try:
                id_el = row.query_selector('.col-orderId')
                order_id = id_el.inner_text().strip() if id_el else None
                
                if not order_id: continue

                # LÓGICA DE RECUPERACIÓN: Si el ID ya existe, lo saltamos
                if order_id in existing_ids:
                    page_duplicates += 1
                    continue

                date_el = row.query_selector('.col-date')
                date_str = date_el.inner_text().strip() if date_el else ""
                
                try:
                    row_date = datetime.strptime(date_str.split(' ')[0], '%d.%m.%y')
                    if start_dt and row_date < start_dt:
                        has_next = False
                        continue
                    if end_dt and row_date > end_dt:
                        continue
                except: pass

                status = row.query_selector('.col-status').inner_text().strip() if row.query_selector('.col-status') else ""
                user = row.query_selector('.col-user').inner_text().strip() if row.query_selector('.col-user') else ""
                total = row.query_selector('.col-total').inner_text().strip() if row.query_selector('.col-total') else ""

                new_data.append({
                    'Order ID': order_id,
                    'Date': date_str,
                    'User': user,
                    'Status': status,
                    'Total': total,
                    'Type': 'Purchase' if 'Received' in url else 'Sale'
                })
                existing_ids.add(order_id)
            except Exception as e:
                print(f"DEBUG: Error procesando fila: {e}")

        # Si toda la página son duplicados, es que ya estamos al día
        if page_duplicates == len(rows) and len(rows) > 0:
            print("INFO: Se detectaron solo registros existentes en esta página. Sincronización completa para esta sección.")
            has_next = False
            break

        next_btn = page.query_selector('a[aria-label="Next Page"]')
        if next_btn and has_next:
            next_btn.click()
            page.wait_for_load_state('networkidle')
            page_num += 1
            time.sleep(1)
        else:
            has_next = False

    return new_data

def run():
    existing_ids, all_rows = load_existing_data()
    
    start_dt = None
    end_dt = datetime.now()
    if args.year:
        start_dt = datetime(int(args.year), 1, 1)
        end_dt = datetime(int(args.year), 12, 31)
    elif args.start_date:
        start_dt = datetime.strptime(args.start_date, '%Y-%m-%d')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()

        print("INFO: Iniciando sesión en Cardmarket...")
        page.goto("https://www.cardmarket.com/en/Magic/MainPage/Login")
        
        # Detección de Cloudflare
        if "Cloudflare" in page.title() or "moment" in page.title():
            print("CRITICAL: Bloqueado por Cloudflare. Las IPs de GitHub suelen estar marcadas.")
            browser.close()
            exit(1)

        try:
            # Selectores alternativos para mayor robustez
            page.wait_for_selector('input[name="_username"], input[name="username"]', timeout=15000)
            user_selector = 'input[name="_username"]' if page.query_selector('input[name="_username"]') else 'input[name="username"]'
            pass_selector = 'input[name="_password"]' if page.query_selector('input[name="_password"]') else 'input[name="password"]'
            
            page.fill(user_selector, USER_NAME)
            page.fill(pass_selector, PASSWORD)
            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_load_state('networkidle')
        except Exception as e:
            print(f"CRITICAL: No se pudo interactuar con el formulario de login: {e}")
            browser.close()
            exit(1)

        if "Login" in page.title():
            print("CRITICAL: Login fallido. Revisa tus credenciales o si hay un CAPTCHA visual.")
            browser.close()
            exit(1)

        new_count = 0
        if args.include_purchases:
            new_count += len(scrape_section(page, "https://www.cardmarket.com/en/Magic/Orders/Received", start_dt, end_dt, existing_ids))
        if args.include_sales:
            new_count += len(scrape_section(page, "https://www.cardmarket.com/en/Magic/Sales/Sent", start_dt, end_dt, existing_ids))

        if new_count > 0:
            # Re-obtener todas las filas (actualizadas en existing_ids/all_rows por referencia en teoría, 
            # pero mejor reconstruir all_rows o asegurar append)
            # Para este script, scrape_section añade directamente a la lógica de retorno.
            # Re-guardar todo
            # Nota: para simplicidad reconstruimos la lista final basándonos en el orden de scrape
            # En una app real ordenaríamos por fecha.
            # Aquí simplemente guardamos all_rows que ya tiene lo viejo + lo nuevo.
            
            # Ordenar por fecha descendente (opcional pero recomendado)
            # all_rows.sort(key=lambda x: x['Date'], reverse=True)

            keys = ['Order ID', 'Date', 'User', 'Status', 'Total', 'Type']
            with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                # Filtrar para asegurar que solo escribimos lo que tiene las llaves correctas
                for r in all_rows:
                    writer.writerow({k: r.get(k, '') for k in keys})
            print(f"SUCCESS: Se añadieron {new_count} nuevos registros. Total actual: {len(all_rows)}")
        else:
            print("INFO: No hay nuevos datos para añadir.")

        browser.close()

if __name__ == "__main__":
    run()
