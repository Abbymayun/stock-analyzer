#!/usr/bin/env python3
"""
买入观察器 watcher.py
每分钟检查买入计划中的股票价格，满足条件时自动执行买入。

用法:
  python3 watcher.py          # 运行一次（适合cron每分钟调用）
  python3 watcher.py --loop   # 持续运行（sleep 60秒循环）

逻辑:
1. 读取 buy_plan.json（由 analyze.py 在每次分析时更新）
2. 拉取计划中股票的实时价格
3. 如果当前价格 <= 目标买入价（或接近目标价的2%以内），执行买入
4. 执行后从计划中移除
5. 每天最多买3只（检查交易日志）
"""

import os
import sys
import json
import time
import math
import requests
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
BUY_PLAN_FILE = os.path.join(DATA_DIR, 'buy_plan.json')
PORTFOLIO_FILE = os.path.join(DATA_DIR, 'portfolio.json')
TRADE_LOG_FILE = os.path.join(DATA_DIR, 'trade_log.json')
MAX_BUY_PER_DAY = 3

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


def get_realtime_prices(codes):
    """从腾讯接口获取实时价格"""
    if not codes:
        return {}
    # 确保前缀格式
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
            if len(data) < 6:
                continue
            code = data[2]  # 纯数字代码
            name = data[1]
            price = float(data[3]) if data[3] else 0
            prev_close = float(data[4]) if data[4] else 0
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0
            result[code] = {
                'name': name,
                'code': code,
                'price': price,
                'prev_close': prev_close,
                'change_pct': change_pct,
            }
        return result
    except Exception as e:
        print(f"  ⚠️ 获取实时价格失败: {e}")
        return {}


def calc_commission(price, qty, direction):
    """计算手续费"""
    amount = price * qty
    if direction == 'buy':
        commission = max(amount * 0.00025, 5)  # 万2.5
    else:
        commission = max(amount * 0.00025, 5) + amount * 0.001  # 万2.5 + 印花税千1
    return round(commission, 2)


def calc_slippage_price(price, is_buy):
    """模拟滑点"""
    return round(price * (1.001 if is_buy else 0.999), 2)


