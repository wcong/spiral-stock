"""
中枢识别
"""
from dataclasses import dataclass, field
from .structure import Bi, Segment


@dataclass
class ZhongShu:
    """中枢"""
    index: int
    bis: list               # 构成中枢的笔列表
    zg: float               # 中枢顶（前3笔重叠区间上边界）
    zd: float               # 中枢底（前3笔重叠区间下边界）
    gg: float               # 中枢最高点
    dd: float               # 中枢最低点
    direction: str          # 中枢所在趋势方向 'up'/'down'/'side'

    @property
    def start_dt(self):
        return self.bis[0].start_dt

    @property
    def end_dt(self):
        return self.bis[-1].end_dt

    @property
    def mid(self):
        return (self.zg + self.zd) / 2

    def is_in_zhongshu(self, price: float) -> bool:
        return self.zd <= price <= self.zg


def find_zhongshus(bis: list[Bi]) -> list[ZhongShu]:
    """
    从笔中识别中枢
    规则：连续3笔的价格区间有重叠部分即构成中枢
    """
    if len(bis) < 3:
        return []

    zhongshus = []
    i = 0
    while i <= len(bis) - 3:
        b0, b1, b2 = bis[i], bis[i + 1], bis[i + 2]

        # 计算3笔的重叠区间
        # 取每笔的高低点
        ranges = []
        for b in [b0, b1, b2]:
            high = max(b.start_price, b.end_price)
            low = min(b.start_price, b.end_price)
            ranges.append((low, high))

        # 重叠区间
        zd = max(r[0] for r in ranges)
        zg = min(r[1] for r in ranges)

        if zg <= zd:
            # 无重叠，不构成中枢
            i += 1
            continue

        # 构成中枢，尝试延伸
        zhu_bis = [b0, b1, b2]
        gg = max(r[1] for r in ranges)
        dd = min(r[0] for r in ranges)

        j = i + 3
        while j < len(bis):
            bj = bis[j]
            bj_high = max(bj.start_price, bj.end_price)
            bj_low = min(bj.start_price, bj.end_price)

            # 如果新笔完全在中枢区间外（离开中枢），停止延伸
            if bj_low > zg or bj_high < zd:
                break

            zhu_bis.append(bj)
            gg = max(gg, bj_high)
            dd = min(dd, bj_low)
            j += 1

        direction = _infer_direction(zhu_bis)
        zs = ZhongShu(
            index=len(zhongshus),
            bis=zhu_bis,
            zg=zg,
            zd=zd,
            gg=gg,
            dd=dd,
            direction=direction,
        )
        zhongshus.append(zs)
        # 下一个中枢从离开当前中枢的笔开始
        i = j if j > i + 3 else i + 1

    return zhongshus


def _infer_direction(bis: list[Bi]) -> str:
    """根据进入中枢的笔方向推断中枢所在趋势"""
    if not bis:
        return 'side'
    # 进入中枢的第一笔方向
    entry = bis[0].direction
    return entry
