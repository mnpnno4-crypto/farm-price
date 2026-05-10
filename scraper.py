from playwright.sync_api import sync_playwright
import pdfplumber
import requests
import re
import io
from datetime import datetime


def get_latest_pdf_url(base_url, page_path):
    """週間市況ページから最新のPDF URLを取得（野菜・果実両対応）"""
    now = datetime.now()
    month_str = f"{now.month:02d}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(f'{base_url}{page_path}', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=20000)

            links = page.query_selector_all('a')
            month_pdfs = []
            all_pdfs = []
            doc_links = []

            for link in links:
                href = link.get_attribute('href') or ''
                if not href:
                    continue
                full_url = href if href.startswith('http') else base_url + href

                if '.pdf' in href.lower():
                    all_pdfs.append(full_url)
                    filename = href.split('/')[-1]
                    if filename.startswith(month_str):
                        month_pdfs.append(full_url)
                elif '/documents/d/' in href:
                    doc_links.append(full_url)

            if month_pdfs:
                return sorted(month_pdfs)[-1]
            elif all_pdfs:
                return sorted(all_pdfs)[-1]
            elif doc_links:
                # 果実ページ: /documents/d/ リンクの最後（最新）を返す
                return doc_links[-1]

            return None
        finally:
            browser.close()


def parse_pdf_prices(pdf_url, target_items):
    """PDFから価格を抽出"""
    prices = {}

    response = requests.get(pdf_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
    if not response.ok:
        print(f"PDF取得失敗: {response.status_code}")
        return prices

    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        full_text = ''
        for p in pdf.pages:
            full_text += (p.extract_text() or '') + '\n'

        lines = full_text.split('\n')
        for i, line in enumerate(lines):
            for item in target_items:
                if item in line:
                    numbers = re.findall(r'\b(\d{2,6})\b', line)
                    for num in numbers:
                        n = int(num)
                        if 50 <= n <= 50000:
                            prices[item] = n
                            break

    return prices


def get_tokyo_market_prices():
    base_url = 'https://www.shijou.metro.tokyo.lg.jp'

    veg_items = {
        'キャベツ', 'トマト', 'たまねぎ', 'だいこん', 'じゃがいも',
        'レタス', 'きゅうり', 'なす', 'ほうれんそう', 'ブロッコリー',
        'ねぎ', 'ピーマン', '白菜'
    }
    fruit_items = {
        'りんご', 'みかん', 'キウイ', 'キウイフルーツ', 'バナナ', 'ぶどう', 'もも', 'なし', 'いちご'
    }

    prices = {}

    yasai_url = get_latest_pdf_url(base_url, '/torihiki/week/yasai')
    if yasai_url:
        print(f"野菜PDF: {yasai_url}")
        prices.update(parse_pdf_prices(yasai_url, veg_items))

    kajitsu_url = get_latest_pdf_url(base_url, '/torihiki/week/kajitsu')
    if kajitsu_url:
        print(f"果実PDF: {kajitsu_url}")
        prices.update(parse_pdf_prices(kajitsu_url, fruit_items))

    return prices


if __name__ == '__main__':
    print("市場価格を取得中...\n")
    prices = get_tokyo_market_prices()
    print(f"\n=== 取得した価格 ===")
    for k, v in prices.items():
        print(f"  {k}: {v}円")
