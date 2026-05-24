import json
import os
from datetime import datetime
from flask import Flask, render_template

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
HIGHLIGHT_ITEMS = {'ミニトマト'}  # 洞戸農場の栽培品目


def load_price_history(days=7):
    """prices_YYYY-MM-DD.json を日付順に最大 days 件読み込む"""
    entries = []
    for fname in os.listdir(DATA_DIR):
        if not (fname.startswith('prices_') and fname.endswith('.json')):
            continue
        date_str = fname[7:-5]
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue
        path = os.path.join(DATA_DIR, fname)
        try:
            with open(path, encoding='utf-8') as f:
                entries.append({'date': date_str, 'prices': json.load(f)})
        except (json.JSONDecodeError, OSError):
            pass
    return sorted(entries, key=lambda x: x['date'])[-days:]


def trend_bars(trend, bar_count=7):
    """トレンドデータを棒グラフ用の高さ(%)リストに変換"""
    if len(trend) < 2:
        return []
    prices = [t['price'] for t in trend]
    lo, hi = min(prices), max(prices)
    span = hi - lo or 1
    return [max(10, int((p - lo) / span * 100)) for p in prices]


@app.route('/')
def index():
    history = load_price_history()
    if not history:
        return render_template('index.html', items=[], date='-', updated='-', no_data=True)

    latest = history[-1]
    prev = history[-2] if len(history) >= 2 else None

    items = []
    for name, price in latest['prices'].items():
        prev_price = prev['prices'].get(name) if prev else None
        change = None
        if prev_price and prev_price > 0:
            change = (price - prev_price) / prev_price * 100

        trend = [{'date': h['date'], 'price': h['prices'][name]}
                 for h in history if name in h['prices']]
        bars = trend_bars(trend)

        items.append({
            'name': name,
            'price': price,
            'prev_price': prev_price,
            'change': change,
            'trend': trend,
            'bars': bars,
            'highlight': name in HIGHLIGHT_ITEMS,
        })

    # ハイライト品目を先頭、残りは名前順
    items.sort(key=lambda x: (not x['highlight'], x['name']))

    dt = datetime.strptime(latest['date'], '%Y-%m-%d')
    updated = f"{dt.year}年{dt.month}月{dt.day}日"

    return render_template('index.html',
                           items=items,
                           date=latest['date'],
                           updated=updated,
                           no_data=False)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5100))
    print(f'Farm Dashboard: http://localhost:{port}')
    app.run(debug=False, port=port, host='0.0.0.0')
