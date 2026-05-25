#!/usr/bin/env python3
"""
尾盘综合分析 v1.0
每个交易日14:20运行（收盘前40分钟），分析：
1. 今日推荐股票的实时表现
2. 全市场即时情绪
3. 尾盘操作建议（是否需要止盈/止损/调仓）
4. 盘中异动板块
"""

import json
import os
import sys
import traceback
import requests
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
sys.path.insert(0, SCRIPT_DIR)

from market_impact import (
    assess_us_impact, assess_commodity_impact, assess_fx_impact,
    assess_global_impact, build_impact_summary
)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
_session = requests.Session()
_session.headers.update(HEADERS)


def _load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_realtime_batch(codes):
    """批量获取实时行情"""
    result = {}
    if not codes:
        return result
    try:
        # 腾讯API，每批最多50个
        for i in range(0, len(codes), 50):
            batch = codes[i:i+50]
            url = f"https://qt.gtimg.cn/q={','.join(batch)}"
            r = _session.get(url, timeout=15)
            for line in r.text.strip().split(';'):
                if '~' not in line or '=' not in line:
                    continue
                parts = line.split('~')
                if len(parts) < 50:
                    continue
                code = parts[2]
                result[code] = {
                    'code': code,
                    'name': parts[1],
                    'price': float(parts[3]) if parts[3] else 0,
                    'prev_close': float(parts[4]) if parts[4] else 0,
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'high': float(parts[33]) if parts[33] else 0,
                    'low': float(parts[34]) if parts[34] else 0,
                    'volume': float(parts[6]) if parts[6] else 0,
                    'amount': float(parts[37]) if parts[37] else 0,
                    'turnover_rate': float(parts[38]) if parts[38] else 0,
                    'pe': float(parts[39]) if parts[39] else 0,
                    'amplitude': float(parts[43]) if parts[43] else 0,
                }
    except Exception as e:
        print(f"  获取实时行情失败: {e}")
    return result


def fetch_cn_indices():
    """获取A股指数"""
    codes = ['sh000001', 'sz399001', 'sz399006', 'sh000688', 'sh000300', 'sz399005']
    result = fetch_realtime_batch(codes)
    indices = {}
    name_map = {
        '000001': '上证指数', '399001': '深证成指', '399006': '创业板指',
        '000688': '科创50', '000300': '沪深300', '399005': '中小100'
    }
    for code, data in result.items():
        code_num = code.replace('sh', '').replace('sz', '')
        indices[code_num] = {
            'name': name_map.get(code_num, data['name']),
            'code': code_num,
            'price': data['price'],
            'prev_close': data['prev_close'],
            'change_pct': data['change_pct'],
        }
    return indices


def get_recommended_stocks():
    """获取今日推荐股票（从morning_analysis或buy_plan）"""
    morning = _load_json(os.path.join(DATA_DIR, 'morning_analysis.json'))
    top_buys = morning.get('top_buys', [])
    if not top_buys:
        # 尝试从buy_plan获取
        buy_plan = _load_json(os.path.join(DATA_DIR, 'buy_plan.json'))
        top_buys = buy_plan.get('items', [])
        top_buys = [{'code': s['code'], 'name': s.get('name', ''),
                      'score': s.get('score', 0), 'price': s.get('target_price', 0),
                      'buy_point': s.get('plan_price', 0)} for s in top_buys]
    return top_buys


