#!/usr/bin/env python3
"""
智能买入观察器 watcher.py v2.0
每分钟采集候选股价格，构建实时K线，做多维度技术分析，信号共振才买入。

升级要点：
- 不再"价格到了就买"，而是每分钟做技术分析
- 分析维度：黄金分割回调位、量价关系、K线形态、均线支撑、成交量异动
- 每只股票独立判断，不同时买入
- 触发阈值：至少3个维度给出买入信号（满分6个）

用法:
  python3 watcher.py          # 单次运行（cron每分钟调用）
  python3 watcher.py --loop   # 持续运行
"""

import os
import sys
import json
import time
import math
import requests
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from market_calendar import is_trading_time as _is_market_open

DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')
BUY_PLAN_FILE = os.path.join(DATA_DIR, 'buy_plan.json')
SELL_PLAN_FILE = os.path.join(DATA_DIR, 'sell_plan.json')
SELL_SIGNAL_FILE = os.path.join(DATA_DIR, 'sell_signals.json')
PORTFOLIO_FILE = os.path.join(DATA_DIR, 'portfolio.json')
TRADE_LOG_FILE = os.path.join(DATA_DIR, 'trade_log.json')
PRICE_BARS_FILE = os.path.join(DATA_DIR, 'price_bars.json')
MAX_BUY_PER_DAY = 3

# 买入触发阈值：至少需要多少个维度给买入信号
BUY_SIGNAL_THRESHOLD = 3

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_market_open():
    return _is_market_open()


# ========== 实时行情获取 ==========

def get_realtime_prices(codes):
    """从腾讯接口获取实时价格"""
    if not codes:
        return {}
    prefixed = []
    for c in codes:
        if c.startswith('sh') or c.startswith('sz'):
            prefixed.append(c)
        elif c.startswith('6'):
            prefixed.append('sh' + c)
        else:
            prefixed.append('sz' + c)
    url = f"https://qt.gtimg.cn/q={','.join(prefixed)}"
    try:
        resp = session.get(url, timeout=10)
        resp.encoding = 'gbk'
        result = {}
        for line in resp.text.strip().split(';'):
            if '=' not in line:
                continue
            data = line.split('~')
            if len(data) < 45:
                continue
            code = data[2]
            name = data[1]
            price = float(data[3]) if data[3] else 0
            prev_close = float(data[4]) if data[4] else 0
            high = float(data[33]) if data[33] else 0
            low = float(data[34]) if data[34] else 0
            open_price = float(data[5]) if data[5] else 0
            volume = float(data[6]) if data[6] else 0
            amount = float(data[37]) if data[37] else 0
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0
            result[code] = {
                'name': name,
                'code': code,
                'price': price,
                'prev_close': prev_close,
                'open': open_price,
                'high': high,
                'low': low,
                'volume': volume,
                'amount': amount,
                'change_pct': change_pct,
            }
        return result
    except Exception as e:
        print(f"  ⚠️ 获取实时价格失败: {e}")
        return {}


# ========== 1分钟K线管理 ==========

def load_price_bars():
    """加载所有股票的分钟K线数据"""
    return load_json(PRICE_BARS_FILE, {})


def save_price_bars(bars):
    """保存分钟K线数据（仅保留当天的）"""
    today = datetime.now().strftime('%Y-%m-%d')
    cleaned = {}
    for code, bar_list in bars.items():
        # 只保留今天的
        today_bars = [b for b in bar_list if b.get('time', '').startswith(today)]
        cleaned[code] = today_bars[-120:]  # 最多保留120根（2小时）
    save_json(PRICE_BARS_FILE, cleaned)


