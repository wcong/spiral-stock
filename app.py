"""
Flask Web API
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import json
import os
import traceback
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen, Request

from chan import analyze_multi_level, result_to_dict

app = Flask(__name__, static_folder='static')
CORS(app)

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
STOCK_DATA_DIR = os.path.join(os.path.dirname(__file__), 'stock_data')


@app.route('/')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """
    接受JSON数据进行缠论分析

    请求体格式：
    {
        "data": [
            {"dt": "2024-01-01", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 10000},
            ...
        ]
    }

    或者上传CSV文件（multipart form），字段名为 file
    """
    try:
        content_type = request.content_type or ''

        if 'multipart/form-data' in content_type:
            # CSV上传
            f = request.files.get('file')
            if not f:
                return jsonify({'error': '未找到上传文件'}), 400
            df = pd.read_csv(f)
        else:
            # JSON
            body = request.get_json(force=True)
            if not body or 'data' not in body:
                return jsonify({'error': '请求体需包含 data 字段'}), 400
            df = pd.DataFrame(body['data'])

        # 列名标准化（支持中文列名）
        col_map = {
            '日期': 'dt', '时间': 'dt', 'date': 'dt', 'Date': 'dt',
            '开盘': 'open', '开盘价': 'open', 'Open': 'open',
            '最高': 'high', '最高价': 'high', 'High': 'high',
            '最低': 'low', '最低价': 'low', 'Low': 'low',
            '收盘': 'close', '收盘价': 'close', 'Close': 'close',
            '成交量': 'volume', 'Volume': 'volume', 'vol': 'volume',
        }
        df.rename(columns=col_map, inplace=True)

        required = {'dt', 'open', 'high', 'low', 'close'}
        missing = required - set(df.columns)
        if missing:
            return jsonify({'error': f'缺少必要列：{missing}'}), 400

        if len(df) < 10:
            return jsonify({'error': '数据量不足，至少需要10根K线'}), 400

        base_result, level_results, warnings = analyze_multi_level(
            df,
            levels=['30min', '60min', '1D'],
        )
        data = result_to_dict(base_result)
        data['levels'] = {
            'base': result_to_dict(base_result),
            **{k: result_to_dict(v) for k, v in level_results.items()},
        }

        # 上级别定方向，下级别找买卖点
        level_order = ['1D', '60min', '30min']
        trend_source = 'base'
        trend_direction = data.get('trend', 'side')
        for lvl in level_order:
            if lvl in data['levels']:
                trend_source = lvl
                trend_direction = data['levels'][lvl].get('trend', 'side')
                break

        if trend_direction == 'up':
            filtered_buy = data['buy_points']
            filtered_sell = []
        elif trend_direction == 'down':
            filtered_buy = []
            filtered_sell = data['sell_points']
        else:
            filtered_buy = data['buy_points']
            filtered_sell = data['sell_points']

        data['trade_bias'] = {
            'direction': trend_direction,
            'source_level': trend_source,
            'rule': 'higher_level_trend_filter',
        }
        data['filtered_buy_points'] = filtered_buy
        data['filtered_sell_points'] = filtered_sell
        if isinstance(data.get('diagnostics'), dict):
            data['diagnostics']['filtered_buy_points'] = len(filtered_buy)
            data['diagnostics']['filtered_sell_points'] = len(filtered_sell)

        data['forecast'] = _compute_forecast(data)

        return jsonify({
            'success': True,
            'data': data,
            'warnings': warnings,
            'summary': {
                'total_candles': len(base_result.raw_candles),
                'merged_candles': len(base_result.merged_candles),
                'bis_count': len(base_result.bis),
                'segments_count': len(base_result.segments),
                'zhongshus_count': len(base_result.zhongshus),
                'buy_points_count': len(base_result.buy_points),
                'sell_points_count': len(base_result.sell_points),
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _compute_forecast(data: dict) -> list[dict]:
    """基于当前结构给出3/5/10天趋势倾向（概率性）"""
    horizons = [3, 5, 10]
    raw = data.get('raw_candles', [])
    if not raw:
        return []

    dt_to_idx = {c['dt']: i for i, c in enumerate(raw)}
    last_idx = len(raw) - 1

    buys = data.get('filtered_buy_points') or data.get('buy_points') or []
    sells = data.get('filtered_sell_points') or data.get('sell_points') or []

    last_buy_idx = max((dt_to_idx.get(p['dt'], -1) for p in buys), default=-1)
    last_sell_idx = max((dt_to_idx.get(p['dt'], -1) for p in sells), default=-1)

    trend = data.get('trade_bias', {}).get('direction') or data.get('trend', 'side')

    forecasts = []
    for h in horizons:
        base_conf = 0.5
        direction = 'side'
        reason_parts = []

        if trend in {'up', 'down'}:
            direction = trend
            base_conf += 0.15
            reason_parts.append(f"趋势偏{('上' if trend == 'up' else '下')}")

        if last_buy_idx >= 0 and last_idx - last_buy_idx <= 5:
            if direction != 'down':
                direction = 'up'
                base_conf += 0.2
                reason_parts.append("近期买点触发")

        if last_sell_idx >= 0 and last_idx - last_sell_idx <= 5:
            if direction != 'up':
                direction = 'down'
                base_conf += 0.2
                reason_parts.append("近期卖点触发")

        if direction == 'side':
            base_conf -= 0.1
            reason_parts.append("结构偏震荡")

        base_conf = max(0.1, min(0.9, base_conf))
        if not reason_parts:
            reason_parts = ["结构信号不足"]

        forecasts.append({
            'horizon_days': h,
            'direction': direction,
            'confidence': round(base_conf, 2),
            'reason': '，'.join(reason_parts),
        })

    return forecasts


@app.route('/api/sample', methods=['GET'])
def api_sample():
    """返回示例数据，方便前端测试"""
    import numpy as np
    np.random.seed(42)
    n = 120
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    price = 100.0
    records = []
    for i, d in enumerate(dates):
        change = np.random.randn() * 2
        open_ = price
        close = price + change
        high = max(open_, close) + abs(np.random.randn())
        low = min(open_, close) - abs(np.random.randn())
        volume = int(np.random.uniform(5000, 20000))
        records.append({
            'dt': d.strftime('%Y-%m-%d'),
            'open': round(open_, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': volume,
        })
        price = close
    return jsonify({'data': records})


@app.route('/api/stock_files', methods=['GET'])
def api_stock_files():
    """列出本地 stock_data 下的文件"""
    try:
        if not os.path.isdir(STOCK_DATA_DIR):
            return jsonify({'files': []})
        files = [f for f in os.listdir(STOCK_DATA_DIR) if f.endswith('.json')]
        files.sort(reverse=True)
        items = []
        for f in files:
            code = f.split('_')[0]
            items.append({'file': f, 'code': code})
        return jsonify({'files': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stock_data', methods=['GET'])
def api_stock_data():
    """读取本地 stock_data 文件内容"""
    try:
        fname = request.args.get('file', '').strip()
        if not fname or '/' in fname or '\\' in fname:
            return jsonify({'error': '文件名无效'}), 400
        path = os.path.join(STOCK_DATA_DIR, fname)
        if not os.path.isfile(path):
            return jsonify({'error': '文件不存在'}), 404
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        data = payload.get('data', []) if isinstance(payload, dict) else []
        return jsonify({'success': True, 'data': data, 'file': fname})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crawl', methods=['POST'])
def api_crawl():
    """抓取东方财富K线数据并保存"""
    try:
        body = request.get_json(force=True) or {}
        code = str(body.get('code', '')).strip()
        fqt = str(body.get('fqt', '0')).strip()
        if fqt not in {'0', '1', '2'}:
            return jsonify({'error': 'fqt 参数无效，仅支持 0/1/2'}), 400
        if not code:
            return jsonify({'error': '请提供股票代码'}), 400

        secid = _to_eastmoney_secid(code)
        if not secid:
            return jsonify({'error': '无法识别股票代码'}), 400

        end_dt = datetime.now().date()
        start_dt = end_dt - timedelta(days=365)
        params = {
            'secid': secid,
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': '101',
            'fqt': fqt,
            'beg': start_dt.strftime('%Y%m%d'),
            'end': end_dt.strftime('%Y%m%d'),
        }
        url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{urlencode(params)}"
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode('utf-8'))

        if not payload or 'data' not in payload or not payload['data']:
            return jsonify({'error': '未获取到数据'}), 502

        klines = payload['data'].get('klines', [])
        if not klines:
            return jsonify({'error': '数据为空'}), 502

        records = []
        for row in klines:
            parts = row.split(',')
            if len(parts) < 6:
                continue
            records.append({
                'dt': parts[0],
                'open': float(parts[1]),
                'close': float(parts[2]),
                'high': float(parts[3]),
                'low': float(parts[4]),
                'volume': float(parts[5]),
            })

        os.makedirs(STOCK_DATA_DIR, exist_ok=True)
        filename = f"{code}_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}.json"
        file_path = os.path.join(STOCK_DATA_DIR, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({'data': records}, f, ensure_ascii=False)

        return jsonify({
            'success': True,
            'data': records,
            'file': os.path.join('stock_data', filename),
            'count': len(records),
            'fqt': fqt,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _to_eastmoney_secid(code: str) -> str | None:
    """将股票代码转换为东方财富 secid"""
    c = code.lower().replace('.', '').replace('sh', '').replace('sz', '').strip()
    if not c.isdigit():
        return None
    if code.lower().startswith('sh'):
        return f"1.{c}"
    if code.lower().startswith('sz'):
        return f"0.{c}"
    if c.startswith('6'):
        return f"1.{c}"
    if c.startswith('0') or c.startswith('3'):
        return f"0.{c}"
    return None


if __name__ == '__main__':
    os.makedirs(STATIC_DIR, exist_ok=True)
    port = int(os.environ.get('PORT', '8080'))
    print(f"缠论分析服务启动：http://localhost:{port}")
    app.run(debug=True, host='0.0.0.0', port=port)
