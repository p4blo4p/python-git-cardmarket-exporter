
import os
import csv
import time
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuration from CLI
parser = argparse.ArgumentParser(description='Cardmarket Order Exporter with State Recovery')
parser.add_argument('--start-date', help='Format: YYYY-MM-DD')
parser.add_argument('--end-date', help='Format: YYYY-MM-DD')
parser.add_argument('--year', help='Full year e.g. 2025')
parser.add_argument('--include-orders', action='store_true', help='Export Purchases (Received)')
parser.add_argument('--include-sales', action='store_true', help='Export Sales (Sent)')
args = parser.parse_args()

USER_NAME = os.environ.get('CM_USERNAME')
PASSWORD = os.environ.get('CM_PASSWORD')
CSV_FILE = 'cardmarket_export.csv'

if not USER_NAME or not PASSWORD:
    print("Error: CM_USERNAME and CM_PASSWORD environment variables are required.")
    exit(1)

def load_existing_data():
    existing_ids = set()
    rows = []
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_ids.add(row.get('Order ID'))
                    rows.append(row)
            print(f"Loaded {len(existing_ids)} existing orders from {CSV_FILE}")
        except Exception as e:
            print(f"Could not load existing CSV: {e}")
    return existing_ids, rows

def parse_date_range():
    start_dt = None
    end_dt = datetime.now()
    if args.year and args.year.strip():
        start_dt = datetime(int(args.year), 1, 1)
        end_dt = datetime(int(args.year), 12, 31)
    elif args.start_date and args.start_date.strip():
        start_dt = datetime.strptime(args.start_date, '%Y-%m-%d')
        if args.end_date and args.end_date.strip():
            end_dt = datetime.strptime(args.end_date, '%Y-%m-%d')
    return start_dt, end_dt

def scrape_table(page, url, start_dt, end_dt, existing_ids):
    print(f"Scraping {url}...")
    page.goto(url)
    
    try:
        if page.query_selector('#cookie-allow-all-button'):
            page.click('#cookie-allow-all-button')
    except:
        pass

    new_data = []
    has_next = True
    page_num = 1

    while has_next:
        print(f"Processing page {page_num}...")
        try:
            page.wait_for_selector('div.table-body', timeout=15000)
        except:
            print("Timeout waiting for table body.")
            break
            
        rows = page.query_selector_all('div.table-body > div.row')
        if not rows:
            print("No rows found on this page.")
            break

        duplicate_count = 0
        for row in rows:
            try:
                order_id_el = row.query_selector('.col-orderId')
                order_id = order_id_el.inner_text().strip() if order_id_el else "N/A"
                
                # RECOVERY LOGIC: Skip if ID already exists
                if order_id in existing_ids:
                    duplicate_count += 1
                    continue

                date_el = row.query_selector('.col-date')
                date_str = date_el.inner_text().strip() if date_el else ""
                row_date = None
                try:
                    row_date = datetime.strptime(date_str.split(' ')[0], '%d.%m.%y')
                except:
                    pass

                if start_dt and row_date and row_date < start_dt:
                    has_next = False 
                    continue
                if end_dt and row_date and row_date > end_dt:
                    continue

                status = row.query_selector('.col-status').inner_text().strip() if row.query_selector('.col-status') else "N/A"
                user = row.query_selector('.col-user').inner_text().strip() if row.query_selector('.col-user') else "N/A"
                total = row.query_selector('.col-total').inner_text().strip() if row.query_selector('.col-total') else "N/A"

                new_data.append({
                    'Order ID': order_id,
                    'Date': date_str,
                    'User': user,
                    'Status': status,
                    'Total': total,
                    'Source': url
                })
                existing_ids.add(order_id)
            except Exception as e:
                print(f"Error parsing row: {e}")

        # If we only found duplicates on this page and we are scraping chronologically, 
        # we might have reached the end of new data.
        if duplicate_count == len(rows) and len(rows) > 0:
            print("All orders on this page already exist in CSV. Stopping.")
            has_next = False
            break

        next_btn = page.query_selector('a[aria-label="Next Page"]')
        if next_btn and has_next:
            next_btn.click()
            page.wait_for_load_state('networkidle')
            page_num += 1
            time.sleep(2)
        else:
            has_next = False

    return new_data

def run():
    start_dt, end_dt = parse_date_range()
    existing_ids, all_rows = load_existing_data()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        print("Logging in...")
        page.goto("https://www.cardmarket.com/en/Magic/MainPage/Login")
        page.fill('input[name="_username"]', USER_NAME)
        page.fill('input[name="_password"]', PASSWORD)
        page.click('input[type="submit"]')
        page.wait_for_load_state('networkidle')

        if "Login" in page.title() or page.query_selector('input[name="_username"]'):
            print("Login failed. Check credentials or CAPTCHA.")
            browser.close()
            exit(1)

        targets = []
        if args.include_orders: targets.append("https://www.cardmarket.com/en/Magic/Orders/Received")
        if args.include_sales: targets.append("https://www.cardmarket.com/en/Magic/Sales/Arrived")

        newly_scraped_count = 0
        for target in targets:
            new_rows = scrape_table(page, target, start_dt, end_dt, existing_ids)
            all_rows.extend(new_rows)
            newly_scraped_count += len(new_rows)

        if newly_scraped_count > 0:
            keys = all_rows[0].keys() if all_rows else ['Order ID', 'Date', 'User', 'Status', 'Total', 'Source']
            with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                dict_writer = csv.DictWriter(f, fieldnames=keys)
                dict_writer.writeheader()
                dict_writer.writerows(all_rows)
            print(f"Updated CSV with {newly_scraped_count} new records. Total: {len(all_rows)}")
        else:
            print("No new data found to add.")

        browser.close()

if __name__ == "__main__":
    run()
