#!/usr/bin/env python3
"""
模拟：10万本金，每天选6只强烈买入（按评分排序取前6），
每只约1.6万（10万/6），次日收盘卖出，再买入新的。
"""
import json, os, random, math
from datetime import datetime, timedelta

DATA_DIR = '/Users/abbyma/.openclaw-autoclaw/workspace/stock-analyzer/data/history'

# 加载所有历史数据
files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith('.json')])
records = []
for f in files:
    with open(os.path.join(DATA_DIR, f)) as fh:
        d = json.load(fh)
    date = d.get('update_time', '')[:10]
    strong = d.get('recommendations', {}).get('strong_buy', [])
    # 添加 snapshot_price 和 next_day_actual
    for s in strong:
        if s.get('next_day_actual'):
            records.append({
                'date': date,
                'code': s['code'],
                'name': s['name'],
                'score': s.get('score', 0),
                'snapshot_price': s.get('snapshot_price') or s.get('price', 0),
                'actual_pct': s['next_day_actual']['actual_pct'],
                'pred_pct': s.get('next_day_estimate', {}).get('estimate', 0),
                'pred_result': s.get('prediction_result', {}),
            })

# 按日期分组
from collections import defaultdict
by_date = defaultdict(list)
for r in records:
    by_date[r['date']].append(r)

# 打印每日数据概况
print("=" * 70)
print("📊 历史强烈买入次日表现数据")
print("=" * 70)
for date in sorted(by_date.keys()):
    stocks = by_date[date]
    pcts = [s['actual_pct'] for s in stocks]
    wins = [p for p in pcts if p > 0]
    avg = sum(pcts) / len(pcts)
    print(f"\n📅 {date} · {len(stocks)}只强烈买入")
    print(f"   平均涨幅: {avg:+.2f}%  胜率: {len(wins)}/{len(pcts)} ({len(wins)/len(pcts)*100:.0f}%)")
    # 显示按评分排序前6
    top6 = sorted(stocks, key=lambda x: x.get('score', 0), reverse=True)[:6]
    print(f"   TOP6(评分排序):")
    for s in top6:
        print(f"     {s['score']:>3}分 {s['name']:<8} {s['snapshot_price']:.2f}→?  实际{s['actual_pct']:+.2f}%  {s['pred_result'].get('icon','?')} {s['pred_result'].get('label','?')}")

# === 模拟 ===
print("\n" + "=" * 70)
print("💰 策略模拟：10万本金 / 每天6只 / 次日卖出")
print("=" * 70)

# 用实际可用的日期数据来做蒙特卡洛模拟
all_pcts = [r['actual_pct'] for r in records]
all_dates = sorted(by_date.keys())
print(f"\n可用历史数据: {len(all_dates)}天, {len(all_pcts)}只股票样本")

# 统计特征
avg_return = sum(all_pcts) / len(all_pcts)
win_rate = sum(1 for p in all_pcts if p > 0) / len(all_pcts)
avg_win = sum(p for p in all_pcts if p > 0) / max(sum(1 for p in all_pcts if p > 0), 1)
avg_loss = sum(p for p in all_pcts if p <= 0) / max(sum(1 for p in all_pcts if p <= 0), 1)
max_return = max(all_pcts)
min_return = min(all_pcts)

print(f"\n📈 样本统计特征:")
print(f"   平均次日涨幅: {avg_return:+.2f}%")
print(f"   胜率: {win_rate*100:.1f}%")
print(f"   平均盈利: +{avg_win:.2f}%")
print(f"   平均亏损: {avg_loss:.2f}%")
print(f"   盈亏比: {abs(avg_win/avg_loss):.2f}")
print(f"   最大单日涨幅: +{max_return:.2f}%")
print(f"   最大单日跌幅: {min_return:.2f}%")

# === 用实际历史数据回测 ===
print(f"\n{'─'*70}")
print("📌 回测1：使用实际历史数据（评分TOP6选股）")
print(f"{'─'*70}")

capital = 100000
trading_days = 21
commission_rate = 0.00025  # 佣金万2.5（买卖各收）
stamp_tax = 0.001  # 印花税千1（仅卖出）

