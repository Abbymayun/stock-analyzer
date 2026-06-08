#!/usr/bin/env python3
"""轻量级API服务器 - 提供实时股票数据 (v2)"""
import json, time, os, sys, threading, subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
PORT = 8765

# 延迟初始化session以避免ESMTP干扰http.client
_session = None

def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({'User-Agent': 'Mozilla/5.0'})
    return _session


def fetch_realtime(codes):
    """通过腾讯API批量获取实时行情（subprocess+curl，独立进程不受限）"""
    if not codes:
        return {}
    # 给上海股票加sh前缀，深圳加sz前缀
    prefixed = []
    for c in codes:
        if c.startswith('6'):
            prefixed.append('sh' + c)
        else:
            prefixed.append('sz' + c)
    url = 'https://qt.gtimg.cn/q=' + ','.join(prefixed)
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '5', '-H', 'User-Agent: Mozilla/5.0', url],
                          capture_output=True, timeout=8)
        text = r.stdout.decode('gbk', errors='ignore')
    except Exception:
        try:
            r = subprocess.run(['wget', '-qO-', '-T', '5', '-U', 'Mozilla/5.0', url],
                              capture_output=True, timeout=8)
            text = r.stdout.decode('gbk', errors='ignore')
        except Exception:
            return {}
    
    result = {}
    for line in text.strip().split(';'):
        if '~' not in line or '=' not in line:
            continue
        parts = line.split('~')
        if len(parts) < 45:
            continue
        code = parts[2]
        prev = float(parts[4]) if parts[4] else 0
        price = float(parts[3]) if parts[3] else 0
        result[code] = {
            'name': parts[1],
            'code': code,
            'price': price,
            'prev_close': prev,
            'change_pct': round((price - prev) / prev * 100, 2) if prev > 0 else 0,
        }
    return result


def get_holding_codes():
    try:
        with open(os.path.join(DATA_DIR, 'portfolio.json')) as f:
            return list(json.load(f).get('holdings', {}).keys())
    except Exception:
        return []


def get_rec_codes():
    codes = []
    try:
        with open(os.path.join(DATA_DIR, 'recommendations.json')) as f:
            data = json.load(f)
        for key in ['strong_buy', 'buy', 'watch']:
            codes.extend([s['code'] for s in data.get(key, [])])
    except Exception:
        pass
    return codes


# 缓存（线程安全）
_cache = {'data': None, 'ts': 0, 'lock': threading.Lock()}
CACHE_TTL = 30


def get_cached_realtime(codes):
    now = time.time()
    with _cache['lock']:
        if _cache['data'] and now - _cache['ts'] < CACHE_TTL:
            cached = _cache['data']
            result = {c: cached[c] for c in codes if c in cached}
            if len(result) >= len(codes):
                return result

    # 获取请求的代码的实时数据
    time.sleep(0.5)  # 防止腾讯API限流
    result = {}
    for i in range(0, len(codes), 50):
        batch = codes[i:i + 50]
        batch_data = fetch_realtime(batch)
        result.update(batch_data)
        if i + 50 < len(codes):
            time.sleep(0.5)

    with _cache['lock']:
        if not _cache['data']:
            _cache['data'] = {}
        _cache['data'].update(result)
        _cache['ts'] = time.time()

    return result


