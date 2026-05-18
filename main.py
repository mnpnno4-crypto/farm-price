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
    from scraper import get_maff_daily_prices
    raw, meta = get_maff_daily_prices()
    # raw = {item: {'price': int, 'yoy': float|None}}
    # prices_simple = {item: price} for backward compat
    prices_simple = {item: d['price'] for item, d in raw.items()}
    return prices_simple, raw, meta


def save_prices(prices_simple, prices_raw, data_date):
    with open(f'prices_{data_date}.json', 'w', encoding='utf-8') as f:
        json.dump(prices_simple, f, ensure_ascii=False, indent=2)


def load_previous_prices(data_date):
    """データ日付の前営業日の価格JSONを読む。なければ空dict。"""
    from datetime import timedelta
    dt = datetime.strptime(data_date, '%Y-%m-%d')
    for i in range(1, 8):
        prev = (dt - timedelta(days=i)).strftime('%Y-%m-%d')
        try:
            with open(f'prices_{prev}.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            continue
    return {}


def load_last_data_date():
    try:
        with open('last_data_date.json', 'r', encoding='utf-8') as f:
            return json.load(f).get('date')
    except FileNotFoundError:
        return None


def save_last_data_date(date_str):
    with open('last_data_date.json', 'w', encoding='utf-8') as f:
        json.dump({'date': date_str}, f)


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
    prices_simple, prices_raw, meta = get_market_prices()
    data_date = meta.get('date') if meta else None

    today_str = datetime.now().strftime('%m月%d日')

    if not data_date:
        message = f"農作物価格レポート {today_str}\nデータ取得に失敗しました。"
        print(message)
        send_line_message(config['line_channel_token'], config['line_user_id'], message)
        return

    last_date = load_last_data_date()
    if data_date == last_date:
        message = f"農作物価格レポート {today_str}\n市場データは未更新です（最新: {data_date}）"
        print(message)
        send_line_message(config['line_channel_token'], config['line_user_id'], message)
        return

    previous = load_previous_prices(data_date)
    date_label = datetime.strptime(data_date, '%Y-%m-%d').strftime('%m月%d日')
    message = f"農作物価格レポート（{date_label}）\n\n"

    if prices_raw:
        for item, d in sorted(prices_raw.items()):
            yoy = f" 前日比{d['yoy']:.1f}%" if d['yoy'] else ''
            message += f"・{item}: {d['price']}円/kg{yoy}\n"
    else:
        message += "本日の価格データを取得できませんでした。\n"

    save_prices(prices_simple, prices_raw, data_date)
    save_last_data_date(data_date)

    alerts = check_price_changes(prices_simple, previous, config['alert_threshold'])
    if alerts:
        message += f"\n価格変動アラート({config['alert_threshold']}%以上):\n"
        for alert in alerts:
            message += f"・{alert}\n"

    print(message)
    send_line_message(config['line_channel_token'], config['line_user_id'], message)


if __name__ == '__main__':
    daily_report()