def update_price_bars(bars, realtime_data):
    """用最新价格更新K线"""
    now = datetime.now()
    current_bar_time = now.strftime('%Y-%m-%d %H:%M')  # 1分钟粒度

    for code, rt in realtime_data.items():
        if rt['price'] <= 0:
            continue

        if code not in bars:
            bars[code] = []

        bar_list = bars[code]

        # 更新当前K线或创建新K线
        if bar_list and bar_list[-1]['time'] == current_bar_time:
            # 更新当前K线
            bar = bar_list[-1]
            bar['close'] = rt['price']
            bar['high'] = max(bar['high'], rt['price'])
            bar['low'] = min(bar['low'], rt['price'])
            bar['volume'] = rt['volume']
            bar['amount'] = rt['amount']
        else:
            # 新建K线
            bar_list.append({
                'time': current_bar_time,
                'open': rt['price'],
                'high': rt['price'],
                'low': rt['price'],
                'close': rt['price'],
                'volume': rt['volume'],
                'amount': rt['amount'],
            })

        # 限制长度
        if len(bar_list) > 120:
            bars[code] = bar_list[-120:]

    return bars


# ========== 技术分析引擎 ==========

def analyze_golden_ratio(bars, target_price, plan_price):
    """
    分析1: 黄金分割回调位
    取最近的高点和低点，计算38.2%、50%、61.8%回调位
    当前价格接近某个回调位 = 买入信号
    """
    if len(bars) < 10:
        return None, '数据不足(需10根K线)'

    recent = bars[-30:] if len(bars) > 30 else bars
    high = max(b['high'] for b in recent)
    low = min(b['low'] for b in recent)
    current = bars[-1]['close']
    diff = high - low

    if diff <= 0:
        return None, '价格无波动'

    # 黄金分割回调位
    fib_382 = high - diff * 0.382
    fib_500 = high - diff * 0.500
    fib_618 = high - diff * 0.618

    # 检查当前价格是否接近某个回调位（±0.5%）
    tolerance = current * 0.005

    for level, label in [(fib_618, '61.8%'), (fib_500, '50%'), (fib_382, '38.2%')]:
        if abs(current - level) < tolerance:
            # 确认是在回调过程中（高点在前，低点在后）
            high_idx = max(range(len(recent)), key=lambda i: recent[i]['high'])
            if high_idx < len(recent) - 3:  # 高点至少在3根K线前
                return True, f'价格{current:.2f}触及黄金分割{label}回调位({level:.2f})'

    # 同时检查是否在目标买入价附近
    if target_price > 0 and abs(current - target_price) / target_price < 0.008:
        return True, f'价格{current:.2f}接近目标买入价{target_price:.2f}'

    return False, f'未触及回调位(38.2%:{fib_382:.2f}, 50%:{fib_500:.2f}, 61.8%:{fib_618:.2f})'


def analyze_volume_price(bars):
    """
    分析2: 量价关系
    - 缩量回调后放量 = 买入信号（洗盘结束）
    - 价格下跌+成交量萎缩 = 抛压减弱
    - 价格企稳+成交量温和放大 = 资金进场
    """
    if len(bars) < 8:
        return None, '数据不足(需8根K线)'

    recent = bars[-8:]
    volumes = [b['volume'] for b in recent]
    closes = [b['close'] for b in recent]

    avg_vol = sum(volumes) / len(volumes)
    if avg_vol == 0:
        return None, '成交量为0'

    # 分前后各4根
    first_vol_avg = sum(volumes[:4]) / 4
    last_vol_avg = sum(volumes[4:]) / 4

    # 价格趋势
    price_trend = closes[-1] - closes[0]
    vol_change = (last_vol_avg - first_vol_avg) / avg_vol * 100 if avg_vol > 0 else 0

    # 信号1: 缩量回调（价格跌 + 量缩）
    if price_trend < 0 and vol_change < -20:
        return True, f'缩量回调(价跌{price_trend:.2f}元,量缩{abs(vol_change):.0f}%)，抛压减弱'

    # 信号2: 企稳放量（价格走平或微涨 + 量增）
    if abs(price_trend) / closes[0] < 0.003 and vol_change > 15:
        return True, f'企稳放量(价稳{price_trend:.2f}元,量增{vol_change:.0f}%)，资金进场'

    # 信号3: 底部放量阳线（最后1根收阳且量大于均量）
    last = recent[-1]
    if last['close'] > last['open'] and last['volume'] > avg_vol * 1.3:
        if closes[-2] < closes[-3]:  # 之前在跌
            return True, f'底部放量阳线(涨幅{(last["close"]-last["open"])/last["open"]*100:.1f}%,量是均量{last["volume"]/avg_vol:.1f}倍)'

    return False, f'量价关系中性(趋势{price_trend:+.2f}元,量变化{vol_change:+.0f}%)'


