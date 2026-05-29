#!/usr/bin/env python3
"""
收盘综合分析 v1.0
每个交易日15:00运行（收盘后），分析今日推荐股票表现，
验证预测准确度，给出操作建议，推荐明日3只股票。
"""

import json
import os
import sys
import traceback
import requests
from datetime import datetime, timedelta
from market_impact import (
    assess_us_impact, assess_commodity_impact, assess_fx_impact,
    assess_global_impact, build_impact_summary
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')

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


def fetch_realtime_price(codes):
    """批量获取实时/收盘价格"""
    result = {}
    try:
        r = _session.get(f"https://qt.gtimg.cn/q={','.join(codes)}", timeout=15)
        for line in r.text.strip().split(';'):
            if '~' not in line or '=' not in line:
                continue
            parts = line.split('~')
            if len(parts) < 50:
                continue
            code = parts[2]
            try:
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
                }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  获取实时价格失败: {e}")
    return result


def _fetch_us_indices_simple():
    """获取美股指数收盘数据（简化版，用于收盘分析）"""
    indices = {}
    try:
        codes = '.DJI,.IXIC,.INX'
        r = _session.get(f"https://hq.sinajs.cn/list={codes}", timeout=10)
        r.encoding = 'gbk'
        for line in r.text.strip().split('\n'):
            if '=' not in line or '"' not in line:
                continue
            name, data = line.split('=', 1)
            name = name.strip()
            data = data.strip().strip('"').split(',')
            if len(data) < 6 or not data[1]:
                continue
            try:
                price = float(data[1])
                prev_close = float(data[2])
                pct = (price - prev_close) / prev_close * 100
                code_map = {'.DJI': 'YM=F', '.IXIC': 'NQ=F', '.INX': 'ES=F'}
                indices[code_map.get(name, name)] = {
                    'name': data[0], 'code': name,
                    'price': price, 'change_pct': pct,
                }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  获取美股失败: {e}")
    return indices


def _fetch_commodities_simple():
    """获取大宗商品（简化版）"""
    commodities = {}
    try:
        codes = 'hf_GC,hf_CL,hf_SI'
        r = _session.get(f"https://hq.sinajs.cn/list={codes}", timeout=10)
        r.encoding = 'gbk'
        for line in r.text.strip().split('\n'):
            if '=' not in line or '"' not in line:
                continue
            name, data = line.split('=', 1)
            name = name.strip()
            data = data.strip().strip('"').split(',')
            if len(data) < 8 or not data[1]:
                continue
            try:
                price = float(data[1])
                prev_close = float(data[4]) if data[4] else price
                pct = (price - prev_close) / prev_close * 100 if prev_close else 0
                unit = '$' if 'GC' in name or 'SI' in name else '$'
                commodities[name] = {
                    'name': data[0], 'code': name,
                    'price': price, 'prev_close': prev_close,
                    'change_pct': pct, 'unit': unit,
                }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  获取商品失败: {e}")
    return commodities


def _fetch_fx_simple():
    """获取汇率（简化版）"""
    fx = {}
    try:
        codes = 'USDCNH,USDJPY'
        r = _session.get(f"https://hq.sinajs.cn/list={codes}", timeout=10)
        r.encoding = 'gbk'
        for line in r.text.strip().split('\n'):
            if '=' not in line or '"' not in line:
                continue
            name, data = line.split('=', 1)
            name = name.strip()
            data = data.strip().strip('"').split(',')
            if len(data) < 6 or not data[1]:
                continue
            try:
                price = float(data[1])
                prev_close = float(data[4]) if data[4] else price
                pct = (price - prev_close) / prev_close * 100 if prev_close else 0
                key = 'usdcnh' if 'CNH' in name else ('usdjpy' if 'JPY' in name else name.lower())
                fx[key] = {
                    'name': data[0], 'code': name,
                    'price': price, 'prev_close': prev_close,
                    'change_pct': pct,
                }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  获取汇率失败: {e}")
    return fx


