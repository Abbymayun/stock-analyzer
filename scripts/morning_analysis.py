#!/usr/bin/env python3
"""
晨间综合分析系统 v1.0
每日早上8:00-8:30运行，分析美股隔夜行情、全球宏观因素对A股的影响，
结合昨日A股表现，给出当日操作建议。
"""

import json
import os
import sys
import time
from market_impact import (
    assess_us_impact, assess_commodity_impact, assess_fx_impact,
    assess_global_impact, build_impact_summary
)
import requests
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

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


def fetch_us_indices():
    """获取美股三大指数收盘数据"""
    indices = {}
    # 新浪API（美股返回格式：name,price,change,pct — 仅4个字段）
    codes = {
        'int_dji': '道琼斯',
        'int_nasdaq': '纳斯达克',
        'int_sp500': '标普500',
    }
    for code, name in codes.items():
        try:
            r = _session.get(f"http://hq.sinajs.cn/list={code}", timeout=10,
                           headers={'Referer': 'https://finance.sina.com.cn'})
            r.encoding = 'gbk'
            text = r.text.strip()
            if text and '=' in text and '"' in text:
                data = text.split('"')[1].split(',')
                price = float(data[1]) if len(data) > 1 else 0
                # 新浪美股格式：name,price,change,pct (4字段)
                # 或 name,price,change,pct,_,prev_close,... (6+字段)
                if len(data) >= 6:
                    prev = float(data[5]) if data[5] else 0
                    pct = round((price - prev) / prev * 100, 2) if prev > 0 else 0
                elif len(data) >= 4:
                    pct = float(data[3]) if data[3] else 0
                    prev = round(price / (1 + pct / 100), 2) if pct != 0 else price
                else:
                    continue
                if abs(pct) < 50:
                    indices[code] = {
                        'name': name,
                        'price': round(price, 2),
                        'prev_close': round(prev, 2),
                        'change_pct': pct,
                    }
        except Exception as e:
            print(f"  获取 {name} 失败: {e}")
    return indices


def fetch_us_bond_yield():
    """获取美债收益率数据"""
    try:
        # 通过新浪获取美债收益率
        r = _session.get("https://hq.sinajs.cn/list=GCN0Y", timeout=10,
                        headers={'Referer': 'https://finance.sina.com.cn'})
        r.encoding = 'gbk'
        text = r.text.strip()
        if text and '=' in text and '"' in text:
            data = text.split('"')[1].split(',')
            if len(data) >= 4:
                return {
                    '10y_yield': data[0],
                    'change': data[1],
                }
    except:
        pass
    return {}


def fetch_commodities():
    """获取大宗商品数据"""
    commodities = {}
    # 新浪期货格式: price,_,_,_,high,low,time,prev_close,open,_,_,_,date,name,_
    codes = {
        'hf_GC': ('COMEX黄金', '美元/盎司'),
        'hf_CL': ('WTI原油', '美元/桶'),
        'hf_SI': ('COMEX白银', '美元/盎司'),
    }
    for code, (name, unit) in codes.items():
        try:
            r = _session.get(f"https://hq.sinajs.cn/list={code}", timeout=10,
                           headers={'Referer': 'https://finance.sina.com.cn'})
            r.encoding = 'gbk'
            text = r.text.strip()
            if text and '=' in text and '"' in text:
                data = text.split('"')[1].split(',')
                if len(data) >= 8 and data[0]:
                    price = float(data[0])
                    prev = float(data[7]) if data[7] else 0
                    if prev > 0:
                        pct = round((price - prev) / prev * 100, 2)
                        commodities[code] = {
                            'name': name,
                            'unit': unit,
                            'price': round(price, 2),
                            'prev_close': round(prev, 2),
                            'change_pct': pct,
                        }
        except Exception as e:
            print(f"  获取 {name} 失败: {e}")
    return commodities