def analyze_kline_pattern(bars):
    """
    分析3: K线形态
    - 锤子线/倒锤子线 = 反转信号
    - 长下影线 = 下方支撑强
    - 吞没形态 = 趋势反转
    - 十字星 = 多空平衡，可能变盘
    """
    if len(bars) < 3:
        return None, '数据不足(需3根K线)'

    last = bars[-1]
    body = abs(last['close'] - last['open'])
    upper_shadow = last['high'] - max(last['close'], last['open'])
    lower_shadow = min(last['close'], last['open']) - last['low']
    total_range = last['high'] - last['low']

    if total_range <= 0:
        return None, 'K线无波动'

    is_bullish = last['close'] > last['open']

    # 信号1: 锤子线（长下影线，小实体，在上部）
    if lower_shadow > body * 2 and upper_shadow < body * 0.5:
        return True, f'锤子线形态(下影{lower_shadow:.2f}是实体{body:.2f}的{lower_shadow/max(body,0.01):.1f}倍)，下方支撑强'

    # 信号2: 长下影线（下影线占总振幅60%以上）
    if lower_shadow / total_range > 0.6 and total_range / last['close'] > 0.005:
        return True, f'长下影线(下影占{lower_shadow/total_range*100:.0f}%)，探底回升'

    # 信号3: 看涨吞没（阳线包住前一根阴线）
    if len(bars) >= 2:
        prev = bars[-2]
        if prev['close'] < prev['open'] and is_bullish:
            if last['close'] > prev['open'] and last['open'] < prev['close']:
                return True, f'看涨吞没形态(阳线完全包住前阴线)'

    # 信号4: 三连阴后阳线（短期超跌反弹）
    if len(bars) >= 4:
        last4 = bars[-4:]
        if all(b['close'] < b['open'] for b in last4[:3]) and is_bullish:
            return True, f'三阴后阳线(连续下跌后止跌)'

    return False, f'无明确买入K线形态'


def analyze_ma_support(bars):
    """
    分析4: 均线支撑
    价格回调到短期均线附近获得支撑
    """
    if len(bars) < 20:
        return None, '数据不足(需20根K线)'

    closes = [b['close'] for b in bars]
    current = closes[-1]

    # 计算多条均线
    def ma(period):
        if len(closes) < period:
            return None
        return sum(closes[-period:]) / period

    ma5 = ma(5)
    ma10 = ma(10)
    ma20 = ma(20)

    if ma5 is None or ma10 is None:
        return None, '均线计算不足'

    signals = []

    # 检查是否在均线附近获得支撑（±0.3%）
    for m, label in [(ma5, 'MA5'), (ma10, 'MA10'), (ma20, 'MA20')]:
        if m is None:
            continue
        tolerance = current * 0.003
        if abs(current - m) < tolerance:
            # 确认是支撑（价格在均线附近，且之前在上方）
            prev_close = closes[-2] if len(closes) >= 2 else current
            if prev_close >= m * 0.995:  # 之前在均线附近或上方
                signals.append(f'触及{label}({m:.2f})获支撑')

    # 检查均线多头（MA5 > MA10）
    if ma5 > ma10:
        signals.append('MA5>MA10多头排列')
    else:
        return False, f'均线空头(MA5={ma5:.2f} < MA10={ma10:.2f})'

    if signals:
        return True, ', '.join(signals)

    return False, f'偏离均线(MA5={ma5:.2f}, MA10={ma10:.2f})'