def fetch_cn_indices():
    """获取A股收盘指数"""
    indices = {}
    codes = 'sh000001,sz399001,sz399006,sh000688,sh000300'
    try:
        r = _session.get(f"https://qt.gtimg.cn/q={codes}", timeout=10)
        for line in r.text.strip().split(';'):
            if '~' not in line:
                continue
            parts = line.split('~')
            if len(parts) < 50 or not parts[1]:
                continue
            code = parts[2]
            try:
                indices[code] = {
                    'name': parts[1], 'code': code,
                    'price': float(parts[3]), 'prev_close': float(parts[4]),
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'high': float(parts[33]), 'low': float(parts[34]),
                    'volume': float(parts[6]) if parts[6] else 0,
                }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  获取A股指数失败: {e}")
    return indices


def get_recommended_stocks():
    """从晨间和午间分析中提取所有推荐股票（去重）"""
    stocks = []
    seen = set()

    for fname in ['morning_analysis.json', 'midday_analysis.json']:
        data = _load_json(os.path.join(DATA_DIR, fname))
        if not data:
            continue
        for s in data.get('top_buys', []):
            code = s.get('code', '')
            if code and code not in seen:
                seen.add(code)
                s['_source'] = 'morning' if 'morning' in fname else 'midday'
                stocks.append(s)

    return stocks


