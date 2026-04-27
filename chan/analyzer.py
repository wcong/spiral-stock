"""
缠论主入口：接收K线数据，输出完整分析结果
"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from .kline import RawCandle, MergedCandle, merge_candles
from .structure import Bi, Segment, find_bis, find_segments, find_fractals
from .zhongshu import ZhongShu, find_zhongshus
from .signals import BuyPoint, SellPoint, find_buy_sell_points
from .beichi import detect_trend_beichi, detect_pan_beichi, detect_simple_beichi


@dataclass
class ChanResult:
    """缠论完整分析结果"""
    raw_candles: list[RawCandle]
    merged_candles: list[MergedCandle]
    bis: list[Bi]
    segments: list[Segment]
    zhongshus: list[ZhongShu]
    buy_points: list[BuyPoint]
    sell_points: list[SellPoint]


def infer_trend(result: "ChanResult") -> str:
    """根据线段/中枢一致性推断当前趋势方向"""
    return _infer_trend_with_meta(result)[0]


def infer_trend_meta(result: "ChanResult") -> dict:
    """输出趋势判断的依据，便于调试与解释"""
    return _infer_trend_with_meta(result)[1]


def _infer_trend_with_meta(result: "ChanResult") -> tuple[str, dict]:
    segment_dir = result.segments[-1].direction if result.segments else None
    last_zs = result.zhongshus[-1] if result.zhongshus else None
    zhongshu_dir = last_zs.direction if last_zs else None

    if result.raw_candles:
        last_price = result.raw_candles[-1].close
    elif result.bis:
        last_price = result.bis[-1].end_price
    else:
        last_price = None

    meta = {
        'rule': 'segment_zhongshu_consistency',
        'segment_direction': segment_dir,
        'zhongshu_direction': zhongshu_dir,
        'last_price': last_price,
        'zhongshu_zg': last_zs.zg if last_zs else None,
        'zhongshu_zd': last_zs.zd if last_zs else None,
        'resolved': None,
    }

    if not segment_dir and not zhongshu_dir:
        if result.bis:
            meta['rule'] = 'fallback_bi'
            meta['resolved'] = result.bis[-1].direction
            return result.bis[-1].direction, meta
        meta['rule'] = 'no_structure'
        meta['resolved'] = 'side'
        return 'side', meta

    if zhongshu_dir:
        if segment_dir and segment_dir != zhongshu_dir:
            meta['rule'] = 'segment_zhongshu_conflict'
            meta['resolved'] = 'side'
            return 'side', meta

        if last_price is not None and last_zs:
            if zhongshu_dir == 'up' and last_price > last_zs.zg:
                meta['resolved'] = 'up'
                return 'up', meta
            if zhongshu_dir == 'down' and last_price < last_zs.zd:
                meta['resolved'] = 'down'
                return 'down', meta

        meta['rule'] = 'zhongshu_no_breakout'
        meta['resolved'] = 'side'
        return 'side', meta

    meta['rule'] = 'segment_only'
    meta['resolved'] = segment_dir or 'side'
    return segment_dir or 'side', meta


def analyze(df: pd.DataFrame) -> ChanResult:
    """
    主分析函数

    Parameters
    ----------
    df : pd.DataFrame
        必须包含列: dt(str), open(float), high(float), low(float), close(float)
        可选列: volume(float)

    Returns
    -------
    ChanResult
    """
    # 1. 转换为原始K线
    raw_candles = []
    for i, row in df.iterrows():
        raw_candles.append(RawCandle(
            index=len(raw_candles),
            dt=str(row['dt']),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row.get('volume', 0)),
        ))

    # 2. 包含关系处理
    merged = merge_candles(raw_candles)

    # 3. 识别笔
    bis = find_bis(merged)

    # 4. 识别线段
    segments = find_segments(bis)

    # 5. 识别中枢
    zhongshus = find_zhongshus(bis)

    # 6. 识别买卖点
    buy_points, sell_points = find_buy_sell_points(bis, zhongshus)

    return ChanResult(
        raw_candles=raw_candles,
        merged_candles=merged,
        bis=bis,
        segments=segments,
        zhongshus=zhongshus,
        buy_points=buy_points,
        sell_points=sell_points,
    )


def analyze_multi_level(
    df: pd.DataFrame,
    levels: Optional[list[str]] = None,
) -> tuple[ChanResult, dict[str, ChanResult], list[str]]:
    """
    多级别分析：在基础级别上，自动聚合到更高周期并分析

    Parameters
    ----------
    df : pd.DataFrame
        原始K线数据
    levels : list[str]
        目标级别，如 ['30min', '60min', '1D']
    """
    base_result = analyze(df)
    warnings: list[str] = []
    levels = levels or []

    norm_df = _normalize_df(df)
    if norm_df.empty:
        return base_result, {}, ["时间字段无法解析，跳过多级别聚合"]

    results: dict[str, ChanResult] = {}
    for rule in levels:
        agg = _aggregate_ohlcv(norm_df, rule)
        if agg is None or len(agg) < 10:
            warnings.append(f"级别 {rule} 数据不足或无法聚合，已跳过")
            continue
        results[rule] = analyze(agg)

    return base_result, results, warnings


def result_to_dict(result: ChanResult) -> dict:
    """将结果序列化为可JSON化的字典"""
    diag = _build_diagnostics(result)
    trend_beichi = detect_trend_beichi(result.bis, result.zhongshus, result.raw_candles)
    pan_beichi = detect_pan_beichi(result.bis, result.zhongshus, result.raw_candles)
    simple_beichi = detect_simple_beichi(result.bis, result.raw_candles)
    all_beichi = trend_beichi + pan_beichi + simple_beichi
    beichi_items = []
    if all_beichi:
        bi_by_index = {b.index: b for b in result.bis}
        for bc in all_beichi:
            bi = bi_by_index.get(bc.bi_index)
            if not bi:
                continue
            beichi_items.append({
                "bi_index": bc.bi_index,
                "btype": bc.btype,
                "direction": bc.direction,
                "strength": bc.strength,
                "desc": bc.desc,
                "start_dt": bi.start_dt,
                "end_dt": bi.end_dt,
                "start_price": bi.start_price,
                "end_price": bi.end_price,
            })
    fractals = find_fractals(result.merged_candles)
    return {
        "trend": infer_trend(result),
        "trend_meta": infer_trend_meta(result),
        "diagnostics": diag,
        "beichi": beichi_items,
        "candles": [
            {
                "dt": c.dt,
                "open": rc.open,
                "high": rc.high,
                "low": rc.low,
                "close": rc.close,
                "volume": rc.volume,
            }
            for c, rc in zip(result.merged_candles, result.raw_candles[:len(result.merged_candles)])
            # 实际用原始K线绘图
        ],
        "raw_candles": [
            {
                "dt": c.dt,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in result.raw_candles
        ],
        "merged_candles": [
            {
                "dt": c.dt,
                "high": c.high,
                "low": c.low,
                "index": c.index,
            }
            for c in result.merged_candles
        ],
        "fractals": [
            {
                "index": f.index,
                "ftype": f.ftype,
                "dt": f.dt,
                "price": f.high if f.ftype == 'top' else f.low,
            }
            for f in fractals
        ],
        "bis": [
            {
                "index": b.index,
                "direction": b.direction,
                "start_dt": b.start_dt,
                "end_dt": b.end_dt,
                "start_price": b.start_price,
                "end_price": b.end_price,
            }
            for b in result.bis
        ],
        "segments": [
            {
                "index": s.index,
                "direction": s.direction,
                "start_dt": s.start_dt,
                "end_dt": s.end_dt,
                "start_price": s.start_price,
                "end_price": s.end_price,
            }
            for s in result.segments
        ],
        "zhongshus": [
            {
                "index": z.index,
                "zg": z.zg,
                "zd": z.zd,
                "gg": z.gg,
                "dd": z.dd,
                "start_dt": z.start_dt,
                "end_dt": z.end_dt,
                "direction": z.direction,
            }
            for z in result.zhongshus
        ],
        "buy_points": [
            {
                "btype": bp.btype,
                "dt": bp.dt,
                "price": bp.price,
                "reason": bp.reason,
                "source": getattr(bp, 'source', None),
                "beichi_strength": bp.beichi.strength if bp.beichi else None,
                "beichi_type": bp.beichi.btype if bp.beichi else None,
            }
            for bp in result.buy_points
        ],
        "sell_points": [
            {
                "btype": sp.btype,
                "dt": sp.dt,
                "price": sp.price,
                "reason": sp.reason,
                "source": getattr(sp, 'source', None),
            }
            for sp in result.sell_points
        ],
    }


def _build_diagnostics(result: ChanResult) -> dict:
    trend_beichi = detect_trend_beichi(result.bis, result.zhongshus, result.raw_candles)
    pan_beichi = detect_pan_beichi(result.bis, result.zhongshus, result.raw_candles)
    simple_beichi = detect_simple_beichi(result.bis, result.raw_candles)

    return {
        'raw_candles': len(result.raw_candles),
        'merged_candles': len(result.merged_candles),
        'bis': len(result.bis),
        'segments': len(result.segments),
        'zhongshus': len(result.zhongshus),
        'beichi_trend': len(trend_beichi),
        'beichi_pan': len(pan_beichi),
        'beichi_simple': len(simple_beichi),
        'beichi_total': len(trend_beichi) + len(pan_beichi) + len(simple_beichi),
        'buy_points': len(result.buy_points),
        'sell_points': len(result.sell_points),
    }


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """标准化时间序列，便于聚合"""
    tmp = df.copy()
    if 'dt' not in tmp.columns:
        return pd.DataFrame()
    tmp['dt'] = pd.to_datetime(tmp['dt'], errors='coerce')
    tmp = tmp.dropna(subset=['dt']).sort_values('dt')
    tmp = tmp.drop_duplicates(subset=['dt'])
    return tmp


def _aggregate_ohlcv(df: pd.DataFrame, rule: str) -> Optional[pd.DataFrame]:
    """按指定频率聚合OHLCV"""
    if df.empty:
        return None
    tmp = df.set_index('dt')

    required = {'open', 'high', 'low', 'close'}
    if not required.issubset(set(tmp.columns)):
        return None

    ohlc = tmp.resample(rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
    })
    if 'volume' in tmp.columns:
        ohlc['volume'] = tmp['volume'].resample(rule).sum()
    ohlc = ohlc.dropna(subset=['open', 'high', 'low', 'close'])
    ohlc = ohlc.reset_index()
    ohlc['dt'] = ohlc['dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
    return ohlc
