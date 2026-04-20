"""
K线基础数据结构与包含关系处理
"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class RawCandle:
    """原始K线"""
    index: int          # 原始索引
    dt: str             # 日期时间
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class MergedCandle:
    """处理包含关系后的合并K线"""
    index: int                      # 合并后的序号
    raw_indices: list               # 包含的原始K线索引列表
    dt: str                         # 代表日期（最后一根）
    high: float
    low: float
    close: float
    direction: int = 0              # 1=上涨方向, -1=下跌方向, 0=初始

    @property
    def mid(self):
        return (self.high + self.low) / 2


def merge_candles(raw_candles: list[RawCandle]) -> list[MergedCandle]:
    """
    处理K线包含关系，返回合并后的K线列表
    规则：
      - 上升趋势中，包含关系取高高（保留较高的高点和高低点）
      - 下降趋势中，包含关系取低低（保留较低的高点和低低点）
    """
    merged = []
    for raw in raw_candles:
        mc = MergedCandle(
            index=len(merged),
            raw_indices=[raw.index],
            dt=raw.dt,
            high=raw.high,
            low=raw.low,
            close=raw.close,
        )
        if not merged:
            merged.append(mc)
            continue

        prev = merged[-1]
        # 判断包含关系
        cur_contains_prev = mc.high >= prev.high and mc.low <= prev.low
        prev_contains_cur = prev.high >= mc.high and prev.low <= mc.low

        if cur_contains_prev or prev_contains_cur:
            # 确定合并方向：看前两根合并K线的方向
            if len(merged) >= 2:
                direction = 1 if merged[-1].high >= merged[-2].high else -1
            else:
                # 默认用当前价格方向
                direction = 1 if mc.close >= prev.high else -1

            # 合并
            if direction == 1:  # 上升：取高高
                new_high = max(prev.high, mc.high)
                new_low = max(prev.low, mc.low)
            else:               # 下降：取低低
                new_high = min(prev.high, mc.high)
                new_low = min(prev.low, mc.low)

            merged[-1].high = new_high
            merged[-1].low = new_low
            merged[-1].dt = mc.dt
            merged[-1].close = mc.close
            merged[-1].raw_indices.extend(mc.raw_indices)
        else:
            # 确定方向
            mc.direction = 1 if mc.high > prev.high else -1
            mc.index = len(merged)
            merged.append(mc)

    return merged
