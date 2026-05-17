#!/usr/bin/env python3
"""
A股全市场智能分析系统
每天自动分析所有主板股票，生成买入/卖出建议
"""

import akshare as ak
import pandas as pd
import numpy as np
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import warnings
warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
KEEP_DAYS = 7


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)


# ========== 数据获取 ==========

def get_all_stocks():
    """获取全部A股实时数据（一次API调用）"""
    print("  [1/5] 获取全市场实时数据...")
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_spot_em()
            print(f"        获取到 {len(df)} 只股票")
            return df
        except Exception as e:
            print(f"        第{attempt+1}次失败: {e}, 重试中...")
            time.sleep(5)
    raise RuntimeError("无法获取股票数据")


def filter_stocks(df):
    """过滤：去除科创板(688)、创业板(300)、ST、北交所(8/4开头)"""
    before = len(df)
    df = df[~df['名称'].str.contains('ST', case=False, na=False)]
    df = df[~df['代码'].str.startswith('688')]
    df = df[~df['代码'].str.startswith('300')]
    df = df[~df['代码'].str.startswith('8')]
    df = df[~df['代码'].str.startswith('4')]
    # 去除停牌股（最新价为空或为-）
    df = df[df['最新价'].notna()]
    df = df[df['最新价'] != '-']
    df = df[df['最新价'].astype(float) > 0]
    print(f"  [2/5] 过滤完成：{before} → {len(df)} 只（去除科创板/创业板/ST/北交所/停牌）")
    return df.reset_index(drop=True)


def get_stock_history(symbol, days=60):
    """获取个股历史K线数据（前复权）"""
    try:
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=int(days * 1.6))).strftime('%Y%m%d')
        df = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=start, end_date=end, adjust="qfq"
        )
        return df if df is not None and len(df) >= 20 else None
    except:
        return None


# ========== 技术指标计算 ==========

def calc_ma(close, periods=(5, 10, 20, 60)):
    return {f'ma{p}': close.rolling(p).mean() for p in periods}


def calc_macd(close, fast=12, slow=26, signal=9):
    ef = close.ewm(span=fast, adjust=False).mean()
    es = close.ewm(span=slow, adjust=False).mean()
    dif = ef - es
    dea = dif.ewm(span=signal, adjust=False).mean()
    return dif, dea, 2 * (dif - dea)


def calc_rsi(close, periods=(6, 12, 24)):
    result = {}
    for p in periods:
        delta = close.diff()
        g = delta.where(delta > 0, 0).rolling(p, min_periods=1).mean()
        l = (-delta.where(delta < 0, 0)).rolling(p, min_periods=1).mean()
        rs = g / (l + 1e-10)
        result[f'rsi{p}'] = 100 - 100 / (1 + rs)
    return result


def calc_kdj(high, low, close, n=9):
    low_n = low.rolling(n, min_periods=1).min()
    high_n = high.rolling(n, min_periods=1).max()
    rsv = (close - low_n) / (high_n - low_n + 1e-10) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return k, d, 3 * k - 2 * d


def calc_boll(close, period=20, std_n=2):
    mid = close.rolling(period, min_periods=1).mean()
    s = close.rolling(period, min_periods=1).std()
    return mid + std_n * s, mid, mid - std_n * s


# ========== 基础分析（全量） ==========

def basic_analyze(row):
    """用实时行情做基础评分和信号识别"""
    signals = []
    score = 50

    chg = safe_f(row, '涨跌幅')
    turnover = safe_f(row, '换手率')
    vol_ratio = safe_f(row, '量比', 1.0)
    amp = safe_f(row, '振幅')
    price = safe_f(row, '最新价')
    high = safe_f(row, '最高')
    low = safe_f(row, '最低')

    # ── 动量 ──
    if 1 <= chg < 5:
        score += 8; signals.append('温和上涨')
    elif 5 <= chg < 9.5:
        score += 13; signals.append('强势上涨')
    elif chg >= 9.5:
        score -= 5; signals.append('涨停')
    elif -1 <= chg < 1:
        score += 2; signals.append('横盘整理')
    elif -5 < chg < -1:
        score -= 8; signals.append('回调')
    elif chg <= -5:
        score -= 15; signals.append('大幅下跌')

    # ── 量能 ──
    if 3 < turnover < 15:
        score += 8
        if vol_ratio > 1.5:
            score += 5; signals.append('放量')
    elif turnover >= 15:
        score -= 3; signals.append('异常换手')
    if vol_ratio < 0.5:
        score -= 5; signals.append('缩量')

    # ── 日内位置 ──
    if high > 0 and low > 0:
        rng = high - low
        if rng > 0:
            pos = (price - low) / rng
            if pos > 0.8:
                score += 3; signals.append('收在高位')
            elif pos < 0.2:
                score -= 3; signals.append('收在低位')

    # ── 估值 ──
    pe = row.get('市盈率-动态')
    if pe is not None:
        try:
            pe_f = float(pe)
            if 0 < pe_f < 15:
                score += 5; signals.append('低PE')
            elif pe_f > 100:
                score -= 3; signals.append('高PE')
        except:
            pass

    score = clamp(score)
    return {
        'score': score,
        'recommendation': rec(score),
        'signals': signals,
        'trend': trend(score)
    }