def analyze_stock_performance(stock, realtime):
    """分析推荐股票的实时表现"""
    code = stock.get('code', '')
    rt = realtime.get(code) or realtime.get(f'sh{code}') or realtime.get(f'sz{code}')
    if not rt:
        return {
            'code': code,
            'name': stock.get('name', '未知'),
            'status': '未获取到数据',
            'change_pct': 0,
            'current_price': 0,
            'action': '—',
        }

    name = stock.get('name', rt['name'])
    buy_point = stock.get('buy_point', 0)
    stop_loss = stock.get('stop_loss', 0)
    target_price = stock.get('target_price', 0)
    current = rt['price']
    change = rt['change_pct']

    # 判断操作建议
    actions = []
    if stop_loss and current <= stop_loss:
        action = '🔴 建议止损'
        actions.append('止损')
    elif target_price and current >= target_price:
        action = '🟢 到达目标价，建议止盈'
        actions.append('止盈')
    elif change > 5:
        action = '⚠️ 涨幅较大，注意追高风险'
        actions.append('观望')
    elif change < -3:
        action = '⚠️ 跌幅较大，关注止损位'
        actions.append('关注止损')
    elif change > 0:
        action = '🟢 持有，走势正常'
        actions.append('持有')
    else:
        action = '🟡 小幅波动，继续观察'
        actions.append('观察')

    # 盈亏比例（相对买入价）
    pnl_pct = 0
    if buy_point and buy_point > 0:
        pnl_pct = (current - buy_point) / buy_point * 100

    return {
        'code': code,
        'name': name,
        'status': '正常' if change > 0 else '下跌',
        'current_price': current,
        'change_pct': round(change, 2),
        'high': rt['high'],
        'low': rt['low'],
        'turnover_rate': rt['turnover_rate'],
        'amplitude': rt['amplitude'],
        'pnl_pct': round(pnl_pct, 2),
        'action': action,
        'action_type': actions[0] if actions else '—',
    }


def assess_intraday_sentiment(cn_indices):
    """评估盘中情绪"""
    scores = {}
    for code, idx in cn_indices.items():
        pct = idx.get('change_pct', 0)
        if pct > 1:
            scores[code] = {'level': '强势', 'score': 80, 'emoji': '📈'}
        elif pct > 0.3:
            scores[code] = {'level': '偏强', 'score': 60, 'emoji': '↗️'}
        elif pct > -0.3:
            scores[code] = {'level': '震荡', 'score': 50, 'emoji': '➡️'}
        elif pct > -1:
            scores[code] = {'level': '偏弱', 'score': 40, 'emoji': '↘️'}
        else:
            scores[code] = {'level': '弱势', 'score': 20, 'emoji': '📉'}
    return scores


def get_all_stocks_change(all_stocks):
    """获取全市场涨跌分布"""
    if not all_stocks:
        return {}
    stocks = all_stocks.get('stocks', all_stocks) if isinstance(all_stocks, dict) else all_stocks
    up = sum(1 for s in stocks if s.get('change_pct', 0) > 0)
    down = sum(1 for s in stocks if s.get('change_pct', 0) < 0)
    flat = sum(1 for s in stocks if s.get('change_pct', 0) == 0)
    limit_up = sum(1 for s in stocks if s.get('change_pct', 0) >= 9.8)
    limit_down = sum(1 for s in stocks if s.get('change_pct', 0) <= -9.8)
    avg_change = 0
    if stocks:
        avg_change = sum(s.get('change_pct', 0) for s in stocks) / len(stocks)
    return {
        'total': len(stocks),
        'up': up,
        'down': down,
        'flat': flat,
        'limit_up': limit_up,
        'limit_down': limit_down,
        'up_ratio': round(up / len(stocks) * 100, 1) if stocks else 0,
        'avg_change': round(avg_change, 2),
    }


