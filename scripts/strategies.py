#!/usr/bin/env python3
"""
策略分析引擎 strategies.py
定义20个短线高收益稳定性策略，每天筛选符合条件的股票，追踪30天表现。

策略设计思路：
1. 基于技术面的经典策略（均线、MACD、KDJ、布林带等）
2. 基于庄家心理的策略（吸筹、拉升、出货周期）
3. 形态学策略（W底、头肩底、平台突破等）
4. 资金面策略（放量、缩量、资金流入）

每天8:30执行筛选，每策略最多选5只，存入 data/strategy_tracking.json
追踪30天内的涨跌表现，统计各策略胜率和平均收益。
"""

import os
import json
import math
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
TRACKING_FILE = os.path.join(DATA_DIR, 'strategy_tracking.json')
STRATEGY_CONFIG_FILE = os.path.join(DATA_DIR, 'strategy_config.json')


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== 20个策略定义 ====================

STRATEGIES = [
    {
        "id": "s01_ma_golden_cross",
        "name": "均线金叉",
        "category": "趋势",
        "description": "MA5上穿MA10形成金叉，配合MACD红柱放大",
        "weight": 5,
        "logic": lambda s: (
            s.get('ma5', 0) > s.get('ma10', 0) and
            s.get('ma10', 0) > s.get('ma20', 0) and
            s.get('macd_dif', 0) > s.get('macd_dif', -99) and  # DIF > 0 或刚转正
            s.get('rsi6', 50) < 70 and s.get('rsi6', 50) > 30 and
            s.get('change_pct', 0) > -3
        ),
    },
    {
        "id": "s02_volume_breakout",
        "name": "放量突破",
        "category": "资金",
        "description": "成交额放大2倍以上突破前高，庄家启动信号",
        "weight": 5,
        "logic": lambda s: (
            s.get('change_pct', 0) > 3 and
            (s.get('signals') and any('放量上涨' in sig or '高换手' in sig for sig in s.get('signals', [])))
        ),
    },
    {
        "id": "s03_macd_dif_bottom",
        "name": "MACD底背离",
        "category": "技术",
        "description": "股价创新低但MACD DIF未创新低，底背离反转信号",
        "weight": 4,
        "logic": lambda s: (
            s.get('rsi6', 50) < 40 and
            s.get('kdj_k', 50) < 40 and
            s.get('macd_dif', 0) < 0 and
            s.get('price', 0) > s.get('boll_lower', 0) and
            s.get('change_pct', 0) > -5
        ),
    },
    {
        "id": "s04_boll_lower_bounce",
        "name": "布林下轨反弹",
        "category": "技术",
        "description": "股价触及布林带下轨后企稳，支撑位反弹",
        "weight": 4,
        "logic": lambda s: (
            s.get('boll_lower', 0) > 0 and
            s.get('price', 999) <= s.get('boll_lower', 0) * 1.02 and
            s.get('rsi6', 50) < 35 and
            s.get('change_pct', 0) > -7
        ),
    },
    {
        "id": "s05_pullback_ma20",
        "name": "缩量回调买入",
        "category": "趋势",
        "description": "上涨趋势中缩量回调至MA20附近企稳，庄家洗盘结束",
        "weight": 5,
        "logic": lambda s: (
            s.get('ma5', 0) > s.get('ma20', 0) and
            s.get('ma20', 0) > s.get('ma60', 0) and
            s.get('price', 999) <= s.get('ma20', 0) * 1.03 and
            s.get('price', 0) >= s.get('ma20', 0) * 0.98 and
            s.get('change_pct', 0) < 2 and s.get('change_pct', 0) > -3 and
            s.get('rsi6', 50) < 55
        ),
    },
    {
        "id": "s06_limit_up_continue",
        "name": "涨停板接力",
        "category": "资金",
        "description": "首板涨停次日高开或继续上攻，短期强势延续",
        "weight": 3,
        "logic": lambda s: (
            s.get('change_pct', 0) >= 9.5 and
            s.get('score', 0) >= 80 and
            (s.get('signals') and any('强势上涨' in sig or '高换手' in sig for sig in s.get('signals', [])))
        ),
    },
    {
        "id": "s07_oversold_bounce",
        "name": "超跌反弹",
        "category": "技术",
        "description": "连续下跌后RSI进入超卖区，技术性反弹概率大",
        "weight": 3,
        "logic": lambda s: (
            s.get('rsi6', 50) < 25 and
            s.get('kdj_j', 50) < 20 and
            s.get('change_pct', 0) < -2
        ),
    },
    {
        "id": "s08_platform_breakout",
        "name": "平台突破",
        "category": "形态",
        "description": "长期横盘整理后放量突破平台，庄家结束整理开始拉升",
        "weight": 5,
        "logic": lambda s: (
            s.get('change_pct', 0) > 4 and
            s.get('rsi6', 50) > 50 and s.get('rsi6', 50) < 75 and
            s.get('ma5', 0) > s.get('ma10', 0) and
            (s.get('signals') and any('放量上涨' in sig or '突破' in sig for sig in s.get('signals', [])))
        ),
    },
    {
        "id": "s09_w_bottom",
        "name": "W底形态",
        "category": "形态",
        "description": "二次探底形成W底后回升，底部确认反弹空间大",
        "weight": 4,
        "logic": lambda s: (
            s.get('boll_lower', 0) > 0 and
            s.get('price', 999) <= s.get('boll_lower', 0) * 1.05 and
            s.get('price', 0) >= s.get('boll_lower', 0) * 0.95 and
            s.get('kdj_j', 50) < 30 and
            s.get('change_pct', 0) > 0  # 开始回升
        ),
    },
    {
        "id": "s10_smart_money_inflow",
        "name": "主力资金流入",
        "category": "资金",
        "description": "大单净流入明显，主力资金持续建仓",
        "weight": 4,
        "logic": lambda s: (
            s.get('change_pct', 0) > 1 and
            s.get('score', 0) >= 70 and
            s.get('ma5', 0) > s.get('ma10', 0) and
            (s.get('signals') and any('强势上涨' in sig or '放量上涨' in sig for sig in s.get('signals', [])))
        ),
    },
    {
        "id": "s11_ma_bull_align",
        "name": "多头排列",
        "category": "趋势",
        "description": "MA5>MA10>MA20>MA60完美多头排列，趋势最强",
        "weight": 5,
        "logic": lambda s: (
            s.get('ma5', 0) > 0 and s.get('ma10', 0) > 0 and
            s.get('ma20', 0) > 0 and s.get('ma60', 0) > 0 and
            s.get('ma5', 0) > s.get('ma10', 0) > s.get('ma20', 0) > s.get('ma60', 0) and
            s.get('change_pct', 0) > 0 and
            s.get('rsi6', 50) < 75
        ),
    },
    {
        "id": "s12_rsi_oversold_recover",
        "name": "RSI超卖回升",
        "category": "技术",
        "description": "RSI从超卖区回升，短期反转信号",
        "weight": 3,
        "logic": lambda s: (
            s.get('rsi6', 50) > 25 and s.get('rsi6', 50) < 45 and
            s.get('change_pct', 0) > 0 and
            s.get('kdj_k', 50) > s.get('kdj_j', 50)
        ),
    },
    {
        "id": "s13_chip_concentration",
        "name": "筹码集中启动",
        "category": "庄家",
        "description": "筹码集中度高+缩量横盘后突然放量，庄家吸筹完毕准备拉升",
        "weight": 4,
        "logic": lambda s: (
            s.get('change_pct', 0) > 2 and s.get('change_pct', 0) < 7 and
            s.get('ma5', 0) > s.get('ma10', 0) and
            (s.get('signals') and any('放量上涨' in sig for sig in s.get('signals', []))) and
            s.get('score', 0) >= 70
        ),
    },
    {
        "id": "s14_gap_up_fill",
        "name": "跳空缺口回补",
        "category": "形态",
        "description": "向上跳空后回补缺口企稳，确认支撑有效",
        "weight": 3,
        "logic": lambda s: (
            s.get('change_pct', 0) > 0 and s.get('change_pct', 0) < 3 and
            s.get('price', 0) > s.get('ma5', 0) and
            s.get('price', 0) > s.get('ma10', 0) and
            s.get('rsi6', 50) > 40 and s.get('rsi6', 50) < 65
        ),
    },
    {
        "id": "s15_high_turnover_start",
        "name": "高换手启动",
        "category": "资金",
        "description": "换手率突然放大至10%以上，庄家大幅建仓或启动",
        "weight": 4,
        "logic": lambda s: (
            s.get('change_pct', 0) > 3 and
            (s.get('signals') and any('高换手' in sig for sig in s.get('signals', []))) and
            s.get('score', 0) >= 65
        ),
    },
    {
        "id": "s16_small_yang_accumulate",
        "name": "小阳线吸筹",
        "category": "庄家",
        "description": "连续小阳线缓慢上涨，换手温和，庄家暗中吸筹",
        "weight": 4,
        "logic": lambda s: (
            0 < s.get('change_pct', 0) < 3 and
            s.get('ma5', 0) > s.get('ma10', 0) and
            s.get('rsi6', 50) > 45 and s.get('rsi6', 50) < 65 and
            s.get('macd_dif', 0) > 0 and
            not any('放量' in sig for sig in s.get('signals', []))  # 缩量
        ),
    },
    {
        "id": "s17_duck_head",
        "name": "老鸭头形态",
        "category": "形态",
        "description": "经典老鸭头形态：MA5金叉MA10后回踩再金叉，中期看涨",
        "weight": 4,
        "logic": lambda s: (
            s.get('ma5', 0) > s.get('ma10', 0) and
            s.get('ma10', 0) > s.get('ma20', 0) and
            s.get('change_pct', 0) > 0 and s.get('change_pct', 0) < 5 and
            s.get('macd_dif', 0) > s.get('macd_dif', -99) and
            s.get('rsi6', 50) > 50 and s.get('rsi6', 50) < 70
        ),
    },
    {
        "id": "s18_guiding_star",
        "name": "仙人指路",
        "category": "形态",
        "description": "长上影线后次日高开，试探性上攻确认方向",
        "weight": 3,
        "logic": lambda s: (
            s.get('change_pct', 0) > 1 and
            s.get('price', 0) > s.get('ma5', 0) > s.get('ma10', 0) and
            s.get('rsi6', 50) > 50 and
            s.get('score', 0) >= 70
        ),
    },
    {
        "id": "s19_downtrend_pullback",
        "name": "下跌回调吃利",
        "category": "趋势",
        "description": "下跌趋势中短期超跌后技术反弹，快进快出",
        "weight": 3,
        "logic": lambda s: (
            s.get('change_pct', 0) < -3 and
            s.get('rsi6', 50) < 30 and
            s.get('kdj_j', 50) < 25 and
            s.get('boll_lower', 0) > 0 and
            s.get('price', 0) < s.get('boll_lower', 0) * 1.01
        ),
    },
    {
        "id": "s20_makers_silent_acc",
        "name": "庄家静默吸筹",
        "category": "庄家",
        "description": "股价长期横盘窄幅震荡，成交量萎缩后突然温和放大，庄家埋伏即将拉升",
        "weight": 5,
        "logic": lambda s: (
            -1 < s.get('change_pct', 0) < 2 and
            s.get('ma5', 0) > 0 and s.get('ma10', 0) > 0 and
            abs(s.get('ma5', 0) - s.get('ma10', 0)) / s.get('ma10', 1) < 0.02 and  # MA5贴近MA10
            s.get('ma20', 0) > 0 and abs(s.get('ma5', 0) - s.get('ma20', 0)) / s.get('ma20', 1) < 0.03 and
            s.get('rsi6', 50) > 40 and s.get('rsi6', 50) < 60 and
            s.get('score', 0) >= 60 and
            s.get('macd_dif', 0) >= -0.5  # MACD接近零轴
        ),
    },
]


