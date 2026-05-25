#!/usr/bin/env python3
"""
午间综合分析系统 v1.0
每个交易日12:00运行，在上午盘收盘后分析半日市场表现，
结合上午盘数据更新风险评分和操作建议。
"""

import json
import os
import sys
import traceback
import requests
from market_impact import (
    assess_us_impact, assess_commodity_impact, assess_fx_impact,
    assess_global_impact, build_impact_summary
)
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
    """获取美股指数（上午盘无变化，仍是隔夜数据）"""
    indices = {}
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
                        'name': name, 'price': round(price, 2),
                        'prev_close': round(prev, 2), 'change_pct': pct,
                    }
        except Exception as e:
            print(f"  获取 {name} 失败: {e}")
    return indices


def fetch_commodities():
    """获取大宗商品"""
    commodities = {}
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
                        commodities[code] = {
                            'name': name, 'unit': unit,
                            'price': round(price, 2), 'prev_close': round(prev, 2),
                            'change_pct': round((price - prev) / prev * 100, 2),
                        }
        except Exception as e:
            print(f"  获取 {name} 失败: {e}")
    return commodities


def fetch_fx():
    """获取汇率"""
    fx = {}
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
                        'name': '美元/离岸人民币', 'price': price,
                        'prev_close': prev, 'change_pct': pct,
                    }
    except Exception as e:
        print(f"  获取汇率失败: {e}")
    return fx


def fetch_global_indices():
    """获取全球指数"""
    indices = {}
    codes = {'hkHSI': '恒生指数'}
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
                            'name': name, 'price': round(price, 2),
                            'prev_close': round(prev, 2), 'change_pct': pct,
                        }
        except:
            pass
    return indices


def fetch_cn_indices():
    """获取A股主要指数"""
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
                    'name': name, 'code': code,
                    'price': float(parts[3]) if parts[3] else 0,
                    'prev_close': float(parts[4]) if parts[4] else 0,
                    'change_pct': float(parts[32]) if parts[32] else 0,
                }
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"  获取A股指数失败: {e}")
    return indices


def fetch_market_summary(all_stocks):
    """从全市场数据生成半日市场概况"""
    if not all_stocks:
        return ''
    total = len(all_stocks)
    rise = sum(1 for s in all_stocks if s.get('change_pct', 0) > 0)
    fall = sum(1 for s in all_stocks if s.get('change_pct', 0) < 0)
    zt = sum(1 for s in all_stocks if s.get('change_pct', 0) >= 9.8)
    dt = sum(1 for s in all_stocks if s.get('change_pct', 0) <= -9.8)
    avg_chg = sum(s.get('change_pct', 0) for s in all_stocks) / total if total else 0
    earning_pct = rise / total * 100 if total else 0

    parts = [f"全市场{total}只：上涨{rise}只({rise/total*100:.1f}%)，下跌{fall}只({fall/total*100:.1f}%)"]
    parts.append(f"涨停{zt}只，跌停{dt}只，平均涨幅{avg_chg:+.2f}%")

    # 赚钱效应
    if earning_pct > 60:
        parts.append(f"赚钱效应{'良好' if earning_pct > 70 else '一般'}")
    elif earning_pct > 40:
        parts.append("赚钱效应一般")
    elif earning_pct > 25:
        parts.append("赚钱效应较差")
    else:
        parts.append("赚钱效应很差，控制风险")

    return ' | '.join(parts)