def analyze_volume_surge(bars):
    """
    分析5: 成交量异动
    - 急缩量到极致后开始放量 = 底部特征
    - 大单资金流入（用成交额判断）
    """
    if len(bars) < 15:
        return None, '数据不足(需15根K线)'

    recent = bars[-15:]
    volumes = [b['volume'] for b in recent]
    amounts = [b['amount'] for b in recent]

    avg_vol = sum(volumes) / len(volumes)
    if avg_vol == 0:
        return None, '成交量为0'

    # 分三段看量能变化
    seg1 = sum(volumes[:5]) / 5
    seg2 = sum(volumes[5:10]) / 5
    seg3 = sum(volumes[10:]) / 5

    # 信号: 量能先缩后放（V型反转）
    if seg1 > seg2 * 1.2 and seg3 > seg2 * 1.3 and seg2 < avg_vol * 0.7:
        return True, f'量能V型反转(先缩{seg2/seg1*100:.0f}%后放{seg3/seg2*100:.0f}%)，底部特征'

    # 信号: 最近3根平均量 > 前10根平均量 的1.5倍（放量启动）
    if len(bars) >= 13:
        recent3 = sum(volumes[-3:]) / 3
        prev10 = sum(volumes[-13:-3]) / 10
        if prev10 > 0 and recent3 > prev10 * 1.5:
            last = bars[-1]
            if last['close'] >= last['open']:  # 阳线放量更可靠
                return True, f'放量启动(近3根量是前10根的{recent3/max(prev10,1):.1f}倍)'

    return False, f'量能无明显异动(近5根均量{seg3:.0f}手 vs 总均量{avg_vol:.0f}手)'


def analyze_price_momentum(bars):
    """
    分析6: 价格动量反转
    - 短期下跌后速度放缓（动量衰减）
    - 价格从加速下跌转为减速
    """
    if len(bars) < 10:
        return None, '数据不足(需10根K线)'

    closes = [b['close'] for b in bars[-10:]]

    # 计算多段变化率
    changes = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            changes.append((closes[i] - closes[i-1]) / closes[i-1])

    if len(changes) < 6:
        return None, '数据不足'

    # 前3根 vs 后3根的变化率
    early_avg = sum(changes[:3]) / 3
    late_avg = sum(changes[-3:]) / 3

    # 信号: 从加速下跌到减速（跌幅收窄）
    if early_avg < -0.002 and late_avg > early_avg * 1.5:
        # 最后1根必须是红的或跌幅很小
        if changes[-1] >= -0.001:
            return True, f'下跌动量衰减(前期每根跌{early_avg*100:.2f}%→近期{late_avg*100:.2f}%)，即将企稳'

    # 信号: 连续阴跌后出现阳线
    neg_count = sum(1 for c in changes[:-1] if c < 0)
    if neg_count >= 4 and changes[-1] > 0:
        return True, f'连跌{neg_count}根后首根阳线(+{changes[-1]*100:.2f}%)'

    return False, f'动量无明显反转(前段{early_avg*100:.3f}% → 后段{late_avg*100:.3f}%)'


def full_technical_analysis(code, name, bars, target_price):
    """
    综合技术分析：6个维度全部评估，计算买入评分
    返回: (buy_score, signal_details)
    """
    analyses = [
        ('黄金分割', analyze_golden_ratio(bars, target_price, 0)),
        ('量价关系', analyze_volume_price(bars)),
        ('K线形态', analyze_kline_pattern(bars)),
        ('均线支撑', analyze_ma_support(bars)),
        ('成交量异动', analyze_volume_surge(bars)),
        ('价格动量', analyze_price_momentum(bars)),
    ]

    buy_signals = 0
    total_score = 0
    details = []
    for dim_name, (result, reason) in analyses:
        if result is True:
            buy_signals += 1
            total_score += 1
            status = '✅ 买入'
        elif result is False:
            status = '❌ 等待'
        else:
            status = '⏳ ' + reason.split('(')[0]
        details.append({
            'dimension': dim_name,
            'signal': result,
            'reason': reason,
            'status': status,
        })

    return buy_signals, details


# ========== 交易执行 ==========

def calc_commission(price, qty, direction):
    amount = price * qty
    if direction == 'buy':
        commission = max(amount * 0.00025, 5)
    else:
        commission = max(amount * 0.00025, 5) + amount * 0.001
    return round(commission, 2)


def calc_slippage_price(price, is_buy):
    return round(price * (1.001 if is_buy else 0.999), 2)


