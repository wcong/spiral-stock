"""
分型、笔、线段识别
"""
from dataclasses import dataclass, field
from typing import Optional
from .kline import MergedCandle


@dataclass
class Fractal:
    """分型"""
    index: int          # 在合并K线列表中的中间K线位置
    ftype: str          # 'top' 顶分型 | 'bottom' 底分型
    candle: MergedCandle
    left: MergedCandle
    right: MergedCandle

    @property
    def high(self):
        return self.candle.high

    @property
    def low(self):
        return self.candle.low

    @property
    def dt(self):
        return self.candle.dt


@dataclass
class Bi:
    """笔"""
    index: int
    start: Fractal      # 起始分型
    end: Fractal        # 结束分型
    direction: str      # 'up' 上笔 | 'down' 下笔

    @property
    def start_price(self):
        return self.start.low if self.direction == 'up' else self.start.high

    @property
    def end_price(self):
        return self.end.high if self.direction == 'up' else self.end.low

    @property
    def start_dt(self):
        return self.start.dt

    @property
    def end_dt(self):
        return self.end.dt

    @property
    def amplitude(self):
        return abs(self.end_price - self.start_price)


@dataclass
class Segment:
    """线段"""
    index: int
    bis: list           # 包含的笔列表
    direction: str      # 'up' 上升线段 | 'down' 下降线段

    @property
    def start_bi(self):
        return self.bis[0]

    @property
    def end_bi(self):
        return self.bis[-1]

    @property
    def start_price(self):
        return self.start_bi.start_price

    @property
    def end_price(self):
        return self.end_bi.end_price

    @property
    def start_dt(self):
        return self.start_bi.start_dt

    @property
    def end_dt(self):
        return self.end_bi.end_dt


def find_fractals(merged: list[MergedCandle]) -> list[Fractal]:
    """从合并K线中识别分型"""
    fractals = []
    for i in range(1, len(merged) - 1):
        left = merged[i - 1]
        mid = merged[i]
        right = merged[i + 1]

        if mid.high > left.high and mid.high > right.high:
            # 顶分型
            fractals.append(Fractal(index=i, ftype='top', candle=mid, left=left, right=right))
        elif mid.low < left.low and mid.low < right.low:
            # 底分型
            fractals.append(Fractal(index=i, ftype='bottom', candle=mid, left=left, right=right))

    return fractals


def find_bis(merged: list[MergedCandle]) -> list[Bi]:
    """
    从合并K线中识别笔
    规则：相邻顶底分型之间至少有1根独立K线（即间距>=2）
    """
    fractals = find_fractals(merged)
    if not fractals:
        return []

    # 过滤：相邻分型必须不同类型，且间距>=2（实际K线索引差>=2+2=更严格）
    valid_fractals = []
    for f in fractals:
        if not valid_fractals:
            valid_fractals.append(f)
            continue
        prev = valid_fractals[-1]
        # 同类型分型，只保留极值更极端的那个
        if f.ftype == prev.ftype:
            # 同类型分型只保留更极端的
            if f.ftype == 'top' and f.high > prev.high:
                valid_fractals[-1] = f
            elif f.ftype == 'bottom' and f.low < prev.low:
                valid_fractals[-1] = f
        else:
            # 不同类型，检查间距（中间至少有1根独立K线，即索引差>=2）
            if f.index - prev.index >= 2:
                valid_fractals.append(f)
            else:
                # 间距不足，保留极值更极端的
                if f.ftype == 'top' and f.high >= prev.high:
                    valid_fractals[-1] = f
                elif f.ftype == 'bottom' and f.low <= prev.low:
                    valid_fractals[-1] = f

    bis = []
    for i in range(len(valid_fractals) - 1):
        start = valid_fractals[i]
        end = valid_fractals[i + 1]
        if start.ftype == 'bottom' and end.ftype == 'top':
            direction = 'up'
        elif start.ftype == 'top' and end.ftype == 'bottom':
            direction = 'down'
        else:
            continue
        bis.append(Bi(index=len(bis), start=start, end=end, direction=direction))

    return bis


def find_segments(bis: list[Bi]) -> list[Segment]:
    """
    从笔中识别线段
    规则：至少3笔，且第1笔和第3笔有重叠（特征序列分型确认）
    简化实现：3笔同向+方向一致构成线段，后续线段被特征序列分型破坏时结束
    """
    if len(bis) < 3:
        return []

    segments = []
    i = 0
    while i <= len(bis) - 3:
        b0, b1, b2 = bis[i], bis[i + 1], bis[i + 2]
        if b0.direction == b2.direction and b0.direction != b1.direction:
            direction = b0.direction
            # 尝试延伸线段
            seg_bis = [b0, b1, b2]
            j = i + 3
            while j <= len(bis) - 2:
                b_next1 = bis[j]
                b_next2 = bis[j + 1] if j + 1 < len(bis) else None
                # 检查线段是否被破坏
                if direction == 'up':
                    # 上升线段被破坏：出现向下的笔创新低（低于线段起始低点）
                    if b_next1.direction == 'down' and b_next1.end_price < seg_bis[0].start_price:
                        break
                    # 延伸：新的上笔高于前高
                    if b_next1.direction == 'up':
                        seg_bis.append(b_next1)
                        if b_next2:
                            seg_bis.append(b_next2)
                            j += 2
                        else:
                            j += 1
                        continue
                else:
                    # 下降线段被破坏
                    if b_next1.direction == 'up' and b_next1.end_price > seg_bis[0].start_price:
                        break
                    if b_next1.direction == 'down':
                        seg_bis.append(b_next1)
                        if b_next2:
                            seg_bis.append(b_next2)
                            j += 2
                        else:
                            j += 1
                        continue
                j += 1

            segments.append(Segment(index=len(segments), bis=seg_bis, direction=direction))
            i += len(seg_bis)
        else:
            i += 1

    return segments