def fetch_fx():
    """获取汇率数据"""
    fx = {}
    # 新浪格式: time,price,open,high,low,volume,prev_close,prev_close2,price2,name,...
    try:
        r = _session.get("https://hq.sinajs.cn/list=fx_susdcnh", timeout=10,
                        headers={'Referer': 'https://finance.sina.com.cn'})
        r.encoding = 'gbk'
        for line in r.text.strip().split(';'):
            if '=' not in line or '"' not in line:
                continue
            data = line.split('"')[1].split(',')
            if len(data) >= 8:
                price = float(data[8])
                prev = float(data[7])
                pct = round((price - prev) / prev * 100, 2) if prev > 0 else 0
                if abs(pct) < 50:
                    fx['usdcnh'] = {
                        'name': '美元/离岸人民币',
                        'price': price,
                        'prev_close': prev,
                        'change_pct': pct,
                    }
    except Exception as e:
        print(f"  获取汇率失败: {e}")
    return fx


def fetch_global_indices():
    """获取全球主要指数"""
    indices = {}
    # 新浪API格式: code,name,price,prev_close,open,high,low,change,pct%,...
    codes = {
        'hkHSI': '恒生指数',
        'ukFTSE': '英国富时100',
        'deDAX': '德国DAX30',
        'jpN225': '日经225',
    }
    for code, name in codes.items():
        try:
            r = _session.get(f"http://hq.sinajs.cn/list={code}", timeout=10,
                           headers={'Referer': 'https://finance.sina.com.cn'})
            r.encoding = 'gbk'
            text = r.text.strip()
            if text and '=' in text and '"' in text:
                data = text.split('"')[1].split(',')
                if len(data) >= 9:
                    price = float(data[2])
                    prev = float(data[3]) if float(data[3]) > 0 else price
                    pct = round((price - prev) / prev * 100, 2) if prev > 0 else 0
                    if abs(pct) < 50:
                        indices[code] = {
                            'name': name,
                            'price': round(price, 2),
                            'prev_close': round(prev, 2),
                            'change_pct': pct,
                        }
        except Exception as e:
            print(f"  获取 {name} 失败: {e}")

    return indices


def fetch_cn_indices():
    """获取A股主要指数（盘前可能有昨日数据）"""
    indices = {}
    codes = 'sh000001,sz399001,sz399006,sh000688,sh000300'
    try:
        r = _session.get(f"https://qt.gtimg.cn/q={codes}", timeout=10)
        lines = [l for l in r.text.strip().split(';') if l.strip() and '~' in l and '=' in l]
        for line in lines:
            parts = line.split('~')
            if len(parts) < 50: continue
            code = parts[2]
            name = parts[1]
            if not name: continue
            try:
                indices[code] = {
                    'name': name,
                    'code': code,
                    'price': float(parts[3]) if parts[3] else 0,
                    'prev_close': float(parts[4]) if parts[4] else 0,
                    'change_pct': float(parts[32]) if parts[32] else 0,
                }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  获取A股指数失败: {e}")
    return indices


