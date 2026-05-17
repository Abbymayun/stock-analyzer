#!/usr/bin/env python3
"""
A股全市场智能分析系统 v2
使用腾讯行情API + 东方财富历史K线API
"""

import requests
import json
import os
import sys
import time
import traceback
import math
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
KEEP_DAYS = 7

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

session = requests.Session()
session.headers.update(HEADERS)


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)


# ========== 数据获取：股票列表 + 实时行情 ==========

def get_stock_list_with_quotes():
    """通过腾讯API批量扫描获取全部有效股票及其实时行情"""
    print("  [1/6] 扫描全市场股票（腾讯API批量查询）...")
    
    all_stocks = []
    seen = set()
    batch_size = 50

    # 代码范围扫描
    scan_ranges = [
        ('sz', 1, 999),        # 深主板 000001-000999
        ('sz', 2001, 2999),    # 中小板 002001-002999
        ('sz', 3001, 3999),    # 新主板 003001-003999
        ('sh', 600000, 604999),# 沪主板 600000-604999
        ('sh', 605000, 605999),
        ('sh', 601000, 603999),
        ('sh', 688000, 689999),# 科创板（后续过滤）
    ]

    for prefix, start, end in scan_ranges:
        codes_batch = []
        for num in range(start, end + 1):
            c = f"{prefix}{num:06d}"
            codes_batch.append(c)
            if len(codes_batch) == batch_size:
                _fetch_batch(codes_batch, seen, all_stocks)
                codes_batch = []
                time.sleep(0.08)
        if codes_batch:
            _fetch_batch(codes_batch, seen, all_stocks)
        print(f"        {prefix}{start:06d}-{end:06d}: 已获取 {len(all_stocks)} 只")
        time.sleep(0.15)

    # 过滤
    before = len(all_stocks)
    filtered = [s for s in all_stocks
                if not s['code'].startswith('688')
                and not s['code'].startswith('300')
                and 'ST' not in s['name']
                and not s['code'].startswith('8')
                and not s['code'].startswith('4')
                and not s['code'].startswith('9')
                and s['price'] > 0]
    print(f"  [2/6] 过滤完成：{before} → {len(filtered)} 只")
    return filtered


def _fetch_batch(codes, seen, all_stocks):
    """获取一批股票的实时行情"""
    codes_str = ','.join(codes)
    for attempt in range(2):
        try:
            r = session.get(f"https://qt.gtimg.cn/q={codes_str}", timeout=15)
            lines = [l for l in r.text.strip().split(';') if l.strip() and '~' in l and '=' in l]
            for line in lines:
                parts = line.split('~')
                if len(parts) < 50:
                    continue
                name = parts[1]
                code = parts[2]
                if not name or not code:
                    continue
                if code in seen:
                    continue
                seen.add(code)
                try:
                    price = float(parts[3]) if parts[3] else 0
                    if price <= 0:
                        continue
                    prev_close = float(parts[4]) if parts[4] else 0
                    open_p = float(parts[5]) if parts[5] else 0
                    vol = int(parts[6]) if parts[6] else 0
                    high = float(parts[33]) if parts[33] else 0
                    low = float(parts[34]) if parts[34] else 0
                    chg_amt = float(parts[31]) if parts[31] else 0
                    chg_pct = float(parts[32]) if parts[32] else 0
                    turnover = float(parts[38]) if parts[38] else 0
                    pe = float(parts[39]) if parts[39] else 0
                    pb = float(parts[46]) if parts[46] else 0
                    mcap = float(parts[44]) if parts[44] else 0  # 亿元
                    amount = float(parts[37]) if parts[37] else 0  # 万元
                    amp = float(parts[43]) if parts[43] else 0

                    all_stocks.append({
                        'code': code, 'name': name,
                        'price': price, 'prev_close': prev_close, 'open': open_p,
                        'high': high, 'low': low,
                        'volume': vol, 'amount': amount,
                        'change_amt': chg_amt, 'change_pct': chg_pct,
                        'amplitude': amp, 'turnover_rate': turnover,
                        'pe': pe, 'pb': pb, 'market_cap': mcap,
                    })
                except (ValueError, IndexError):
                    continue
            return
        except Exception as e:
            time.sleep(1)


# ========== 历史K线数据 ==========

def get_stock_history(code, days=60):
    """获取个股历史K线（腾讯API）"""
    prefix = 'sz' if code.startswith('0') or code.startswith('3') else 'sh'
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        'param': f"{prefix}{code},day,,,60,qfq",
    }
    for attempt in range(3):
        try:
            r = session.get(url, params=params, timeout=10)
            d = r.json()
            key = f"{prefix}{code}"
            if d.get('data') and d['data'].get(key) and d['data'][key].get('qfqday'):
                lines = d['data'][key]['qfqday']
                records = []
                for item in lines:
                    records.append({
                        'date': item[0],
                        'open': float(item[1]),
                        'close': float(item[2]),
                        'high': float(item[3]),
                        'low': float(item[4]),
                        'volume': float(item[5]),
                        'amount': 0,
                    })
                return records[-days:]
            return None
        except Exception:
            time.sleep(2)
    return None


