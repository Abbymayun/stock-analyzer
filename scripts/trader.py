#!/usr/bin/env python3
"""
虚拟炒股引擎 v3.0
- 10万启动资金
- 每天最多买入3只股票
- T+1规则：今天买入的股票，明天才能卖出
- 基于分析评分自动决策买卖
- 不可篡改的交易记录（hash链）
"""

import json
import os
import sys
import hashlib
from datetime import datetime

# 导入统一交易日历
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CALENDAR_DIR = SCRIPT_DIR
sys.path.insert(0, CALENDAR_DIR)
from market_calendar import is_trading_time, is_trading_day

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
PORTFOLIO_FILE = os.path.join(DATA_DIR, 'portfolio.json')
TRADE_LOG_FILE = os.path.join(DATA_DIR, 'trade_log.json')

INITIAL_CAPITAL = 100000.0
MAX_BUY_PER_DAY = 3
COMMISSION_RATE = 0.0003  # 佣金万三
MIN_COMMISSION = 5.0      # 最低5元
STAMP_TAX_RATE = 0.001    # 印花税千一（仅卖出）
SLIPPAGE = 0.002          # 滑点0.2%


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_portfolio():
    """加载投资组合"""
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, 'r') as f:
            data = json.load(f)
        # 兼容性检查
        if 'cash' not in data:
            data['cash'] = INITIAL_CAPITAL
        if 'holdings' not in data:
            data['holdings'] = {}
        if 'daily_reports' not in data:
            data['daily_reports'] = []
        if 'trading_stats' not in data:
            data['trading_stats'] = {'total_trades': 0, 'win_trades': 0, 'total_pnl': 0}
        return data
    else:
        return init_portfolio()


def save_portfolio(data):
    """保存投资组合"""
    ensure_data_dir()
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def init_portfolio():
    """初始化投资组合"""
    data = {
        'initial_capital': INITIAL_CAPITAL,
        'cash': INITIAL_CAPITAL,
        'holdings': {},  # code -> { name, qty, avg_cost, buy_date, scores: [], signals: [] }
        'daily_reports': [],
        'trading_stats': {
            'total_trades': 0,
            'win_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0,
            'best_trade': None,
            'worst_trade': None,
        },
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_trade_date': None,
    }
    save_portfolio(data)
    return data


def load_trade_log():
    """加载不可篡改的交易记录（hash链）"""
    if os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, 'r') as f:
            data = json.load(f)
        return data
    return {'trades': [], 'prev_hash': '0' * 64}


