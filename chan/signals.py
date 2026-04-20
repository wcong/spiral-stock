"""
三类买卖点识别
"""
from dataclasses import dataclass, field
from typing import Optional
from .structure import Bi
from .zhongshu import ZhongShu
from .beichi import BeiChi, detect_trend_beichi, detect_pan_beichi


@dataclass
class BuyPoint:
    """买入点"""
    btype: int              # 1/2/3 类买点
    bi: Bi                  # 对应的笔
    zhongshu: Optional[ZhongShu]
    dt: str                 # 日期
    price: float            # 建议入场价（笔的底部）
    beichi: Optional[BeiChi]
    reason: str             # 详细理由


@dataclass
class SellPoint:
    """卖出点"""
    btype: int
    bi: Bi
    zhongshu: Optional[ZhongShu]
    dt: str
    price: float
    beichi: Optional[BeiChi]
    reason: str


def find_buy_sell_points(
    bis: list[Bi],
    zhongshus: list[ZhongShu],
) -> tuple[list[BuyPoint], list[SellPoint]]:
    """识别三类买卖点"""

    all_beichi = detect_trend_beichi(bis, zhongshus) + detect_pan_beichi(bis, zhongshus)
    beichi_by_bi = {b.bi_index: b for b in all_beichi}

    buy_points = []
    sell_points = []

    # ---- 第一类买卖点 ----
    # 下跌趋势末端背驰后的向下笔的最低点
    for bi in bis:
        if bi.direction == 'down' and bi.index in beichi_by_bi:
            bc = beichi_by_bi[bi.index]
            if bc.direction == 'down':
                zs = _find_related_zhongshu(bi, zhongshus)
                reason = _build_b1_buy_reason(bi, bc, zs)
                buy_points.append(BuyPoint(
                    btype=1, bi=bi, zhongshu=zs,
                    dt=bi.end_dt, price=bi.end_price,
                    beichi=bc, reason=reason,
                ))

        if bi.direction == 'up' and bi.index in beichi_by_bi:
            bc = beichi_by_bi[bi.index]
            if bc.direction == 'up':
                zs = _find_related_zhongshu(bi, zhongshus)
                reason = _build_b1_sell_reason(bi, bc, zs)
                sell_points.append(SellPoint(
                    btype=1, bi=bi, zhongshu=zs,
                    dt=bi.end_dt, price=bi.end_price,
                    beichi=bc, reason=reason,
                ))

    # ---- 第二类买卖点 ----
    # 第一买点之后的向上笔（回调不破低）
    b1_indices = {bp.bi.index for bp in buy_points if bp.btype == 1}
    for bp in [p for p in buy_points if p.btype == 1]:
        bi_idx = bp.bi.index
        # 找第一买点之后的第二笔（向上笔）
        if bi_idx + 2 < len(bis):
            next_up_bi = bis[bi_idx + 2]  # 跳过一笔（向上后的回调笔）
            if next_up_bi.direction == 'up':
                pullback_bi = bis[bi_idx + 1] if bi_idx + 1 < len(bis) else None
                if pullback_bi and pullback_bi.end_price > bp.price:
                    # 回调未破第一买点低点
                    reason = _build_b2_buy_reason(bp, pullback_bi, next_up_bi)
                    buy_points.append(BuyPoint(
                        btype=2, bi=next_up_bi, zhongshu=bp.zhongshu,
                        dt=next_up_bi.start_dt, price=next_up_bi.start_price,
                        beichi=None, reason=reason,
                    ))

    s1_indices = {sp.bi.index for sp in sell_points if sp.btype == 1}
    for sp in [p for p in sell_points if p.btype == 1]:
        bi_idx = sp.bi.index
        if bi_idx + 2 < len(bis):
            next_down_bi = bis[bi_idx + 2]
            if next_down_bi.direction == 'down':
                bounce_bi = bis[bi_idx + 1] if bi_idx + 1 < len(bis) else None
                if bounce_bi and bounce_bi.end_price < sp.price:
                    reason = _build_b2_sell_reason(sp, bounce_bi, next_down_bi)
                    sell_points.append(SellPoint(
                        btype=2, bi=next_down_bi, zhongshu=sp.zhongshu,
                        dt=next_down_bi.start_dt, price=next_down_bi.start_price,
                        beichi=None, reason=reason,
                    ))

    # ---- 第三类买卖点 ----
    # 中枢结束后，新趋势回调不进入中枢
    for i, zs in enumerate(zhongshus):
        if not zs.bis:
            continue
        last_bi = zs.bis[-1]
        # 找中枢之后的笔
        last_bi_idx = last_bi.index
        if last_bi_idx + 2 >= len(bis):
            continue

        exit_bi = bis[last_bi_idx + 1] if last_bi_idx + 1 < len(bis) else None
        pullback_bi = bis[last_bi_idx + 2] if last_bi_idx + 2 < len(bis) else None

        if not exit_bi or not pullback_bi:
            continue

        # 上升方向：中枢后向上突破，回调不进入中枢 → 第三买点
        if exit_bi.direction == 'up' and exit_bi.end_price > zs.zg:
            if pullback_bi.direction == 'down' and pullback_bi.end_price > zs.zg:
                reason = _build_b3_buy_reason(zs, exit_bi, pullback_bi)
                buy_points.append(BuyPoint(
                    btype=3, bi=pullback_bi, zhongshu=zs,
                    dt=pullback_bi.end_dt, price=pullback_bi.end_price,
                    beichi=None, reason=reason,
                ))

        # 下降方向：中枢后向下跌破，反弹不进入中枢 → 第三卖点
        if exit_bi.direction == 'down' and exit_bi.end_price < zs.zd:
            if pullback_bi.direction == 'up' and pullback_bi.end_price < zs.zd:
                reason = _build_b3_sell_reason(zs, exit_bi, pullback_bi)
                sell_points.append(SellPoint(
                    btype=3, bi=pullback_bi, zhongshu=zs,
                    dt=pullback_bi.end_dt, price=pullback_bi.end_price,
                    beichi=None, reason=reason,
                ))

    # 去重并排序
    buy_points = _deduplicate(buy_points, key=lambda x: (x.dt, x.btype))
    sell_points = _deduplicate(sell_points, key=lambda x: (x.dt, x.btype))
    buy_points.sort(key=lambda x: x.dt)
    sell_points.sort(key=lambda x: x.dt)

    return buy_points, sell_points