def load_yesterday_data():
    """加载昨日分析数据"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    history_dir = os.path.join(DATA_DIR, 'history')
    if not os.path.exists(history_dir):
        return None

    # 找昨天的最新文件
    yesterday_files = [f for f in os.listdir(history_dir) if f.startswith(yesterday) and f.endswith('.json')]
    if not yesterday_files:
        return None

    yesterday_files.sort(reverse=True)
    filepath = os.path.join(history_dir, yesterday_files[0])
    return _load_json(filepath)



import traceback

def generate_strategy(yesterday_data, us_impact, commodity_impact, fx_impact, global_impact):
    """综合所有因素生成当日操作策略"""
    lines = []

    # 综合风险评分 (0-100, 越高风险越大)
    risk_score = 50  # 基准

    # 1. 美股影响
    if us_impact['level'] == 'high':
        risk_score += 20 if '利空' in us_impact['direction'] else -10
    elif us_impact['level'] == 'medium':
        risk_score += 10 if '利空' in us_impact['direction'] else -5

    # 2. 商品影响（金价大跌=避险情绪，油价大涨=通胀压力）
    gold = commodity_impact.get('detail', '')
    if '金价大跌' in gold:
        risk_score -= 5
    if '油价飙升' in gold:
        risk_score += 10

    # 3. 汇率
    if '人民币贬值' in fx_impact.get('summary', ''):
        risk_score += 10
    elif '人民币走强' in fx_impact.get('summary', ''):
        risk_score -= 5

    # 4. 昨日A股表现
    if yesterday_data:
        yesterday_sentiment = yesterday_data.get('market_sentiment', '中性')
        yesterday_score = yesterday_data.get('avg_score', 50)

        if yesterday_sentiment == '偏空' or yesterday_score < 45:
            risk_score += 10
            lines.append("⚠️ 昨日A股偏弱，市场情绪低迷，短期可能延续调整")
        elif yesterday_sentiment == '偏多' and yesterday_score > 55:
            risk_score -= 10
            lines.append("✅ 昨日A股偏强，市场情绪较好，有望延续")

        # 昨日涨停股质量 - 重点防追涨
        recs = yesterday_data.get('recommendations', {})
        strong_buy_yesterday = recs.get('strong_buy', [])
        if strong_buy_yesterday:
            high_chase = [s for s in strong_buy_yesterday if s.get('change_pct', 0) > 5]
            if high_chase:
                risk_score += 15
                lines.append(f"⚠️ 昨日有{len(high_chase)}只强烈推荐股涨幅超5%，今日追高风险大")
                for s in high_chase[:3]:
                    lines.append(f"   · {s.get('name','')}({s.get('code','')}) 昨涨{s.get('change_pct',0):.1f}%，今日不追")

    risk_score = max(0, min(100, risk_score))

    # 根据风险评分生成策略
    if risk_score >= 70:
        lines.append("\n🔴 【当日总体策略】高风险环境")
        lines.append("  建议：空仓或极低仓位（≤2成），以观望为主")
        lines.append("  操作：不追涨、不抄底、不加仓")
        lines.append("  关注：避险板块（黄金、国债ETF）和低位超跌反弹机会")
    elif risk_score >= 55:
        lines.append("\n🟡 【当日总体策略】中高风险环境")
        lines.append("  建议：低仓位运行（2-4成），严格执行止损")
        lines.append("  操作：只做确定性高的低吸机会，避免追高")
        lines.append("  禁止：不追当天涨幅超3%的股票")
    elif risk_score >= 40:
        lines.append("\n🟢 【当日总体策略】中性环境")
        lines.append("  建议：中等仓位（4-6成），精选个股")
        lines.append("  操作：关注技术面信号明确的标的，分批建仓")
        lines.append("  策略：回调低吸为主，突破追涨为辅")
    else:
        lines.append("\n🟢 【当日总体策略】低风险环境")
        lines.append("  建议：可适度积极（5-7成），把握机会")
        lines.append("  操作：关注强势板块龙头和突破信号")
        lines.append("  策略：积极参与，但单票仓位不超过3成")

    # 仓位建议
    position_map = {range(0, 30): '≤2成', range(30, 45): '2-4成', range(45, 60): '4-6成'}
    for r, pos in position_map.items():
        if risk_score in r:
            lines.append(f"\n  📊 建议仓位：{pos} | 风险评分：{risk_score}/100")
            break
    else:
        if risk_score >= 60:
            lines.append(f"\n  📊 建议仓位：≤2成 | 风险评分：{risk_score}/100")
        else:
            lines.append(f"\n  📊 建议仓位：5-7成 | 风险评分：{risk_score}/100")

    # 过滤器建议
    lines.append("\n  🚫 当日买入过滤规则：")
    lines.append("  • 今天涨幅 > 5% 的股票不买（追高风险）")
    lines.append("  • 昨天涨停的股票今天不追（获利盘抛压）")
    lines.append("  • 评分 < 50 的股票不考虑买入")
    lines.append("  • 买入价格必须低于MA5（回调买入，不追高）")
    lines.append("  • 单票仓位不超过总资金的30%")

    return {
        'risk_score': risk_score,
        'strategy_text': '\n'.join(lines),
        'position_advice': {
            'max': 0.7 if risk_score < 40 else (0.4 if risk_score < 55 else 0.2),
            'single_max': 0.3,
        },
    }


def format_report(analysis):
    """格式化分析报告供前端展示"""
    lines = []

    # 美股
    lines.append("## 🇺🇸 美股隔夜行情")
    if analysis.get('us_indices'):
        for code, info in analysis['us_indices'].items():
            emoji = '📈' if info['change_pct'] >= 0 else '📉'
            color = 'rise' if info['change_pct'] >= 0 else 'fall'
            lines.append(f"  {emoji} **{info['name']}**: {info['price']:.2f} (<span class='{color}'>{info['change_pct']:+.2f}%</span>)")
    else:
        lines.append("  暂无数据")

    # 美债收益率
    if analysis.get('bond_yield'):
        lines.append(f"\n  🏦 10年期美债收益率: {analysis['bond_yield'].get('10y_yield', '-')}")

    # 大宗商品 + 汇率 + 全球
    for section_key, section_title, unit_key in [
        ('commodities', '📦 大宗商品', 'unit'),
        ('fx', '💱 汇率', None),
        ('global_indices', '🌏 亚太/欧洲市场', None),
    ]:
        data = analysis.get(section_key, {})
        impact_key = section_key.replace('_indices', '_impact')
        if section_key == 'commodities':
            impact_key = 'commodity_impact'
        lines.append(f"\n## {section_title}")
        if data:
            for code, info in data.items():
                emoji = '📈' if info['change_pct'] >= 0 else '📉'
                color = 'rise' if info['change_pct'] >= 0 else 'fall'
                if unit_key:
                    lines.append(f"  {emoji} **{info['name']}**: {info['price']:.2f} {info.get(unit_key, '')} (<span class='{color}'>{info['change_pct']:+.2f}%</span>)")
                elif section_key == 'fx':
                    lines.append(f"  {emoji} **{info['name']}**: {info['price']:.4f} (<span class='{color}'>{info['change_pct']:+.2f}%</span>)")
                else:
                    lines.append(f"  {emoji} **{info['name']}**: {info['price']:.2f} (<span class='{color}'>{info['change_pct']:+.2f}%</span>)")
            impact = analysis.get(impact_key, {})
            if impact.get('summary'):
                lines.append(f"\n**对A股影响**: {impact['summary']}")
        else:
            lines.append("  暂无数据")

    # 外围综合影响总结
    impact_summary = analysis.get('impact_summary', '')
    if impact_summary:
        lines.append("\n## 🌐 外围综合影响")
        for line in impact_summary.split('\n'):
            if line.strip():
                lines.append(line)

    return '\n'.join(lines)


def format_strategy_text(analysis):
    """格式化策略文本供前端展示"""
    strategy = analysis.get('strategy', {})
    text = strategy.get('strategy_text', '')
    return text.replace('\n', '<br>').replace('**', '')


def load_top_buys():
    """晨间推荐：选出适合开盘立即买入并持有的股票
    策略：入口点买入，不追涨。选趋势强但尚未过度拉升的标的。
    核心逻辑：
      1. 趋势信号强（均线多头/MACD金叉/放量）= 多日上涨潜力，要求>=2个信号
      2. 现价在买点附近或买点之下 = 还没拉升，有入场空间
      3. 昨日涨幅不过大 = 不是追高，有持股空间
      4. 明日预估为正 = 短期趋势延续
      5. RSI未超买 = 还没到顶部
      6. 风险收益比合理 = 值得入场
    """
    rec_path = os.path.join(DATA_DIR, 'recommendations.json')
    rec_data = _load_json(rec_path)
    if not rec_data:
        return []

    strong_buy = rec_data.get('strong_buy', [])
    buy_list = rec_data.get('buy', [])
    all_candidates = strong_buy + buy_list

    # 趋势信号评分（多日持股的依据）- 要求至少2个
    TREND_SIGNALS = {'均线多头排列', 'MA金叉', 'MACD金叉', '红柱放大', '放量'}
    # 追高风险信号
    CHASE_SIGNALS = {'涨停', '强势上涨', '触布林上轨', 'RSI偏高'}

    filtered = []
    for s in all_candidates:
        signals = set(s.get('signals', []))
        chg = s.get('change_pct', 0)
        est = (s.get('next_day_estimate') or {}).get('estimate', None)
        score = s.get('score', 0)
        price = s.get('price', 0)
        buy_point = s.get('buy_point', 0)
        ma5 = s.get('ma5', 0)
        rsi6 = s.get('rsi6', 0)
        rsi12 = s.get('rsi12', 0)

        # 至少2个趋势信号（更强的趋势确认）
        trend_count = len(signals & TREND_SIGNALS)
        if trend_count < 2:
            continue
        # 昨日涨幅不超过5%（超过的追高风险大）
        if chg > 5:
            continue
        # 明日预估为正
        if est is None or est <= 0:
            continue
        # 评分 >= 75（提高门槛）
        if score < 75:
            continue
        # RSI不能过高（>75说明已经超买区域）
        if rsi6 > 75 or rsi12 > 75:
            continue
        # 趋势必须是上升
        if s.get('trend', '') == '下降':
            continue

        # 计算入口质量分
        entry_score = 0
        # 现价在MA5附近或之下（回调到均线买入，不是追高）
        if ma5 > 0:
            price_vs_ma5 = (price - ma5) / ma5 * 100
            if -2 <= price_vs_ma5 <= 1:
                entry_score += 10  # 刚好在MA5附近，最佳入场
            elif -5 <= price_vs_ma5 < -2:
                entry_score += 6   # 略低于MA5，回调整理中
            elif price_vs_ma5 > 1:
                entry_score += 2   # 远离MA5，追高风险
            else:
                entry_score -= 3  # 大幅低于MA5，趋势可能破位

        # 有明确的买点且价格接近或低于买点
        if buy_point > 0 and price > 0:
            if price <= buy_point * 1.01:
                entry_score += 8  # 还在买点之下，入场空间大
            elif price <= buy_point * 1.03:
                entry_score += 4  # 略高于买点，可接受

        # 风险/收益比（要求>=2才加分）
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
            # rr < 1.5 不加分（风险收益比不好）

        # 趋势信号越多越好
        entry_score += min(trend_count * 3, 12)

        # 追高风险扣分
        chase_count = len(signals & CHASE_SIGNALS)
        entry_score -= chase_count * 4  # 加重扣分

        # RSI在40-65区间加分（健康的多头区间）
        if 40 <= rsi6 <= 65:
            entry_score += 3
        elif 65 < rsi6 <= 75:
            entry_score += 1  # 偏高但没超买

        # 成交额加分（流动性好）
        amount = s.get('amount', 0)
        if amount >= 50000:  # 5万以上
            entry_score += 2

        s['_entry_score'] = entry_score
        filtered.append(s)

    # 综合排序：入口质量分 * 0.45 + 评分 * 0.25 + 明日预估 * 8 * 0.3
    def rank_key(s):
        entry = s.get('_entry_score', 0)
        score = s.get('score', 0)
        est = (s.get('next_day_estimate') or {}).get('estimate', 0)
        return entry * 0.45 + score * 0.25 + est * 8 * 0.3

    filtered.sort(key=rank_key, reverse=True)
    selected = filtered[:3]

    # 不够3只时放宽：评分>=65且明日预估>0且至少1个趋势信号
    if len(selected) < 3:
        selected_codes = {s.get('code', '') for s in selected}
        for s in all_candidates:
            if s.get('code', '') in selected_codes:
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
        entry = s.get('_entry_score', 0)
        result.append({
            'code': s.get('code', ''),
            'name': s.get('name', ''),
            'score': s.get('score', 0),
            'price': s.get('price', 0),
            'change_pct': s.get('change_pct', 0),
            'buy_point': s.get('buy_point'),
            'buy_time': s.get('buy_time', '开盘30分钟内 (9:30-10:00)'),
            'stop_loss': s.get('stop_loss'),
            'target_price': s.get('target_price'),
            'signals': s.get('signals', []),
            'next_day_estimate': s.get('next_day_estimate', {}),
            'entry_score': entry,
        })
    return result


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("=" * 60)
    print(f"  🌅 晨间综合分析  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取美股数据
    print("  [1/7] 获取美股指数...")
    us_indices = fetch_us_indices()

    # 2. 获取美债收益率
    print("  [2/7] 获取美债收益率...")
    bond_yield = fetch_us_bond_yield()

    # 3. 获取大宗商品
    print("  [3/7] 获取大宗商品...")
    commodities = fetch_commodities()

    # 4. 获取汇率
    print("  [4/7] 获取汇率...")
    fx = fetch_fx()

    # 5. 获取全球指数
    print("  [5/7] 获取全球指数...")
    global_indices = fetch_global_indices()

    # 6. 获取A股指数
    print("  [6/7] 获取A股指数...")
    cn_indices = fetch_cn_indices()

    # 6.5 获取今日推荐（如果有）
    print("  [6.5] 获取推荐数据...")
    top_buys = load_top_buys()

    # 7. 评估影响
    print("  [7/7] 生成分析报告...")
    yesterday_data = load_yesterday_data()

    us_impact = assess_us_impact(us_indices)
    commodity_impact = assess_commodity_impact(commodities)
    fx_impact = assess_fx_impact(fx)
    global_impact = assess_global_impact(global_indices)
    impact_summary = build_impact_summary(us_impact, commodity_impact, fx_impact, global_impact)
    strategy = generate_strategy(yesterday_data, us_impact, commodity_impact, fx_impact, global_impact)

    analysis = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'us_indices': us_indices,
        'bond_yield': bond_yield,
        'commodities': commodities,
        'fx': fx,
        'global_indices': global_indices,
        'cn_indices': cn_indices,
        'us_impact': us_impact,
        'commodity_impact': commodity_impact,
        'fx_impact': fx_impact,
        'global_impact': global_impact,
        'impact_summary': impact_summary,
        'strategy': strategy,
        'top_buys': top_buys,
        'yesterday_sentiment': yesterday_data.get('market_sentiment') if yesterday_data else None,
        'yesterday_score': yesterday_data.get('avg_score') if yesterday_data else None,
    }

    # 保存
    _save_json(os.path.join(DATA_DIR, 'morning_analysis.json'), analysis)

    # 7.5 生成综合买入策略（基于外围影响的精准买入建议）
    print("  [7.5] 生成综合买入策略...")
    try:
        from comprehensive_strategy import generate_comprehensive_buy_strategy
        comprehensive = generate_comprehensive_buy_strategy(analysis)
        _save_json(os.path.join(DATA_DIR, 'comprehensive_strategy.json'), comprehensive)
        print(f"  📊 操作模式: {comprehensive['operation_mode']['name']}")
        print(f"  📊 开盘预测: {comprehensive['open_forecast']['description']}")
    except Exception as e:
        print(f"  ⚠️ 综合策略生成失败: {e}")

    # 打印摘要
    print(f"\n  📊 风险评分: {strategy['risk_score']}/100")
    print(f"  🇺🇸 美股影响: {us_impact.get('direction', '未知')} ({us_impact.get('level', '?')})")
    print(f"  💰 建议仓位: {strategy['position_advice']['max']*100:.0f}%")
    # 打印外围影响摘要
    if impact_summary:
        for line in impact_summary.split('\n')[:8]:
            print(f"  {line}")
    print(f"\n  ✅ 晨间分析完成！")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 晨间分析失败: {e}")
        traceback.print_exc()
        sys.exit(1)
