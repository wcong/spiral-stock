"""
背驰判断
"""
from dataclasses import dataclass
from .structure import Bi
from .zhongshu import ZhongShu
from .kline import RawCandle
import math


@dataclass
class BeiChi:
    """背驰结果"""
    bi_index: int           # 背驰发生的笔的索引
    btype: str              # 'trend' 趋势背驰 | 'pan' 盘整背驰
    direction: str          # 'up' 顶背驰 | 'down' 底背驰
    strength: float         # 背驰强度（0~1），越大越明显
    desc: str               # 描述


def _build_macd_hist(raw_candles: list[RawCandle]) -> list[float]:
    """计算MACD柱，长度与原始K线对齐"""
    if not raw_candles:
        return []
    closes = [c.close for c in raw_candles]
    ema12 = []
    ema26 = []
    alpha12 = 2 / (12 + 1)
    alpha26 = 2 / (26 + 1)
    for i, val in enumerate(closes):
        if i == 0:
            ema12.append(val)
            ema26.append(val)
        else:
            ema12.append(alpha12 * val + (1 - alpha12) * ema12[-1])
            ema26.append(alpha26 * val + (1 - alpha26) * ema26[-1])
    macd = [a - b for a, b in zip(ema12, ema26)]
    signal = []
    alpha9 = 2 / (9 + 1)
    for i, val in enumerate(macd):
        if i == 0:
            signal.append(val)
        else:
            signal.append(alpha9 * val + (1 - alpha9) * signal[-1])
    hist = [m - s for m, s in zip(macd, signal)]
    return hist


def _bi_range_indices(bi: Bi, dt_to_idx: dict) -> tuple[int, int] | None:
    start_idx = dt_to_idx.get(bi.start_dt)
    end_idx = dt_to_idx.get(bi.end_dt)
    if start_idx is None or end_idx is None:
        return None
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    return start_idx, end_idx


def calc_bi_energy(bi: Bi, dt_to_idx: dict | None = None, macd_hist: list[float] | None = None) -> float:
    """计算笔的力度，优先使用MACD柱面积，否则退化为振幅"""
    if dt_to_idx is None or not macd_hist:
        return bi.amplitude
    rng = _bi_range_indices(bi, dt_to_idx)
    if not rng:
        return bi.amplitude
    start_idx, end_idx = rng
    if end_idx - start_idx < 1:
        return bi.amplitude
    window = macd_hist[start_idx:end_idx + 1]
    if bi.direction == 'up':
        return sum(v for v in window if v > 0)
    return sum(-v for v in window if v < 0)


def detect_trend_beichi(
    bis: list[Bi],
    zhongshus: list[ZhongShu],
    raw_candles: list[RawCandle] | None = None,
) -> list[BeiChi]:
    """
    趋势背驰检测：
    在两个同向中枢之间，比较两段离开中枢的笔的力度
    后一段力度弱于前一段 → 趋势背驰
    """
    results = []
    if len(zhongshus) < 2:
        return results

    dt_to_idx = {c.dt: c.index for c in raw_candles} if raw_candles else None
    macd_hist = _build_macd_hist(raw_candles) if raw_candles else None

    for k in range(1, len(zhongshus)):
        prev_zs = zhongshus[k - 1]
        curr_zs = zhongshus[k]

        # 两个中枢需要同向（方向一致）
        if prev_zs.direction != curr_zs.direction:
            continue

        direction = prev_zs.direction

        # 找两个中枢之间的笔（离开前中枢、进入后中枢的段）
        prev_end_bi_idx = prev_zs.bis[-1].index
        curr_start_bi_idx = curr_zs.bis[0].index
        curr_end_bi_idx = curr_zs.bis[-1].index

        if prev_end_bi_idx < 0 or curr_start_bi_idx < 0 or curr_end_bi_idx < 0:
            continue

        # 离开前中枢的笔（上涨/下跌方向的笔）
        between_bis = [
            b for b in bis[prev_end_bi_idx + 1:curr_start_bi_idx]
            if b.direction == direction
        ]

        # 离开当前中枢后的同向笔（到下一个中枢前为止）
        next_zs = zhongshus[k + 1] if k + 1 < len(zhongshus) else None
        next_start_idx = next_zs.bis[0].index if next_zs else len(bis)
        after_curr_bis = [
            b for b in bis[curr_end_bi_idx + 1:next_start_idx]
            if b.direction == direction
        ]

        if not between_bis or not after_curr_bis:
            continue

        energy_before = sum(calc_bi_energy(b, dt_to_idx, macd_hist) for b in between_bis)
        energy_after = sum(calc_bi_energy(b, dt_to_idx, macd_hist) for b in after_curr_bis[:len(between_bis)])

        if energy_after < energy_before:
            strength = 1.0 - energy_after / (energy_before + 1e-9)
            desc = (
                f"趋势背驰（{direction}）：前段力度={energy_before:.2f}，"
                f"后段力度={energy_after:.2f}，背驰强度={strength:.1%}"
            )
            results.append(BeiChi(
                bi_index=curr_zs.bis[-1].index,
                btype='trend',
                direction=direction,
                strength=strength,
                desc=desc,
            ))

    return results