def generate_advice(cn_indices, performances, market_stats):
    """生成尾盘操作建议"""
    advices = []
    sh_pct = cn_indices.get('000001', {}).get('change_pct', 0)

    # 大盘建议
    if sh_pct > 1:
        advices.append(f"📈 大盘强势（上证+{sh_pct:.2f}%），持股为主，尾盘可适当加仓优质标的")
    elif sh_pct > 0:
        advices.append(f"↗️ 大盘偏强（上证+{sh_pct:.2f}%），走势稳健，维持现有仓位")
    elif sh_pct > -0.5:
        advices.append(f"➡️ 大盘震荡（上证{sh_pct:.2f}%），控制仓位，尾盘不建议追涨")
    else:
        advices.append(f"📉 大盘偏弱（上证{sh_pct:.2f}%），注意风险，尾盘考虑减仓")

    # 推荐股票建议
    need_stop_loss = [p for p in performances if p.get('action_type') == '止损']
    need_take_profit = [p for p in performances if p.get('action_type') == '止盈']
    profitable = [p for p in performances if p.get('pnl_pct', 0) > 0]
    losing = [p for p in performances if p.get('pnl_pct', 0) < 0]

    if need_stop_loss:
        names = ', '.join([f"{p['name']}({p['change_pct']:+.1f}%)" for p in need_stop_loss])
        advices.append(f"🔴 止损预警: {names}，尾盘建议卖出")
    if need_take_profit:
        names = ', '.join([f"{p['name']}({p['change_pct']:+.1f}%)" for p in need_take_profit])
        advices.append(f"🟢 止盈提醒: {names}，可考虑部分获利了结")
    if profitable and not need_take_profit:
        avg_pnl = sum(p['pnl_pct'] for p in profitable) / len(profitable)
        advices.append(f"🟢 推荐股平均浮盈 {avg_pnl:+.1f}%，走势良好，继续持有")
    if losing and not need_stop_loss:
        avg_loss = sum(p['pnl_pct'] for p in losing) / len(losing)
        advices.append(f"🟡 推荐股平均浮亏 {avg_loss:+.1f}%，关注关键支撑位")

    # 赚钱效应
    up_ratio = market_stats.get('up_ratio', 50)
    if up_ratio > 60:
        advices.append(f"💰 赚钱效应较好（{up_ratio}%上涨），市场情绪积极")
    elif up_ratio > 40:
        advices.append(f"🟡 赚钱效应一般（{up_ratio}%上涨），板块分化明显")
    else:
        advices.append(f"⚠️ 赚钱效应较差（{up_ratio}%上涨），操作需谨慎")

    # 尾盘通用建议
    advices.append("⏰ 距收盘约40分钟，避免尾盘追涨杀跌")

    return advices


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now()
    print("=" * 60)
    print(f"  🔔 尾盘综合分析  |  {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取A股指数
    print("  [1/5] 获取A股指数...")
    cn_indices = fetch_cn_indices()
    sh = cn_indices.get('000001', {})
    print(f"        上证: {sh.get('price', '-')} ({sh.get('change_pct', 0):+.2f}%)")

    # 2. 获取推荐股票实时行情
    print("  [2/5] 获取推荐股票实时行情...")
    recommended = get_recommended_stocks()
    print(f"        找到 {len(recommended)} 只推荐股票")

    codes = []
    for s in recommended:
        code = s.get('code', '')
        if code.startswith('6'):
            codes.append(f'sh{code}')
        else:
            codes.append(f'sz{code}')

    realtime = fetch_realtime_batch(codes)

    # 3. 分析推荐股票表现
    print("  [3/5] 分析推荐股票表现...")
    performances = []
    for stock in recommended:
        perf = analyze_stock_performance(stock, realtime)
        performances.append(perf)
        change = perf.get('change_pct', 0)
        emoji = '🟢' if change > 0 else '🔴' if change < 0 else '🟡'
        print(f"        {perf['name']}: {perf.get('current_price', '-')} ({change:+.2f}%) {emoji} {perf['action']}")

    # 4. 市场情绪分析
    print("  [4/5] 分析市场情绪...")
    all_stocks = _load_json(os.path.join(DATA_DIR, 'all_stocks.json'))
    market_stats = get_all_stocks_change(all_stocks)
    sentiment = assess_intraday_sentiment(cn_indices)

    for code, s in sentiment.items():
        idx = cn_indices.get(code, {})
        print(f"        {idx.get('name', code)}: {s['emoji']} {s['level']} ({idx.get('change_pct', 0):+.2f}%)")

    print(f"        涨跌比: {market_stats.get('up', 0)}涨 / {market_stats.get('down', 0)}跌 | "
          f"涨停{market_stats.get('limit_up', 0)} / 跌停{market_stats.get('limit_down', 0)}")

    # 5. 生成尾盘建议
    print("  [5/5] 生成尾盘操作建议...")
    advices = generate_advice(cn_indices, performances, market_stats)

    # 保存分析数据
    analysis = {
        'update_time': now.strftime('%Y-%m-%d %H:%M:%S'),
        'cn_indices': cn_indices,
        'recommended_stocks': performances,
        'market_stats': market_stats,
        'sentiment': sentiment,
        'advices': advices,
        'source_recommendations': recommended,
    }
    _save_json(os.path.join(DATA_DIR, 'eod_analysis.json'), analysis)

    print()
    for advice in advices:
        print(f"  {advice}")
    print(f"\n  ✅ 尾盘分析完成！")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 尾盘分析失败: {e}")
        traceback.print_exc()
        sys.exit(1)
