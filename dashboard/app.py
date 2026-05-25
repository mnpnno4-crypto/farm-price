import json
import os
from datetime import datetime
from flask import Flask, render_template, abort

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
HIGHLIGHT_ITEMS = {'ミニトマト'}  # 洞戸農場の栽培品目

ALL_ITEMS = {
    'だいこん', 'にんじん', 'キャベツ', 'はくさい', 'ほうれんそう',
    'ねぎ', 'ブロッコリー', 'レタス', 'きゅうり', 'なす',
    'トマト', 'ミニトマト', 'ピーマン', 'ばれいしょ', 'たまねぎ',
}


def load_price_history(days=None):
    """prices_YYYY-MM-DD.json を日付順に読み込む。days=None で全件。"""
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
    entries = sorted(entries, key=lambda x: x['date'])
    return entries[-days:] if days else entries


def trend_bars(trend):
    """トレンドデータを棒グラフ用の高さ(%)リストに変換"""
    if len(trend) < 2:
        return []
    prices = [t['price'] for t in trend]
    lo, hi = min(prices), max(prices)
    span = hi - lo or 1
    return [max(10, int((p - lo) / span * 100)) for p in prices]


def fmt_date(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{dt.year}年{dt.month}月{dt.day}日"


@app.route('/')
def index():
    history = load_price_history(days=7)
    if not history:
        return render_template('index.html', items=[], no_items=[], updated='-', no_data=True)

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

        items.append({
            'name': name,
            'price': price,
            'prev_price': prev_price,
            'change': change,
            'trend': trend,
            'bars': trend_bars(trend),
            'highlight': name in HIGHLIGHT_ITEMS,
        })

    items.sort(key=lambda x: (not x['highlight'], x['name']))

    # 本日取引なしの品目
    today_names = set(latest['prices'].keys())
    no_items = sorted(ALL_ITEMS - today_names)

    return render_template('index.html',
                           items=items,
                           no_items=no_items,
                           updated=fmt_date(latest['date']),
                           no_data=False)


@app.route('/item/<item_name>')
def item_detail(item_name):
    if item_name not in ALL_ITEMS:
        abort(404)

    history = load_price_history()  # 全件
    series = [{'date': h['date'], 'price': h['prices'][item_name]}
              for h in history if item_name in h['prices']]

    if not series:
        return render_template('item_detail.html',
                               item_name=item_name,
                               no_data=True,
                               highlight=item_name in HIGHLIGHT_ITEMS)

    latest_price = series[-1]['price']
    prev_price = series[-2]['price'] if len(series) >= 2 else None
    change = ((latest_price - prev_price) / prev_price * 100) if prev_price else None

    prices = [s['price'] for s in series]

    return render_template('item_detail.html',
                           item_name=item_name,
                           series=series,
                           latest_price=latest_price,
                           prev_price=prev_price,
                           change=change,
                           max_price=max(prices),
                           min_price=min(prices),
                           avg_price=round(sum(prices) / len(prices)),
                           days=len(series),
                           highlight=item_name in HIGHLIGHT_ITEMS,
                           no_data=False)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5100))
    print(f'Farm Dashboard: http://localhost:{port}')
    app.run(debug=False, port=port, host='0.0.0.0')