# 按评分TOP6选股，用实际数据回测
# 因为只有3天数据，我们用这3天的实际表现，然后外推21天
daily_portfolios = []
for date in all_dates:
    stocks = by_date[date]
    # 按评分排序取前6
    top6 = sorted(stocks, key=lambda x: x.get('score', 0), reverse=True)[:6]
    daily_portfolios.append({
        'date': date,
        'stocks': top6,
        'avg_return': sum(s['actual_pct'] for s in top6) / len(top6) if top6 else 0,
    })

for dp in daily_portfolios:
    avg = dp['avg_return']
    per_stock = capital / 6
    gross = per_stock * (1 + avg / 100) * 6
    buy_cost = capital * commission_rate
    sell_cost = gross * (commission_rate + stamp_tax)
    net = gross - buy_cost - sell_cost
    net_pct = (net - capital) / capital * 100
    print(f"   {dp['date']}: TOP6平均{avg:+.2f}% | 本金{capital:,.0f}→净额{net:,.0f} | 净收益{net-capital:+,.0f} ({net_pct:+.2f}%)")
    for s in dp['stocks']:
        print(f"     {s['score']:>3}分 {s['name']:<8} {s['actual_pct']:+.2f}%")
    capital = net  # 滚动

print(f"\n   实际{len(daily_portfolios)}天复利后本金: {capital:,.2f}元")
print(f"   总收益: {capital - 100000:+,.2f}元 ({(capital/100000-1)*100:+.2f}%)")

# === 蒙特卡洛模拟（1万次，21个交易日）===
print(f"\n{'─'*70}")
print("📌 回测2：蒙特卡洛模拟 10000次 × 21个交易日")
print(f"{'─'*70}")

random.seed(42)
sim_results = []
N_SIM = 10000

# 两种选股策略
print("\n🔬 策略A: 按评分TOP6选股（用历史评分分布模拟）")
print("🔬 策略B: 随机选6只强烈买入（基准对照）")

# 获取评分分布
all_scores = [r['score'] for r in records]
high_score_threshold = sorted(all_scores, reverse=True)[min(5, len(all_scores)-1)] if all_scores else 80
high_score_pcts = [r['actual_pct'] for r in records if r.get('score', 0) >= high_score_threshold]
mid_score_pcts = [r['actual_pct'] for r in records if high_score_threshold > r.get('score', 0) >= 80]
low_score_pcts = [r['actual_pct'] for r in records if r.get('score', 0) < 80]

print(f"\n   高分(≥{high_score_threshold}分)样本: {len(high_score_pcts)}只, 均幅{sum(high_score_pcts)/max(len(high_score_pcts),1):+.2f}%")
print(f"   中分(80-{high_score_threshold}分)样本: {len(mid_score_pcts)}只, 均幅{sum(mid_score_pcts)/max(len(mid_score_pcts),1):+.2f}%")
print(f"   低分(<80分)样本: {len(low_score_pcts)}只, 均幅{sum(low_score_pcts)/max(len(low_score_pcts),1):+.2f}%")