def _find_related_zhongshu(bi: Bi, zhongshus: list[ZhongShu]) -> Optional[ZhongShu]:
    for zs in reversed(zhongshus):
        for b in zs.bis:
            if b.index == bi.index:
                return zs
    return None


def _deduplicate(lst, key):
    seen = set()
    result = []
    for item in lst:
        k = key(item)
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result


def _build_b1_buy_reason(bi: Bi, bc: BeiChi, zs) -> str:
    zs_info = f"，所在中枢区间 [{zs.zd:.2f}, {zs.zg:.2f}]" if zs else ""
    return (
        f"【第一类买点】\n"
        f"📍 位置：{bi.end_dt}，价格 {bi.end_price:.2f}\n"
        f"🔍 识别依据：\n"
        f"  • 当前处于下跌趋势末端，向下笔({bi.start_dt} → {bi.end_dt})完成{zs_info}\n"
        f"  • {bc.desc}\n"
        f"  • 背驰强度：{bc.strength:.1%}，下跌动能明显衰竭\n"
        f"💡 操作建议：\n"
        f"  • 可在该笔低点附近轻仓试多\n"
        f"  • 止损：跌破本笔低点则离场\n"
        f"  • 风险最高，需等待第二买点确认后加仓\n"
        f"⚠️  风险提示：第一买点存在继续下跌风险，仓位不超过30%"
    )