# ========== 技术指标 ==========

def calc_ma(closes, periods=(5, 10, 20, 60)):
    result = {}
    for p in periods:
        if len(closes) >= p:
            result[f'ma{p}'] = sum(closes[-p:]) / p
    return result


def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return None
    # 简化EMA计算
    def ema(data, period):
        k = 2 / (period + 1)
        result = [data[0]]
        for i in range(1, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result

    ef = ema(closes, fast)
    es = ema(closes, slow)
    dif = [ef[i] - es[i] for i in range(len(closes))]
    dea = ema(dif, signal)
    macd_hist = [2 * (dif[i] - dea[i]) for i in range(len(closes))]
    return dif[-1], dea[-1], macd_hist[-1], dif[-2], dea[-2], macd_hist[-2]


def calc_rsi(closes, period=6):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def calc_kdj(highs, lows, closes, n=9):
    if len(closes) < n:
        return None
    low_n = min(lows[-n:])
    high_n = max(highs[-n:])
    rsv = (closes[-1] - low_n) / (high_n - low_n + 1e-10) * 100
    k = rsv * 1/3 + 50 * 2/3
    d = k * 1/3 + 50 * 2/3
    j = 3 * k - 2 * d
    return k, d, j


def calc_boll(closes, period=20):
    if len(closes) < period:
        return None
    mid = sum(closes[-period:]) / period
    variance = sum((c - mid) ** 2 for c in closes[-period:]) / period
    std = math.sqrt(variance)
    return mid + 2 * std, mid, mid - 2 * std


# ========== 基础分析 ==========

def basic_analyze(stock):
    """用实时行情做基础评分"""
    signals = []
    score = 50
    chg = stock['change_pct']
    turnover = stock['turnover_rate']
    amp = stock['amplitude']
    price = stock['price']
    high = stock['high']
    low = stock['low']
    pe = stock['pe']
    prev = stock['prev_close']

    # 动量
    if 1 <= chg < 5:
        score += 8; signals.append('温和上涨')
    elif 5 <= chg < 9.5:
        score += 13; signals.append('强势上涨')
    elif chg >= 9.5:
        score -= 3; signals.append('涨停')
    elif -1 <= chg < 1:
        score += 2; signals.append('横盘整理')
    elif -5 < chg < -1:
        score -= 8; signals.append('回调')
    elif chg <= -5:
        score -= 15; signals.append('大幅下跌')

    # 换手率
    if 3 < turnover < 15:
        score += 6
        if turnover > 8:
            signals.append('高换手')
    elif turnover >= 15:
        score -= 5; signals.append('异常换手')
    elif turnover < 1:
        score -= 2; signals.append('低换手')

    # 日内位置
    if high > 0 and low > 0 and high != low:
        pos = (price - low) / (high - low)
        if pos > 0.85:
            score += 3; signals.append('收在高位')
        elif pos < 0.15:
            score -= 3; signals.append('收在低位')

    # 振幅
    if amp > 5:
        signals.append('大振幅')
    elif amp > 8:
        score += 2; signals.append('大幅波动')

    # 估值
    if pe > 0:
        if pe < 15:
            score += 5; signals.append('低PE')
        elif pe > 100:
            score -= 3; signals.append('高PE')

    # 成交量(与换手关联)
    if stock['amount'] > 0 and stock['market_cap'] > 0:
        vol_ratio = stock['amount'] / (stock['market_cap'] * 10000) * 100
        if vol_ratio > 2:
            score += 3; signals.append('放量')
        elif vol_ratio < 0.3:
            score -= 2; signals.append('缩量')

    score = clamp(score)
    return {
        'score': score,
        'recommendation': rec(score),
        'signals': signals,
        'trend': trend(score),
    }


# ========== 深度分析 ==========

def deep_analyze(stock, basic, hist):
    """深度技术分析"""
    if not hist or len(hist) < 20:
        return basic

    closes = [d['close'] for d in hist]
    highs = [d['high'] for d in hist]
    lows = [d['low'] for d in hist]
    vols = [d['volume'] for d in hist]
    cp = closes[-1]

    r = dict(basic)
    signals = list(basic.get('signals', []))
    score = basic['score']

    # 均线
    ma = calc_ma(closes)
    ma5 = ma.get('ma5')
    ma10 = ma.get('ma10')
    ma20 = ma.get('ma20')
    ma60 = ma.get('ma60')

    if ma5: r['ma5'] = round(ma5, 2)
    if ma10: r['ma10'] = round(ma10, 2)
    if ma20: r['ma20'] = round(ma20, 2)
    if ma60: r['ma60'] = round(ma60, 2)

    # 均线排列
    if ma5 and ma10 and ma20 and cp > ma5 > ma10 > ma20:
        score += 15; signals.append('均线多头排列')
    elif ma5 and ma10 and ma20 and ma5 > ma10 > ma20 and cp > ma20:
        score += 8; signals.append('短期多头')
    elif ma5 and ma10 and ma20 and cp < ma5 < ma10 < ma20:
        score -= 15; signals.append('均线空头排列')

    # MA金叉/死叉（5日与10日）
    if len(closes) >= 11:
        ma5_prev = sum(closes[-6:-1]) / 5
        ma10_prev = sum(closes[-11:-1]) / 10
        if ma5 and ma10 and ma5_prev <= ma10_prev and ma5 > ma10:
            score += 10; signals.append('MA金叉')
        elif ma5 and ma10 and ma5_prev >= ma10_prev and ma5 < ma10:
            score -= 10; signals.append('MA死叉')

    # MACD
    macd = calc_macd(closes)
    if macd:
        dif, dea, hist_val, dif_p, dea_p, hist_p = macd
        r['macd_dif'] = round(dif, 4)
        r['macd_dea'] = round(dea, 4)
        r['macd_hist'] = round(hist_val, 4)
        if dif_p <= dea_p and dif > dea:
            score += 12; signals.append('MACD金叉')
        elif dif_p >= dea_p and dif < dea:
            score -= 12; signals.append('MACD死叉')
        if dif > 0:
            score += 3
        else:
            score -= 3
        if hist_p < hist_val and hist_val > 0:
            score += 5; signals.append('红柱放大')
        elif hist_p > hist_val and hist_val < 0:
            score -= 5; signals.append('绿柱放大')

    # RSI
    rsi6 = calc_rsi(closes, 6)
    rsi12 = calc_rsi(closes, 12)
    if rsi6 is not None:
        r['rsi6'] = round(rsi6, 1)
        if rsi6 < 20:
            score += 10; signals.append('RSI超卖')
        elif rsi6 < 30:
            score += 5; signals.append('RSI偏低')
        elif rsi6 > 80:
            score -= 10; signals.append('RSI超买')
        elif rsi6 > 70:
            score -= 5; signals.append('RSI偏高')
    if rsi12 is not None:
        r['rsi12'] = round(rsi12, 1)

    # KDJ
    kdj = calc_kdj(highs, lows, closes)
    if kdj:
        k, d, j = kdj
        r['kdj_k'] = round(k, 1)
        r['kdj_d'] = round(d, 1)
        r['kdj_j'] = round(j, 1)
        if j < 20:
            score += 8; signals.append('KDJ超卖')
        elif j > 100:
            score -= 8; signals.append('KDJ超买')
        if k > d and k < 50:
            score += 3

    # 布林带
    boll = calc_boll(closes)
    if boll:
        upper, mid, lower = boll
        r['boll_upper'] = round(upper, 2)
        r['boll_middle'] = round(mid, 2)
        r['boll_lower'] = round(lower, 2)
        if cp <= lower:
            score += 10; signals.append('触布林下轨')
        elif cp >= upper:
            score -= 5; signals.append('触布林上轨')

    # 量价关系
    if len(vols) >= 5:
        avg_vol = sum(vols[-5:]) / 5
        if vols[-1] > avg_vol * 1.5 and closes[-1] > closes[-2]:
            score += 5; signals.append('放量上涨')
        elif vols[-1] > avg_vol * 1.5 and closes[-1] < closes[-2]:
            score -= 5; signals.append('放量下跌')

    # 支撑压力位
    if len(hist) >= 5:
        r_hi = max(highs[-min(20, len(highs)):])
        r_lo = min(lows[-min(20, len(lows)):])
        r['support'] = round(r_lo, 2)
        r['resistance'] = round(r_hi, 2)
        r['buy_point'] = round((ma20 if ma20 else r_lo) * 0.98, 2)
        r['stop_loss'] = round(r_lo * 0.97, 2)
        r['target_price'] = round(r_hi * 1.03, 2)

    # 明日预估涨幅（基于技术面信号综合判断）
    r['next_day_estimate'] = calc_next_day_estimate(r, closes, vols)

    # 主力心理分析
    if len(hist) >= 10:
        r['main_force_analysis'] = gen_main_force_analysis(r, hist, closes, vols, highs, lows)

    # 筹码分布分析
    if len(hist) >= 20:
        r['chip_analysis'] = gen_chip_analysis(hist, closes, vols, r)

    # 操作时间
    if score >= 65:
        r['buy_time'] = '开盘30分钟内 (9:30-10:00)'
        r['sell_time'] = '冲高回落时 (10:30-11:00 或 14:00-14:30)'
    elif score >= 50:
        r['buy_time'] = '回调支撑位附近 (10:30-11:00 或 14:00-14:30)'
        r['sell_time'] = '反弹压力位附近'
    else:
        r['buy_time'] = '暂不建议买入'
        r['sell_time'] = '建议观望或减仓'

    score = clamp(score)
    r.update({
        'score': score,
        'recommendation': rec(score),
        'signals': signals,
        'trend': trend(score),
        'analysis_text': gen_text(r, cp, ma5, ma10, ma20),
    })
    return r


def calc_next_day_estimate(r, closes, vols):
    """预估明日涨幅"""
    estimate = 0.0
    factors = []
    score = r.get('score', 50)

    # 1. 趋势因子
    if score >= 80:
        estimate += 3.0; factors.append('技术面极强')
    elif score >= 65:
        estimate += 1.5; factors.append('技术面偏强')
    elif score < 35:
        estimate -= 2.0; factors.append('技术面偏弱')
    elif score < 50:
        estimate -= 0.5

    # 2. 动量因子
    if len(closes) >= 3:
        chg1 = (closes[-1] - closes[-2]) / closes[-2] * 100
        chg2 = (closes[-2] - closes[-3]) / closes[-3] * 100
        if chg1 > 0 and chg2 > 0:
            estimate += 1.0; factors.append('连续上涨')
        elif chg1 < 0 and chg2 < 0:
            estimate -= 1.5; factors.append('连续下跌')
        if chg1 > 5:
            estimate -= 0.5; factors.append('今日涨幅较大，注意回调')
        if chg1 < -5:
            estimate += 0.5; factors.append('超跌可能反弹')

    # 3. MACD信号
    if r.get('macd_dif', 0) > r.get('macd_dea', 0) and r.get('macd_hist', 0) > 0:
        estimate += 0.5; factors.append('MACD多头')
    elif r.get('macd_dif', 0) < r.get('macd_dea', 0) and r.get('macd_hist', 0) < 0:
        estimate -= 0.5

    # 4. 量能因子
    if len(vols) >= 5:
        avg_vol = sum(vols[-5:]) / 5
        if vols[-1] > avg_vol * 1.5 and closes[-1] > closes[-2]:
            estimate += 1.0; factors.append('放量上攻')
        elif vols[-1] > avg_vol * 2:
            estimate -= 0.3; factors.append('量能过大需观察')

    # 5. RSI因子
    rsi = r.get('rsi6', 50)
    if rsi < 25:
        estimate += 1.5; factors.append('RSI超卖反弹')
    elif rsi > 80:
        estimate -= 1.5; factors.append('RSI超买回落')

    # 6. 布林带因子
    if r.get('boll_lower') and closes[-1] <= r['boll_lower']:
        estimate += 1.0; factors.append('触及布林下轨')
    elif r.get('boll_upper') and closes[-1] >= r['boll_upper']:
        estimate -= 0.8; factors.append('触及布林上轨')

    # 限制范围 -5% ~ +5%
    estimate = max(-5.0, min(5.0, estimate))
    return {'estimate': round(estimate, 2), 'factors': factors}


def gen_main_force_analysis(r, hist, closes, vols, highs, lows):
    """分析主力心理和行为"""
    lines = []

    if len(closes) < 10 or len(vols) < 10:
        return "数据不足，无法分析主力行为。"

    # 量价分析 - 判断主力意图
    avg_vol_5 = sum(vols[-5:]) / 5
    avg_vol_10 = sum(vols[-10:]) / 10
    vol_ratio = avg_vol_5 / avg_vol_10 if avg_vol_10 > 0 else 1

    chg_5d = (closes[-1] - closes[-5]) / closes[-5] * 100
    chg_10d = (closes[-1] - closes[-min(10, len(closes))]) / closes[-min(10, len(closes))] * 100

    # 主力行为判断
    if vol_ratio > 1.5 and chg_5d > 3:
        lines.append("📈 主力行为判断：主力放量拉升，处于主动建仓/加仓阶段。放量上涨表明主力资金积极介入，短期趋势偏强。")
    elif vol_ratio > 1.5 and chg_5d < -3:
        lines.append("📉 主力行为判断：主力放量杀跌，可能为洗盘或出货。需关注下方支撑位是否有效。")
    elif vol_ratio < 0.7 and abs(chg_5d) < 2:
        lines.append("⏸ 主力行为判断：缩量横盘，主力观望态度明显。可能为蓄势阶段，等待方向选择。")
    elif vol_ratio < 0.7 and chg_5d < 0:
        lines.append("⏬ 主力行为判断：缩量下跌，抛压较轻，主力可能未大规模出货。关注是否出现放量止跌信号。")
    elif vol_ratio > 1.2 and abs(chg_5d) < 2:
        lines.append("🔄 主力行为判断：放量震荡，多空分歧加大。主力可能在换手或调仓。")
    else:
        lines.append("📊 主力行为判断：量价关系正常，主力暂无明显异动。")

    # 主力成本区间估算
    if len(closes) >= 20:
        cost_low = min(closes[-20:])
        cost_high = max(closes[-20:])
        cost_mid = sum(closes[-20:]) / 20
        lines.append(f"\n💰 主力估算成本区间：{cost_low:.2f} - {cost_high:.2f} 元，中位成本约 {cost_mid:.2f} 元。")

        cp = closes[-1]
        if cp < cost_mid * 0.95:
            lines.append(f"现价 {cp:.2f} 低于主力成本中位 {((1 - cp/cost_mid)*100):.1f}%，主力可能被套或处于吸筹末期。")
        elif cp > cost_mid * 1.05:
            lines.append(f"现价 {cp:.2f} 高于主力成本中位 {((cp/cost_mid-1)*100):.1f}%，主力已有浮盈，注意获利了结压力。")
        else:
            lines.append(f"现价 {cp:.2f} 在主力成本区间附近，主力处于盈亏平衡区域。")

    # 操盘手法识别
    recent_highs = highs[-5:]
    recent_lows = lows[-5:]
    intra_range = max(recent_highs) - min(recent_lows)
    avg_range = sum(h - l for h, l in zip(recent_highs, recent_lows)) / 5

    if intra_range / closes[-1] > 0.05:
        lines.append(f"\n🎯 操盘特征：近5日振幅较大（{intra_range/closes[-1]*100:.1f}%），主力可能采用宽幅震荡洗盘手法。")
    elif intra_range / closes[-1] < 0.02:
        lines.append(f"\n🎯 操盘特征：近5日振幅较小（{intra_range/closes[-1]*100:.1f}%），主力控盘度较高或暂无明显方向。")

    # 建议
    signals_str = ' '.join(r.get('signals', []))
    if '金叉' in signals_str or '放量上涨' in signals_str:
        lines.append("\n💡 操作建议：技术信号积极，主力资金流入迹象明显，可考虑在支撑位附近分批介入。")
    elif '死叉' in signals_str or '放量下跌' in signals_str:
        lines.append("\n💡 操作建议：主力资金有流出迹象，建议控制仓位，等待企稳信号再考虑介入。")
    else:
        lines.append("\n💡 操作建议：主力暂未表态，建议保持观察，等待放量突破或缩量企稳信号。")

    return '\n'.join(lines)


def gen_chip_analysis(hist, closes, vols, r):
    """筹码分布分析"""
    lines = []
    cp = closes[-1]

    if len(closes) < 20:
        return "数据不足，无法进行筹码分析。"

    # 模拟筹码分布（基于成交量加权价格区间）
    price_range = max(closes[-20:]) - min(closes[-20:])
    if price_range <= 0:
        return "价格区间过窄，筹码分析意义有限。"

    # 计算各价位筹码集中度
    slots = {}
    for i, (c, v) in enumerate(zip(closes[-20:], vols[-20:])):
        slot = round(c, 1)
        slots[slot] = slots.get(slot, 0) + v

    total_vol = sum(slots.values())
    if total_vol == 0:
        return "成交量数据异常，无法进行筹码分析。"

    # 找筹码密集区
    sorted_slots = sorted(slots.items(), key=lambda x: x[1], reverse=True)
    top_areas = sorted_slots[:5]

    # 筹码集中度
    max_vol = top_areas[0][1] if top_areas else 0
    concentration = max_vol / total_vol * 100

    lines.append(f"📊 20日筹码分布分析（现价 {cp:.2f} 元）：")

    # 筹码集中度
    if concentration > 15:
        lines.append(f"\n🔴 筹码高度集中（{concentration:.1f}%），主力控盘迹象明显。")
    elif concentration > 10:
        lines.append(f"\n🟡 筹码较为集中（{concentration:.1f}%），存在一定控盘。")
    else:
        lines.append(f"\n🟢 筹码较为分散（{concentration:.1f}%），多空博弈激烈。")

    # 筹码密集区
    lines.append(f"\n筹码密集价位：")
    for price, vol in top_areas:
        pct = vol / total_vol * 100
        bar = '█' * int(pct / 2)
        pos = '上方' if price > cp else '下方' if price < cp else '当前'
        lines.append(f"  {price:.1f}元 [{pos:>4}] {bar} {pct:.1f}%")

    # 获利盘/套牢盘估算
    above = sum(v for (p, v) in slots.items() if p < cp)
    below = sum(v for (p, v) in slots.items() if p > cp)
    profit_pct = above / total_vol * 100
    trapped_pct = below / total_vol * 100

    lines.append(f"\n📈 估算获利盘：{profit_pct:.1f}% | 📉 估算套牢盘：{trapped_pct:.1f}%")

    if profit_pct > 80:
        lines.append("⚠️ 获利盘比例过高，上方抛压风险较大，追高需谨慎。")
    elif profit_pct < 20:
        lines.append("💡 套牢盘比例较高，上方存在较强解套压力，但下跌空间可能有限。")
    elif 40 <= profit_pct <= 60:
        lines.append("✅ 获利盘与套牢盘比例适中，筹码结构相对健康，具备上攻基础。")

    # 筹码转移趋势
    if len(closes) >= 10:
        recent_slots = {}
        for c, v in zip(closes[-10:], vols[-10:]):
            slot = round(c, 1)
            recent_slots[slot] = recent_slots.get(slot, 0) + v
        recent_avg = sum(c * v for c, v in recent_slots.items()) / sum(vols[-10:]) if sum(vols[-10:]) > 0 else cp

        if recent_avg > cp:
            lines.append(f"\n🔄 筹码转移：近10日筹码重心上移至 {recent_avg:.2f} 元，高于现价，主力可能在高位派发或洗盘。")
        elif recent_avg < cp * 0.97:
            lines.append(f"\n🔄 筹码转移：近10日筹码重心下移至 {recent_avg:.2f} 元，低于现价，低位筹码堆积，可能为主力吸筹。")
        else:
            lines.append(f"\n🔄 筹码转移：近10日筹码重心在 {recent_avg:.2f} 元附近，与现价接近，筹码相对稳定。")

    return '\n'.join(lines)


def gen_text(r, cp, ma5, ma10, ma20):
    t = []
    if r['trend'] == '上升':
        t.append(f"该股处于上升趋势，现价{cp:.2f}元运行在MA5({ma5:.2f})上方。" if ma5 else f"该股处于上升趋势，现价{cp:.2f}元。")
    elif r['trend'] == '下降':
        t.append(f"该股处于下降趋势，现价{cp:.2f}元跌破MA5({ma5:.2f})。" if ma5 else f"该股处于下降趋势，现价{cp:.2f}元。")
    else:
        t.append(f"该股横盘震荡，现价{cp:.2f}元在MA10({ma10:.2f})附近整理。" if ma10 else f"该股横盘震荡，现价{cp:.2f}元。")

    buy_kw = ['金叉', '超卖', '放量上涨', '多头', '突破', '低位', '偏低', '下轨', '低PE', '红柱']
    sell_kw = ['死叉', '超买', '放量下跌', '空头', '高估', '偏高', '上轨', '回调', '大幅下跌', '绿柱']

    pos_s = [s for s in r['signals'] if any(k in s for k in buy_kw)]
    neg_s = [s for s in r['signals'] if any(k in s for k in sell_kw)]
    if pos_s:
        t.append(f"积极信号：{'、'.join(pos_s)}。")
    if neg_s:
        t.append(f"风险信号：{'、'.join(neg_s)}。")

    t.append(f"综合评分{r['score']}分，操作建议：{r['recommendation']}。")
    if r.get('buy_point'):
        t.append(f"参考买入区间 {r['buy_point']} 元，止损 {r['stop_loss']} 元，目标 {r['target_price']} 元。")
    return ''.join(t)


# ========== 批量深度分析 ==========

def batch_deep_analyze(candidates):
    results = {}
    print(f"  [4/6] 深度分析 {len(candidates)} 只候选股...")
    done = 0

    def work(stock):
        hist = get_stock_history(stock['code'], 60)
        if hist and len(hist) >= 20:
            basic = basic_analyze(stock)
            return stock['code'], deep_analyze(stock, basic, hist)
        else:
            basic = basic_analyze(stock)
            return stock['code'], basic

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(work, s): s for s in candidates}
        for f in as_completed(futures):
            code, result = f.result()
            results[code] = result
            done += 1
            if done % 20 == 0:
                print(f"        进度: {done}/{len(candidates)}")

    print(f"        深度分析完成: {done}/{len(candidates)}")
    return results


