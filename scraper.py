from playwright.sync_api import sync_playwright
import pdfplumber
import requests
import re
import io
import csv
import tempfile
import os
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
    pdf_urls = {}

    yasai_url = get_latest_pdf_url(base_url, '/torihiki/week/yasai')
    if yasai_url:
        print(f"野菜PDF: {yasai_url}")
        pdf_urls['yasai'] = yasai_url
        prices.update(parse_pdf_prices(yasai_url, veg_items))

    kajitsu_url = get_latest_pdf_url(base_url, '/torihiki/week/kajitsu')
    if kajitsu_url:
        print(f"果実PDF: {kajitsu_url}")
        pdf_urls['kajitsu'] = kajitsu_url
        prices.update(parse_pdf_prices(kajitsu_url, fruit_items))

    return prices, pdf_urls


def get_maff_daily_prices():
    """農水省 日次価格データを取得 → {品目名: {'price': 円/kg, 'yoy': 対前日比%}}"""
    target_items = {
        'だいこん', 'にんじん', 'キャベツ', 'はくさい', 'ほうれんそう',
        'ねぎ', 'ブロッコリー', 'レタス', 'きゅうり', 'なす',
        'トマト', 'ミニトマト', 'ピーマン', 'ばれいしょ', 'たまねぎ',
    }
    base_url = 'https://www.seisen.maff.go.jp'
    index_url = f'{base_url}/seisen/bs04b040md001/BS04B040UC020SC998-Evt001.do'

    prices = {}
    data_date = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ],
        )
        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            locale='ja-JP',
        )
        page = context.new_page()
        try:
            page.goto(index_url, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=20000)

            # 最新日付のリンクをクリック（getElementById を含む JS リンク）
            date_links = page.query_selector_all('a[href*="getElementById"]')
            if not date_links:
                date_links = page.query_selector_all('a[href^="javascript:"]')
            if not date_links:
                content = page.content()
                print(f"日付リンクが見つかりませんでした。ページ内容(先頭500文字):\n{content[:500]}")
                return {}, {}

            print(f"日付リンク {len(date_links)}個 発見: {date_links[0].get_attribute('href')}")
            date_links[0].click()

            # CSV リンクが現れるまで待つ（navigation イベント非依存）
            try:
                page.wait_for_selector('a:has-text("CSV")', timeout=20000)
            except Exception as e:
                print(f"CSVリンク待機タイムアウト: {e}")
                return {}, {}

            csv_links = page.query_selector_all('a:has-text("CSV")')
            if not csv_links:
                print("CSVリンクが見つかりませんでした")
                return {}, {}

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            tmp.close()
            with page.expect_download(timeout=20000) as dl:
                csv_links[0].click()
            dl.value.save_as(tmp.name)

        finally:
            browser.close()

    # CSV を shift-jis でパース
    try:
        with open(tmp.name, 'rb') as f:
            raw = f.read()
        text = raw.decode('shift-jis')
        reader = csv.reader(text.splitlines())
        header = next(reader)  # 年,月,日,曜日,品目名,品目コード,産地名,産地コード,数量,価格,...

        for row in reader:
            if len(row) < 10:
                continue
            year, month, day = row[0], row[1], row[2]
            item_name = row[4].strip()
            area_name = row[6].strip()  # 空 = 全市場集計行
            price_str = row[9].strip()
            yoy_str = row[11].strip() if len(row) > 11 else ''

            # 集計行のみ（産地名が空）かつ対象品目
            if area_name == '' and item_name in target_items and price_str:
                try:
                    data_date = f"{year}-{int(month):02d}-{int(day):02d}"
                    prices[item_name] = {
                        'price': int(price_str),
                        'yoy': float(yoy_str) if yoy_str else None,
                    }
                except (ValueError, TypeError):
                    pass
    finally:
        os.unlink(tmp.name)

    print(f"農水省日次データ取得完了: {data_date}, {len(prices)}品目")
    return prices, {'date': data_date} if data_date else {}


if __name__ == '__main__':
    print("=== 農水省 日次価格データ取得テスト ===\n")
    prices, meta = get_maff_daily_prices()
    print(f"\nデータ日付: {meta.get('date')}")
    print(f"\n{'品目':<15} {'価格(円/kg)':>10} {'対前日比':>8}")
    print('-' * 38)
    for item, data in sorted(prices.items()):
        yoy = f"{data['yoy']:.1f}%" if data['yoy'] else '-'
        print(f"{item:<15} {data['price']:>10} {yoy:>8}")

    print("\n=== 旧方式（週次PDF）テスト ===\n")
    prices2, pdf_urls = get_tokyo_market_prices()
    print(f"\n=== 取得した価格 ===")
    for k, v in prices2.items():
        print(f"  {k}: {v}円")
    print(f"\n=== 使用したPDF ===")
    for k, v in pdf_urls.items():
        print(f"  {k}: {v}")
