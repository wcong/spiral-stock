"""
缠论主入口：接收K线数据，输出完整分析结果
"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from .kline import RawCandle, MergedCandle, merge_candles
from .structure import Bi, Segment, find_bis, find_segments
from .zhongshu import ZhongShu, find_zhongshus
from .signals import BuyPoint, SellPoint, find_buy_sell_points


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


def result_to_dict(result: ChanResult) -> dict:
    """将结果序列化为可JSON化的字典"""
    return {
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
            }
            for sp in result.sell_points
        ],
    }