# ========== 推荐 ==========

def gen_market_analysis(all_stocks, scored, rec):
    """生成大盘综合分析"""
    rise = [s for s in all_stocks if s.get('change_pct', 0) > 0]
    fall = [s for s in all_stocks if s.get('change_pct', 0) < 0]
    flat = [s for s in all_stocks if s.get('change_pct', 0) == 0]
    zt = [s for s in all_stocks if s.get('change_pct', 0) >= 9.8]
    dt = [s for s in all_stocks if s.get('change_pct', 0) <= -9.8]
    rise_pct = len(rise) / len(all_stocks) * 100 if all_stocks else 0
    fall_pct = len(fall) / len(all_stocks) * 100 if all_stocks else 0
    avg_chg = sum(s.get('change_pct', 0) for s in all_stocks) / len(all_stocks) if all_stocks else 0

    # 行业分布
    industries = defaultdict(list)
    for s in all_stocks:
        signals_str = ' '.join(s.get('signals', []))
        if s.get('change_pct', 0) > 3:
            industries['强势'].append(s)
        elif s.get('change_pct', 0) < -3:
            industries['弱势'].append(s)

    # 资金面
    high_turnover = [s for s in all_stocks if s.get('turnover_rate', 0) > 10]
    total_amount = sum(s.get('amount', 0) for s in all_stocks)

    lines = []
    lines.append(f"今日A股市场整体{rec['market_sentiment']}，全市场{len(all_stocks)}只股票中，上涨{len(rise)}只（{rise_pct:.1f}%），下跌{len(fall)}只（{fall_pct:.1f}%），平盘{len(flat)}只。")
    lines.append(f"平均涨幅{avg_chg:+.2f}%，涨停{len(zt)}只，跌停{len(dt)}只。")

    if zt:
        top_zt = zt[:3]
        zt_strs = [f"{s['name']}({s['change_pct']:.1f}%)" for s in top_zt]
        lines.append(f"涨停股代表：{', '.join(zt_strs)}。")
    if dt:
        top_dt = dt[:3]
        dt_strs = [f"{s['name']}({s['change_pct']:.1f}%)" for s in top_dt]
        lines.append(f"跌停股代表：{', '.join(dt_strs)}。")

    lines.append(f"市场总成交额约{total_amount/10000:.0f}亿元，高换手率（>10%）股票{len(high_turnover)}只。")
    lines.append(f"综合评分{rec['avg_score']}分，技术面{'偏强' if rec['avg_score'] > 55 else '偏弱' if rec['avg_score'] < 45 else '中性'}。")

    # 涨停板块分析
    if industries.get('强势'):
        strong_names = [s['name'] for s in industries['强势'][:5]]
        lines.append(f"今日强势股代表：{'、'.join(strong_names)}。")

    return '\n'.join(lines)