# ========== 深度分析（Top候选） ==========

def deep_analyze(code, basic, hist_df):
    """对候选股做深度技术分析"""
    if hist_df is None or len(hist_df) < 20:
        return basic

    close = hist_df['收盘'].astype(float)
    high = hist_df['最高'].astype(float)
    low = hist_df['最低'].astype(float)
    vol = hist_df['成交量'].astype(float)

    r = dict(basic)
    signals = list(basic.get('signals', []))
    score = basic['score']

    # ── 均线 ──
    ma = calc_ma(close)
    cp = close.iloc[-1]
    ma5, ma10, ma20 = ma['ma5'].iloc[-1], ma['ma10'].iloc[-1], ma['ma20'].iloc[-1]
    ma60 = ma['ma60'].iloc[-1] if len(close) >= 60 else None

    r.update({'ma5': r2(ma5), 'ma10': r2(ma10), 'ma20': r2(ma20)})
    if ma60 is not None and not pd.isna(ma60):
        r['ma60'] = r2(ma60)

    # 均线排列
    if cp > ma5 > ma10 > ma20:
        score += 15; signals.append('均线多头排列')
    elif ma5 > ma10 > ma20 and cp > ma20:
        score += 8; signals.append('短期多头')
    elif cp < ma5 < ma10 < ma20:
        score -= 15; signals.append('均线空头排列')

    # MA金叉/死叉
    if len(ma['ma5']) >= 2:
        p5, p10 = ma['ma5'].iloc[-2], ma['ma10'].iloc[-2]
        if p5 <= p10 and ma5 > ma10:
            score += 10; signals.append('MA金叉')
        elif p5 >= p10 and ma5 < ma10:
            score -= 10; signals.append('MA死叉')

    # ── MACD ──
    dif, dea, macd_h = calc_macd(close)
    r.update({
        'macd_dif': r2(dif.iloc[-1], 4),
        'macd_dea': r2(dea.iloc[-1], 4),
        'macd_hist': r2(macd_h.iloc[-1], 4)
    })
    if len(dif) >= 2:
        if dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
            score += 12; signals.append('MACD金叉')
        elif dif.iloc[-2] >= dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
            score -= 12; signals.append('MACD死叉')
    if dif.iloc[-1] > 0:
        score += 3
    else:
        score -= 3
    if len(macd_h) >= 3:
        if macd_h.iloc[-3] < macd_h.iloc[-2] < macd_h.iloc[-1]:
            score += 5; signals.append('红柱放大')
        elif macd_h.iloc[-3] > macd_h.iloc[-2] > macd_h.iloc[-1] and macd_h.iloc[-1] < 0:
            score -= 5; signals.append('绿柱放大')

    # ── RSI ──
    rsi = calc_rsi(close)
    rsi6, rsi12 = float(rsi['rsi6'].iloc[-1]), float(rsi['rsi12'].iloc[-1])
    r.update({'rsi6': r1(rsi6), 'rsi12': r1(rsi12)})
    if rsi6 < 20:
        score += 10; signals.append('RSI超卖')
    elif rsi6 < 30:
        score += 5; signals.append('RSI偏低')
    elif rsi6 > 80:
        score -= 10; signals.append('RSI超买')
    elif rsi6 > 70:
        score -= 5; signals.append('RSI偏高')

    # ── KDJ ──
    k, d, j = calc_kdj(high, low, close)
    r.update({'kdj_k': r1(k.iloc[-1]), 'kdj_d': r1(d.iloc[-1]), 'kdj_j': r1(j.iloc[-1])})
    if j.iloc[-1] < 20:
        score += 8; signals.append('KDJ超卖')
    elif j.iloc[-1] > 100:
        score -= 8; signals.append('KDJ超买')
    if len(k) >= 2:
        if k.iloc[-2] < d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
            score += 8; signals.append('KDJ金叉')
        elif k.iloc[-2] > d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
            score -= 8; signals.append('KDJ死叉')

    # ── 布林带 ──
    upper, mid, lower = calc_boll(close)
    r.update({
        'boll_upper': r2(upper.iloc[-1]),
        'boll_middle': r2(mid.iloc[-1]),
        'boll_lower': r2(lower.iloc[-1])
    })
    if cp <= lower.iloc[-1]:
        score += 10; signals.append('触布林下轨')
    elif cp >= upper.iloc[-1]:
        score -= 5; signals.append('触布林上轨')

    # ── 量价关系 ──
    if len(vol) >= 5:
        vm5 = vol.iloc[-5:].mean()
        if vol.iloc[-1] > vm5 * 1.5 and cp > close.iloc[-2]:
            score += 5; signals.append('放量上涨')
        elif vol.iloc[-1] > vm5 * 1.5 and cp < close.iloc[-2]:
            score -= 5; signals.append('放量下跌')

    # ── 支撑压力 ──
    win = min(20, len(high))
    r_hi = high.iloc[-win:].max()
    r_lo = low.iloc[-win:].min()
    r.update({
        'support': r2(r_lo),
        'resistance': r2(r_hi),
        'buy_point': r2(ma20 * 0.98),
        'stop_loss': r2(r_lo * 0.97),
        'target_price': r2(r_hi * 1.03)
    })

    # ── 操作时间建议 ──
    if score >= 65:
        r['buy_time'] = '开盘30分钟内 (9:30-10:00)'
        r['sell_time'] = '冲高回落时 (10:30-11:00 或 14:00-14:30)'
    elif score >= 50:
        r['buy_time'] = '回调支撑位附近 (10:30-11:00 或 14:00-14:30)'
        r['sell_time'] = '反弹压力位附近'
    else:
        r['buy_time'] = '暂不建议买入'
        r['sell_time'] = '建议观望或减仓'

    # ── 最终评分 ──
    score = clamp(score)
    r.update({
        'score': score,
        'recommendation': rec(score),
        'signals': signals,
        'trend': trend(score),
        'analysis_text': gen_text(r, cp, ma5, ma10, ma20)
    })
    return r