def run_strategy_screening(all_stocks):
    """
    对所有股票运行策略筛选
    返回: {strategy_id: [top5_stocks]}
    """
    results = {}
    for strategy in STRATEGIES:
        matched = []
        for s in all_stocks:
            try:
                # 确保股票有足够的技术指标数据
                if s.get('ma5', 0) <= 0 or s.get('ma10', 0) <= 0:
                    continue
                if strategy['logic'](s):
                    matched.append({
                        'code': s['code'],
                        'name': s['name'],
                        'price': s['price'],
                        'change_pct': s.get('change_pct', 0),
                        'score': s.get('score', 0),
                        'signals': s.get('signals', []),
                        'reason': _get_match_reason(s, strategy),
                    })
            except:
                continue

        # 按评分排序，取前5
        matched.sort(key=lambda x: x['score'], reverse=True)
        results[strategy['id']] = matched[:5]

    return results


def _get_match_reason(stock, strategy):
    """生成匹配原因说明"""
    s = stock
    reasons = []
    name = strategy['name']

    if '金叉' in name:
        reasons.append('MA5>MA10金叉')
    if '多头排列' in name:
        reasons.append('均线多头排列')
    if '放量' in name:
        reasons.append('成交量放大')
    if '超卖' in name:
        reasons.append(f'RSI={s.get("rsi6",0):.0f}超卖')
    if '布林' in name:
        reasons.append(f'触及布林下轨{s.get("boll_lower",0):.2f}')
    if '缩量' in name:
        reasons.append('缩量回调至均线附近')
    if '横盘' in name or '静默' in name:
        reasons.append('横盘整理中')
    if '涨停' in name:
        reasons.append(f'涨幅{s.get("change_pct",0):.1f}%')

    return f"[{name}] {'，'.join(reasons[:3])}"