def gen_next_day_advice(all_stocks, scored, rec):
    """生成明日操作建议"""
    lines = []
    sentiment = rec['market_sentiment']

    if sentiment == '偏多':
        lines.append("【明日展望】市场情绪偏暖，可适度积极。")
        lines.append("1. 强烈买入标的可在开盘低吸，关注竞价量能")
        lines.append("2. 买入标的可在回调至支撑位附近分批建仓")
        lines.append("3. 控制仓位在6-7成，留有加仓空间")
    elif sentiment == '偏空':
        lines.append("【明日展望】市场情绪偏冷，以防守为主。")
        lines.append("1. 优先考虑减仓或观望，避免追高")
        lines.append("2. 若持仓亏损超5%，建议设好止损严格执行")
        lines.append("3. 保持低仓位（3-4成），等待企稳信号")
    else:
        lines.append("【明日展望】市场震荡分化，精选个股为主。")
        lines.append("1. 关注评分65分以上且处于上升趋势的个股")
        lines.append("2. 避免追涨杀跌，逢低吸纳优质标的")
        lines.append("3. 仓位控制在5成左右，灵活应对")

    if rec.get('strong_buy'):
        lines.append(f"\n【重点关注】{', '.join(s['name'] + '(' + str(s['score']) + '分)' for s in rec['strong_buy'][:3])}")
    if rec.get('strategies'):
        for st in rec['strategies'][:2]:
            lines.append(f"\n【{st['name']}】{st['desc']}")

    return '\n'.join(lines)