def gen_text(r, cp, ma5, ma10, ma20):
    """生成自然语言分析"""
    t = []
    if r['trend'] == '上升':
        t.append(f"该股处于上升趋势，现价{cp:.2f}元运行在MA5({ma5:.2f})上方。")
    elif r['trend'] == '下降':
        t.append(f"该股处于下降趋势，现价{cp:.2f}元跌破MA5({ma5:.2f})。")
    else:
        t.append(f"该股横盘震荡，现价{cp:.2f}元在MA10({ma10:.2f})附近整理。")

    pos_s = [s for s in r['signals'] if any(k in s for k in ['金叉','超卖','放量上涨','多头','突破','低位','偏低','下轨'])]
    neg_s = [s for s in r['signals'] if any(k in s for k in ['死叉','超买','放量下跌','空头','高估','偏高','上轨'])]

    if pos_s:
        t.append(f"积极信号：{'、'.join(pos_s)}。")
    if neg_s:
        t.append(f"风险信号：{'、'.join(neg_s)}。")

    t.append(f"综合评分{r['score']}分，操作建议：{r['recommendation']}。")
    if r.get('buy_point'):
        t.append(f"参考买入区间 {r['buy_point']} 元，止损 {r['stop_loss']} 元，目标 {r['target_price']} 元。")

    return ''.join(t)


# ========== 推荐与策略 ==========