def analyze_stock_performance(stock, realtime):
    """分析今日推荐股票表现，给出持仓管理建议（卖出/持有策略）"""
    code = stock.get('code', '')
    name = stock.get('name', '')
    source = stock.get('_source', '')

    rt = realtime.get(code, {})
    if not rt:
        return None

    predicted_chg = stock.get('change_pct', 0)
    actual_chg = rt.get('change_pct', 0)
    est = (stock.get('next_day_estimate') or {}).get('estimate', None)
    buy_point = stock.get('buy_point')
    target = stock.get('target_price')
    stop_loss = stock.get('stop_loss')

    prev_close = rt.get('prev_close', 0)
    actual_close = rt.get('price', 0)
    day_chg = (actual_close - prev_close) / prev_close * 100 if prev_close > 0 else 0

    # 判断买入点是否被触及
    buy_triggered = False
    buy_profit = None
    if buy_point and actual_close:
        low = rt.get('low', 0)
        if low <= buy_point:
            buy_triggered = True
            buy_profit = (actual_close - buy_point) / buy_point * 100

    # 止损是否触发
    stop_triggered = False
    if stop_loss and rt.get('low', 0) <= stop_loss:
        stop_triggered = True

    # 判断是否已持有（盘中触及买入点 = 假设已买入）
    held = buy_triggered

    # === 预测准确度评估 ===
    if est is not None:
        if est > 0 and day_chg > 0:
            verdict = '🟢 预测正确'
            icon = '✓'
        elif est < 0 and day_chg < 0:
            verdict = '🟢 预测正确'
            icon = '✓'
        elif est > 0 and day_chg > 0 and day_chg > est:
            verdict = '🔥 超出预期'
            icon = '🔥'
        elif abs(day_chg - est) < 1:
            verdict = '≈ 基本符合'
            icon = '≈'
        else:
            verdict = '🟡 预测偏差'
            icon = '≈'
    else:
        if day_chg > 1:
            verdict = '🟢 表现不错'
            icon = '✓'
        elif day_chg < -3:
            verdict = '🔴 表现较差'
            icon = '✗'
        else:
            verdict = '≈ 表现一般'
            icon = '≈'

    # === 持仓管理建议（核心修改：给出卖出/持有策略，而非买入建议）===
    if not held:
        # 未触及买入点，未建仓
        position_status = '未建仓'
        if day_chg > 0:
            position_advice = '今日未触及买入点，未建仓。明日可继续关注买入机会'
        elif day_chg < -3:
            position_advice = '今日下跌未建仓，规避了风险。明日可关注是否企稳后低吸'
        else:
            position_advice = '今日未触及买入点，走势平淡。明日继续观察'

        sell_strategy = None
        hold_conditions = None
    elif stop_triggered:
        # 已买入但触发止损
        position_status = '🔴 触发止损'
        loss_pct = round((rt.get('low', actual_close) - buy_point) / buy_point * 100, 2) if buy_point else 0
        position_advice = f'今日最低价触及止损位{stop_loss}元，亏损约{abs(loss_pct):.1f}%。应在触发时立即卖出止损，不抱幻想'

        sell_strategy = (
            f"📌 止损卖出策略：\n"
            f"  • 如果今天盘中未卖出，明日开盘立即卖出（不犹豫）\n"
            f"  • 卖出条件：明日开盘任何价格都卖出，不等待反弹\n"
            f"  • 如果明日继续大跌超过-5%，说明止损是正确的\n"
            f"  • 止损后该股暂时拉黑，至少3个交易日内不再考虑买入"
        )
        hold_conditions = "❌ 不建议继续持有，严格执行止损"
    elif buy_profit and buy_profit > 3:
        # 已买入且盈利较多
        position_status = f'🟢 盈利 +{buy_profit:.1f}%'
        position_advice = f'今日在买入点{buy_point}元附近建仓，收盘{actual_close}元，浮盈{buy_profit:.1f}%'

        sell_strategy = (
            f"📌 止盈卖出策略：\n"
            f"  • 第一目标：{target or round(actual_close * 1.03, 2)}元附近，到达后卖出1/2仓位\n"
            f"  • 第二目标：{round(actual_close * 1.05, 2)}元附近，卖出剩余仓位\n"
            f"  • 明日冲高回落时（涨超2%后回落1%以上）立即止盈\n"
            f"  • 保护利润：若明日低开超过-2%，先卖出1/3保护利润"
        )
        hold_conditions = (
            f"✅ 继续持有条件：\n"
            f"  • 明日继续上涨，未到目标价\n"
            f"  • 回调幅度不超过买入点的-1.5%\n"
            f"  • 量能未明显萎缩"
        )
    elif buy_profit and buy_profit > 0:
        # 已买入且小幅盈利
        position_status = f'🟢 微盈 +{buy_profit:.1f}%'
        position_advice = f'今日建仓，小幅浮盈{buy_profit:.1f}%，走势尚可'

        sell_strategy = (
            f"📌 卖出策略：\n"
            f"  • 短期目标：{target or round(actual_close * 1.03, 2)}元\n"
            f"  • 明日冲高到{round(actual_close * 1.02, 2)}元可考虑止盈\n"
            f"  • 若跌破买入点{buy_point}元，观察是否企稳，不企稳则止损"
        )
        hold_conditions = (
            f"✅ 继续持有条件：\n"
            f"  • 明日不跌破买入点{buy_point}元\n"
            f"  • 量能维持或放大"
        )
    elif buy_profit is not None and buy_profit <= -3:
        # 已买入且亏损较多（但未触发止损）
        position_status = f'🟡 亏损 {buy_profit:.1f}%'
        position_advice = f'今日建仓后下跌，浮亏{abs(buy_profit):.1f}%，需要关注止损'

        sell_strategy = (
            f"📌 止损卖出策略：\n"
            f"  • 若明日继续下跌至止损位{stop_loss}元，立即卖出\n"
            f"  • 若明日低开超过-3%，竞价阶段就考虑卖出\n"
            f"  • 最大亏损承受：-8%（绝对止损线）"
        )
        hold_conditions = (
            f"⚠️ 可持有条件（需同时满足）：\n"
            f"  • 明日企稳反弹，收盘价回到买入点{buy_point}元以上\n"
            f"  • 出现企稳信号（下影线、放量止跌）\n"
            f"  • 若明日继续阴跌，不建议死扛"
        )
    else:
        # 已买入但持平
        position_status = '➡️ 持平'
        position_advice = f'今日建仓，收盘{actual_close}元与买入点基本持平'

        sell_strategy = (
            f"📌 卖出策略：\n"
            f"  • 目标价：{target or round(actual_close * 1.03, 2)}元\n"
            f"  • 止损价：{stop_loss or round(buy_point * 0.95, 2)}元\n"
            f"  • 给2-3天时间观察，到期未达目标则离场"
        )
        hold_conditions = (
            f"✅ 继续持有条件：\n"
            f"  • 明日不跌破{stop_loss or round(buy_point * 0.95, 2)}元\n"
            f"  • 走势偏多，有上攻迹象"
        )

    return {
        'code': code,
        'name': name,
        'source': source,
        'morning_chg': stock.get('change_pct', 0),
        'close_price': actual_close,
        'day_chg': round(day_chg, 2),
        'high': rt.get('high', 0),
        'low': rt.get('low', 0),
        'volume': rt.get('volume', 0),
        'amount': rt.get('amount', 0),
        'buy_point': buy_point,
        'target_price': target,
        'stop_loss': stop_loss,
        'next_day_est': est,
        'buy_triggered': buy_triggered,
        'buy_profit': round(buy_profit, 2) if buy_profit else None,
        'stop_triggered': stop_triggered,
        'held': held,
        'verdict': verdict,
        'icon': icon,
        'position_status': position_status,
        'position_advice': position_advice,
        'sell_strategy': sell_strategy,
        'hold_conditions': hold_conditions,
    }


