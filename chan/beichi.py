"""
背驰判断
"""
from dataclasses import dataclass
from .structure import Bi
from .zhongshu import ZhongShu
import math


@dataclass
class BeiChi:
    """背驰结果"""
    bi_index: int           # 背驰发生的笔的索引
    btype: str              # 'trend' 趋势背驰 | 'pan' 盘整背驰
    direction: str          # 'up' 顶背驰 | 'down' 底背驰
    strength: float         # 背驰强度（0~1），越大越明显
    desc: str               # 描述


def calc_bi_energy(bi: Bi) -> float:
    """计算笔的力度（简化：振幅作为力度代理）"""
    return bi.amplitude


def detect_trend_beichi(bis: list[Bi], zhongshus: list[ZhongShu]) -> list[BeiChi]:
    """
    趋势背驰检测：
    在两个同向中枢之间，比较两段离开中枢的笔的力度
    后一段力度弱于前一段 → 趋势背驰
    """
    results = []
    if len(zhongshus) < 2:
        return results

    for k in range(1, len(zhongshus)):
        prev_zs = zhongshus[k - 1]
        curr_zs = zhongshus[k]

        # 两个中枢需要同向（方向一致）
        if prev_zs.direction != curr_zs.direction:
            continue

        direction = prev_zs.direction

        # 找两个中枢之间的笔（离开前中枢、进入后中枢的段）
        prev_end_bi_idx = bis.index(prev_zs.bis[-1]) if prev_zs.bis[-1] in bis else -1
        curr_start_bi_idx = bis.index(curr_zs.bis[0]) if curr_zs.bis[0] in bis else -1

        if prev_end_bi_idx < 0 or curr_start_bi_idx < 0:
            continue

        # 离开前中枢的笔（上涨/下跌方向的笔）
        between_bis = [
            b for b in bis[prev_end_bi_idx:curr_start_bi_idx]
            if b.direction == direction
        ]
        # 离开后中枢的笔
        after_curr_bis = [
            b for b in bis[curr_start_bi_idx:]
            if b.direction == direction
        ]

        if not between_bis or not after_curr_bis:
            continue

        energy_before = sum(calc_bi_energy(b) for b in between_bis)
        energy_after = sum(calc_bi_energy(b) for b in after_curr_bis[:len(between_bis)])

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


def detect_pan_beichi(bis: list[Bi], zhongshus: list[ZhongShu]) -> list[BeiChi]:
    """
    盘整背驰：在同一中枢内，进入和离开的力度对比
    离开力度 < 进入力度 → 盘整背驰
    """
    results = []
    for zs in zhongshus:
        if len(zs.bis) < 3:
            continue
        entry_bi = zs.bis[0]
        exit_bi = zs.bis[-1]
        entry_energy = calc_bi_energy(entry_bi)
        exit_energy = calc_bi_energy(exit_bi)

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


def detect_simple_beichi(bis: list[Bi]) -> list[BeiChi]:
    """
    简易背驰：同向两笔创新高/新低，但后一笔力度明显减弱
    """
    results = []
    if len(bis) < 2:
        return results

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

        if not made_new or prev.amplitude <= 0:
            continue

        if cur.amplitude < prev.amplitude * 0.95:
            strength = 1.0 - cur.amplitude / (prev.amplitude + 1e-9)
            desc = (
                f"简易背驰（{cur.direction}）：前段力度={prev.amplitude:.2f}，"
                f"后段力度={cur.amplitude:.2f}，背驰强度={strength:.1%}"
            )
            results.append(BeiChi(
                bi_index=cur.index,
                btype='simple',
                direction=cur.direction,
                strength=strength,
                desc=desc,
            ))

    return results