def generate_recommendations(all_stocks):
    """生成操作建议和策略"""
    scored = [s for s in all_stocks if s.get('score') is not None]
    scored.sort(key=lambda x: x['score'], reverse=True)

    strong_buy = [s for s in scored if s['score'] >= 80][:5]
    buy_list = [s for s in scored if 65 <= s['score'] < 80][:10]
    watch = [s for s in scored if 50 <= s['score'] < 65][:5]
    avoid = [s for s in scored if s['score'] < 35][-5:]

    # 简易策略
    strategies = []
    avg_score = np.mean([s['score'] for s in scored]) if scored else 50
    sentiment = '偏多' if avg_score > 55 else ('偏空' if avg_score < 45 else '中性')

    # 涨停板策略
    zt = [s for s in all_stocks if '涨停' in s.get('signals', []) and s['score'] >= 50]
    if zt:
        strategies.append({
            'name': '涨停板接力',
            'desc': f"今日{len(zt)}只涨停股中评分较高的可关注明日竞价表现，低开3-7%企稳可考虑介入",
            'stocks': [{'code': s['code'], 'name': s['name'], 'score': s['score']} for s in zt[:5]]
        })

    # 回调低吸策略
    pullback = [s for s in all_stocks if s['score'] >= 60 and ('超卖' in s.get('signals', []) or '下轨' in s.get('signals', []) or '偏低' in s.get('signals', []))]
    if pullback:
        strategies.append({
            'name': '回调低吸',
            'desc': f"技术面超卖/触及支撑位的强势股，可在支撑位附近分批建仓",
            'stocks': [{'code': s['code'], 'name': s['name'], 'score': s['score']} for s in pullback[:5]]
        })

    # 突破策略
    breakout = [s for s in all_stocks if '金叉' in s.get('signals', []) and s['score'] >= 65]
    if breakout:
        strategies.append({
            'name': '技术突破',
            'desc': f"MACD/MA/KDJ出现金叉确认信号的个股，趋势有望延续",
            'stocks': [{'code': s['code'], 'name': s['name'], 'score': s['score']} for s in breakout[:5]]
        })

    return {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'market_sentiment': sentiment,
        'avg_score': round(avg_score, 1),
        'strong_buy': strong_buy,
        'buy': buy_list,
        'watch': watch,
        'avoid': avoid,
        'strategies': strategies
    }


# ========== 辅助函数 ==========

def safe_f(row, key, default=0):
    try:
        v = row.get(key, default)
        return float(v) if v is not None and str(v) != '-' and str(v) != '' else default
    except:
        return default

def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

def r2(v, d=2):
    try:
        return round(float(v), d) if not pd.isna(v) else None
    except:
        return None

def r1(v):
    return r2(v, 1)

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


# ========== 批量深度分析 ==========

def batch_deep_analyze(candidates):
    """多线程获取历史数据并做深度分析"""
    results = {}
    codes = [c['code'] for c in candidates]
    codes_set = set(codes)
    code_to_basic = {c['code']: c for c in candidates}

    print(f"  [4/5] 深度分析 {len(codes)} 只候选股（多线程获取历史数据）...")

    def work(code):
        hist = get_stock_history(code, days=60)
        if hist is not None:
            return code, deep_analyze(code, code_to_basic[code], hist)
        return code, code_to_basic[code]

    done = 0
    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = {pool.submit(work, c): c for c in codes}
        for f in as_completed(futures):
            code, result = f.result()
            results[code] = result
            done += 1
            if done % 20 == 0:
                print(f"        进度: {done}/{len(codes)}")

    print(f"        深度分析完成: {done}/{len(codes)}")
    return results


# ========== 历史管理 ==========

def cleanup_history():
    """清理超过 KEEP_DAYS 的历史数据"""
    if not os.path.exists(HISTORY_DIR):
        return
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    for f in os.listdir(HISTORY_DIR):
        if not f.endswith('.json'):
            continue
        try:
            # 文件名格式: 2026-05-17_1530.json
            date_str = f.split('_')[0]
            fdate = datetime.strptime(date_str, '%Y-%m-%d')
            if fdate < cutoff:
                os.remove(os.path.join(HISTORY_DIR, f))
                print(f"        清理历史: {f}")
        except:
            pass