def get_buyable_amount(cash, price):
    if price <= 0 or cash <= 0:
        return 0
    max_qty = int(cash / price / (1 + 0.00025 + 0.001))
    return (max_qty // 100) * 100


def execute_buy(code, name, price, qty, reason):
    portfolio = load_json(PORTFOLIO_FILE)
    if not portfolio:
        return False

    buy_price = calc_slippage_price(price, True)
    total_cost = buy_price * qty + calc_commission(buy_price, qty, 'buy')

    if total_cost > portfolio['cash']:
        return False

    portfolio['cash'] -= total_cost

    if code in portfolio['holdings']:
        h = portfolio['holdings'][code]
        old_total = h['avg_cost'] * h['qty']
        new_total = buy_price * qty
        h['avg_cost'] = round((old_total + new_total) / (h['qty'] + qty), 3)
        h['qty'] += qty
    else:
        portfolio['holdings'][code] = {
            'name': name,
            'qty': qty,
            'avg_cost': round(buy_price, 3),
            'buy_date': datetime.now().strftime('%Y-%m-%d'),
            'buy_score': 0,
            'signals': [],
        }

    trade = {
        'type': 'buy',
        'code': code,
        'name': name,
        'price': buy_price,
        'qty': qty,
        'total_cost': round(total_cost, 2),
        'commission': round(calc_commission(buy_price, qty, 'buy'), 2),
        'reason': reason,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    trade_log = load_json(TRADE_LOG_FILE, {'trades': []})
    trade_log['trades'].append(trade)
    portfolio['trading_stats']['total_trades'] += 1

    save_json(PORTFOLIO_FILE, portfolio)
    save_json(TRADE_LOG_FILE, trade_log)

    print(f"  ✅ 买入 {name}（{code}）{qty}股 × {buy_price:.2f}元 = {total_cost:.2f}元")
    print(f"      原因：{reason}")
    return True


def execute_sell(code, name, price, qty, reason):
    portfolio = load_json(PORTFOLIO_FILE)
    if not portfolio:
        return False

    h = portfolio.get('holdings', {}).get(code)
    if not h or h['qty'] < qty:
        return False

    sell_price = calc_slippage_price(price, False)
    sell_amount = sell_price * qty
    commission = calc_commission(sell_price, qty, 'sell')
    net_amount = sell_amount - commission

    cost_amount = h['avg_cost'] * qty
    pnl = net_amount - cost_amount
    pnl_pct = (sell_price - h['avg_cost']) / h['avg_cost'] * 100

    portfolio['cash'] += net_amount
    h['qty'] -= qty
    if h['qty'] <= 0:
        del portfolio['holdings'][code]

    portfolio['trading_stats']['total_trades'] += 1
    portfolio['trading_stats']['total_pnl'] += pnl
    if pnl > 0:
        portfolio['trading_stats']['win_trades'] += 1

    trade = {
        'type': 'sell',
        'code': code,
        'name': name,
        'price': sell_price,
        'qty': qty,
        'amount': round(sell_amount, 2),
        'commission': round(commission, 2),
        'pnl': round(pnl, 2),
        'pnl_pct': round(pnl_pct, 2),
        'reason': reason,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    trade_log = load_json(TRADE_LOG_FILE, {'trades': []})
    trade_log['trades'].append(trade)

    save_json(PORTFOLIO_FILE, portfolio)
    save_json(TRADE_LOG_FILE, trade_log)

    print(f"  ❌ 卖出 {name}（{code}）{qty}股 × {sell_price:.2f}元（{'+' if pnl>=0 else ''}{pnl:.2f}元）")
    return True


# ========== 持仓监控（卖出分析） ==========

def check_sell_signals(portfolio, realtime_data):
    """对持仓股票做卖出技术分析"""
    holdings = portfolio.get('holdings', {})
    today = datetime.now().strftime('%Y-%m-%d')
    sell_signals = []

    for code, h in holdings.items():
        # T+1：今天买入的不卖
        if h.get('buy_date', '') == today:
            continue

        rt = realtime_data.get(code)
        if not rt or rt['price'] <= 0:
            continue

        cost = h['avg_cost']
        current = rt['price']
        pnl_pct = (current - cost) / cost * 100
        qty = h['qty']

        # 获取该股票的K线
        bars = load_price_bars().get(code, [])

        # 买入原因
        reasons = []

        # 止损（-8%无条件卖出）
        if pnl_pct < -8:
            reasons.append(f'止损触发(亏损{pnl_pct:.1f}%)')

        # 止盈（+15%分批卖出半仓）
        elif pnl_pct > 15:
            reasons.append(f'止盈触发(盈利{pnl_pct:.1f}%)')
            qty = qty // 2  # 只卖一半

        # 技术分析卖出信号
        if len(bars) >= 10:
            closes = [b['close'] for b in bars[-10:]]

            # 放量跌破MA5
            if len(bars) >= 5:
                ma5 = sum(closes[-5:]) / 5
                if current < ma5 and bars[-1]['volume'] > sum(b['volume'] for b in bars[-5:]) / 5 * 1.5:
                    reasons.append(f'放量跌破MA5({ma5:.2f})')

            # 连续5根阴线且亏损
            if len(closes) >= 5 and all(closes[i] < closes[i-1] for i in range(-4, 0)):
                if pnl_pct < -3:
                    reasons.append(f'连续5阴下跌且亏损{pnl_pct:.1f}%')

            # 量价背离（价创新高但量萎缩）
            if len(bars) >= 8:
                recent_high = max(bars[-8:][-4:], key=lambda x: x['high'])
                current_high = bars[-1]['high']
                if current_high > recent_high['high']:
                    recent_vol = sum(b['volume'] for b in bars[-4:]) / 4
                    early_vol = sum(b['volume'] for b in bars[-8:-4]) / 4
                    if early_vol > 0 and recent_vol < early_vol * 0.6:
                        reasons.append(f'量价背离(创新高但量缩{recent_vol/early_vol*100:.0f}%)')

        if reasons:
            sell_signals.append({
                'code': code,
                'name': h['name'],
                'qty': qty,
                'price': current,
                'reasons': reasons,
                'pnl_pct': pnl_pct,
            })

    return sell_signals


# ========== 主循环 ==========

def run_once():
    """执行一次观察检查"""
    if not is_market_open():
        return

    today = datetime.now().strftime('%Y-%m-%d')
    executed_any = False

    # === 1. 处理卖出计划 ===
    sell_plan = load_json(SELL_PLAN_FILE)
    sell_items = sell_plan.get('items', [])
    if sell_items:
        plan_date = sell_plan.get('date', '')
        if plan_date != today:
            save_json(SELL_PLAN_FILE, {'date': today, 'items': [], 'created_at': ''})
        else:
            remaining_sells = []
            sell_codes = [item['code'] for item in sell_items]
            prices = get_realtime_prices(sell_codes)
            for item in sell_items:
                rt = prices.get(item['code'])
                if rt and rt['price'] > 0:
                    if execute_sell(item['code'], item['name'], rt['price'], item['qty'],
                                   item['reason'] + '（开盘后由watcher执行）'):
                        executed_any = True
                    else:
                        remaining_sells.append(item)
                else:
                    remaining_sells.append(item)
            sell_plan['items'] = remaining_sells
            save_json(SELL_PLAN_FILE, sell_plan)

    # === 2. 买入观察 ===
    plan = load_json(BUY_PLAN_FILE)
    items = plan.get('items', [])
    if not items:
        return

    plan_date = plan.get('date', '')
    if plan_date and plan_date != today:
        plan['items'] = []
        save_json(BUY_PLAN_FILE, plan)
        return

    # 检查今天已买入数量
    trade_log = load_json(TRADE_LOG_FILE, {'trades': []})
    today_buys = [t for t in trade_log.get('trades', [])
                  if t.get('timestamp', '').startswith(today) and t.get('type') == 'buy']
    bought_today = len(today_buys)
    bought_codes = set(t['code'] for t in today_buys)

    if bought_today >= MAX_BUY_PER_DAY:
        plan['items'] = []
        save_json(BUY_PLAN_FILE, plan)
        print(f"  📋 今天已买满{MAX_BUY_PER_DAY}只，清空买入计划")
        return

    remaining_items = []
    codes = [item['code'] for item in items if item['code'] not in bought_codes]
    if not codes:
        plan['items'] = []
        save_json(BUY_PLAN_FILE, plan)
        return

    # 获取实时价格并更新K线
    prices = get_realtime_prices(codes)
    if not prices:
        return

    bars = update_price_bars(load_price_bars(), prices)
    save_price_bars(bars)

    remaining_slots = MAX_BUY_PER_DAY - bought_today

    for item in items:
        if item['code'] in bought_codes:
            continue

        if len([c for c in bought_codes if c not in [item['code']]]) >= remaining_slots:
            remaining_items.append(item)
            continue

        rt = prices.get(item['code'])
        if not rt or rt['price'] <= 0:
            remaining_items.append(item)
            continue

        code = item['code']
        stock_bars = bars.get(code, [])
        current_price = rt['price']

        # ===== 核心改动：技术分析后再决定是否买入 =====
        buy_score, details = full_technical_analysis(
            code, item['name'], stock_bars, item.get('target_price', 0)
        )

        # 输出分析结果（方便调试）
        signal_count = sum(1 for d in details if d['signal'] is True)
        if signal_count > 0 or len(stock_bars) % 10 == 0:  # 每10根K线或有不买入信号时输出
            print(f"\n  🔍 {item['name']}（{code}）现价{current_price:.2f} | 信号 {signal_count}/{BUY_SIGNAL_THRESHOLD}")
            for d in details:
                print(f"     {d['status']} {d['dimension']}: {d['reason']}")

        # 信号评分达到阈值才买入
        if buy_score >= BUY_SIGNAL_THRESHOLD:
            # 构建买入理由
            signal_reasons = [d['reason'] for d in details if d['signal'] is True]
            reason = item.get('reason', '观察买入')
            reason += f"；{signal_count}维技术信号共振：{'；'.join(signal_reasons)}"

            # 用当前可用资金重新计算数量
            portfolio = load_json(PORTFOLIO_FILE)
            ratio = item.get('ratio', 0.35)
            alloc_cash = portfolio['cash'] * ratio
            qty = get_buyable_amount(alloc_cash, current_price)

            if qty >= 100:
                if execute_buy(code, item['name'], current_price, qty, reason):
                    bought_codes.add(code)
                    executed_any = True
                    continue

        # 没买，继续观察
        remaining_items.append(item)

    # === 3. 持仓监控 ===
    portfolio = load_json(PORTFOLIO_FILE)
    if portfolio.get('holdings'):
        all_holding_codes = list(portfolio['holdings'].keys())
        all_prices = get_realtime_prices(all_holding_codes)
        sell_signals = check_sell_signals(portfolio, all_prices)
        for ss in sell_signals:
            print(f"\n  ⚠️ {ss['name']}（{ss['code']}）卖出信号：{'；'.join(ss['reasons'])}")
            execute_sell(ss['code'], ss['name'], ss['price'], ss['qty'], '；'.join(ss['reasons']))

    # 更新计划
    plan['items'] = remaining_items
    plan['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_json(BUY_PLAN_FILE, plan)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--save-plan':
        plan_data = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
        # 简单保存
        today = datetime.now().strftime('%Y-%m-%d')
        plan = load_json(BUY_PLAN_FILE)
        if plan.get('date', '') != today:
            plan = {'date': today, 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'items': []}
        existing = set(item['code'] for item in plan.get('items', []))
        for c in plan_data:
            if c['code'] not in existing:
                plan['items'].append(c)
                existing.add(c['code'])
        save_json(BUY_PLAN_FILE, plan)
    elif len(sys.argv) > 1 and sys.argv[1] == '--loop':
        print(f"🔍 智能观察器启动（每分钟技术分析，{BUY_SIGNAL_THRESHOLD}维信号共振才买入）...", flush=True)
        while True:
            try:
                run_once()
            except Exception as e:
                print(f"  ❌ 观察器错误: {e}")
            time.sleep(60)
    else:
        if not is_market_open():
            sys.exit(0)
        run_once()