for strategy_name, pick_pool in [("策略A-高分TOP6", high_score_pcts if len(high_score_pcts) >= 6 else all_pcts),
                                   ("策略B-随机6只", all_pcts)]:
    if not pick_pool:
        continue

    final_capitals = []
    best_day_pnl = []
    worst_day_pnl = []
    max_drawdown_list = []
    daily_returns_all = []

    for _ in range(N_SIM):
        cap = 100000.0
        peak = cap
        max_dd = 0
        day_returns = []

        for day in range(trading_days):
            per_stock = cap / 6
            # 随机抽取6只（有放回，因为样本有限）
            picks = random.choices(pick_pool, k=6)
            day_avg = sum(picks) / 6

            # 计算净值（含手续费）
            gross = per_stock * (1 + day_avg / 100) * 6
            buy_cost = cap * commission_rate
            sell_cost = gross * (commission_rate + stamp_tax)
            net = gross - buy_cost - sell_cost
            day_ret = (net - cap) / cap * 100

            cap = net
            day_returns.append(day_ret)
            daily_returns_all.append(day_ret)

            if cap > peak:
                peak = cap
            dd = (peak - cap) / peak * 100
            if dd > max_dd:
                max_dd = dd

        final_capitals.append(cap)
        max_drawdown_list.append(max_dd)
        best_day_pnl.append(max(day_returns))
        worst_day_pnl.append(min(day_returns))

    final_capitals.sort()
    avg_daily_ret = sum(daily_returns_all) / len(daily_returns_all)

    print(f"\n{'─'*50}")
    print(f"🎯 {strategy_name}（{N_SIM}次模拟结果）")
    print(f"{'─'*50}")
    print(f"   📊 日均收益率: {avg_daily_ret:+.3f}%")
    print(f"   💰 21天后最终本金（含手续费）:")
    print(f"      🏆 最优(99%分位): ¥{final_capitals[int(N_SIM*0.99)]:>12,.2f}  (+{(final_capitals[int(N_SIM*0.99)]/100000-1)*100:>7.2f}%)")
    print(f"      📈 乐观(90%分位): ¥{final_capitals[int(N_SIM*0.90)]:>12,.2f}  (+{(final_capitals[int(N_SIM*0.90)]/100000-1)*100:>7.2f}%)")
    print(f"      📊 中位(50%分位): ¥{final_capitals[int(N_SIM*0.50)]:>12,.2f}  (+{(final_capitals[int(N_SIM*0.50)]/100000-1)*100:>7.2f}%)")
    print(f"      📉 悲观(10%分位): ¥{final_capitals[int(N_SIM*0.10)]:>12,.2f}  ({(final_capitals[int(N_SIM*0.10)]/100000-1)*100:>7.2f}%)")
    print(f"      ⚠️  最差(1%分位): ¥{final_capitals[int(N_SIM*0.01)]:>12,.2f}  ({(final_capitals[int(N_SIM*0.01)]/100000-1)*100:>7.2f}%)")
    print(f"      🎲 绝对最差: ¥{final_capitals[0]:>12,.2f}  ({(final_capitals[0]/100000-1)*100:>7.2f}%)")
    print(f"      🎲 绝对最好: ¥{final_capitals[-1]:>12,.2f}  (+{(final_capitals[-1]/100000-1)*100:>7.2f}%)")
    print(f"   📉 最大回撤中位数: {sorted(max_drawdown_list)[int(N_SIM*0.50)]:.2f}%")
    print(f"   📈 单日最大盈利中位数: +{sorted(best_day_pnl)[int(N_SIM*0.50)]:.2f}%")
    print(f"   📉 单日最大亏损中位数: {sorted(worst_day_pnl)[int(N_SIM*0.50)]:.2f}%")

# === 理论最优/最差 ===
print(f"\n{'─'*70}")
print("📌 理论极端值（基于历史样本极值）")
print(f"{'─'*70}")
# 每天6只都是最好/最差的
per = 100000 / 6
best_daily = per * (1 + max_return/100) * 6 * (1 - commission_rate - commission_rate - stamp_tax)
worst_daily = per * (1 + min_return/100) * 6 * (1 - commission_rate - commission_rate - stamp_tax)

best_21 = 100000
worst_21 = 100000
for _ in range(21):
    best_21 = best_21 * (best_daily / 100000)
    worst_21 = worst_21 * (worst_daily / 100000)

print(f"   🌟 每天6只都涨{max_return:+.2f}% × 21天: ¥{best_21:,.2f} (+{(best_21/100000-1)*100:+.1f}%)")
print(f"   💀 每天6只都跌{min_return:.2f}% × 21天: ¥{worst_21:,.2f} ({(worst_21/100000-1)*100:.1f}%)")
print(f"\n   （以上为理论极端，实际不可能每天都是最好/最差）")

# === 关键假设说明 ===
print(f"\n{'─'*70}")
print("⚠️ 关键假设与风险提示")
print(f"{'─'*70}")
print("""
1. 样本量有限：仅基于3天历史数据，统计结论需谨慎
2. 评分TOP6选股假设：假设每天能稳定选出评分最高的6只
3. 手续费已计算：佣金万2.5(买卖各收) + 印花税千1(卖出)
4. 未考虑：
   - 涨跌停无法买入/卖出的情况
   - 流动性不足导致滑点
   - 冲击成本（大额交易影响价格）
   - 选股策略随市场变化失效的可能
5. 次日表现用的是收盘价，实际操作中无法精确在收盘卖出
6. 以上为模拟回测，不构成投资建议
""")