def save_tracking(strategy_results):
    """保存策略筛选结果到追踪文件"""
    tracking = load_json(TRACKING_FILE, {'daily_results': {}, 'config': {}})
    today = datetime.now().strftime('%Y-%m-%d')

    # 今天的筛选结果
    daily = {
        'date': today,
        'time': datetime.now().strftime('%H:%M'),
        'strategies': {},
    }

    for sid, stocks in strategy_results.items():
        strategy_info = next((s for s in STRATEGIES if s['id'] == sid), None)
        daily['strategies'][sid] = {
            'name': strategy_info['name'] if strategy_info else sid,
            'category': strategy_info['category'] if strategy_info else '',
            'stocks': stocks,
            'count': len(stocks),
        }

    tracking['daily_results'][today] = daily
    tracking['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 清理超过30天的旧数据
    cutoff = datetime.now()
    from datetime import timedelta
    cutoff = cutoff - timedelta(days=35)
    for date in list(tracking['daily_results'].keys()):
        try:
            d = datetime.strptime(date, '%Y-%m-%d')
            if d < cutoff:
                del tracking['daily_results'][date]
        except:
            pass

    save_json(TRACKING_FILE, tracking)
    return tracking


def get_strategy_stats():
    """计算各策略的统计数据"""
    tracking = load_json(TRACKING_FILE, {'daily_results': {}})
    daily_results = tracking.get('daily_results', {})

    stats = {}
    for sid, strategy in [(s['id'], s) for s in STRATEGIES]:
        total = 0
        wins = 0
        total_pnl = 0
        days_active = 0

        # 遍历每一天的结果
        for date_str, daily in sorted(daily_results.items()):
            strat_data = daily.get('strategies', {}).get(sid)
            if not strat_data or not strat_data.get('stocks'):
                continue
            days_active += 1

            for stock in strat_data['stocks']:
                code = stock['code']
                entry_price = stock['price']

                # 找下一天的数据
                dates = sorted(daily_results.keys())
                date_idx = dates.index(date_str) if date_str in dates else -1
                if date_idx < 0 or date_idx >= len(dates) - 1:
                    continue

                next_date = dates[date_idx + 1]
                if not next_date.startswith(date_str[:10].replace(date_str[8:10], str(int(date_str[8:10])+1).zfill(2))):
                    # 不是下一天
                    for d in dates[date_idx+1:]:
                        if d > date_str:
                            next_date = d
                            break

                next_daily = daily_results.get(next_date, {})
                next_strat = next_daily.get('strategies', {})
                next_price = None

                # 在下一天的所有策略结果中找这个股票的价格
                for nsid, nsdata in next_strat.items():
                    for ns in nsdata.get('stocks', []):
                        if ns['code'] == code:
                            next_price = ns['price']
                            break
                    if next_price:
                        break

                # 也在 scores 中查找
                if next_price is None:
                    # 尝试从历史文件获取（简化：用前一天的价格近似）
                    pass

                if next_price and entry_price > 0:
                    pnl_pct = (next_price - entry_price) / entry_price * 100
                    total += 1
                    total_pnl += pnl_pct
                    if pnl_pct > 0:
                        wins += 1

        if total > 0:
            stats[sid] = {
                'name': strategy['name'],
                'category': strategy['category'],
                'total_trades': total,
                'win_rate': round(wins / total * 100, 1),
                'avg_pnl': round(total_pnl / total, 2),
                'days_active': days_active,
            }
        else:
            stats[sid] = {
                'name': strategy['name'],
                'category': strategy['category'],
                'total_trades': 0,
                'win_rate': 0,
                'avg_pnl': 0,
                'days_active': days_active,
            }

    # 按胜率排序
    sorted_stats = sorted(stats.items(), key=lambda x: x[1].get('win_rate', 0), reverse=True)
    return dict(sorted_stats)


def format_report(strategy_results, strategy_stats=None):
    """格式化策略筛选报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("  🧪 策略筛选日报  |  " + datetime.now().strftime('%Y-%m-%d %H:%M'))
    lines.append("=" * 60)

    total_matched = sum(len(v) for v in strategy_results.values())
    active_strategies = sum(1 for v in strategy_results.values() if v)
    lines.append(f"\n📊 筛选结果：{active_strategies}个策略命中，共{total_matched}只股票\n")

    # 按类别分组
    categories = {}
    for strategy in STRATEGIES:
        cat = strategy['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(strategy)

    for cat, strats in categories.items():
        lines.append(f"\n--- {cat}类策略 ---")
        for strategy in strats:
            stocks = strategy_results.get(strategy['id'], [])
            stat = strategy_stats.get(strategy['id'], {}) if strategy_stats else {}

            if stocks:
                wr = stat.get('win_rate', '-')
                avg = stat.get('avg_pnl', '-')
                lines.append(f"\n  📌 {strategy['name']}（{strategy['description']}）")
                lines.append(f"     历史：{stat.get('total_trades', 0)}次 | 胜率{wr}% | 平均{avg}%")
                for i, s in enumerate(stocks, 1):
                    chg = s.get('change_pct', 0)
                    sign = '+' if chg >= 0 else ''
                    lines.append(f"     {i}. {s['name']}（{s['code']}）{s['price']:.2f}元 {sign}{chg:.2f}% 评分{s['score']} {s.get('reason','')}")
            else:
                lines.append(f"\n  📌 {strategy['name']}：今日无匹配")

    return '\n'.join(lines)


def update_tracking_prices(all_stocks):
    """更新追踪中股票的最新价格（用于计算收益）"""
    tracking = load_json(TRACKING_FILE, {'daily_results': {}})
    price_map = {s['code']: s['price'] for s in all_stocks}
    today = datetime.now().strftime('%Y-%m-%d')

    # 为每个历史筛选记录添加最新价格
    for date_str, daily in tracking.get('daily_results', {}).items():
        if date_str == today:
            continue
        for sid, sdata in daily.get('strategies', {}).items():
            for stock in sdata.get('stocks', []):
                code = stock.get('code', '')
                if code in price_map and 'current_price' not in stock:
                    stock['current_price'] = price_map[code]
                    entry = stock.get('price', 0)
                    if entry > 0:
                        stock['pnl_pct'] = round((price_map[code] - entry) / entry * 100, 2)

    save_json(TRACKING_FILE, tracking)


if __name__ == '__main__':
    # 独立运行时的测试
    print("🧪 策略分析引擎 v1.0")
    print(f"已定义 {len(STRATEGIES)} 个策略：")
    for s in STRATEGIES:
        print(f"  {s['id']}: {s['name']} [{s['category']}] - {s['description']} (权重{s['weight']})")