def load_top_buys_for_tomorrow():
    """收盘后筛选明日建议买入的3只股票
    策略：入口点买入，排除今天已推荐的（晨间+午间+尾盘）
    核心逻辑：
      1. 趋势信号强（均线多头/MACD金叉/放量）= 多日上涨潜力，要求>=2个
      2. 现价在买点附近或之下 = 还没拉升，有入场空间
      3. 今日涨幅不过大 = 不是追高，有持股空间
      4. 明日预估为正 = 短期趋势延续
      5. RSI未超买
      6. 风险收益比合理
    """
    rec_path = os.path.join(DATA_DIR, 'recommendations.json')
    rec_data = _load_json(rec_path)
    if not rec_data:
        return []

    # 排除今天已经推荐过的（晨间+午间+尾盘）
    excluded = set()
    for fname in ['morning_analysis.json', 'midday_analysis.json', 'eod_analysis.json']:
        data = _load_json(os.path.join(DATA_DIR, fname))
        for s in (data or {}).get('top_buys', []):
            excluded.add(s.get('code', ''))

    strong_buy = rec_data.get('strong_buy', [])
    buy_list = rec_data.get('buy', [])
    all_candidates = strong_buy + buy_list

    TREND_SIGNALS = {'均线多头排列', 'MA金叉', 'MACD金叉', '红柱放大', '放量'}
    CHASE_SIGNALS = {'涨停', '强势上涨', '触布林上轨', 'RSI偏高'}

    filtered = []
    for s in all_candidates:
        signals = set(s.get('signals', []))
        chg = s.get('change_pct', 0)
        est = (s.get('next_day_estimate') or {}).get('estimate', None)
        score = s.get('score', 0)
        code = s.get('code', '')
        price = s.get('price', 0)
        buy_point = s.get('buy_point', 0)
        ma5 = s.get('ma5', 0)
        rsi6 = s.get('rsi6', 0)
        rsi12 = s.get('rsi12', 0)

        if code in excluded:
            continue
        # 至少2个趋势信号
        trend_count = len(signals & TREND_SIGNALS)
        if trend_count < 2:
            continue
        if chg > 5:
            continue
        if est is None or est <= 0:
            continue
        if score < 75:
            continue
        # RSI不能过高
        if rsi6 > 75 or rsi12 > 75:
            continue
        if s.get('trend', '') == '下降':
            continue

        # 入口质量分
        entry_score = 0
        if ma5 > 0:
            price_vs_ma5 = (price - ma5) / ma5 * 100
            if -2 <= price_vs_ma5 <= 1:
                entry_score += 10
            elif -5 <= price_vs_ma5 < -2:
                entry_score += 6
            elif price_vs_ma5 > 1:
                entry_score += 2
            else:
                entry_score -= 3

        if buy_point > 0 and price > 0:
            if price <= buy_point * 1.01:
                entry_score += 8
            elif price <= buy_point * 1.03:
                entry_score += 4

        target = s.get('target_price', 0)
        stop = s.get('stop_loss', 0)
        if buy_point > 0 and stop > 0 and target > 0:
            rr = (target - buy_point) / (buy_point - stop)
            if rr >= 3:
                entry_score += 6
            elif rr >= 2:
                entry_score += 4
            elif rr >= 1.5:
                entry_score += 2

        entry_score += min(trend_count * 3, 12)

        chase_count = len(signals & CHASE_SIGNALS)
        entry_score -= chase_count * 4

        # RSI加分
        if 40 <= rsi6 <= 65:
            entry_score += 3
        elif 65 < rsi6 <= 75:
            entry_score += 1

        # 成交额
        amount = s.get('amount', 0)
        if amount >= 50000:
            entry_score += 2

        s['_entry_score'] = entry_score
        filtered.append(s)

    # 排序：入口质量 * 0.35 + 明日预估 * 10 * 0.35 + 评分 * 0.3
    def rank_key(s):
        entry = s.get('_entry_score', 0)
        score = s.get('score', 0)
        est = (s.get('next_day_estimate') or {}).get('estimate', 0)
        return entry * 0.35 + est * 10 * 0.35 + score * 0.3

    filtered.sort(key=rank_key, reverse=True)
    selected = filtered[:3]

    if len(selected) < 3:
        selected_codes = {s.get('code', '') for s in selected}
        for s in all_candidates:
            if s.get('code', '') in selected_codes or s.get('code', '') in excluded:
                continue
            est = (s.get('next_day_estimate') or {}).get('estimate', None)
            signals = set(s.get('signals', []))
            if est and est > 0 and s.get('score', 0) >= 65 and s.get('change_pct', 0) <= 5:
                if signals & TREND_SIGNALS:
                    selected.append(s)
            if len(selected) >= 3:
                break

    result = []
    for s in selected:
        signals = s.get('signals', [])
        reasons = []
        if s.get('score', 0) >= 95:
            reasons.append('收盘强劲')
        else:
            reasons.append('收盘稳健')
        trend_sigs = [x for x in signals if x in TREND_SIGNALS]
        if trend_sigs:
            reasons.append('、'.join(trend_sigs[:3]))
        est_val = (s.get('next_day_estimate') or {}).get('estimate', 0)
        if est_val >= 3:
            reasons.append('明日高预期')
        result.append({
            'code': s.get('code', ''), 'name': s.get('name', ''),
            'score': s.get('score', 0), 'price': s.get('price', 0),
            'change_pct': s.get('change_pct', 0),
            'buy_point': s.get('buy_point'),
            'buy_time': '明日开盘买入 (9:30-10:00)',
            'stop_loss': s.get('stop_loss'), 'target_price': s.get('target_price'),
            'signals': signals,
            'next_day_estimate': s.get('next_day_estimate', {}),
            'entry_score': s.get('_entry_score', 0),
            'reason': '，'.join(reasons) if reasons else '趋势信号确认',
        })
    return result


