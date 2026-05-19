#!/usr/bin/env python3
"""轻量级API服务器 - 提供实时股票数据 (v2)"""
import json, time, os, sys, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
PORT = 8765

_session = requests.Session()
_session.headers.update({'User-Agent': 'Mozilla/5.0'})


def fetch_realtime(codes):
    """通过腾讯API批量获取实时行情"""
    if not codes:
        return {}
    url = 'https://qt.gtimg.cn/q=' + ','.join(codes)
    try:
        r = _session.get(url, timeout=10)
        result = {}
        for line in r.text.strip().split(';'):
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
    except Exception as e:
        return {}


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
    result = {}
    for i in range(0, len(codes), 50):
        batch = codes[i:i + 50]
        batch_data = fetch_realtime(batch)
        result.update(batch_data)
        if i + 50 < len(codes):
            time.sleep(0.1)

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

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == '/api/realtime':
                self._handle_realtime(parsed)
            elif path == '/api/portfolio':
                self._handle_portfolio()
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
            else:
                super().do_GET()
        except Exception as e:
            try:
                self._json({'error': str(e)})
            except Exception:
                pass

    def _handle_realtime(self, parsed):
        params = parse_qs(parsed.query)
        codes_str = params.get('codes', [''])[0]
        codes = [c.strip() for c in codes_str.split(',') if c.strip()]
        if not codes:
            codes = list(set(get_holding_codes() + get_rec_codes()))
        data = get_cached_realtime(codes)
        self._json({'ts': time.time(), 'data': data})

    def _handle_portfolio(self):
        pf = load_json(os.path.join(DATA_DIR, 'portfolio.json'), {})
        holdings = pf.get('holdings', {})

        # 返回基本信息，即使没有持仓
        if not holdings:
            self._json({
                'total_assets': pf.get('initial_capital', 100000),
                'cash': pf.get('cash', 100000),
                'total_return': 0,
                'holdings': [],
            })
            return

        codes = list(holdings.keys())
        rt = get_cached_realtime(codes) if codes else {}

        trade_log = load_json(os.path.join(DATA_DIR, 'trade_log.json'), {}).get('trades', [])

        result = []
        for code, h in holdings.items():
            r = rt.get(code, {})
            buys = [t for t in trade_log if t.get('code') == code and t.get('type') == 'buy']
            sells = [t for t in trade_log if t.get('code') == code and t.get('type') == 'sell']
            cp = r.get('price', h.get('current_price', 0))
            ac = h.get('avg_cost', 0)
            qty = h.get('qty', 0)
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

        self._json({
            'total_assets': pf.get('total_assets', 0),
            'cash': pf.get('cash', 0),
            'total_return': pf.get('total_return', 0),
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
            resp = _session.get('https://push2his.eastmoney.com/api/qt/stock/kline/get', params={
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

    def log_message(self, fmt, *args):
        pass  # suppress logs


if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    server.daemon_threads = True
    server.allow_reuse_address = True
    print(f'Stock API server running on http://127.0.0.1:{PORT}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