def load_json(filepath, default=None):
    try:
        with open(filepath) as f:
            return json.load(f)
    except Exception:
        return default


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def end_headers(self):
        # 所有文件不缓存
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == '/api/realtime':
                self._handle_realtime(parsed)
            elif path == '/api/portfolio':
                params = parse_qs(parsed.query)
                force = params.get('force', [''])[0] == '1'
                self._handle_portfolio(force_realtime=force)
            elif path == '/api/trade_log':
                self._handle_trade_log()
            elif path == '/api/history_list':
                self._handle_history_list()
            elif path == '/api/history_detail':
                self._handle_history_detail(parsed)
            elif path == '/api/kline':
                self._handle_kline(parsed)
            elif path == '/api/purchased_stocks':
                self._handle_purchased_stocks()
            elif path == '/api/price_history':
                self._handle_price_history()
            elif path == '/api/strategy_results':
                self._handle_strategy_results()
            elif path == '/api/health':
                self._json({'ok': True, 'ts': time.time()})
            elif path == '/api/stock_advice':
                self._handle_stock_advice(parsed)
            elif path == '/api/buy_plan':
                self._handle_buy_plan()
            elif path == '/api/real_portfolio':
                self._handle_real_portfolio()
            elif path == '/api/auto_trade_config':
                self._handle_auto_trade_config()
            elif path == '/api/unified_buys':
                self._handle_unified_buys()
            elif path == '/api/latest_trades':
                self._handle_latest_trades()
            elif path == '/api/morning_analysis':
                self._handle_morning_analysis()
            elif path == '/api/midday_analysis':
                self._handle_midday_analysis()
            elif path == '/api/closing_analysis':
                self._handle_closing_analysis()
            elif path == '/api/strategy_tracks':
                self._handle_strategy_tracks()
            elif path == '/api/eod_analysis':
                self._handle_eod_analysis()
            elif path == '/api/trading_reports':
                self._handle_trading_reports()
            elif path.startswith('/api/trading_reports/generate'):
                self._handle_generate_report()
            else:
                super().do_GET()
        except Exception as e:
            try:
                self._json({'error': str(e)})
            except Exception:
                pass

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            params = json.loads(body.decode('utf-8'))

            if path == '/api/manual_buy':
                self._handle_manual_buy(params)
            elif path == '/api/real_portfolio':
                self._handle_real_portfolio(params)
            elif path == '/api/broker_connect':
                self._handle_broker_connect(params)
            elif path == '/api/broker_sync':
                self._handle_broker_sync()
            elif path == '/api/broker_signals':
                self._handle_broker_signals()
            elif path == '/api/auto_trade_config':
                self._handle_auto_trade_config(params)
            elif path == '/api/batch_stop_profit':
                self._handle_batch_stop_profit(params)
            elif path == '/api/delete_holding':
                self._handle_delete_holding(params)
            elif path == '/api/manual_sell':
                self._handle_manual_sell(params)
            elif path == '/api/reset_portfolio':
                self._handle_reset_portfolio(params)
            else:
                self.send_response(404)
                self.end_headers()
        except json.JSONDecodeError:
            self._json({'error': 'invalid JSON'})
        except Exception as e:
            self._json({'error': str(e)})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _handle_realtime(self, parsed):
        params = parse_qs(parsed.query)
        codes_str = params.get('codes', [''])[0]
        codes = [c.strip() for c in codes_str.split(',') if c.strip()]
        if not codes:
            codes = list(set(get_holding_codes() + get_rec_codes()))
        data = get_cached_realtime(codes)
        self._json({'ts': time.time(), 'data': data})

    def _handle_portfolio(self, force_realtime=False):
        pf = load_json(os.path.join(DATA_DIR, 'portfolio.json'), {})
        holdings = pf.get('holdings', {})

        initial = pf.get('initial_capital', 200000)
        # 返回基本信息，即使没有持仓
        if not holdings:
            self._json({
                'total_assets': pf.get('total_assets', initial),
                'cash': pf.get('cash', initial),
                'initial_capital': initial,
                'total_return': 0,
                'position_value': 0,
                'position_ratio': 0,
                'trading_stats': pf.get('trading_stats', {}),
                'holdings': [],
            })
            return

        codes = list(holdings.keys())
        # 支持强制刷新行情
        if force_realtime:
            rt = fetch_realtime(codes)
        else:
            rt = get_cached_realtime(codes) if codes else {}
        # 如果缓存没数据，直接拉取
        if not rt:
            rt = fetch_realtime(codes)

        trade_log = load_json(os.path.join(DATA_DIR, 'trade_log.json'), {}).get('trades', [])

        result = []
        for code, h in holdings.items():
            r = rt.get(code, {})
            buys = [t for t in trade_log if t.get('code') == code and t.get('type') == 'buy']
            sells = [t for t in trade_log if t.get('code') == code and t.get('type') == 'sell']
            ac = h.get('avg_cost', 0)
            cp = r.get('price', 0)
            # 实时价无效时保留上次价格（不归零）
            if cp <= 0:
                cp = h.get('last_price', ac)
            qty = h.get('qty', 0)
            # 保存最新价格到持仓（供下次查询用）
            if cp > 0 and r.get('price', 0) > 0:
                h['last_price'] = cp
            result.append({
                'code': code,
                'name': h.get('name', ''),
                'qty': qty,
                'avg_cost': ac,
                'current_price': cp,
                'change_pct': r.get('change_pct', 0),
                'pnl': (cp - ac) * qty,
                'pnl_pct': ((cp - ac) / ac * 100) if ac > 0 else 0,
                'buys': buys,
                'sells': sells,
            })

        initial = pf.get('initial_capital', 200000)
        market_value = 0
        unrealized_pnl = 0
        for code, h in holdings.items():
            cp = rt.get(code, {}).get('price', h.get('last_price', h.get('avg_cost', 0)))
            if cp <= 0: cp = h.get('avg_cost', 0)
            market_value += cp * h.get('qty', 0)
            unrealized_pnl += (cp - h.get('avg_cost', 0)) * h.get('qty', 0)
        total_assets = pf.get('cash', 0) + market_value
        stats = pf.get('trading_stats', {})
        realized_pnl = stats.get('total_pnl', 0)
        self._json({
            'total_assets': round(total_assets, 2),
            'cash': pf.get('cash', 0),
            'initial_capital': initial,
            'total_return': round((total_assets - initial) / initial * 100, 2),
            'unrealized_pnl': round(unrealized_pnl, 2),
            'realized_pnl': round(realized_pnl, 2),
            'position_value': round(market_value, 2),
            'position_ratio': round(market_value / total_assets * 100, 1) if total_assets > 0 else 0,
            'trading_stats': pf.get('trading_stats', {}),
            'holdings': result,
        })

    def _handle_trade_log(self):
        data = load_json(os.path.join(DATA_DIR, 'trade_log.json'), {'trades': []})
        self._json(data)

    def _handle_history_list(self):
        hist_dir = os.path.join(DATA_DIR, 'history')
        if not os.path.isdir(hist_dir):
            self._json([])
            return
        files = sorted([f for f in os.listdir(hist_dir) if f.endswith('.json')], reverse=True)
        result = []
        for f in files[:50]:
            data = load_json(os.path.join(hist_dir, f))
            if not data:
                continue
            rec = data.get('recommendations', {})
            result.append({
                'file': f,
                'update_time': data.get('update_time', ''),
                'market_sentiment': data.get('market_sentiment', ''),
                'avg_score': data.get('avg_score', 0),
                'strong_buy_count': len(rec.get('strong_buy', [])),
                'buy_count': len(rec.get('buy', [])),
                'watch_count': len(rec.get('watch', [])),
            })
        self._json(result)

    def _handle_history_detail(self, parsed):
        params = parse_qs(parsed.query)
        filename = params.get('file', [''])[0]
        if not filename or '..' in filename:
            self._json({'error': 'invalid file'})
            return
        data = load_json(os.path.join(DATA_DIR, 'history', filename))
        if not data:
            self._json({'error': 'not found'})
            return
        self._json({
            'update_time': data.get('update_time', ''),
            'market_sentiment': data.get('market_sentiment', ''),
            'avg_score': data.get('avg_score', 0),
            'market_analysis': data.get('market_analysis', ''),
            'next_day_advice': data.get('next_day_advice', ''),
            'strategies': data.get('strategies', []),
            'recommendations': data.get('recommendations', {}),
            'scores': data.get('scores', {}),
        })

    def _handle_kline(self, parsed):
        params = parse_qs(parsed.query)
        code = params.get('code', [''])[0]
        if not code:
            self._json({'error': 'no code'})
            return
        market = '1' if code.startswith('sh') else '0'
        secid = market + '.' + code[2:]
        try:
            resp = _get_session().get('https://push2his.eastmoney.com/api/qt/stock/kline/get', params={
                'secid': secid,
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57',
                'klt': '60',
                'fqt': '1',
                'end': '20500101',
                'lmt': '20',
            }, timeout=10)
            result = resp.json()
            klines = result.get('data', {}).get('klines', [])
            parsed_kl = []
            for kl in klines:
                parts = kl.split(',')
                if len(parts) >= 7:
                    parsed_kl.append({
                        'time': parts[0],
                        'open': float(parts[1]),
                        'close': float(parts[2]),
                        'high': float(parts[3]),
                        'low': float(parts[4]),
                        'volume': int(parts[5]),
                        'amount': float(parts[6]),
                    })
            self._json({'code': code, 'klines': parsed_kl})
        except Exception as e:
            self._json({'error': str(e)})

    def _handle_purchased_stocks(self):
        """返回所有购买过的股票记录"""
        tl = load_json(os.path.join(DATA_DIR, 'trade_log.json'), {'trades': []})
        trades = tl.get('trades', [])
        if not trades:
            self._json({'stocks': []})
            return

        # 按code分组，找到每只股票的首次买入和最后卖出
        from collections import defaultdict
        buy_map = defaultdict(list)
        sell_map = defaultdict(list)
        for t in trades:
            if t.get('type') in ('buy', 'day_trade_buy'):
                buy_map[t['code']].append(t)
            elif t.get('type') in ('sell', 'day_trade_sell'):
                sell_map[t['code']].append(t)

        result = []
        # 获取所有曾经买入过的股票代码
        all_codes = set(buy_map.keys())
        # 获取实时价格
        codes = list(all_codes)
        rt = get_cached_realtime(codes) if codes else {}

        for code in all_codes:
            buys = buy_map[code]
            sells = sell_map[code]
            first_buy = buys[0] if buys else None
            last_sell = sells[-1] if sells else None
            rt_data = rt.get(code, {})

            stock_info = {
                'code': code,
                'name': first_buy['name'] if first_buy else code,
                'current_price': rt_data.get('price', 0),
                'change_pct': rt_data.get('change_pct', 0),
                'buy_price': first_buy['price'] if first_buy else 0,
                'buy_time': first_buy['timestamp'] if first_buy else '',
                'buy_qty': first_buy['qty'] if first_buy else 0,
                'buy_reason': first_buy.get('reason', '') if first_buy else '',
                'sell_price': last_sell['price'] if last_sell else 0,
                'sell_time': last_sell['timestamp'] if last_sell else '',
                'sell_qty': last_sell['qty'] if last_sell else 0,
                'sell_pnl': last_sell.get('pnl', 0) if last_sell else None,
                'sell_pnl_pct': last_sell.get('pnl_pct', 0) if last_sell else None,
                'total_buys': len(buys),
                'total_sells': len(sells),
                'status': '已卖出' if sells and (not buy_map[code] or buys[-1]['timestamp'] < last_sell['timestamp']) else '持有中',
            }

            # 计算总盈亏（用所有卖出记录的pnl之和）
            total_pnl = sum(s.get('pnl', 0) for s in sells)
            stock_info['total_pnl'] = round(total_pnl, 2)

            result.append(stock_info)

        # 按最近交易时间排序
        result.sort(key=lambda x: x['buy_time'], reverse=True)
        self._json({'stocks': result})

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _handle_price_history(self):
        """从历史记录中提取某只股票的价格走势"""
        params = parse_qs(self.path.split('?')[1]) if '?' in self.path else {}
        code = params.get('code', [''])[0]
        days = int(params.get('days', ['3'])[0])
        if not code:
            self._json({'error': 'no code'})
            return

        history_dir = os.path.join(DATA_DIR, 'history')
        if not os.path.isdir(history_dir):
            self._json({'points': []})
            return

        files = sorted(os.listdir(history_dir))
        points = []
        for f in files:
            if not f.endswith('.json'):
                continue
            try:
                data = load_json(os.path.join(history_dir, f), {})
                # 从 scores 和 recommendations 中查找该股票
                price = None
                scores = data.get('scores', {})
                if code in scores:
                    price = scores[code].get('price')
                if price is None:
                    # 在 recommendations 中查找
                    for key in ('strong_buy', 'buy', 'watch', 'avoid'):
                        for s in data.get('recommendations', {}).get(key, []):
                            if s.get('code') == code:
                                price = s.get('price')
                                break
                        if price is not None:
                            break
                if price is not None:
                    points.append({
                        'time': data.get('update_time', f.replace('.json', '')),
                        'price': price,
                    })
            except:
                pass

        # 按时间排序，只保留最近N天
        points.sort(key=lambda x: x['time'])
        if len(points) > days * 20:  # 最多保留合理数量
            points = points[-days * 20:]
        self._json({'code': code, 'points': points})

    def _handle_strategy_results(self):
        rec = load_json(os.path.join(DATA_DIR, 'recommendations.json'), {})
        strategy = rec.get('strategy_results')
        if not strategy:
            self._json({})
            return
        self._json(strategy)

    def _handle_unified_buys(self):
        """返回统一的今日推荐买入（以晨间/午间/收盘分析的top_buys为准）"""
        seen_codes = set()
        unified = []
        sources = []
        
        # 收盘分析 (tomorrow_buys 或 top_buys)
        closing = load_json(os.path.join(DATA_DIR, 'closing_analysis.json'))
        if closing:
            buys = closing.get('tomorrow_buys', []) or closing.get('top_buys', [])
            for s in buys:
                if s.get('code') not in seen_codes:
                    seen_codes.add(s['code'])
                    s['_source'] = '收盘'
                    unified.append(s)
                    sources.append({'code': s['code'], 'source': '收盘分析', 'name': s.get('name', '')})
        
        # 午间分析
        midday = load_json(os.path.join(DATA_DIR, 'midday_analysis.json'))
        if midday:
            for s in midday.get('top_buys', []):
                if s.get('code') not in seen_codes:
                    seen_codes.add(s['code'])
                    s['_source'] = '午间'
                    unified.append(s)
                    sources.append({'code': s['code'], 'source': '午间分析', 'name': s.get('name', '')})
        
        # 晨间分析
        morning = load_json(os.path.join(DATA_DIR, 'morning_analysis.json'))
        if morning:
            for s in morning.get('top_buys', []):
                if s.get('code') not in seen_codes:
                    seen_codes.add(s['code'])
                    s['_source'] = '晨间'
                    unified.append(s)
                    sources.append({'code': s['code'], 'source': '晨间分析', 'name': s.get('name', '')})
        
        codes = [s['code'] for s in unified]
        rt = get_cached_realtime(codes) if codes else {}
        
        items = []
        for s in unified:
            r = rt.get(s['code'], {})
            items.append({
                'code': s.get('code', ''),
                'name': s.get('name', ''),
                'score': s.get('score', 0),
                'price': s.get('price', 0),
                'change_pct': s.get('change_pct', 0),
                'buy_point': s.get('buy_point'),
                'target_price': s.get('target_price'),
                'stop_loss': s.get('stop_loss'),
                'buy_time': s.get('buy_time', ''),
                'signals': s.get('signals', []),
                'next_day_estimate': s.get('next_day_estimate', {}),
                'entry_score': s.get('entry_score', 0),
                'reason': s.get('reason', ''),
                'source': s.get('_source', ''),
                'current_price': r.get('price', s.get('price', 0)),
                'current_change_pct': r.get('change_pct', s.get('change_pct', 0)),
            })
        
        self._json({
            'items': items,
            'sources': sources,
            'total': len(items),
            'update_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        })

    def _handle_stock_advice(self, parsed):
        """个股操作建议：输入股票代码+买入价格，返回持有/卖出建议"""
        params = parse_qs(parsed.query)
        code_raw = params.get('code', [''])[0].strip()
        buy_price = float(params.get('buy_price', ['0'])[0] or 0)
        
        if not code_raw or buy_price <= 0:
            self._json({'error': '请提供股票代码/名称和买入价格'})
            return
        
        # 查找股票
        all_data = load_json(os.path.join(DATA_DIR, 'all_stocks.json'), {})
        stocks = all_data.get('stocks', [])
        
        stock = None
        code_lower = code_raw.lower()
        for s in stocks:
            if s.get('code', '') == code_raw or s.get('name', '') == code_raw:
                stock = s
                break
            if code_raw in s.get('name', '') or (code_lower.startswith('sz') and s.get('code','') == code_raw[2:]) or (code_lower.startswith('sh') and s.get('code','') == code_raw[2:]):
                stock = s
                break
        
        if not stock:
            self._json({'error': f'未找到股票: {code_raw}'})
            return
        
        # 获取实时价格
        rt = get_cached_realtime([stock['code']])
        rt_data = rt.get(stock['code'], {})
        current_price = rt_data.get('price', stock.get('price', 0))
        
        # 计算盈亏
        pnl_pct = round((current_price - buy_price) / buy_price * 100, 2) if buy_price > 0 else 0
        
        # 获取推荐数据
        rec_data = load_json(os.path.join(DATA_DIR, 'recommendations.json'), {})
        rec_stock = None
        for k in ['strong_buy', 'buy', 'watch', 'avoid']:
            for s in rec_data.get(k, []):
                if s.get('code') == stock['code']:
                    rec_stock = s
                    break
            if rec_stock:
                break
        
        score = rec_stock.get('score', stock.get('score', 0)) if rec_stock else stock.get('score', 0)
        trend = rec_stock.get('trend', stock.get('trend', '')) if rec_stock else stock.get('trend', '')
        rec = rec_stock.get('recommendation', stock.get('recommendation', '')) if rec_stock else stock.get('recommendation', '')
        signals = (rec_stock or stock).get('signals', [])
        target_price = (rec_stock or stock).get('target_price')
        stop_loss = (rec_stock or stock).get('stop_loss')
        buy_point = (rec_stock or stock).get('buy_point')
        rsi6 = (rec_stock or stock).get('rsi6', 0)
        ma5 = (rec_stock or stock).get('ma5', 0)
        
        # 生成建议
        advice = ''
        action = ''
        action_color = ''
        reasons = []
        
        if pnl_pct <= -8:
            action = '🛑 建议止损卖出'
            action_color = '#ef4444'
            reasons.append(f'亏损已达{pnl_pct}%，触及-8%止损线')
            reasons.append('纪律性止损，避免更大亏损')
        elif pnl_pct >= 15:
            action = '💰 建议分批止盈'
            action_color = '#22c55e'
            reasons.append(f'盈利{pnl_pct}%，建议先卖出一半锁定利润')
            reasons.append('剩余仓位设移动止盈保护')
        elif rec and ('卖出' in rec):
            action = '🔴 建议卖出'
            action_color = '#ef4444'
            reasons.append(f'系统推荐: {rec}，评分{score}分')
            reasons.append('技术面转弱，趋势可能逆转')
        elif target_price and current_price >= target_price:
            action = '✅ 建议止盈卖出'
            action_color = '#22c55e'
            reasons.append(f'已达到目标价{target_price}元，当前{current_price}元')
            reasons.append(f'浮盈{pnl_pct}%，纪律性止盈')
        elif score >= 75 and ('上升' in str(trend)):
            action = '🟢 建议继续持有'
            action_color = '#22c55e'
            reasons.append(f'评分{score}分，趋势{trend}，技术面健康')
            if target_price:
                reasons.append(f'目标价{target_price}元，还有上行空间')
            if pnl_pct < 0:
                reasons.append(f'当前浮亏{pnl_pct}%，但趋势未坏，可观察')
        elif score >= 50:
            action = '🟡 建议持有观望'
            action_color = '#f59e0b'
            reasons.append(f'评分{score}分，趋势{trend or "震荡"}，方向不明确')
            if pnl_pct > 0:
                reasons.append(f'浮盈{pnl_pct}%，可设保本止损继续观察')
            else:
                reasons.append(f'浮亏{abs(pnl_pct)}%，关注是否跌破支撑位')
        else:
            action = '🔴 建议卖出'
            action_color = '#ef4444'
            reasons.append(f'评分{score}分偏低，技术面走弱')
            if pnl_pct > 0:
                reasons.append(f'仍有浮盈{pnl_pct}%，趁盈利离场')
            else:
                reasons.append(f'浮亏{abs(pnl_pct)}%，及时止损避免扩大')
        
        # 额外信号分析
        if rsi6 and rsi6 > 75:
            reasons.append('RSI超买(>75)，短期回调风险高')
        if rsi6 and rsi6 < 30:
            reasons.append('RSI超卖(<30)，可能触底反弹，不建议割肉')
        if signals:
            key_neg = [s for s in signals if '下跌' in s or '空头' in s]
            if key_neg:
                reasons.append(f'危险信号: {"、".join(key_neg[:2])}')
        
        advice = '\n'.join([f'{i+1}. {r}' for i, r in enumerate(reasons)])
        
        self._json({
            'code': stock['code'],
            'name': stock['name'],
            'buy_price': buy_price,
            'current_price': current_price,
            'change_pct': rt_data.get('change_pct', stock.get('change_pct', 0)),
            'pnl_pct': pnl_pct,
            'score': score,
            'trend': trend,
            'recommendation': rec,
            'signals': signals,
            'target_price': target_price,
            'stop_loss': stop_loss,
            'buy_point': buy_point,
            'rsi6': rsi6,
            'ma5': ma5,
            'action': action,
            'action_color': action_color,
            'advice': advice,
        })

    def _handle_buy_plan(self):
        """返回当前买入观察计划（含实时价格）"""
        plan = load_json(os.path.join(DATA_DIR, 'buy_plan.json'), {})
        items = plan.get('items', [])
        if not items:
            self._json({'date': plan.get('date', ''), 'items': [], 'created_at': plan.get('created_at', '')})
            return

        codes = [item['code'] for item in items]
        rt = get_cached_realtime(codes) if codes else {}

        # 读取K线分析状态
        bars = load_json(os.path.join(DATA_DIR, 'price_bars.json'), {})

        result = []
        for item in items:
            r = rt.get(item['code'], {})
            stock_bars = bars.get(item['code'], [])
            result.append({
                'code': item['code'],
                'name': item['name'],
                'score': item.get('score', 0),
                'plan_qty': item.get('plan_qty', 0),
                'target_price': item.get('target_price', 0),
                'reason': item.get('reason', ''),
                'signals': item.get('signals', []),
                'ratio': item.get('ratio', 0),
                # 实时数据
                'current_price': r.get('price', item.get('target_price', 0)),
                'change_pct': r.get('change_pct', 0),
                'high': r.get('high', 0),
                'low': r.get('low', 0),
                'volume': r.get('volume', 0),
                # K线数据量
                'bar_count': len(stock_bars),
                'last_bar_time': stock_bars[-1]['time'] if stock_bars else '',
            })

        self._json({
            'date': plan.get('date', ''),
            'created_at': plan.get('created_at', ''),
            'items': result,
        })

    def _handle_latest_trades(self):
        """返回最新的交易记录（用于通知检测）"""
        tl = load_json(os.path.join(DATA_DIR, 'trade_log.json'), {'trades': []})
        trades = tl.get('trades', [])
        # 返回最近5条
        recent = []
        for t in trades[-5:]:
            recent.append({
                'id': t.get('id', 0),
                'type': t.get('type', ''),
                'code': t.get('code', ''),
                'name': t.get('name', ''),
                'price': t.get('price', 0),
                'qty': t.get('qty', 0),
                'amount': t.get('amount', 0),
                'pnl': t.get('pnl', 0),
                'pnl_pct': t.get('pnl_pct', 0),
                'reason': t.get('reason', ''),
                'timestamp': t.get('timestamp', ''),
                'hash': t.get('hash', ''),
            })
        self._json({
            'total': len(trades),
            'trades': recent,
        })

    def log_message(self, fmt, *args):
        pass  # suppress logs

    def _handle_morning_analysis(self):
        """晨间综合分析数据"""
        data = load_json(os.path.join(DATA_DIR, 'morning_analysis.json'))
        if data:
            self._json(data)
        else:
            self._json({'error': '晨间分析数据暂无', 'update_time': None})

    def _handle_midday_analysis(self):
        """午间综合分析数据"""
        data = load_json(os.path.join(DATA_DIR, 'midday_analysis.json'))
        if data:
            self._json(data)
        else:
            self._json({'error': '午间分析数据暂无', 'update_time': None})

    def _handle_closing_analysis(self):
        """收盘综合分析数据"""
        data = load_json(os.path.join(DATA_DIR, 'closing_analysis.json'))
        if data:
            self._json(data)
        else:
            self._json({'error': '收盘分析数据暂无', 'update_time': None})

    def _handle_trading_reports(self):
        """返回交易报告（日报/周报/月报）"""
        reports = load_json(os.path.join(DATA_DIR, 'trading_reports.json'), {'daily': [], 'weekly': [], 'monthly': []})
        self._json(reports)

    def _handle_generate_report(self):
        """手动触发生成报告"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        rtype = params.get('type', ['daily'])[0]
        try:
            # 用subprocess调用generate_report.py
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'generate_report.py')
            r = subprocess.run(['python3', script, '--type', rtype],
                              capture_output=True, timeout=30, cwd=os.path.dirname(script))
            self._json({'ok': True, 'message': f'{rtype}报告已生成', 'output': r.stdout.decode()})
        except Exception as e:
            self._json({'error': str(e)})

    def _handle_strategy_tracks(self):
        """返回策略追踪数据"""
        summary = load_json(os.path.join(DATA_DIR, 'strategy_tracks_summary.json'), {})
        tracks = []
        track_dir = os.path.join(DATA_DIR, 'strategy_tracks')
        if os.path.isdir(track_dir):
            for f in sorted(os.listdir(track_dir), reverse=True)[:30]:
                if f.endswith('.json'):
                    t = load_json(os.path.join(track_dir, f))
                    if t: tracks.append(t)
        self._json({'summary': summary, 'tracks': tracks})

    def _handle_eod_analysis(self):
        """尾盘综合分析数据"""
        data = load_json(os.path.join(DATA_DIR, 'eod_analysis.json'))
        if data:
            self._json(data)
        else:
            self._json({'error': '尾盘分析数据暂无', 'update_time': None})

    def _handle_manual_buy(self, params):
        """手动买入：用户点击推荐股票的买入按钮"""
        code = params.get('code', '').strip()
        name = params.get('name', '').strip()
        price = float(params.get('price', 0))
        qty = int(params.get('qty', 0))
        reason = params.get('reason', '手动买入')

        if not code or not name:
            self._json({'error': '缺少股票代码或名称'})
            return
        if price <= 0 or qty <= 0:
            self._json({'error': '价格和数量必须大于0'})
            return

        amount = price * qty
        commission = max(5, round(amount * 0.0003, 2))  # 最低5元

        pf_path = os.path.join(DATA_DIR, 'portfolio.json')
        pf = load_json(pf_path)
        if not pf:
            pf = {'cash': 200000, 'initial_capital': 200000, 'holdings': {},
                  'total_assets': 200000, 'total_return': 0,
                  'trading_stats': {'total_trades': 0, 'win_trades': 0, 'lose_trades': 0, 'total_pnl': 0, 'total_commission': 0, 'max_drawdown': 0}}

        if pf['cash'] < amount + commission:
            self._json({'error': f'资金不足，需要{amount + commission:.2f}元，可用{pf["cash"]:.2f}元'})
            return

        # Update holdings
        holdings = pf.get('holdings', {})
        if code in holdings:
            h = holdings[code]
            old_total = h['avg_cost'] * h['qty']
            new_total = price * qty
            h['qty'] += qty
            h['avg_cost'] = round((old_total + new_total) / h['qty'], 3)
        else:
            holdings[code] = {
                'name': name, 'code': code,
                'qty': qty, 'avg_cost': price,
                'buy_date': time.strftime('%Y-%m-%d'),
                'buy_score': params.get('score', 0),
                'signals': params.get('signals', []),
            }
        pf['holdings'] = holdings
        pf['cash'] = round(pf['cash'] - amount - commission, 2)

        # Recalculate total assets
        total_position = sum(h['avg_cost'] * h['qty'] for h in holdings.values())
        pf['total_assets'] = round(pf['cash'] + total_position, 2)
        pf['total_return'] = round((pf['total_assets'] - pf['initial_capital']) / pf['initial_capital'] * 100, 2)

        # Stats
        stats = pf.get('trading_stats', {})
        stats['total_trades'] = stats.get('total_trades', 0) + 1
        stats['total_commission'] = round(stats.get('total_commission', 0) + commission, 2)
        pf['trading_stats'] = stats

        # Trade log
        tl_path = os.path.join(DATA_DIR, 'trade_log.json')
        tl = load_json(tl_path, {'trades': [], 'next_id': 1})
        trade = {
            'id': tl.get('next_id', 1),
            'type': 'buy',
            'code': code, 'name': name,
            'price': price, 'qty': qty,
            'amount': round(amount, 2),
            'commission': commission,
            'reason': reason,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        tl['trades'].append(trade)
        tl['next_id'] = trade['id'] + 1

        # Save
        with open(pf_path, 'w') as f:
            json.dump(pf, f, ensure_ascii=False, indent=2)
        with open(tl_path, 'w') as f:
            json.dump(tl, f, ensure_ascii=False, indent=2)

        self._json({'ok': True, 'message': f'买入 {name} {qty}股 × {price}元，手续费{commission}元', 'trade': trade, 'cash': pf['cash']})

    def _handle_real_portfolio(self, params=None):
        """真实持仓管理"""
        rp_path = os.path.join(DATA_DIR, 'real_portfolio.json')
        if params:
            action = params.get('action', '')
            
            if action == 'add':
                rp = load_json(rp_path, {'holdings': [], 'cash': params.get('cash', 0), 'initial': params.get('initial', 0)})
                code = params.get('code', '').strip()
                name = params.get('name', '').strip()
                cost = float(params.get('cost', 0))
                qty = int(params.get('qty', 0))
                if not code or cost <= 0 or qty <= 0:
                    self._json({'error': '参数不完整'})
                    return
                # 去重更新
                existing = [h for h in rp['holdings'] if h['code'] == code]
                if existing:
                    existing[0]['cost'] = cost
                    existing[0]['qty'] = qty
                    existing[0]['name'] = name
                else:
                    rp['holdings'].append({'code': code, 'name': name, 'cost': cost, 'qty': qty, 'stop_loss': params.get('stop_loss', 0), 'target_price': params.get('target_price', 0)})
                rp['cash'] = params.get('cash', rp.get('cash', 0))
                rp['initial'] = params.get('initial', rp.get('initial', 0))
                _save_json(rp_path, rp)
                self._json({'ok': True, 'message': f'已添加 {name}'})
            elif action == 'delete':
                rp = load_json(rp_path, {'holdings': []})
                code = params.get('code', '')
                rp['holdings'] = [h for h in rp['holdings'] if h['code'] != code]
                _save_json(rp_path, rp)
                self._json({'ok': True, 'message': '已删除'})
            elif action == 'update_settings':
                rp = load_json(rp_path, {'holdings': [], 'cash': 0, 'initial': 0})
                rp['cash'] = params.get('cash', rp.get('cash', 0))
                rp['initial'] = params.get('initial', rp.get('initial', 0))
                _save_json(rp_path, rp)
                self._json({'ok': True})
            elif action == 'import':
                rp = load_json(rp_path, {'holdings': [], 'cash': 0, 'initial': 0})
                stocks = params.get('stocks', [])
                for s in stocks:
                    existing = [h for h in rp['holdings'] if h['code'] == s['code']]
                    if existing:
                        existing[0]['cost'] = float(s.get('cost', 0))
                        existing[0]['qty'] = int(s.get('qty', 0))
                        existing[0]['name'] = s.get('name', '')
                    else:
                        rp['holdings'].append({'code': s['code'], 'name': s.get('name', ''), 'cost': float(s.get('cost', 0)), 'qty': int(s.get('qty', 0)), 'stop_loss': 0, 'target_price': 0})
                rp['cash'] = params.get('cash', rp.get('cash', 0))
                rp['initial'] = params.get('initial', rp.get('initial', 0))
                _save_json(rp_path, rp)
                self._json({'ok': True, 'message': f'已导入 {len(stocks)} 只股票'})
            else:
                self._json({'error': '未知操作'})
            return
        
        # GET: 返回真实持仓+实时价格
        rp = load_json(rp_path, {'holdings': [], 'cash': 0, 'initial': 0})
        holdings = rp.get('holdings', [])
        codes = [h['code'] for h in holdings]
        rt = get_cached_realtime(codes) if codes else {}
        
        total_cost = 0
        total_market = 0
        result = []
        for h in holdings:
            r = rt.get(h['code'], {})
            cp = r.get('price', h.get('cost', 0))
            if cp <= 0: cp = h.get('cost', 0)
            cost_val = h['cost'] * h['qty']
            market_val = cp * h['qty']
            total_cost += cost_val
            total_market += market_val
            pnl = market_val - cost_val
            pnl_pct = (cp - h['cost']) / h['cost'] * 100 if h['cost'] > 0 else 0
            
            # 查找推荐数据获取止盈止损
            rec_data = load_json(os.path.join(DATA_DIR, 'recommendations.json'), {})
            target = h.get('target_price') or 0
            stop = h.get('stop_loss') or 0
            if not target or not stop:
                for k in ['strong_buy', 'buy', 'watch']:
                    for s in rec_data.get(k, []):
                        if s.get('code') == h['code']:
                            if not target: target = s.get('target_price', 0)
                            if not stop: stop = s.get('stop_loss', 0)
                            break
            
            # 预警状态
            alert = ''
            if stop > 0 and cp <= stop:
                alert = 'stop'  # 触及止损
            elif target > 0 and cp >= target:
                alert = 'target'  # 触及止盈
            
            result.append({
                'code': h['code'], 'name': h['name'],
                'qty': h['qty'], 'cost': h['cost'],
                'current_price': cp, 'change_pct': r.get('change_pct', 0),
                'cost_value': round(cost_val, 2),
                'market_value': round(market_val, 2),
                'pnl': round(pnl, 2), 'pnl_pct': round(pnl_pct, 2),
                'target_price': round(target, 2) if target else 0,
                'stop_loss': round(stop, 2) if stop else 0,
                'alert': alert,
            })
        
        total_pnl = total_market - total_cost
        self._json({
            'holdings': result,
            'cash': rp.get('cash', 0),
            'initial': rp.get('initial', 0),
            'total_cost': round(total_cost, 2),
            'total_market': round(total_market, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_pct': round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
            'total_assets': round((rp.get('cash', 0)) + total_market, 2),
        })

    def _handle_broker_connect(self, params):
        """连接券商账户"""
        broker = params.get('broker', 'htsc')
        user = params.get('user', '')
        password = params.get('password', '')
        if not user or not password:
            self._json({'error': '请输入账号密码'})
            return
        try:
            # 尝试连接
            import easytrader
            session = easytrader.use('ht')
            session.prepare(user=user, password=password)
            # 获取持仓
            positions = session.position
            balance = session.balance
            # 保存到real_portfolio
            rp = {'holdings': [], 'cash': float(balance.get('可用资金', 0)), 'initial': float(balance.get('总资产', 0))}
            for p in positions:
                rp['holdings'].append({
                    'code': p.get('证券代码', '').strip(),
                    'name': p.get('证券名称', '').strip(),
                    'cost': float(p.get('成本价', 0)),
                    'qty': int(p.get('股票余额', 0)),
                    'stop_loss': 0, 'target_price': 0
                })
            _save_json(os.path.join(DATA_DIR, 'real_portfolio.json'), rp)
            # 保存登录凭证
            _save_json(os.path.join(DATA_DIR, 'broker_config.json'), {'broker': broker, 'user': user, 'password': password})
            self._json({'ok': True, 'count': len(positions), 'message': f'连接成功，已导入{len(positions)}只持仓'})
        except Exception as e:
            self._json({'error': f'连接失败: {e}'})

    def _handle_broker_sync(self):
        """同步券商持仓"""
        cfg = load_json(os.path.join(DATA_DIR, 'broker_config.json'))
        if not cfg.get('user'):
            self._json({'error': '请先连接券商账户'})
            return
        try:
            import easytrader
            session = easytrader.use('ht')
            session.prepare(user=cfg['user'], password=cfg['password'])
            positions = session.position
            balance = session.balance
            rp = {'holdings': [], 'cash': float(balance.get('可用资金', 0)), 'initial': float(balance.get('总资产', 0))}
            for p in positions:
                rp['holdings'].append({
                    'code': p.get('证券代码', '').strip(),
                    'name': p.get('证券名称', '').strip(),
                    'cost': float(p.get('成本价', 0)),
                    'qty': int(p.get('股票余额', 0)),
                    'stop_loss': 0, 'target_price': 0
                })
            _save_json(os.path.join(DATA_DIR, 'real_portfolio.json'), rp)
            self._json({'ok': True, 'count': len(positions), 'message': f'已同步{len(positions)}只持仓'})
        except Exception as e:
            self._json({'error': f'同步失败: {e}'})

    def _handle_broker_signals(self):
        """检查交易信号"""
        cfg = load_json(os.path.join(DATA_DIR, 'broker_config.json'))
        if not cfg.get('user'):
            self._json({'error': '请先连接券商账户'})
            return
        try:
            import easytrader
            session = easytrader.use('ht')
            session.prepare(user=cfg['user'], password=cfg['password'])
            positions = session.position
            rec = load_json(os.path.join(DATA_DIR, 'recommendations.json'), {})
            signals = []
            for p in positions:
                code = p.get('证券代码', '').strip()
                cost = float(p.get('成本价', 0))
                qty = int(p.get('股票余额', 0))
                price = float(p.get('市价', 0))
                pnl_pct = (price - cost) / cost * 100 if cost > 0 else 0
                target = stop = 0
                for k in ['strong_buy', 'buy']:
                    for s in rec.get(k, []):
                        if s.get('code') == code:
                            target = s.get('target_price', 0)
                            stop = s.get('stop_loss', 0)
                            break
                action = ''
                reason = ''
                if pnl_pct <= -8:
                    action = 'stop_loss'; reason = f'触及-8%止损线'
                elif stop > 0 and price <= stop:
                    action = 'stop_loss'; reason = f'触及止损价{stop}'
                elif target > 0 and price >= target:
                    action = 'take_profit'; reason = f'触及止盈价{target}'
                elif pnl_pct >= 15:
                    action = 'take_profit'; reason = f'盈利{pnl_pct:.0f}%'
                if action:
                    signals.append({'code': code, 'name': p.get('证券名称', ''), 'action': action, 'reason': reason, 'price': price, 'pnl_pct': round(pnl_pct, 2)})
            self._json({'ok': True, 'signals': signals})
        except Exception as e:
            self._json({'error': f'检查失败: {e}'})

    def _handle_auto_trade_config(self, params=None):
        """自动交易配置"""
        cfg_path = os.path.join(DATA_DIR, 'auto_trade_config.json')
        if params:
            _save_json(cfg_path, params)
            self._json({'ok': True, 'message': '配置已保存'})
        else:
            cfg = load_json(cfg_path, {'per_stock': 10000, 'stop_loss_pct': 5, 'take_profit_pct': 10, 'auto_buy': False, 'auto_sell': False})
            self._json(cfg)

    def _handle_batch_stop_profit(self, params):
        """批量设置止盈止损"""
        stop_pct = float(params.get('stop_loss_pct', 5))
        profit_pct = float(params.get('take_profit_pct', 10))
        rp_path = os.path.join(DATA_DIR, 'real_portfolio.json')
        rp = load_json(rp_path, {'holdings': []})
        for h in rp['holdings']:
            cost = h.get('cost', 0)
            if cost > 0:
                h['stop_loss'] = round(cost * (1 - stop_pct / 100), 2)
                h['target_price'] = round(cost * (1 + profit_pct / 100), 2)
        _save_json(rp_path, rp)
        self._json({'ok': True, 'message': f'已设置{len(rp["holdings"])}只股票的止盈止损'})

    def _handle_delete_holding(self, params):
        """删除持仓股票，退回资金，不计入盈亏"""
        code = params.get('code', '').strip()
        pf_path = os.path.join(DATA_DIR, 'portfolio.json')
        pf = load_json(pf_path)
        if not pf or code not in pf.get('holdings', {}):
            self._json({'error': '未找到该持仓'})
            return
        h = pf['holdings'][code]
        cost = h['avg_cost'] * h['qty']
        del pf['holdings'][code]
        pf['cash'] = round(pf['cash'] + cost, 2)
        total_position = sum(x['avg_cost'] * x['qty'] for x in pf['holdings'].values())
        pf['total_assets'] = round(pf['cash'] + total_position, 2)
        # 删除相关交易记录
        tl_path = os.path.join(DATA_DIR, 'trade_log.json')
        tl = load_json(tl_path, {'trades': [], 'next_id': 1})
        tl['trades'] = [t for t in tl.get('trades', []) if t.get('code') != code]
        with open(pf_path, 'w') as f: json.dump(pf, f, ensure_ascii=False, indent=2)
        with open(tl_path, 'w') as f: json.dump(tl, f, ensure_ascii=False, indent=2)
        self._json({'ok': True, 'message': f'已删除 {h["name"]}，退回 {cost:.2f} 元'})

    def _handle_manual_sell(self, params):
        """手动卖出"""
        code = params.get('code', '').strip()
        price = float(params.get('price', 0))
        qty = int(params.get('qty', 0))
        reason = params.get('reason', '手动卖出')

        if not code:
            self._json({'error': '缺少股票代码'})
            return
        if price <= 0 or qty <= 0:
            self._json({'error': '价格和数量必须大于0'})
            return

        pf_path = os.path.join(DATA_DIR, 'portfolio.json')
        pf = load_json(pf_path)
        if not pf:
            self._json({'error': '虚拟盘数据异常'})
            return

        holdings = pf.get('holdings', {})
        if code not in holdings:
            self._json({'error': '未持有该股票'})
            return

        h = holdings[code]
        if qty > h['qty']:
            self._json({'error': f'持有{h["qty"]}股，不能卖{qty}股'})
            return

        amount = price * qty
        commission = max(5, round(amount * 0.0003, 2))
        pnl = (price - h['avg_cost']) * qty - commission
        pnl_pct = round((price - h['avg_cost']) / h['avg_cost'] * 100, 2)
        name = h['name']

        # Update or remove holding
        if qty == h['qty']:
            del holdings[code]
        else:
            h['qty'] -= qty

        pf['holdings'] = holdings
        pf['cash'] = round(pf['cash'] + amount - commission, 2)

        # Recalculate
        total_position = sum(x['avg_cost'] * x['qty'] for x in holdings.values())
        pf['total_assets'] = round(pf['cash'] + total_position, 2)
        pf['total_return'] = round((pf['total_assets'] - pf['initial_capital']) / pf['initial_capital'] * 100, 2)

        # Stats
        stats = pf.get('trading_stats', {})
        stats['total_trades'] = stats.get('total_trades', 0) + 1
        stats['total_commission'] = round(stats.get('total_commission', 0) + commission, 2)
        stats['total_pnl'] = round(stats.get('total_pnl', 0) + pnl, 2)
        if pnl > 0:
            stats['win_trades'] = stats.get('win_trades', 0) + 1
        else:
            stats['lose_trades'] = stats.get('lose_trades', 0) + 1
        pf['trading_stats'] = stats

        # Trade log
        tl_path = os.path.join(DATA_DIR, 'trade_log.json')
        tl = load_json(tl_path, {'trades': [], 'next_id': 1})
        trade = {
            'id': tl.get('next_id', 1),
            'type': 'sell',
            'code': code, 'name': name,
            'price': price, 'qty': qty,
            'amount': round(amount, 2),
            'commission': commission,
            'pnl': round(pnl, 2),
            'pnl_pct': pnl_pct,
            'reason': reason,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        tl['trades'].append(trade)
        tl['next_id'] = trade['id'] + 1

        with open(pf_path, 'w') as f:
            json.dump(pf, f, ensure_ascii=False, indent=2)
        with open(tl_path, 'w') as f:
            json.dump(tl, f, ensure_ascii=False, indent=2)

        pnl_sign = '+' if pnl >= 0 else ''
        self._json({'ok': True, 'message': f'卖出 {name} {qty}股 × {price}元，{pnl_sign}{pnl:.2f}元({pnl_sign}{pnl_pct}%)', 'trade': trade, 'cash': pf['cash']})

    def _handle_reset_portfolio(self, params):
        """重置虚拟盘"""
        pf_path = os.path.join(DATA_DIR, 'portfolio.json')
        tl_path = os.path.join(DATA_DIR, 'trade_log.json')
        portfolio = {
            'cash': 200000, 'initial_capital': 200000, 'holdings': {},
            'total_assets': 200000, 'total_return': 0,
            'trading_stats': {'total_trades': 0, 'win_trades': 0, 'lose_trades': 0, 'total_pnl': 0, 'total_commission': 0, 'max_drawdown': 0}
        }
        trade_log = {'trades': [], 'next_id': 1}
        with open(pf_path, 'w') as f:
            json.dump(portfolio, f, ensure_ascii=False, indent=2)
        with open(tl_path, 'w') as f:
            json.dump(trade_log, f, ensure_ascii=False, indent=2)
        self._json({'ok': True, 'message': '虚拟盘已重置'})


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    server.daemon_threads = True
    server.allow_reuse_address = True
    print(f'Stock API server running on http://0.0.0.0:{PORT}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