def _build_b1_sell_reason(bi: Bi, bc: BeiChi, zs) -> str:
    zs_info = f"，所在中枢区间 [{zs.zd:.2f}, {zs.zg:.2f}]" if zs else ""
    return (
        f"【第一类卖点】\n"
        f"📍 位置：{bi.end_dt}，价格 {bi.end_price:.2f}\n"
        f"🔍 识别依据：\n"
        f"  • 当前处于上涨趋势末端，向上笔({bi.start_dt} → {bi.end_dt})完成{zs_info}\n"
        f"  • {bc.desc}\n"
        f"  • 背驰强度：{bc.strength:.1%}，上涨动能明显衰竭\n"
        f"💡 操作建议：减仓或离场，等待回调后重新布局"
    )


def _build_b2_buy_reason(b1: BuyPoint, pullback_bi: Bi, entry_bi: Bi) -> str:
    return (
        f"【第二类买点】\n"
        f"📍 位置：{entry_bi.start_dt}，价格 {entry_bi.start_price:.2f}\n"
        f"🔍 识别依据：\n"
        f"  • 来源于第一买点（{b1.dt}，{b1.price:.2f}）的确认性回调\n"
        f"  • 回调笔({pullback_bi.start_dt} → {pullback_bi.end_dt})低点 {pullback_bi.end_price:.2f}"
        f" 高于第一买点低点 {b1.price:.2f}，结构不破\n"
        f"  • 趋势方向已初步确立，多头结构完整\n"
        f"💡 操作建议：\n"
        f"  • 本买点确定性高于第一买点，可加仓至50-60%\n"
        f"  • 止损：跌破第一买点低点 {b1.price:.2f}\n"
        f"  • 目标：前期压力位或中枢上沿"
    )


def _build_b2_sell_reason(s1: SellPoint, bounce_bi: Bi, entry_bi: Bi) -> str:
    return (
        f"【第二类卖点】\n"
        f"📍 位置：{entry_bi.start_dt}，价格 {entry_bi.start_price:.2f}\n"
        f"🔍 识别依据：\n"
        f"  • 来源于第一卖点（{s1.dt}，{s1.price:.2f}）的确认性反弹\n"
        f"  • 反弹笔高点 {bounce_bi.end_price:.2f} 低于第一卖点高点 {s1.price:.2f}，弱反弹\n"
        f"💡 操作建议：减仓或做空"
    )


def _build_b3_buy_reason(zs: ZhongShu, exit_bi: Bi, pullback_bi: Bi) -> str:
    return (
        f"【第三类买点】\n"
        f"📍 位置：{pullback_bi.end_dt}，价格 {pullback_bi.end_price:.2f}\n"
        f"🔍 识别依据：\n"
        f"  • 中枢区间：[{zs.zd:.2f}, {zs.zg:.2f}]，中枢时间：{zs.start_dt} → {zs.end_dt}\n"
        f"  • 向上离开笔({exit_bi.start_dt} → {exit_bi.end_dt})突破中枢顶部 {zs.zg:.2f}\n"
        f"  • 回调笔({pullback_bi.start_dt} → {pullback_bi.end_dt})低点 {pullback_bi.end_price:.2f}"
        f" 始终高于中枢顶 {zs.zg:.2f}，回调不入中枢\n"
        f"  • 这是趋势延续的强烈信号（前中枢顶变支撑）\n"
        f"💡 操作建议：\n"
        f"  • 第三买点确定性最高，可重仓介入（60-80%）\n"
        f"  • 止损：跌回中枢内（跌破 {zs.zg:.2f}）\n"
        f"  • 目标：下一个中枢或前高压力位\n"
        f"✅ 风险最低的买点类型，趋势已完全确认"
    )


def _build_b3_sell_reason(zs: ZhongShu, exit_bi: Bi, pullback_bi: Bi) -> str:
    return (
        f"【第三类卖点】\n"
        f"📍 位置：{pullback_bi.end_dt}，价格 {pullback_bi.end_price:.2f}\n"
        f"🔍 识别依据：\n"
        f"  • 中枢区间：[{zs.zd:.2f}, {zs.zg:.2f}]\n"
        f"  • 向下离开笔跌破中枢底部 {zs.zd:.2f}\n"
        f"  • 反弹不回中枢，趋势延续向下\n"
        f"💡 操作建议：减仓离场或做空"
    )
