#!/usr/bin/env python3
"""
回填历史数据 v2：
1. 为每条历史记录的股票添加 snapshot_price（分析时的价格）
2. 获取当前实时价格（latest_price）
3. 尝试获取次日K线计算次日表现和预测验证
4. 用腾讯行情接口获取K线（东方财富限流时备用）
"""
import json, os, urllib.request, time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
HIST_DIR = os.path.join(DATA_DIR, 'history')

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fetch_kline_tencent(code: str) -> list:
    """从腾讯获取日K线"""
    # 腾讯格式: sh600000, sz000001
    if code.startswith('6'):
        prefix = 'sh'
    else:
        prefix = 'sz'
    
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,10,qfq"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            klines = data.get('data', {}).get(prefix + code, {}).get('qfqday', []) or data.get('data', {}).get(prefix + code, {}).get('day', [])
            if not klines:
                return []
            result = []
            for k in klines:
                # 腾讯返回的是 list 不是 string
                if isinstance(k, list):
                    if len(k) >= 6:
                        result.append({
                            'date': str(k[0]),
                            'open': float(k[1]),
                            'close': float(k[2]),
                            'high': float(k[3]),
                            'low': float(k[4]),
                            'volume': float(k[5]),
                        })
                elif isinstance(k, str):
                    parts = k.split(' ')
                    if len(parts) >= 6:
                        result.append({
                            'date': parts[0],
                            'open': float(parts[1]),
                            'close': float(parts[2]),
                            'high': float(parts[3]),
                            'low': float(parts[4]),
                            'volume': float(parts[5]),
                        })
            return result
    except Exception as e:
        return []


def fetch_kline_eastmoney(code: str) -> list:
    """从东方财富获取日K线"""
    if code.startswith('6') or code.startswith('9'):
        secid = f"1.{code}"
    else:
        secid = f"0.{code}"
    
    url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=10"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            klines = data.get('data', {}).get('klines', [])
            result = []
            for k in klines:
                parts = k.split(',')
                result.append({
                    'date': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': int(parts[5]),
                    'change_pct': float(parts[8]),
                })
            return result
    except:
        return []


def fetch_realtime(codes: list) -> dict:
    """通过腾讯获取实时价格（编码的）"""
    if not codes:
        return {}
    result = {}
    batch_size = 50
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        qs = ','.join([f"{'sh' if c.startswith('6') else 'sz'}{c}" for c in batch])
        url = f"http://qt.gtimg.cn/q={qs}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                text = raw.decode('gbk', errors='replace')
                for line in text.strip().split(';'):
                    if '~' not in line:
                        continue
                    parts = line.split('~')
                    if len(parts) < 45:
                        continue
                    code = parts[2]
                    price = float(parts[3]) if parts[3] else 0
                    change_pct = float(parts[32]) if parts[32] else 0
                    result[code] = {'price': price, 'change_pct': change_pct}
        except Exception as e:
            print(f"  批次失败: {e}")
        time.sleep(0.3)
    return result