def generate_summary(perfs, cn_indices):
    """生成收盘总结"""
    lines = []

    # 大盘概况
    sh = cn_indices.get('000001', {})
    if sh:
        sh_chg = sh.get('change_pct', 0)
        if sh_chg > 1:
            lines.append(f"✅ 大盘强势，上证收涨{sh_chg:+.2f}%，做多氛围良好")
        elif sh_chg > 0:
            lines.append(f"➡️ 大盘小幅收涨{sh_chg:+.2f}%，整体平稳")
        elif sh_chg > -1:
            lines.append(f"➡️ 大盘小幅收跌{abs(sh_chg):.2f}%，震荡整理")
        else:
            lines.append(f"⚠️ 大盘收跌{abs(sh_chg):.2f}%，市场偏弱")

    # 涨跌家数
    if sh.get('volume'):
        # 用全市场数据
        all_stocks = _load_json(os.path.join(DATA_DIR, 'all_stocks.json'), {}).get('stocks', [])
        if all_stocks:
            total = len(all_stocks)
            rise = sum(1 for s in all_stocks if s.get('change_pct', 0) > 0)
            zt = sum(1 for s in all_stocks if s.get('change_pct', 0) >= 9.8)
            dt = sum(1 for s in all_stocks if s.get('change_pct', 0) <= -9.8)
            lines.append(f"全市场{total}只，上涨{rise}只({rise/total*100:.0f}%)，涨停{zt}只，跌停{dt}只")

    # 推荐股票表现汇总
    if perfs:
        correct = sum(1 for p in perfs if p and p['icon'] in ('✓', '🔥'))
        wrong = sum(1 for p in perfs if p and p['icon'] == '✗')
        held = sum(1 for p in perfs if p.get('held', False))
        total = len(perfs)

        parts = []
        if held > 0:
            parts.append(f"{held}只触及买入点已建仓")
        if correct > total / 2:
            parts.append(f"预测方向正确率{correct/total*100:.0f}%")
        elif wrong > 0:
            parts.append(f"{wrong}只预测偏差")

        lines.append(f"📊 今日推荐{total}只，{'，'.join(parts)}")

        # 持仓盈亏汇总
        if held > 0:
            held_profits = [p['buy_profit'] for p in perfs if p.get('held') and p.get('buy_profit') is not None]
            if held_profits:
                profit_stocks = sum(1 for x in held_profits if x > 0)
                loss_stocks = sum(1 for x in held_profits if x <= 0)
                total_pnl = sum(held_profits)
                pnl_sign = '+' if total_pnl >= 0 else ''
                lines.append(f"💼 建仓{held}只：{profit_stocks}只盈利/{loss_stocks}只亏损，合计浮盈{pnl_sign}{total_pnl:.1f}%")

    return '\n'.join(lines)


