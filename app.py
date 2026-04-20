"""
Flask Web API
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import json
import os
import traceback

from chan import analyze, result_to_dict

app = Flask(__name__, static_folder='static')
CORS(app)

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')


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

        result = analyze(df)
        data = result_to_dict(result)

        return jsonify({
            'success': True,
            'data': data,
            'summary': {
                'total_candles': len(result.raw_candles),
                'merged_candles': len(result.merged_candles),
                'bis_count': len(result.bis),
                'segments_count': len(result.segments),
                'zhongshus_count': len(result.zhongshus),
                'buy_points_count': len(result.buy_points),
                'sell_points_count': len(result.sell_points),
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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


if __name__ == '__main__':
    os.makedirs(STATIC_DIR, exist_ok=True)
    print("缠论分析服务启动：http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