def generate_recommendations(all_stocks):
    scored = [s for s in all_stocks if s.get('score') is not None]
    scored.sort(key=lambda x: x['score'], reverse=True)

    strong_buy = scored[:5]
    buy_list = [s for s in scored if 65 <= s['score'] < 80][:10]
    watch = [s for s in scored if 50 <= s['score'] < 65][:5]
    avoid = [s for s in scored if s['score'] < 35][-5:]

    strategies = []
    avg_score = sum(s['score'] for s in scored) / len(scored) if scored else 50
    sentiment = '偏多' if avg_score > 55 else ('偏空' if avg_score < 45 else '中性')

    # 涨停板接力
    zt = [s for s in all_stocks if '涨停' in s.get('signals', []) and s['score'] >= 50]
    if zt:
        strategies.append({
            'name': '涨停板接力',
            'desc': f"今日{len(zt)}只涨停股中评分较高者可关注明日竞价表现，低开3-7%企稳可考虑介入",
            'stocks': [{'code': s['code'], 'name': s['name'], 'score': s['score']} for s in zt[:5]]
        })

    # 回调低吸
    pullback = [s for s in all_stocks if s['score'] >= 60 and any(k in str(s.get('signals', [])) for k in ['超卖', '下轨', '偏低'])]
    if pullback:
        strategies.append({
            'name': '回调低吸',
            'desc': "技术面超卖或触及支撑位的强势股，可在支撑位附近分批建仓",
            'stocks': [{'code': s['code'], 'name': s['name'], 'score': s['score']} for s in pullback[:5]]
        })

    # 技术突破
    breakout = [s for s in all_stocks if '金叉' in str(s.get('signals', [])) and s['score'] >= 65]
    if breakout:
        strategies.append({
            'name': '技术突破',
            'desc': "MACD/MA出现金叉确认信号，趋势有望延续",
            'stocks': [{'code': s['code'], 'name': s['name'], 'score': s['score']} for s in breakout[:5]]
        })

    # 先生成基础推荐
    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'market_sentiment': sentiment,
        'avg_score': round(avg_score, 1),
        'strong_buy': strong_buy,
        'buy': buy_list,
        'watch': watch,
        'avoid': avoid,
        'strategies': strategies,
    }
    # 再基于 result 生成分析和建议（避免递归引用）
    result['market_analysis'] = gen_market_analysis(all_stocks, scored, result)
    result['next_day_advice'] = gen_next_day_advice(all_stocks, scored, result)
    return result