def detect_pan_beichi(
    bis: list[Bi],
    zhongshus: list[ZhongShu],
    raw_candles: list[RawCandle] | None = None,
) -> list[BeiChi]:
    """
    盘整背驰：在同一中枢内，进入和离开的力度对比
    离开力度 < 进入力度 → 盘整背驰
    """
    results = []
    dt_to_idx = {c.dt: c.index for c in raw_candles} if raw_candles else None
    macd_hist = _build_macd_hist(raw_candles) if raw_candles else None

    for zs in zhongshus:
        if not zs.bis:
            continue
        start_idx = zs.bis[0].index
        end_idx = zs.bis[-1].index
        if start_idx - 1 < 0 or end_idx + 1 >= len(bis):
            continue

        entry_bi = bis[start_idx - 1]
        exit_bi = bis[end_idx + 1]
        if entry_bi.direction != exit_bi.direction:
            continue

        entry_energy = calc_bi_energy(entry_bi, dt_to_idx, macd_hist)
        exit_energy = calc_bi_energy(exit_bi, dt_to_idx, macd_hist)

        if exit_energy < entry_energy * 0.8:  # 离开力度明显弱于进入
            strength = 1.0 - exit_energy / (entry_energy + 1e-9)
            desc = (
                f"盘整背驰：进入力度={entry_energy:.2f}，"
                f"离开力度={exit_energy:.2f}，背驰强度={strength:.1%}"
            )
            results.append(BeiChi(
                bi_index=exit_bi.index,
                btype='pan',
                direction=exit_bi.direction,
                strength=strength,
                desc=desc,
            ))

    return results


def detect_simple_beichi(
    bis: list[Bi],
    raw_candles: list[RawCandle] | None = None,
) -> list[BeiChi]:
    """
    简易背驰：同向两笔创新高/新低，但后一笔力度明显减弱
    """
    results = []
    if len(bis) < 2:
        return results

    dt_to_idx = {c.dt: c.index for c in raw_candles} if raw_candles else None
    macd_hist = _build_macd_hist(raw_candles) if raw_candles else None

    for i in range(1, len(bis)):
        cur = bis[i]
        # 找上一个同方向的笔
        prev = None
        for j in range(i - 1, -1, -1):
            if bis[j].direction == cur.direction:
                prev = bis[j]
                break
        if not prev:
            continue

        if cur.direction == 'down':
            made_new = cur.end_price < prev.end_price
        else:
            made_new = cur.end_price > prev.end_price

        prev_energy = calc_bi_energy(prev, dt_to_idx, macd_hist)
        cur_energy = calc_bi_energy(cur, dt_to_idx, macd_hist)
        if not made_new or prev_energy <= 0:
            continue

        if cur_energy < prev_energy * 0.85:
            strength = 1.0 - cur_energy / (prev_energy + 1e-9)
            desc = (
                f"简易背驰（{cur.direction}）：前段力度={prev_energy:.2f}，"
                f"后段力度={cur_energy:.2f}，背驰强度={strength:.1%}"
            )
            results.append(BeiChi(
                bi_index=cur.index,
                btype='simple',
                direction=cur.direction,
                strength=strength,
                desc=desc,
            ))

    return results