def load_top_buys():
    """午间推荐：选出与晨间不同的3只股票
    晨间看重动量（已涨+明日预估涨），午间更看重午后空间：
    - 上午涨幅适中（1-5%），午后还有上涨空间
    - 明日预估为正
    - 排除晨间已推荐的股票
    """
    rec_path = os.path.join(DATA_DIR, 'recommendations.json')
    rec_data = _load_json(rec_path)
    if not rec_data:
        return []

    # 获取晨间推荐的股票，排除
    morning_data = _load_json(os.path.join(DATA_DIR, 'morning_analysis.json'))
    morning_codes = set()
    for s in (morning_data or {}).get('top_buys', []):
        morning_codes.add(s.get('code', ''))

    strong_buy = rec_data.get('strong_buy', [])
    buy_list = rec_data.get('buy', [])
    all_candidates = strong_buy + buy_list

    filtered = []
    for s in all_candidates:
        chg = s.get('change_pct', 0)
        est = (s.get('next_day_estimate') or {}).get('estimate', None)
        score = s.get('score', 0)
        code = s.get('code', '')

        if code in morning_codes:
            continue  # 排除晨间已推荐
        if est is None or est <= 0:
            continue  # 明日不看好的排除
        if score < 70:
            continue
        # 午间偏好：涨幅1-5%（还有午后空间），不宜太大
        if chg < 1 or chg > 5:
            continue
        filtered.append(s)

    # 午间排序：偏向涨幅适中（2-4%最佳，午后还有空间）+ 高评分 + 强预估
    def rank_key(s):
        est = (s.get('next_day_estimate') or {}).get('estimate', 0)
        chg = s.get('change_pct', 0)
        score = s.get('score', 0)
        # 涨幅2-4%得分最高（午后还有空间）
        chg_score = max(0, 10 - abs(chg - 3) * 2.5) if chg else 0
        return score * 0.3 + est * 10 * 0.4 + chg_score * 0.3

    filtered.sort(key=rank_key, reverse=True)
    selected = filtered[:3]

    # 不够3只时放宽：不限涨幅上限
    if len(selected) < 3:
        for s in all_candidates:
            est = (s.get('next_day_estimate') or {}).get('estimate', None)
            code = s.get('code', '')
            if est and est > 0 and code not in morning_codes and code not in [x.get('code', '') for x in selected]:
                selected.append(s)
            if len(selected) >= 3:
                break

    result = []
    for s in selected:
        result.append({
            'code': s.get('code', ''), 'name': s.get('name', ''),
            'score': s.get('score', 0), 'price': s.get('price', 0),
            'change_pct': s.get('change_pct', 0),
            'buy_point': s.get('buy_point'), 'buy_time': s.get('buy_time', ''),
            'stop_loss': s.get('stop_loss'), 'target_price': s.get('target_price'),
            'signals': s.get('signals', []),
            'next_day_estimate': s.get('next_day_estimate', {}),
        })
    return result


def load_morning_analysis():
    """加载早间分析数据"""
    path = os.path.join(DATA_DIR, 'morning_analysis.json')
    return _load_json(path)