def save_snapshot(all_stocks, deep_results, recommendations):
    """保存当前分析数据"""
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H%M')
    ts = now.strftime('%Y-%m-%d %H:%M:%S')

    # 合并深度分析结果
    final_stocks = []
    for s in all_stocks:
        code = s['code']
        if code in deep_results:
            final_stocks.append(deep_results[code])
        else:
            final_stocks.append(s)

    # 按评分排序
    final_stocks.sort(key=lambda x: x.get('score', 0), reverse=True)

    # 保存全部股票数据
    all_data = {
        'update_time': ts,
        'total': len(final_stocks),
        'stocks': final_stocks
    }
    all_path = os.path.join(DATA_DIR, 'all_stocks.json')
    with open(all_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False)

    # 保存推荐数据
    rec_path = os.path.join(DATA_DIR, 'recommendations.json')
    with open(rec_path, 'w', encoding='utf-8') as f:
        json.dump(recommendations, f, ensure_ascii=False)

    # 保存历史快照（用于对比）
    hist_path = os.path.join(HISTORY_DIR, f'{date_str}_{time_str}.json')
    hist_data = {
        'update_time': ts,
        'recommendations': {
            'strong_buy': [{'code': s['code'], 'name': s['name'], 'score': s['score']}
                           for s in recommendations['strong_buy']],
            'buy': [{'code': s['code'], 'name': s['name'], 'score': s['score']}
                    for s in recommendations['buy']],
            'avoid': [{'code': s['code'], 'name': s['name'], 'score': s['score']}
                      for s in recommendations['avoid']],
        },
        'scores': {s['code']: s['score'] for s in final_stocks[:500]}
    }
    with open(hist_path, 'w', encoding='utf-8') as f:
        json.dump(hist_data, f, ensure_ascii=False)

    print(f"  [5/5] 数据已保存 ({len(final_stocks)} 只股票)")
    print(f"        → {all_path}")
    print(f"        → {rec_path}")
    print(f"        → {hist_path}")


# ========== 主函数 ==========

def main():
    ensure_dirs()
    print("=" * 60)
    print(f"  A股全市场智能分析  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取数据
    df = get_all_stocks()

    # 2. 过滤
    df = filter_stocks(df)

    # 3. 基础分析（全量）
    print("  [3/5] 基础分析（全量）...")
    all_stocks = []
    for _, row in df.iterrows():
        try:
            basic = basic_analyze(row)
            stock = {
                'code': row['代码'],
                'name': row['名称'],
                'industry': row.get('所属行业', ''),
                'price': safe_f(row, '最新价'),
                'change_pct': safe_f(row, '涨跌幅'),
                'change_amt': safe_f(row, '涨跌额'),
                'volume': safe_f(row, '成交量'),
                'amount': safe_f(row, '成交额'),
                'amplitude': safe_f(row, '振幅'),
                'high': safe_f(row, '最高'),
                'low': safe_f(row, '最低'),
                'open': safe_f(row, '今开'),
                'prev_close': safe_f(row, '昨收'),
                'turnover_rate': safe_f(row, '换手率'),
                'volume_ratio': safe_f(row, '量比', 1.0),
                'pe': safe_f(row, '市盈率-动态') if row.get('市盈率-动态') else None,
                'pb': safe_f(row, '市净率') if row.get('市净率') else None,
                'market_cap': safe_f(row, '总市值'),
                **basic
            }
            all_stocks.append(stock)
        except Exception as e:
            pass

    # 4. 深度分析（Top 200）
    all_stocks.sort(key=lambda x: x['score'], reverse=True)
    candidates = all_stocks[:200]
    deep_results = batch_deep_analyze(candidates)

    # 5. 生成推荐
    recommendations = generate_recommendations(all_stocks)
    print(f"\n  📊 市场情绪: {recommendations['market_sentiment']} (平均分 {recommendations['avg_score']})")
    if recommendations['strong_buy']:
        print(f"  🔥 强烈买入: {', '.join(s['name'] + '(' + str(s['score']) + ')' for s in recommendations['strong_buy'][:3])}")
    if recommendations['buy']:
        print(f"  📈 买入关注: {', '.join(s['name'] + '(' + str(s['score']) + ')' for s in recommendations['buy'][:3])}")

    # 6. 保存
    save_snapshot(all_stocks, deep_results, recommendations)

    # 7. 清理历史
    cleanup_history()

    print("\n  ✅ 分析完成！")
    return True


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 分析失败: {e}")
        traceback.print_exc()
        sys.exit(1)