def get_buyable_amount(cash, price):
    """计算可买股数（100的整数倍）"""
    if price <= 0 or cash <= 0:
        return 0
    max_qty = int(cash / price / (1 + 0.00025 + 0.001))  # 扣除手续费
    return (max_qty // 100) * 100


def execute_buy(code, name, price, qty, reason):
    """执行一笔买入"""
    portfolio = load_json(PORTFOLIO_FILE)
    if not portfolio:
        print(f"  ❌ 无法读取投资组合")
        return False

    buy_price = calc_slippage_price(price, True)
    total_cost = buy_price * qty + calc_commission(buy_price, qty, 'buy')

    if total_cost > portfolio['cash']:
        print(f"  ❌ 资金不足：需要{total_cost:.0f}元，可用{portfolio['cash']:.0f}元")
        return False

    # 扣款
    portfolio['cash'] -= total_cost

    if code in portfolio['holdings']:
        # 加仓
        h = portfolio['holdings'][code]
        old_total = h['avg_cost'] * h['qty']
        new_total = buy_price * qty
        h['avg_cost'] = round((old_total + new_total) / (h['qty'] + qty), 3)
        h['qty'] += qty
    else:
        # 新建仓
        portfolio['holdings'][code] = {
            'name': name,
            'qty': qty,
            'avg_cost': round(buy_price, 3),
            'buy_date': datetime.now().strftime('%Y-%m-%d'),
            'buy_score': 0,
            'signals': [],
        }

    # 记录交易
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


def run_once():
    """执行一次观察检查"""
    plan = load_json(BUY_PLAN_FILE)
    if not plan or not plan.get('items'):
        return  # 没有计划

    today = datetime.now().strftime('%Y-%m-%d')

    # 检查今天已买入数量
    trade_log = load_json(TRADE_LOG_FILE, {'trades': []})
    today_buys = [t for t in trade_log.get('trades', []) if t.get('timestamp', '').startswith(today) and t.get('type') == 'buy']
    bought_today = len(today_buys)
    bought_codes = set(t['code'] for t in today_buys)

    if bought_today >= MAX_BUY_PER_DAY:
        # 今天已买满3只，清空计划
        plan['items'] = []
        save_json(BUY_PLAN_FILE, plan)
        return

    remaining_slots = MAX_BUY_PER_DAY - bought_today

    # 检查计划日期，过期的清空
    plan_date = plan.get('date', '')
    if plan_date and plan_date != today:
        # 计划过期了（第二天了），清空
        print(f"  🗑️ 买入计划已过期（{plan_date}），清空")
        plan['items'] = []
        save_json(BUY_PLAN_FILE, plan)
        return

    # 获取计划中股票的实时价格
    items = plan.get('items', [])
    codes = [item['code'] for item in items if item['code'] not in bought_codes]
    if not codes:
        plan['items'] = []
        save_json(BUY_PLAN_FILE, plan)
        return

    prices = get_realtime_prices(codes)
    if not prices:
        return

    executed = []
    remaining_items = []

    for item in items:
        if item['code'] in bought_codes or item['code'] not in prices:
            continue  # 已买入或无价格

        if len(executed) >= remaining_slots:
            remaining_items.append(item)
            continue

        rt = prices[item['code']]
        current_price = rt['price']
        target_price = item.get('target_price', item.get('plan_price', 0))

        if current_price <= 0 or target_price <= 0:
            remaining_items.append(item)
            continue

        # 买入条件：当前价格 <= 目标价格 * 1.02（允许2%的上浮）
        buy_threshold = target_price * 1.02

        if current_price <= buy_threshold:
            # 计算买入数量（重新计算，用当前可用资金）
            portfolio = load_json(PORTFOLIO_FILE)
            ratio = item.get('ratio', 0.35)
            alloc_cash = portfolio['cash'] * ratio
            qty = get_buyable_amount(alloc_cash, current_price)

            if qty >= 100:
                reason = item.get('reason', '观察买入')
                reason += f"；观察价格{current_price:.2f}元，接近目标{target_price:.2f}元，执行买入"

                if execute_buy(item['code'], item['name'], current_price, qty, reason):
                    executed.append(item['code'])
                    bought_codes.add(item['code'])
                    continue

        remaining_items.append(item)

    # 更新计划
    plan['items'] = remaining_items
    plan['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_json(BUY_PLAN_FILE, plan)

    if executed:
        print(f"  📋 观察器：本次执行买入{len(executed)}只（{', '.join(executed)}），剩余{len(remaining_items)}只在观察中")


def save_buy_plan(buy_plan_candidates):
    """由 analyze.py 调用，保存新的买入计划"""
    today = datetime.now().strftime('%Y-%m-%d')
    plan = load_json(BUY_PLAN_FILE)

    # 如果日期变了，重置计划
    if plan.get('date', '') != today:
        plan = {'date': today, 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'items': []}

    # 添加新候选（不重复）
    existing_codes = set(item['code'] for item in plan.get('items', []))
    for c in buy_plan_candidates:
        if c['code'] not in existing_codes:
            plan['items'].append(c)
            existing_codes.add(c['code'])

    save_json(BUY_PLAN_FILE, plan)
    print(f"  📋 买入计划已更新：{len(plan['items'])}只股票在观察中")
    for item in plan['items']:
        print(f"     👀 {item['name']}（{item['code']}）目标买入价 {item.get('target_price', '-'):.2f}元")


def is_market_open():
    """检查A股市场是否开盘（周一到周五 9:15-15:00）"""
    now = datetime.now()
    # 周末不开盘
    if now.weekday() >= 5:
        return False
    hour, minute = now.hour, now.minute
    t = hour * 60 + minute
    # 9:15 - 15:00
    return 555 <= t <= 900


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--save-plan':
        # 被 analyze.py 调用：保存买入计划
        plan_data = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
        save_buy_plan(plan_data)
    elif len(sys.argv) > 1 and sys.argv[1] == '--loop':
        # 持续运行模式
        print(f"🔍 买入观察器启动，每60秒检查一次...", flush=True)
        while True:
            try:
                run_once()
            except Exception as e:
                print(f"  ❌ 观察器错误: {e}")
            time.sleep(60)
    else:
        # 单次运行（适合cron调用）
        if not is_market_open():
            sys.exit(0)  # 非交易时间静默退出
        run_once()