def main():
    files = sorted([f for f in os.listdir(HIST_DIR) if f.endswith('.json')])
    if not files:
        print("无历史数据")
        return
    
    print(f"共 {len(files)} 条历史记录")
    
    # 收集日期
    date_files = {}
    for f in files:
        date = f[:10]
        if date not in date_files:
            date_files[date] = []
        date_files[date].append(f)
    sorted_dates = sorted(date_files.keys())
    print(f"覆盖日期: {sorted_dates[0]} ~ {sorted_dates[-1]}")
    
    # 收集所有股票
    stock_dates = {}
    for f in files:
        date = f[:10]
        with open(os.path.join(HIST_DIR, f)) as fh:
            data = json.load(fh)
        rec = data.get('recommendations', {})
        all_stocks = (rec.get('strong_buy', []) + rec.get('buy', []) + rec.get('watch', []))
        for s in all_stocks:
            code = s.get('code', '')
            if not code:
                continue
            if code not in stock_dates:
                stock_dates[code] = set()
            stock_dates[code].add(date)
    
    # 获取K线
    kline_cache = {}
    total = len(stock_dates)
    print(f"\n获取 {total} 只股票K线数据...")
    
    for i, code in enumerate(stock_dates.keys()):
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{total}")
        # 先试腾讯
        klines = fetch_kline_tencent(code)
        if not klines:
            # 再试东方财富
            klines = fetch_kline_eastmoney(code)
        if klines:
            kline_cache[code] = {k['date']: k for k in klines}
        time.sleep(0.5)
    
    print(f"K线获取完成: {len(kline_cache)}/{total} 成功")
    
    # 获取实时价格
    all_codes = list(stock_dates.keys())
    print(f"获取实时价格...")
    rt = fetch_realtime(all_codes)
    print(f"实时价格: {len(rt)} 只成功")
    
    # 处理每条记录
    updated = 0
    stats = {'total': 0, 'with_actual': 0, 'accurate': 0}
    
    for f in files:
        filepath = os.path.join(HIST_DIR, f)
        date = f[:10]
        
        with open(filepath) as fh:
            data = json.load(fh)
        
        rec = data.get('recommendations', {})
        all_stocks = (rec.get('strong_buy', []) + rec.get('buy', []) + rec.get('watch', []))
        
        date_idx = sorted_dates.index(date) if date in sorted_dates else -1
        next_date = sorted_dates[date_idx + 1] if date_idx >= 0 and date_idx < len(sorted_dates) - 1 else None
        
        modified = False
        for s in all_stocks:
            code = s.get('code', '')
            if not code:
                continue
            stats['total'] += 1
            
            # 1. snapshot_price
            price = s.get('price', 0)
            if price and 'snapshot_price' not in s:
                s['snapshot_price'] = price
                modified = True
            
            # 2. 次日表现：用次日收盘价（或最新价）vs snapshot_price
            if 'next_day_actual' in s or (next_date and 'next_day_actual' not in s):
                kc = kline_cache.get(code, {})
                next_kline = kc.get(next_date)
                snapshot = s.get('snapshot_price') or price
                if snapshot and snapshot > 0:
                    if next_kline:
                        # 有次日K线：用收盘价
                        actual_close = next_kline['close']
                        actual_pct = (actual_close - snapshot) / snapshot * 100
                    elif code in rt and rt[code]['price'] > 0:
                        # 没有次日K线但有实时价（同日或跨日）
                        actual_close = rt[code]['price']
                        actual_pct = (actual_close - snapshot) / snapshot * 100
                        next_date_str = date if date == sorted_dates[-1] else 'N/A'
                    else:
                        actual_close = None
                    
                    if actual_close is not None:
                        est = s.get('next_day_estimate', {}).get('estimate', 0)
                        s['next_day_actual'] = {
                            'actual_pct': round(actual_pct, 2),
                            'actual_close': actual_close,
                            'next_date': next_date or date,
                            'vs_estimate': round(actual_pct - est, 2),
                        }
                        modified = True
                        stats['with_actual'] += 1
            
            # 3. 预测验证
            if 'prediction_result' not in s and s.get('next_day_actual'):
                actual_pct = s['next_day_actual']['actual_pct']
                est = s.get('next_day_estimate', {}).get('estimate', 0)
                diff = actual_pct - est  # 正值=超预期，负值=低于预期
                predicted_up = est > 0
                actual_up = actual_pct > 0
                hit_dir = predicted_up == actual_up
                abs_diff = abs(actual_pct - est)
                
                # 判断逻辑：实际涨跌幅与预估的对比
                if diff >= 2:
                    label, icon = f'超预期+{diff:.1f}%', '🔥'
                elif diff >= 0.5:
                    label, icon = '超预期', '✓'
                elif abs_diff < 0.5:
                    label, icon = '精准命中', '✓'
                elif diff >= -1:
                    label, icon = '基本符合', '≈'
                elif diff >= -3:
                    label, icon = '低于预期', '↓'
                else:
                    label, icon = f'远低预期{diff:.1f}%', '✗'
                
                s['prediction_result'] = {'label': label, 'icon': icon, 'hit_dir': hit_dir}
                modified = True
                if hit_dir or diff >= 0:
                    stats['accurate'] += 1
            
            # 4. 当前价格
            if code in rt:
                s['latest_price'] = rt[code]['price']
                s['latest_change_pct'] = rt[code]['change_pct']
                modified = True
        
        if modified:
            with open(filepath, 'w') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            updated += 1
    
    print(f"\n✅ 更新了 {updated}/{len(files)} 条记录")
    print(f"\n📊 统计:")
    print(f"  总计: {stats['total']} 只")
    print(f"  有次日数据: {stats['with_actual']}")
    print(f"  方向命中: {stats['accurate']}")
    if stats['with_actual'] > 0:
        print(f"  命中率: {stats['accurate']/stats['with_actual']*100:.1f}%")


if __name__ == '__main__':
    main()
