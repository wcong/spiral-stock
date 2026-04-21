# Spiral Stock (Chan Theory)

A Flask-based Chan Theory (ChanLun) analysis tool for stock K-line data. It provides:
- Candlestick visualization with Chan structure layers (bi, segments, zhongshu)
- Buy/sell point detection with explanations
- Multi-level trend filter (30min/60min/1D) from a single input series
- Web UI with charts and signal list

## Requirements

- Python 3.10+ recommended

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Then open:

```
http://localhost:5000
```

## Usage (Web UI)

1. Upload a CSV/JSON file, or click "Load Sample".
2. Toggle layers (bi, segments, zhongshu, buy/sell points).
3. Use the trend filter toggle to show only signals that match the higher-level trend.
4. Click a signal card or a point on the chart to read the explanation.

### Expected data format

Columns (CSV) or fields (JSON objects):

- dt (date or datetime)
- open
- high
- low
- close
- volume (optional)

Example JSON:

```json
{
  "data": [
    {"dt": "2024-01-01", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 10000}
  ]
}
```

Example CSV header:

```
dt,open,high,low,close,volume
```

## API

### POST /api/analyze

Send JSON:

```json
{
  "data": [
    {"dt": "2024-01-01", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 10000}
  ]
}
```

Or upload CSV as multipart form field `file`.

Response (trimmed):

```json
{
  "success": true,
  "data": {
    "trend": "up",
    "trend_meta": {"rule": "segment_zhongshu_consistency"},
    "levels": {"base": {"trend": "up"}, "60min": {"trend": "side"}},
    "trade_bias": {"direction": "up", "source_level": "1D"},
    "filtered_buy_points": [],
    "filtered_sell_points": []
  },
  "warnings": []
}
```

### GET /api/sample

Returns sample K-line data.

## Production

Use a WSGI server (gunicorn) instead of the Flask dev server.

Install:

```bash
pip install gunicorn
```

Run:

```bash
PORT=8080 gunicorn -w 2 -b 0.0.0.0:80 app:app
```

Background run:

```bash
conda run -n spiral gunicorn -w 2 -b 0.0.0.0:80 app:app
```

Then open:

```
http://localhost:80
```

Notes:
- Set `PORT` to any safe port (avoid Chrome-blocked ports like 5060).
- Use a reverse proxy (nginx) if you need HTTPS or domain routing.

## Notes

- If the input series is daily data, the 30min/60min/1D aggregation may skip some levels.
- Trend filtering is based on higher-level trend consistency rules.