# ========== 辅助 ==========

def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

def rec(score):
    if score >= 80: return '强烈买入'
    if score >= 65: return '买入'
    if score >= 50: return '关注'
    if score >= 35: return '卖出'
    return '强烈卖出'

def trend(score):
    if score >= 55: return '上升'
    if score <= 45: return '下降'
    return '震荡'


# ========== 历史管理 ==========

def cleanup_history():
    if not os.path.exists(HISTORY_DIR):
        return
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    for f in os.listdir(HISTORY_DIR):
        if not f.endswith('.json'):
            continue
        try:
            date_str = f.split('_')[0]
            fdate = datetime.strptime(date_str, '%Y-%m-%d')
            if fdate < cutoff:
                os.remove(os.path.join(HISTORY_DIR, f))
        except:
            pass


def save_snapshot(all_stocks, recommendations):
    now = datetime.now()
    ts = now.strftime('%Y-%m-%d %H:%M:%S')
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H%M')

    all_stocks.sort(key=lambda x: x.get('score', 0), reverse=True)

    all_data = {
        'update_time': ts,
        'total': len(all_stocks),
        'stocks': all_stocks,
    }
    with open(os.path.join(DATA_DIR, 'all_stocks.json'), 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)

    with open(os.path.join(DATA_DIR, 'recommendations.json'), 'w', encoding='utf-8') as f:
        json.dump(recommendations, f, ensure_ascii=False)

    # 历史快照（包含价格，用于准确率统计）
    hist_data = {
        'update_time': ts,
        'recommendations': {
            'strong_buy': [{'code': s['code'], 'name': s['name'], 'score': s['score'], 'price': s['price'], 'prev_close': s['prev_close']} for s in recommendations['strong_buy']],
            'buy': [{'code': s['code'], 'name': s['name'], 'score': s['score'], 'price': s['price'], 'prev_close': s['prev_close']} for s in recommendations['buy']],
            'avoid': [{'code': s['code'], 'name': s['name'], 'score': s['score'], 'price': s['price'], 'prev_close': s['prev_close']} for s in recommendations['avoid']],
        },
        'scores': {s['code']: {'score': s['score'], 'price': s['price'], 'name': s['name']} for s in all_stocks[:500]},
        'market_sentiment': recommendations['market_sentiment'],
        'avg_score': recommendations['avg_score'],
    }
    with open(os.path.join(HISTORY_DIR, f'{date_str}_{time_str}.json'), 'w', encoding='utf-8') as f:
        json.dump(hist_data, f, ensure_ascii=False)

    print(f"  [6/6] 数据已保存 ({len(all_stocks)} 只股票)")