def assess_tomorrow_risk(cn_indices, perfs, us_impact=None):
    """评估明日风险"""
    risk_score = 50

    # 基于今日大盘表现
    sh = cn_indices.get('000001', {})
    if sh:
        chg = sh.get('change_pct', 0)
        if chg > 1:
            risk_score -= 10
        elif chg < -1.5:
            risk_score += 15

    # 基于推荐股票表现
    if perfs:
        avg_chg = sum(p['day_chg'] for p in perfs) / len(perfs)
        if avg_chg < -2:
            risk_score += 10

    # 美股隔夜期货（收盘后美股期货预示明日氛围）
    if us_impact:
        us_dir = us_impact.get('direction', '')
        us_level = us_impact.get('level', 'low')
        if '利空' in us_dir and us_level == 'high':
            risk_score += 10
        elif '利空' in us_dir and us_level == 'medium':
            risk_score += 5
        elif '利好' in us_dir and us_level == 'high':
            risk_score -= 5

    risk_score = max(0, min(100, risk_score))

    risk_level = risk_score >= 70 and '高' or risk_score >= 55 and '中高' or risk_score >= 40 and '中低' or '低'

    # 明日策略
    strategy_lines = []
    if risk_score >= 70:
        strategy_lines.append("🔴 高风险环境，控制仓位")
        strategy_lines.append("不追涨，不抄底，观望为主")
    elif risk_score >= 55:
        strategy_lines.append("🟡 中高风险，谨慎操作")
        strategy_lines.append("优先关注已持仓股票，不轻易开新仓")
    elif risk_score >= 40:
        strategy_lines.append("🟢 中性环境，可适度参与")
        strategy_lines.append("关注强势股回调机会，设好止损")
    else:
        strategy_lines.append("🟢 低风险，可积极操作")
        strategy_lines.append("关注明日推荐股票的买入机会")

    # 操作规则
    strategy_lines.append("\n📌 明日操作规则：")
    strategy_lines.append("• 买入严格按建议买入价执行，不追高")
    strategy_lines.append("• 止损触发立即卖出，不犹豫")
    strategy_lines.append("• 达到目标价分批止盈（先卖一半）")
    strategy_lines.append("• 单票仓位不超过总资金30%")

    return {
        'risk_score': risk_score,
        'risk_level': risk_level,
        'strategy_text': '\n'.join(strategy_lines),
    }


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("=" * 60)
    print(f"  📊 收盘综合分析  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取推荐股票
    print("  [1/5] 获取今日推荐股票...")
    recommended = get_recommended_stocks()
    print(f"  找到 {len(recommended)} 只推荐股票")

    if not recommended:
        print("  ⚠️ 未找到推荐股票，跳过分析")
        return

    # 2. 获取实时/收盘价格
    print("  [2/5] 获取收盘数据...")
    codes = [s['code'] for s in recommended]
    # 确保code格式正确（腾讯API需要sh/sz前缀）
    qt_codes = []
    for c in codes:
        if c.startswith('6'):
            qt_codes.append(f'sh{c}')
        else:
            qt_codes.append(f'sz{c}')
    realtime = fetch_realtime_price(qt_codes)

    # 3. 分析每只股票
    print("  [3/5] 分析股票表现...")
    performances = []
    for stock in recommended:
        perf = analyze_stock_performance(stock, realtime)
        if perf:
            performances.append(perf)
            pos = perf['position_status']
            print(f"  {perf['name']}: 收盘{perf['close_price']:.2f} ({perf['day_chg']:+.2f}%) {perf['verdict']} [{pos}]")

    # 4. 获取大盘收盘数据
    print("  [4/6] 获取大盘数据...")
    cn_indices = fetch_cn_indices()

    # 4.5 获取收盘外围数据（美股日内期货/商品最新）
    print("  [4.5/6] 获取收盘外围数据...")
    us_indices = _fetch_us_indices_simple()
    commodities = _fetch_commodities_simple()
    fx = _fetch_fx_simple()
    global_indices = {}  # 收盘后亚太已收盘，意义不大
    us_impact = assess_us_impact(us_indices)
    commodity_impact = assess_commodity_impact(commodities)
    fx_impact = assess_fx_impact(fx)
    global_impact = assess_global_impact(global_indices)

    # 5. 生成分析
    print("  [5/6] 生成收盘分析...")
    summary = generate_summary(performances, cn_indices)
    impact_summary = build_impact_summary(us_impact, commodity_impact, fx_impact, global_impact)
    tomorrow_risk = assess_tomorrow_risk(cn_indices, performances, us_impact)
    tomorrow_buys = load_top_buys_for_tomorrow()

    analysis = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'cn_indices': cn_indices,
        'us_indices': us_indices,
        'commodities': commodities,
        'fx': fx,
        'us_impact': us_impact,
        'commodity_impact': commodity_impact,
        'fx_impact': fx_impact,
        'global_impact': global_impact,
        'impact_summary': impact_summary,
        'performances': performances,
        'summary': summary,
        'tomorrow_risk': tomorrow_risk,
        'tomorrow_buys': tomorrow_buys,
    }

    _save_json(os.path.join(DATA_DIR, 'closing_analysis.json'), analysis)

    # 6. 回填历史推荐数据（更新所有待计算的次日表现和预测验证）
    print("  [6/6] 回填历史推荐数据...")
    try:
        import subprocess
        backfill_script = os.path.join(SCRIPT_DIR, 'backfill_history.py')
        if os.path.exists(backfill_script):
            result = subprocess.run(
                [sys.executable, backfill_script],
                capture_output=True, text=True, timeout=180,
                cwd=SCRIPT_DIR
            )
            if result.returncode == 0:
                # 只打印最后几行摘要
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines[-5:]:
                    print(f"  {line}")
            else:
                print(f"  ⚠️ 回填失败: {result.stderr[:200]}")
        else:
            print("  ⚠️ backfill_history.py 不存在")
    except Exception as e:
        print(f"  ⚠️ 回填异常: {e}")

    print(f"\n  📊 明日风险评分: {tomorrow_risk['risk_score']}/100 ({tomorrow_risk['risk_level']})")
    print(f"  📈 明日建议买入: {len(tomorrow_buys)} 只")
    for s in tomorrow_buys:
        est = s.get('next_day_estimate', {}).get('estimate', 0)
        print(f"    {s['name']}({s['code']}) 评分{s['score']} 今日{s['change_pct']:+.2f}% 明日预估{est:+.1f}%")
    # 打印外围影响
    if impact_summary:
        for line in impact_summary.split('\n')[:6]:
            print(f"  {line}")

    # 6.5 生成明日综合买入策略（基于收盘后的外围数据）
    print("  [6.5] 生成明日综合买入策略...")
    try:
        from comprehensive_strategy import generate_comprehensive_buy_strategy
        tomorrow_morning_data = {
            'us_impact': us_impact,
            'commodity_impact': commodity_impact,
            'fx_impact': fx_impact,
            'global_impact': global_impact,
            'strategy': {'risk_score': tomorrow_risk['risk_score']},
            'top_buys': tomorrow_buys,
            'impact_summary': impact_summary,
        }
        comprehensive = generate_comprehensive_buy_strategy(tomorrow_morning_data)
        comprehensive['source'] = 'closing_preview'
        comprehensive['source_desc'] = '基于收盘后外围数据预生成的明日策略'
        _save_json(os.path.join(DATA_DIR, 'comprehensive_strategy.json'), comprehensive)
        print(f"  📊 明日操作模式: {comprehensive['operation_mode']['name']}")
        print(f"  📊 明日开盘预测: {comprehensive['open_forecast']['description']}")
    except Exception as e:
        print(f"  ⚠️ 明日综合策略生成失败: {e}")

    print(f"\n  ✅ 收盘分析完成！")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 收盘分析失败: {e}")
        traceback.print_exc()
        sys.exit(1)
