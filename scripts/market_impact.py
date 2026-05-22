#!/usr/bin/env python3
"""
外围市场影响评估模块 v2.0
精准分析海外股市对A股的影响，给出具体应对建议。
供 morning_analysis.py / midday_analysis.py / closing_analysis.py 共用。
"""

import requests

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}


def assess_us_impact(us_indices):
    """精准评估美股对A股开盘及当日走势的影响"""
    if not us_indices:
        return {'direction': '中性', 'level': 'low', 'summary': '美股数据未获取', 'detail': '', 'affect_sectors': [], 'open_forecast': '', 'coping': []}

    pcts = {k: v['change_pct'] for k, v in us_indices.items()}
    avg = sum(pcts.values()) / len(pcts)
    max_fall = min(pcts.values())
    max_rise = max(pcts.values())

    # 影响方向和程度
    if avg > 1.5:
        direction, level = '大幅利好', 'high'
    elif avg > 0.5:
        direction, level = '小幅利好', 'medium'
    elif avg < -1.5:
        direction, level = '大幅利空', 'high'
    elif avg < -0.5:
        direction, level = '小幅利空', 'medium'
    else:
        direction, level = '中性', 'low'

    # 涨跌细节
    details = []
    for code, info in us_indices.items():
        emoji = '📈' if info['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {info['name']} {info['price']:.2f} ({info['change_pct']:+.2f}%)")

    # 领涨/领跌判断
    lead_info = ''
    if max_fall < -1:
        worst = min(pcts, key=pcts.get)
        lead_info = f"，{us_indices[worst]['name']}领跌{max_fall:+.2f}%"
    elif max_rise > 1:
        best = max(pcts, key=pcts.get)
        lead_info = f"，{us_indices[best]['name']}领涨{max_rise:+.2f}%"

    # 具体影响板块
    affect_sectors = []

    # 纳斯达克强 → 科技板块
    nasdaq = pcts.get('NQ=F', pcts.get('.IXIC', 0))
    if nasdaq > 1.5:
        affect_sectors.append('🟢 美股科技大涨，利好A股半导体/AI/消费电子板块')
    elif nasdaq < -1.5:
        affect_sectors.append('🔴 美股科技大跌，A股半导体/消费电子可能承压低开')

    # 道琼斯 → 传统行业/金融
    dow = pcts.get('YM=F', pcts.get('.DJI', 0))
    if dow > 1.5:
        affect_sectors.append('🟢 道指走强，金融/消费/制造业有望受益')
    elif dow < -1.5:
        affect_sectors.append('🔴 道指大跌，银行/周期股可能受拖累')

    # 标普 → 整体市场情绪
    sp = pcts.get('ES=F', pcts.get('.INX', 0))
    if sp > 2:
        affect_sectors.append('🟢 标普强势，北向资金有望净流入，带动蓝筹白马')
    elif sp < -2:
        affect_sectors.append('🔴 标普暴跌，北向资金可能大幅流出，大盘承压')

    # 创业板/科创板与纳斯达克关联度更高
    if abs(nasdaq) > 1:
        affect_sectors.append(f"{'📈 创业板/科创50与纳指联动性强，' if nasdaq > 0 else '📉 创业板/科创50可能跟随纳指走弱，'}关注联动反应")

    # 开盘预测
    if avg > 1.5:
        open_forecast = 'A股大概率小幅高开（+0.3%~0.8%），高开后关注量能是否跟上'
    elif avg > 0.5:
        open_forecast = 'A股可能平开或小幅高开，开盘后走势取决于自身技术面'
    elif avg < -1.5:
        open_forecast = 'A股大概率低开（-0.3%~-1%），低开后可能有技术性反弹'
    elif avg < -0.5:
        open_forecast = 'A股可能小幅低开，但低开后容易企稳'
    else:
        open_forecast = '美股影响中性，A股开盘受自身因素影响更大'

    # 具体应对方法
    coping = []
    if avg > 1.5:
        coping.append('• 美股大涨营造做多氛围，可关注科技板块（AI/半导体/机器人）的高开回踩买点')
        coping.append('• 高开不宜追涨，等回调到均线支撑位再介入')
        coping.append('• 关注北向资金流向，若大幅净流入可跟随加仓')
    elif avg > 0.5:
        coping.append('• 外围偏暖但力度一般，维持正常操作节奏')
        coping.append('• 科技方向可适度关注，但不必重仓追')
    elif avg < -1.5:
        coping.append('• 美股大跌带来情绪冲击，开盘30分钟内以观望为主')
        coping.append('• 控制仓位，不盲目抄底低开股')
        coping.append('• 防御为主：关注黄金/国债/公用事业等避险板块')
        coping.append('• 若持仓股大幅低开触及止损位，坚决止损')
    elif avg < -0.5:
        coping.append('• 外围小幅利空，开盘可能弱势但不至于恐慌')
        coping.append('• 不追涨，已有持仓可观望，不轻易加仓')
        coping.append('• 等待A股自身企稳信号（如分时黄线走平、量能萎缩）')
    else:
        coping.append('• 美股涨跌互现/波动不大，参考意义有限')
        coping.append('• 关注A股自身技术面和市场热点，按原策略执行')

    summary = f"美股{'全线' if all(p > 0 for p in pcts.values()) else ''}{'下跌' if avg < 0 else '上涨'}，三大指数平均{avg:+.2f}%{lead_info}"
    summary += f"。对A股：{direction}"

    return {
        'direction': direction,
        'level': level,
        'avg_pct': round(avg, 2),
        'summary': summary,
        'detail': '\n'.join(details),
        'affect_sectors': affect_sectors,
        'open_forecast': open_forecast,
        'coping': coping,
    }


def assess_commodity_impact(commodities):
    """评估大宗商品对A股板块的具体影响"""
    if not commodities:
        return {'summary': '大宗商品数据未获取', 'detail': '', 'affect_sectors': [], 'coping': []}

    details = []
    affect_sectors = []
    coping = []

    gold = commodities.get('hf_GC', {})
    oil = commodities.get('hf_CL', {})
    silver = commodities.get('hf_SI', {})

    if gold:
        emoji = '📈' if gold['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {gold['name']} {gold['price']:.2f} {gold.get('unit', '')} ({gold['change_pct']:+.2f}%)")
        if gold['change_pct'] > 2:
            affect_sectors.append('🟢 金价大涨→利好黄金板块（山东黄金/中金黄金/紫金矿业）')
            coping.append('• 金价突破，黄金板块短期有交易机会，关注龙头个股回踩买入')
        elif gold['change_pct'] > 0.5:
            affect_sectors.append('🟢 金价温和上涨，黄金板块有支撑')
        elif gold['change_pct'] < -2:
            affect_sectors.append('🔴 金价大跌→黄金板块承压，注意回避')
            coping.append('• 金价急跌，黄金板块可能补跌，已有持仓注意止损')

    if silver:
        emoji = '📈' if silver['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {silver['name']} {silver['price']:.2f} {silver.get('unit', '')} ({silver['change_pct']:+.2f}%)")
        if abs(silver['change_pct']) > 2:
            affect_sectors.append(f"{'🟢 白银大涨→白银/有色板块联动走强' if silver['change_pct'] > 0 else '🔴 白银大跌→有色板块承压'}")

    if oil:
        emoji = '📈' if oil['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {oil['name']} {oil['price']:.2f} {oil.get('unit', '')} ({oil['change_pct']:+.2f}%)")
        if oil['change_pct'] > 3:
            affect_sectors.append('🟢 油价飙升→利好油气板块（中国石油/中国海油），但增加输入性通胀压力')
            coping.append('• 油价大涨利好油气开采，但下游制造/航空成本承压，注意分化')
        elif oil['change_pct'] > 1:
            affect_sectors.append('🟢 油价温和上涨，油气板块有支撑')
        elif oil['change_pct'] < -3:
            affect_sectors.append('🔴 油价暴跌→利好航空/化工/物流（成本下降），利空油气板块')
            coping.append('• 油价大跌降低成本压力，可关注航空股机会，回避油气股')

    summary_parts = []
    if gold:
        g = gold['change_pct']
        if abs(g) > 1.5:
            summary_parts.append(f"金价{'大涨' if g > 0 else '大跌'}{abs(g):.1f}%，{'利好' if g > 0 else '利空'}黄金板块")
    if oil:
        o = oil['change_pct']
        if abs(o) > 1.5:
            summary_parts.append(f"油价{'飙升' if o > 0 else '暴跌'}{abs(o):.1f}%，{'利好油气/利空航空' if o > 0 else '利好航空/利空气油'}")

    summary = '；'.join(summary_parts) if summary_parts else '大宗商品波动平稳，对A股直接影响有限'

    return {'summary': summary, 'detail': '\n'.join(details), 'affect_sectors': affect_sectors, 'coping': coping}


def assess_fx_impact(fx_data):
    """评估汇率对A股资金面的影响"""
    if not fx_data:
        return {'summary': '汇率数据未获取', 'detail': '', 'affect_sectors': [], 'coping': []}

    details = []
    affect_sectors = []
    coping = []

    usdcnh = fx_data.get('usdcnh', {})
    if usdcnh:
        details.append(f"💵 美元/离岸人民币 {usdcnh['price']:.4f} ({usdcnh['change_pct']:+.2f}%)")
        chg = usdcnh['change_pct']
        if chg > 0.3:
            affect_sectors.append('🔴 人民币贬值较快→外资（北向资金）可能流出，大盘蓝筹承压')
            coping.append('• 人民币走弱注意北向资金动向，若大幅净流出则控制仓位')
            coping.append('• 人民币贬值利好出口导向型公司（纺织/家电/跨境电商）')
        elif chg < -0.3:
            affect_sectors.append('🟢 人民币升值→外资有望流入，利好A股核心资产')
            coping.append('• 人民币走强有利于外资配置A股，关注沪深300成分股机会')
        elif chg > 0.1:
            affect_sectors.append('🟡 人民币小幅走弱，影响有限')
        elif chg < -0.1:
            affect_sectors.append('🟡 人民币小幅走强，影响有限')

    # 日元汇率（影响亚太市场联动）
    usdjpy = fx_data.get('usdjpy', {})
    if usdjpy:
        details.append(f"💴 美元/日元 {usdjpy['price']:.2f} ({usdjpy['change_pct']:+.2f}%)")
        if usdjpy['change_pct'] > 0.5:
            affect_sectors.append('🟡 日元走弱，日本套息交易活跃，亚太市场波动可能加大')

    summary_parts = []
    if usdcnh:
        c = usdcnh['change_pct']
        if abs(c) > 0.2:
            summary_parts.append(f"人民币{'贬值' if c > 0 else '升值'}压力{'增加' if c > 0 else '减弱'}，{'外资流出风险加大' if c > 0 else '有利于外资流入'}")

    summary = '；'.join(summary_parts) if summary_parts else '汇率相对稳定'

    return {'summary': summary, 'detail': '\n'.join(details), 'affect_sectors': affect_sectors, 'coping': coping}


def assess_global_impact(global_indices):
    """评估亚太/欧洲市场对A股的影响"""
    if not global_indices:
        return {'summary': '全球指数数据未获取', 'detail': '', 'affect_sectors': [], 'coping': []}

    details = []
    affect_sectors = []
    coping = []

    hsi = global_indices.get('hkHSI', {})
    n225 = global_indices.get('jpN225', {})
    dax = global_indices.get('deDAX', {})
    ftse = global_indices.get('ukFTSE', {})

    if hsi:
        emoji = '📈' if hsi['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {hsi['name']} {hsi['price']:.2f} ({hsi['change_pct']:+.2f}%)")
        c = hsi['change_pct']
        if c > 1.5:
            affect_sectors.append('🟢 恒指大涨→港股走强，A股可能高开，关注AH股溢价收敛机会')
            coping.append('• 恒指强势有望带动A股，关注金融/互联网/消费等港股联动板块')
        elif c > 0.5:
            affect_sectors.append('🟢 恒指小幅上涨，港股情绪偏暖，对A股有正面带动')
        elif c < -1.5:
            affect_sectors.append('🔴 恒指大跌→港股走弱拖累A股情绪，可能低开')
            coping.append('• 恒指走弱增加市场不确定性，控制仓位观望')
        elif c < -0.5:
            affect_sectors.append('🟡 恒指小幅下跌，影响有限')

    if n225:
        emoji = '📈' if n225['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {n225['name']} {n225['price']:.2f} ({n225['change_pct']:+.2f}%)")
        if abs(n225['change_pct']) > 1.5:
            affect_sectors.append(f"{'🟢 日经' if n225['change_pct'] > 0 else '🔴 日经'}大涨{'↑' if n225['change_pct'] > 0 else '↓'}，亚太市场{'偏暖' if n225['change_pct'] > 0 else '承压'}")

    if dax:
        emoji = '📈' if dax['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {dax['name']} {dax['price']:.2f} ({dax['change_pct']:+.2f}%)")
        if abs(dax['change_pct']) > 1.5:
            affect_sectors.append(f"{'🟢 欧洲' if dax['change_pct'] > 0 else '🔴 欧洲'}市场{'偏暖' if dax['change_pct'] > 0 else '偏冷'}，{'提振' if dax['change_pct'] > 0 else '压制'}全球风险偏好")

    if ftse:
        emoji = '📈' if ftse['change_pct'] >= 0 else '📉'
        details.append(f"{emoji} {ftse['name']} {ftse['price']:.2f} ({ftse['change_pct']:+.2f}%)")

    summary_parts = []
    if hsi and abs(hsi['change_pct']) > 1:
        summary_parts.append(f"恒指{hsi['change_pct']:+.2f}%，{'带动' if hsi['change_pct'] > 0 else '拖累'}A股开盘情绪")
    if dax and abs(dax['change_pct']) > 1:
        summary_parts.append(f"{'欧洲偏暖' if dax['change_pct'] > 0 else '欧洲走弱'}，影响全球风险偏好")

    summary = '；'.join(summary_parts) if summary_parts else '外围市场整体平稳'

    return {'summary': summary, 'detail': '\n'.join(details), 'affect_sectors': affect_sectors, 'coping': coping}


def build_impact_summary(us_impact, commodity_impact, fx_impact, global_impact):
    """将所有外围影响汇总成一段精准总结"""
    parts = []

    # 美股影响（核心）
    us = us_impact.get('summary', '')
    if us:
        parts.append(f"🇺🇸 {us}")

    # 开盘预测
    forecast = us_impact.get('open_forecast', '')
    if forecast:
        parts.append(f"📊 预计{forecast}")

    # 受影响板块
    all_sectors = []
    for impact in [us_impact, commodity_impact, fx_impact, global_impact]:
        all_sectors.extend(impact.get('affect_sectors', []))
    if all_sectors:
        parts.append("")
        parts.append("🎯 受影响板块：")
        for s in all_sectors[:5]:
            parts.append(f"  {s}")

    # 应对方法
    all_coping = []
    for impact in [us_impact, commodity_impact, fx_impact, global_impact]:
        all_coping.extend(impact.get('coping', []))
    if all_coping:
        parts.append("")
        parts.append("💡 应对方法：")
        for c in all_coping[:6]:
            parts.append(f"  {c}")

    return '\n'.join(parts)