# ========== 主函数 ==========

def main():
    ensure_dirs()
    print("=" * 60)
    print(f"  A股全市场智能分析  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取实时数据
    stocks = get_stock_list_with_quotes()
    if not stocks:
        print("❌ 未获取到股票数据")
        sys.exit(1)

    # 2. 基础分析（全量）
    print(f"  [3/6] 基础分析（{len(stocks)} 只）...")
    for s in stocks:
        basic = basic_analyze(s)
        s.update(basic)

    # 3. 深度分析（Top 200）
    stocks.sort(key=lambda x: x['score'], reverse=True)
    candidates = stocks[:200]
    deep_results = batch_deep_analyze(candidates)

    # 合并深度结果
    for s in stocks:
        if s['code'] in deep_results:
            s.update(deep_results[s['code']])

    # 4. 生成推荐
    recommendations = generate_recommendations(stocks)
    print(f"\n  📊 市场情绪: {recommendations['market_sentiment']} (平均分 {recommendations['avg_score']})")
    if recommendations['strong_buy']:
        top = recommendations['strong_buy'][:3]
        print(f"  🔥 强烈买入: {', '.join(s['name'] + '(' + str(s['score']) + ')' for s in top)}")

    # 5. 保存
    save_snapshot(stocks, recommendations)
    cleanup_history()
    print("\n  ✅ 分析完成！")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 分析失败: {e}")
        traceback.print_exc()
        sys.exit(1)