def assess_midday_impact(cn_indices, morning_data, all_stocks, us_impact, commodity_impact, fx_impact, global_impact):
    """午间综合评估：A股半日表现 + 外围影响验证 + 午后策略"""
    lines = []
    risk_score = 50  # 基准

    # 1. 外围影响是否已被消化
    if morning_data:
        morning_risk = morning_data.get('strategy', {}).get('risk_score', 50)
        morning_us_dir = morning_data.get('us_impact', {}).get('direction', '中性')
        risk_score = morning_risk

        # 对比预测 vs 实际
        sh = cn_indices.get('000001', {})
        if sh and morning_us_dir:
            actual = sh.get('change_pct', 0)
            if morning_us_dir in ('大幅利好', '小幅利好') and actual > 0:
                lines.append(f"✅ 美股利好兑现，上证{actual:+.2f}%符合预期，午后看量能能否持续")
            elif morning_us_dir in ('大幅利好', '小幅利好') and actual <= 0:
                lines.append(f"⚠️ 美股利好未兑现，上证{actual:+.2f}%高开低走，午后承压")
                risk_score += 10
            elif morning_us_dir in ('大幅利空', '小幅利空') and actual < 0:
                lines.append(f"⚠️ 美股利空延续，上证{actual:+.2f}%弱势，午后可能继续调整")
            elif morning_us_dir in ('大幅利空', '小幅利空') and actual >= 0:
                lines.append(f"✅ 美股利空已消化，上证{actual:+.2f}%低开高走，午后有望延续反弹")
                risk_score -= 5
            else:
                lines.append(f"➡️ 外围中性影响，上证{actual:+.2f}%按自身节奏运行")

    # 2. A股上午表现
    sh = cn_indices.get('000001', {})
    sz = cn_indices.get('399001', {})
    kcb = cn_indices.get('000688', {})

    if sh:
        sh_chg = sh['change_pct']
        if sh_chg > 1:
            if not any('利好兑现' in l or '利空已消化' in l for l in lines):
                lines.append(f"✅ 上证指数午盘涨{sh_chg:+.2f}%，上午走势偏强")
            risk_score -= 10
        elif sh_chg < -1:
            if not any('利空延续' in l or '利好未兑现' in l for l in lines):
                lines.append(f"⚠️ 上证指数午盘跌{abs(sh_chg):.2f}%，上午承压明显")
            risk_score += 10
        else:
            lines.append(f"➡️ 上证指数午盘{sh_chg:+.2f}%，走势平稳")

    # 创业板 vs 主板分化
    if sh and kcb:
        if kcb['change_pct'] - sh['change_pct'] > 1.5:
            lines.append(f"📈 科创50({kcb['change_pct']:+.2f}%)远强于主板，资金向科技方向集中")
        elif sh['change_pct'] - kcb['change_pct'] > 1.5:
            lines.append(f"📉 科创50({kcb['change_pct']:+.2f}%)弱于主板，科技股回调")

    # 3. 赚钱效应
    if all_stocks:
        total = len(all_stocks)
        rise = sum(1 for s in all_stocks if s.get('change_pct', 0) > 0)
        earning_pct = rise / total * 100 if total else 50

        if earning_pct < 30:
            risk_score += 15
            lines.append(f"🔴 赚钱效应极差（仅{earning_pct:.0f}%上涨），多数个股下跌，午后不宜追高")
        elif earning_pct < 40:
            risk_score += 8
            lines.append(f"🟡 赚钱效应偏差（{earning_pct:.0f}%上涨），午后以观望为主")
        elif earning_pct > 60:
            risk_score -= 10
            lines.append(f"🟢 赚钱效应良好（{earning_pct:.0f}%上涨），午后可适度参与")

    # 4. 涨跌停分析
    if all_stocks:
        zt = sum(1 for s in all_stocks if s.get('change_pct', 0) >= 9.8)
        dt = sum(1 for s in all_stocks if s.get('change_pct', 0) <= -9.8)
        if dt > zt * 2:
            risk_score += 5
            lines.append(f"⚠️ 跌停{dt}只远超涨停{zt}只，空方力量占优")

    # 5. 持仓检查
    portfolio = _load_json(os.path.join(DATA_DIR, 'portfolio.json'), {})
    holdings = portfolio.get('holdings', {})
    if holdings:
        lines.append("\n💼 持仓午间检查：")
        for code, h in holdings.items():
            name = h.get('name', code)
            qty = h.get('qty', 0)
            cost = h.get('avg_cost', 0)
            # 找实时价格
            match = next((s for s in (all_stocks or []) if s.get('code') == code), None)
            if match and cost > 0:
                price = match.get('price', 0)
                pnl_pct = (price - cost) / cost * 100
                pnl_cls = '盈利' if pnl_pct >= 0 else '亏损'
                lines.append(f"  • {name}({code}) {qty}股 成本{cost:.2f} 现价{price:.2f} {pnl_cls}{abs(pnl_pct):.2f}%")
                if pnl_pct < -5:
                    lines.append(f"    ⚠️ 已接近止损线，关注午后能否企稳")
                elif pnl_pct < -3:
                    lines.append(f"    📉 浮亏{abs(pnl_pct):.2f}%，注意风险")

    # 6. 午间外围市场最新动态（商品/汇率可能有变化）
    # 商品期货在日间有波动，可能影响午后A股
    all_coping = []
    for impact in [commodity_impact, fx_impact, global_impact]:
        all_coping.extend(impact.get('coping', []))
    if all_coping:
        lines.append("\n🌐 午间外围最新动态：")
        for c in all_coping[:4]:
            lines.append(f"  {c}")

    risk_score = max(0, min(100, risk_score))

    # 根据风险评分生成午后策略
    if risk_score >= 70:
        lines.append("\n🔴 【午后策略】高风险环境")
        lines.append("  不加仓、不追高，持仓股若继续走弱可考虑减仓")
        lines.append("  若大盘午后继续下跌，优先保护本金")
    elif risk_score >= 55:
        lines.append("\n🟡 【午后策略】中高风险环境")
        lines.append("  不开新仓，持仓股可择机做T或持有观望")
        lines.append("  关注午后1:30-2:00是否有企稳信号")
    elif risk_score >= 40:
        lines.append("\n🟢 【午后策略】中性环境")
        lines.append("  可择机低吸优质标的，但控制单票仓位")
        lines.append("  优先关注回调到支撑位的强势股")
    else:
        lines.append("\n🟢 【午后策略】低风险环境")
        lines.append("  可积极操作，关注午后突破方向")
        lines.append("  放量突破可适当加仓")

    # 过滤规则提醒
    lines.append("\n  🚫 午后操作规则：")
    lines.append("  • 上午已涨超5%的不追（获利盘压力）")
    lines.append("  • 上午大幅下跌的股票不盲目抄底（等企稳信号）")
    lines.append("  • 临近尾盘（14:30后）谨慎操作")

    return {
        'risk_score': risk_score,
        'strategy_text': '\n'.join(lines),
        'position_advice': {
            'max': 0.7 if risk_score < 40 else (0.4 if risk_score < 55 else 0.2),
            'single_max': 0.3,
        },
    }


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("=" * 60)
    print(f"  ☀️ 午间综合分析  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取全市场股票数据
    print("  [1/6] 获取全市场数据...")
    all_stocks = _load_json(os.path.join(DATA_DIR, 'all_stocks.json'), {}).get('stocks', [])

    # 2. 获取美股（隔夜数据无变化）
    print("  [2/6] 获取美股指数...")
    us_indices = fetch_us_indices()

    # 3. 获取大宗商品
    print("  [3/6] 获取大宗商品...")
    commodities = fetch_commodities()

    # 4. 获取汇率
    print("  [4/6] 获取汇率...")
    fx = fetch_fx()

    # 5. 获取A股指数和全球市场
    print("  [5/6] 获取A股指数...")
    cn_indices = fetch_cn_indices()
    global_indices = fetch_global_indices()

    # 6. 生成分析
    print("  [6/6] 生成午间分析报告...")
    morning_data = load_morning_analysis()

    # 外围影响评估（午间更新，商品/汇率可能变化）
    us_impact = assess_us_impact(us_indices)
    commodity_impact = assess_commodity_impact(commodities)
    fx_impact = assess_fx_impact(fx)
    global_impact = assess_global_impact(global_indices)
    impact_summary = build_impact_summary(us_impact, commodity_impact, fx_impact, global_impact)

    strategy = assess_midday_impact(cn_indices, morning_data, all_stocks, us_impact, commodity_impact, fx_impact, global_impact)
    top_buys = load_top_buys()
    market_summary = fetch_market_summary(all_stocks)

    analysis = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'us_indices': us_indices,
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
        'market_summary': market_summary,
        'morning_risk': morning_data.get('strategy', {}).get('risk_score') if morning_data else None,
    }

    _save_json(os.path.join(DATA_DIR, 'midday_analysis.json'), analysis)

    print(f"\n  📊 午后风险评分: {strategy['risk_score']}/100")
    print(f"  🇨🇳 上证指数: {cn_indices.get('000001', {}).get('price', '-')} ({cn_indices.get('000001', {}).get('change_pct', 0):+.2f}%)")
    print(f"\n  ✅ 午间分析完成！")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 午间分析失败: {e}")
        traceback.print_exc()
        sys.exit(1)
