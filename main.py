import requests
import json
import os
from datetime import datetime, timedelta


def load_config():
    # GitHub Actions では環境変数から、ローカルでは config.json から読み込む
    if os.environ.get('LINE_CHANNEL_TOKEN'):
        return {
            'line_channel_token': os.environ['LINE_CHANNEL_TOKEN'],
            'line_user_id': os.environ['LINE_USER_ID'],
            'alert_threshold': int(os.environ.get('ALERT_THRESHOLD', '10')),
        }
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def send_line_message(token, user_id, message):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    data = {
        'to': user_id,
        'messages': [{'type': 'text', 'text': message}]
    }
    response = requests.post(
        'https://api.line.me/v2/bot/message/push',
        headers=headers,
        json=data
    )
    if not response.ok:
        print(f"LINE送信エラー: {response.status_code} {response.text}")
    return response.ok


def get_market_prices():
    from scraper import get_tokyo_market_prices
    return get_tokyo_market_prices()


def save_prices(prices):
    date = datetime.now().strftime('%Y-%m-%d')
    with open(f'prices_{date}.json', 'w', encoding='utf-8') as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)


def load_yesterday_prices():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        with open(f'prices_{yesterday}.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def load_last_pdf_urls():
    try:
        with open('last_pdf_urls.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_last_pdf_urls(urls):
    with open('last_pdf_urls.json', 'w', encoding='utf-8') as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)


def check_price_changes(current, previous, threshold):
    alerts = []
    for item, price in current.items():
        if item in previous and previous[item] > 0:
            change = (price - previous[item]) / previous[item] * 100
            if abs(change) >= threshold:
                direction = '上昇' if change > 0 else '下落'
                alerts.append(f"{item}: {previous[item]}円 → {price}円 ({change:+.1f}% {direction})")
    return alerts


def daily_report():
    config = load_config()
    prices, pdf_urls = get_market_prices()
    last_pdf_urls = load_last_pdf_urls()

    date = datetime.now().strftime('%m月%d日')

    if pdf_urls and pdf_urls == last_pdf_urls:
        message = f"農作物価格レポート {date}\n市場データは未更新です（週次レポートの次回更新をお待ちください）"
        print(message)
        send_line_message(config['line_channel_token'], config['line_user_id'], message)
        return

    yesterday = load_yesterday_prices()
    message = f"農作物価格レポート {date}\n\n"

    if prices:
        for item, price in prices.items():
            message += f"・{item}: {price}円/kg\n"
    else:
        message += "本日の価格データを取得できませんでした。\n"

    if pdf_urls:
        save_prices(prices)
        save_last_pdf_urls(pdf_urls)

    alerts = check_price_changes(prices, yesterday, config['alert_threshold'])
    if alerts:
        message += f"\n価格変動アラート({config['alert_threshold']}%以上):\n"
        for alert in alerts:
            message += f"・{alert}\n"

    print(message)
    send_line_message(config['line_channel_token'], config['line_user_id'], message)


if __name__ == '__main__':
    daily_report()