def save_trade_log(data):
    """保存交易记录"""
    ensure_data_dir()
    with open(TRADE_LOG_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_trade(trade_type, code, name, price, qty, reason, portfolio_data, extra=None):
    """添加交易记录（hash链保证不可篡改）"""
    log = load_trade_log()
    prev_hash = log['prev_hash']
    
    trade = {
        'id': len(log['trades']) + 1,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'type': trade_type,  # 'buy', 'sell', 'day_trade_buy', 'day_trade_sell'
        'code': code,
        'name': name,
        'price': round(price, 3),
        'qty': qty,
        'amount': round(price * qty, 2),
        'commission': round(calc_commission(price, qty, trade_type), 2),
        'reason': reason,
        'portfolio_snapshot': {
            'cash': round(portfolio_data['cash'], 2),
            'total_assets': round(calc_total_assets(portfolio_data), 2),
        },
        'prev_hash': prev_hash,
    }
    if extra:
        trade.update(extra)
    
    # 计算hash（防止篡改）
    hash_str = json.dumps(trade, sort_keys=True, ensure_ascii=False) + prev_hash
    trade['hash'] = hashlib.sha256(hash_str.encode()).hexdigest()
    
    log['trades'].append(trade)
    log['prev_hash'] = trade['hash']
    save_trade_log(log)
    
    return trade


def verify_trade_log():
    """验证交易记录完整性"""
    log = load_trade_log()
    prev_hash = '0' * 64
    valid = True
    for i, trade in enumerate(log['trades']):
        # 重建hash
        check = {k: v for k, v in trade.items() if k != 'hash'}
        hash_str = json.dumps(check, sort_keys=True, ensure_ascii=False) + prev_hash
        expected = hashlib.sha256(hash_str.encode()).hexdigest()
        if trade['hash'] != expected:
            return False, i
        if trade['prev_hash'] != prev_hash:
            return False, i
        prev_hash = trade['hash']
    return True, None


def calc_commission(price, qty, trade_type='buy'):
    """计算交易费用"""
    amount = price * qty
    commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
    tax = 0
    if trade_type in ('sell', 'day_trade_sell'):
        tax = amount * STAMP_TAX_RATE
    return commission + tax


def calc_total_assets(portfolio_data, current_prices=None):
    """计算总资产"""
    total = portfolio_data['cash']
    for code, h in portfolio_data.get('holdings', {}).items():
        if current_prices and code in current_prices:
            total += current_prices[code] * h['qty']
        else:
            total += h.get('current_price', h['avg_cost']) * h['qty']
    return total


def calc_slippage_price(price, is_buy=True):
    """计算滑点后的实际价格"""
    if is_buy:
        return round(price * (1 + SLIPPAGE), 2)
    else:
        return round(price * (1 - SLIPPAGE), 2)


def get_buyable_amount(cash, price):
    """计算可买入股数（100的整数倍）"""
    fee = max(price * 100 * COMMISSION_RATE, MIN_COMMISSION)
    max_qty = int((cash - fee) / (price * (1 + SLIPPAGE))) // 100 * 100
    return max(max_qty, 0)


def make_trading_decision(portfolio, recommendations, all_stocks, macro_indices):
    """
    核心交易决策引擎
    返回: (decisions, buy_plan) - decisions立即执行（仅卖出），buy_plan写入计划文件由watcher观察执行
    """
    decisions = []
    buy_plan = []
    today = datetime.now().strftime('%Y-%m-%d')
    sentiment = recommendations.get('market_sentiment', '中性')
    avg_score = recommendations.get('avg_score', 50)
    
    # 获取当前持仓代码
    holdings = portfolio.get('holdings', {})
    holding_codes = set(holdings.keys())
    
    # 构建价格查询表
    price_map = {}
    for s in all_stocks:
        price_map[s['code']] = {
            'price': s['price'],
            'name': s['name'],
            'change_pct': s.get('change_pct', 0),
            'score': s.get('score', 0),
            'recommendation': s.get('recommendation', ''),
            'signals': s.get('signals', []),
        }
    
    # === 第一步：持仓管理 - 决定是否卖出 ===
    for code, h in list(holdings.items()):
        info = price_map.get(code)
        if not info:
            continue
        
        # T+1 规则：今天买入的股票不能今天卖出
        buy_date = h.get('buy_date', '')
        if buy_date == today:
            continue
        
        current_price = info['price']
        cost = h['avg_cost']
        qty = h['qty']
        pnl_pct = (current_price - cost) / cost * 100
        
        sell_reason = None
        sell_type = 'sell'
        
        # 止损检查（亏损超8%）
        if pnl_pct < -8:
            sell_reason = f"止损卖出：当前亏损{pnl_pct:.1f}%，触及-8%止损线"
        
        # 止盈检查（盈利超15%分批止盈）
        elif pnl_pct > 15:
            sell_qty = qty // 2  # 先卖一半
            if sell_qty >= 100:
                decisions.append({
                    'action': 'sell',
                    'code': code,
                    'name': h['name'],
                    'qty': sell_qty,
                    'price': calc_slippage_price(current_price, False),
                    'reason': f"分批止盈：盈利{pnl_pct:.1f}%，卖出半仓锁定利润",
                    'type': 'sell',
                })
        
        # 评分大幅下降（从买入时下降20分以上）
        elif h.get('buy_score', 0) > 0 and info['score'] < h['buy_score'] - 20:
            sell_reason = f"评分下降：从{h['buy_score']}分降至{info['score']}分，趋势转弱"
        
        # 连续下跌信号
        elif '均线空头排列' in info.get('signals', []) and pnl_pct < -3:
            sell_reason = f"趋势转空：均线空头排列且亏损{pnl_pct:.1f}%"
        
        # 市场偏空且持仓亏损
        elif sentiment == '偏空' and avg_score < 45 and pnl_pct < -3:
            sell_reason = f"风险控制：市场偏空（{avg_score}分），亏损{pnl_pct:.1f}%，减仓避险"
        
        if sell_reason:
            decisions.append({
                'action': 'sell',
                'code': code,
                'name': h['name'],
                'qty': qty,
                'price': calc_slippage_price(current_price, False),
                'reason': sell_reason,
                'type': sell_type,
            })
    
    # === 第二步：日内回转已移除（T+1规则下不支持） ===
    
    # === 第三步：买入新股票 ===
    # 统计今天已经决定买入的次数（包括历史交易日志中的记录）
    buy_count_today = sum(1 for d in decisions if d['action'] == 'buy')
    # 从交易日志中加载今天已有的买入记录数量
    try:
        tl = load_json(os.path.join(DATA_DIR, 'trade_log.json'), {'trades': []})
        today_trades = [t for t in tl.get('trades', []) if t.get('timestamp', '').startswith(today) and t.get('type') == 'buy']
        already_bought_codes = set(t['code'] for t in today_trades)
        buy_count_today += len(today_trades)
    except:
        already_bought_codes = set()
    
    if buy_count_today < MAX_BUY_PER_DAY:
        # 市场环境判断
        should_buy = True
        if sentiment == '偏空' and avg_score < 40:
            should_buy = False  # 极端弱势不买
        
        if should_buy:
            # 收集候选股票（不重复持有）
            candidates = []
            
            # 强烈买入（高分优先）
            for s in recommendations.get('strong_buy', []):
                if s['code'] not in holding_codes and s['code'] not in [d['code'] for d in decisions] and s['code'] not in already_bought_codes:
                    est = s.get('next_day_estimate', {})
                    est_val = est.get('estimate', 0) if est else 0
                    candidates.append({
                        'code': s['code'],
                        'name': s['name'],
                        'price': s['price'],
                        'score': s['score'],
                        'est': est_val,
                        'signals': s.get('signals', []),
                        'priority': 1,
                    })
            
            # 建议买入
            for s in recommendations.get('buy', []):
                if s['code'] not in holding_codes and s['code'] not in [d['code'] for d in decisions] and s['code'] not in already_bought_codes:
                    est = s.get('next_day_estimate', {})
                    est_val = est.get('estimate', 0) if est else 0
                    candidates.append({
                        'code': s['code'],
                        'name': s['name'],
                        'price': s['price'],
                        'score': s['score'],
                        'est': est_val,
                        'signals': s.get('signals', []),
                        'priority': 2,
                    })
            
            # 值得关注中评分特别高的
            for s in recommendations.get('watch', []):
                if s['score'] >= 75 and s['code'] not in holding_codes and s['code'] not in [d['code'] for d in decisions] and s['code'] not in already_bought_codes:
                    candidates.append({
                        'code': s['code'],
                        'name': s['name'],
                        'price': s['price'],
                        'score': s['score'],
                        'est': 0,
                        'signals': s.get('signals', []),
                        'priority': 3,
                    })
            
            # 按优先级和评分排序
            candidates.sort(key=lambda x: (x['priority'], -x['score']))
            
            # 资金分配策略
            available_cash = portfolio['cash']
            remaining_slots = MAX_BUY_PER_DAY - buy_count_today
            
            # 分仓：每只股票用可用资金的 30-40%（分散风险）
            for c in candidates[:remaining_slots]:
                if available_cash < 5000:  # 至少留5000元
                    break
                
                # 根据评分调整仓位比例（仓位可以放大）
                if c['score'] >= 90:
                    ratio = 0.45
                elif c['score'] >= 75:
                    ratio = 0.35
                else:
                    ratio = 0.30
                
                alloc_cash = available_cash * ratio
                qty = get_buyable_amount(alloc_cash, c['price'])
                
                if qty < 100:
                    continue
                
                # 构建买入理由
                reasons = [f"评分{c['score']}分"]
                if c['priority'] == 1:
                    reasons.append("强烈买入推荐")
                elif c['priority'] == 2:
                    reasons.append("建议买入推荐")
                
                # 关键信号
                buy_signals = [sig for sig in c['signals'] if any(k in sig for k in ['金叉','超卖','放量上涨','多头','突破','低位','红柱','缩量企稳'])]
                if buy_signals:
                    reasons.append('、'.join(buy_signals[:3]))
                
                if c['est'] > 0:
                    reasons.append(f"明日预估+{c['est']:.1f}%")
                
                buy_price = calc_slippage_price(c['price'], True)
                actual_cost = buy_price * qty + calc_commission(buy_price, qty, 'buy')
                
                if actual_cost > available_cash:
                    # 调整数量
                    qty = get_buyable_amount(available_cash * 0.9, c['price'])
                    if qty < 100:
                        continue
                    buy_price = calc_slippage_price(c['price'], True)
                
                # 不立即买入，加入观察计划
                buy_plan.append({
                    'code': c['code'],
                    'name': c['name'],
                    'plan_qty': qty,
                    'plan_price': buy_price,
                    'target_price': c.get('buy_point', c['price']),
                    'score': c['score'],
                    'reason': '；'.join(reasons),
                    'est': c['est'],
                    'ratio': ratio,
                    'signals': c['signals'],
                    'priority': c['priority'],
                })
                
                available_cash -= buy_price * qty + calc_commission(buy_price, qty, 'buy')
    
    return decisions, buy_plan


def execute_trades(portfolio, decisions, all_stocks):
    """执行交易决策，更新持仓"""
    trades_executed = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    # ===== 交易时间校验 =====
    if not is_trading_time():
        print("\n  ⏰ 当前非交易时间，买卖指令仅记录为计划，不实际执行。")
        print(f"     交易时间: 周一至周五 9:30-11:30, 13:00-15:00")
        # 仍然记录卖出决策到 buy_plan 供开盘后 watcher 执行
        sell_plans = []
        for d in decisions:
            if d['action'] == 'sell':
                sell_plans.append({
                    'code': d['code'],
                    'name': d['name'],
                    'qty': d['qty'],
                    'price': d['price'],
                    'reason': d['reason'],
                    'type': 'sell',
                })
        if sell_plans:
            plan_file = os.path.join(DATA_DIR, 'sell_plan.json')
            with open(plan_file, 'w') as f:
                json.dump({'date': today, 'items': sell_plans, 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False, indent=2)
            print(f"  📋 已记录 {len(sell_plans)} 笔卖出计划到 sell_plan.json，开盘后由 watcher 执行。")
        return trades_executed
    
    # 构建价格查询
    price_map = {s['code']: s['price'] for s in all_stocks}
    
    for d in decisions:
        if d['action'] == 'sell':
            code = d['code']
            qty = d['qty']
            sell_price = d['price']
            h = portfolio['holdings'].get(code)
            
            if not h or h['qty'] < qty:
                continue
            
            # 执行卖出
            sell_amount = sell_price * qty
            commission = calc_commission(sell_price, qty, 'sell')
            net_amount = sell_amount - commission
            
            # 计算盈亏
            cost_amount = h['avg_cost'] * qty
            pnl = net_amount - cost_amount
            pnl_pct = (sell_price - h['avg_cost']) / h['avg_cost'] * 100
            
            portfolio['cash'] += net_amount
            h['qty'] -= qty
            
            # 如果全部卖出，移除持仓
            if h['qty'] <= 0:
                del portfolio['holdings'][code]
            
            # 记录交易
            trade = add_trade(
                d['type'], code, d['name'], sell_price, qty, d['reason'], portfolio,
                extra={'pnl': round(pnl, 2), 'pnl_pct': round(pnl_pct, 2), 'avg_cost': h.get('avg_cost', 0)}
            )
            trades_executed.append(trade)
            
            # 更新统计
            portfolio['trading_stats']['total_trades'] += 1
            portfolio['trading_stats']['total_pnl'] += pnl
            if pnl > 0:
                portfolio['trading_stats']['win_trades'] += 1
            if portfolio['trading_stats']['best_trade'] is None or pnl > portfolio['trading_stats']['best_trade']['pnl']:
                portfolio['trading_stats']['best_trade'] = {'code': code, 'name': d['name'], 'pnl': round(pnl, 2), 'pct': round(pnl_pct, 2)}
            if portfolio['trading_stats']['worst_trade'] is None or pnl < portfolio['trading_stats']['worst_trade']['pnl']:
                portfolio['trading_stats']['worst_trade'] = {'code': code, 'name': d['name'], 'pnl': round(pnl, 2), 'pct': round(pnl_pct, 2)}
        
        elif d['action'] == 'buy':
            code = d['code']
            qty = d['qty']
            buy_price = d['price']
            
            # 检查资金
            total_cost = buy_price * qty + calc_commission(buy_price, qty, 'buy')
            if total_cost > portfolio['cash']:
                continue
            
            # 执行买入
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
                info = price_map.get(code, {})
                portfolio['holdings'][code] = {
                    'name': d['name'],
                    'qty': qty,
                    'avg_cost': round(buy_price, 3),
                    'buy_date': today,
                    'buy_score': d.get('score', 0),
                    'signals': d.get('signals', []),
                    'current_price': buy_price,
                }
            
            # 记录交易
            trade = add_trade(
                d['type'], code, d['name'], buy_price, qty, d['reason'], portfolio,
                extra={'buy_score': d.get('score', 0)}
            )
            trades_executed.append(trade)
            
            portfolio['trading_stats']['total_trades'] += 1
    
    # 更新持仓当前价格
    for code, h in portfolio['holdings'].items():
        if code in price_map:
            h['current_price'] = price_map[code]
    
    # 更新最大回撤
    total_assets = calc_total_assets(portfolio)
    peak = max(portfolio.get('peak_assets', INITIAL_CAPITAL), total_assets)
    portfolio['peak_assets'] = peak
    drawdown = (peak - total_assets) / peak * 100
    if drawdown > portfolio['trading_stats']['max_drawdown']:
        portfolio['trading_stats']['max_drawdown'] = round(drawdown, 2)
    
    portfolio['last_trade_date'] = today
    
    save_portfolio(portfolio)
    return trades_executed


def generate_daily_report(portfolio, trades_executed, recommendations, all_stocks, macro_indices):
    """生成每日交易汇报"""
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    total_assets = calc_total_assets(portfolio)
    initial = portfolio.get('initial_capital', INITIAL_CAPITAL)
    total_return = (total_assets - initial) / initial * 100
    
    # 持仓盈亏
    holdings_pnl = []
    for code, h in portfolio['holdings'].items():
        current = h.get('current_price', h['avg_cost'])
        pnl = (current - h['avg_cost']) * h['qty']
        pnl_pct = (current - h['avg_cost']) / h['avg_cost'] * 100
        holdings_pnl.append({
            'code': code,
            'name': h['name'],
            'qty': h['qty'],
            'avg_cost': h['avg_cost'],
            'current_price': current,
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
        })
    
    holdings_pnl.sort(key=lambda x: x['pnl'], reverse=True)
    
    # 今日交易汇总
    buys = [t for t in trades_executed if t['type'] in ('buy', 'day_trade_buy')]
    sells = [t for t in trades_executed if t['type'] in ('sell', 'day_trade_sell')]
    today_pnl = sum(t.get('pnl', 0) for t in sells)
    
    # 后续操作计划
    plans = []
    for code, h in portfolio['holdings'].items():
        info = next((s for s in all_stocks if s['code'] == code), None)
        if not info:
            continue
        
        pnl_pct = (h['current_price'] - h['avg_cost']) / h['avg_cost'] * 100
        plan = f"{h['name']}（{code}）：成本{h['avg_cost']:.2f}，现价{h['current_price']:.2f}，{'盈利' if pnl_pct >= 0 else '亏损'}{abs(pnl_pct):.1f}%"
        
        if pnl_pct >= 15:
            plan += "。已到止盈区间，关注是否需要分批止盈。"
        elif pnl_pct < -5:
            plan += "。亏损较大，密切关注，若继续下跌至-8%将触发止损。"
        elif pnl_pct >= 5:
            plan += "。盈利中，继续持有等待目标价。"
        else:
            plan += "。浮盈/浮亏较小，继续观察。"
        
        plans.append(plan)
    
    report = {
        'date': today,
        'market_sentiment': recommendations.get('market_sentiment', ''),
        'market_score': recommendations.get('avg_score', 0),
        'total_assets': round(total_assets, 2),
        'total_return': round(total_return, 2),
        'cash': round(portfolio['cash'], 2),
        'position_value': round(total_assets - portfolio['cash'], 2),
        'position_ratio': round((total_assets - portfolio['cash']) / total_assets * 100, 1) if total_assets > 0 else 0,
        'today_pnl': round(today_pnl, 2),
        'trades_today': len(trades_executed),
        'buys': [{
            'code': t['code'],
            'name': t['name'],
            'price': t['price'],
            'qty': t['qty'],
            'amount': t['amount'],
            'reason': t['reason'],
        } for t in buys],
        'sells': [{
            'code': t['code'],
            'name': t['name'],
            'price': t['price'],
            'qty': t['qty'],
            'amount': t['amount'],
            'pnl': t.get('pnl', 0),
            'pnl_pct': t.get('pnl_pct', 0),
            'reason': t['reason'],
        } for t in sells],
        'holdings': holdings_pnl,
        'plans': plans,
        'stats': portfolio['trading_stats'],
    }
    
    # 保存日报
    portfolio['daily_reports'].append(report)
    # 只保留最近30天
    if len(portfolio['daily_reports']) > 30:
        portfolio['daily_reports'] = portfolio['daily_reports'][-30:]
    save_portfolio(portfolio)
    
    return report


def format_report_text(report):
    """格式化日报为文本"""
    lines = []
    lines.append("=" * 50)
    lines.append(f"  📊 虚拟炒股日报  |  {report['date']}")
    lines.append("=" * 50)
    
    # 账户概览
    ret_sign = '+' if report['total_return'] >= 0 else ''
    lines.append(f"\n💰 账户概览")
    lines.append(f"   总资产：{report['total_assets']:,.2f} 元")
    lines.append(f"   总收益率：{ret_sign}{report['total_return']:.2f}%")
    lines.append(f"   可用资金：{report['cash']:,.2f} 元")
    lines.append(f"   持仓市值：{report['position_value']:,.2f} 元（仓位{report['position_ratio']:.1f}%）")
    lines.append(f"   今日盈亏：{'+' if report['today_pnl'] >= 0 else ''}{report['today_pnl']:,.2f} 元")
    
    # 市场环境
    lines.append(f"\n🌡️ 市场环境：{report['market_sentiment']}（{report['market_score']}分）")
    
    # 今日交易
    if report['trades_today'] > 0:
        lines.append(f"\n📝 今日操作（共{report['trades_today']}笔）")
        
        if report['buys']:
            lines.append(f"   【买入】")
            for b in report['buys']:
                lines.append(f"   ✅ {b['name']}（{b['code']}）{b['qty']}股 × {b['price']:.2f}元 = {b['amount']:,.2f}元")
                lines.append(f"      原因：{b['reason']}")
        
        if report['sells']:
            lines.append(f"   【卖出】")
            for s in report['sells']:
                pnl_sign = '+' if s['pnl'] >= 0 else ''
                lines.append(f"   ❌ {s['name']}（{s['code']}）{s['qty']}股 × {s['price']:.2f}元 = {s['amount']:,.2f}元（{pnl_sign}{s['pnl']:,.2f}元 / {pnl_sign}{s['pnl_pct']:.1f}%）")
                lines.append(f"      原因：{s['reason']}")
    else:
        lines.append(f"\n📝 今日无操作（持仓观望）")
    
    # 当前持仓
    if report['holdings']:
        lines.append(f"\n📈 当前持仓（{len(report['holdings'])}只）")
        for h in report['holdings']:
            pnl_sign = '+' if h['pnl'] >= 0 else ''
            emoji = '🟢' if h['pnl'] >= 0 else '🔴'
            lines.append(f"   {emoji} {h['name']}（{h['code']}）{h['qty']}股")
            lines.append(f"      成本{h['avg_cost']:.2f} → 现价{h['current_price']:.2f}（{pnl_sign}{h['pnl_pct']:.1f}% / {pnl_sign}{h['pnl']:,.0f}元）")
    
    # 后续计划
    if report['plans']:
        lines.append(f"\n📋 后续操作计划")
        for p in report['plans']:
            lines.append(f"   • {p}")
    
    lines.append(f"\n{'=' * 50}")
    
    # 交易统计
    stats = report['stats']
    lines.append(f"  累计交易{stats['total_trades']}笔 | 胜率{(stats['win_trades']/max(1,stats['total_trades'])*100):.0f}% | 总盈亏{'+' if stats['total_pnl']>=0 else ''}{stats['total_pnl']:,.0f}元 | 最大回撤{stats['max_drawdown']:.1f}%")
    
    return '\n'.join(lines)


if __name__ == '__main__':
    # 测试
    data = load_portfolio()
    print(f"初始资金: {data['initial_capital']}")
    print(f"当前现金: {data['cash']}")
    print(f"持仓数量: {len(data['holdings'])}")
    print(f"交易记录验证: {verify_trade_log()}")
