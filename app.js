/* === A股智能分析系统 v3.0 === */

const App = {
  allData: null,
  recData: null,
  historyData: [],
  yesterdayData: null,
  recList: [],
  recPage: 0,
  recPageSize: 50,
  realtimeCache: {},
  realtimeTimer: null,
  API_BASE: '',
  watchTimer: null,
  tradeCheckTimer: null,
  _lastTradeCount: 0,

  // === 初始化 ===
  async init() {
    // 检测API服务器
    this._apiAvailable = false;
    try {
      const r = await fetch('/api/health');
      if (r.ok) { this.API_BASE = ''; this._apiAvailable = true; }
    } catch {
      try {
        const r = await fetch('http://127.0.0.1:8765/api/health');
        if (r.ok) { this.API_BASE = 'http://127.0.0.1:8765'; this._apiAvailable = true; }
      } catch {}
    }

    try {
      const [allRes, recRes] = await Promise.all([
        fetch('data/all_stocks.json'),
        fetch('data/recommendations.json')
      ]);
      if (!allRes.ok || !recRes.ok) throw new Error('数据未就绪');
      this.allData = await allRes.json();
      this.recData = await recRes.json();
      await this.loadHistory();
      this.renderHome();
      // 启动实时数据刷新
      if (this._apiAvailable) {
        this.startRealtimeRefresh();
        this.startWatchRefresh();
        this.startTradeNotification();
      }
    } catch (e) {
      document.getElementById('update-time').textContent = '暂无数据';
      document.getElementById('market-analysis').innerHTML =
        '<div class="empty"><div class="empty-icon">⏳</div><div>等待首次分析数据...</div></div>';
    }
  },

  // === 统一推荐买入加载 ===
  async loadUnifiedBuys() {
    try {
      const r = this._apiAvailable
        ? await fetch(`${this.API_BASE}/api/unified_buys`)
        : null;
      if (r && r.ok) {
        const data = await r.json();
        this.renderUnifiedBuys(data);
        return;
      }
    } catch {}
    // fallback: 从本地JSON加载
    try {
      const files = [
        { url: 'data/closing_analysis.json', key: 'tomorrow_buys' },
        { url: 'data/midday_analysis.json', key: 'top_buys' },
        { url: 'data/morning_analysis.json', key: 'top_buys' },
      ];
      const items = [];
      const seen = new Set();
      for (const f of files) {
        const res = await fetch(f.url);
        if (!res.ok) continue;
        const data = await res.json();
        const buys = data[f.key] || [];
        for (const s of buys) {
          if (!seen.has(s.code)) {
            seen.add(s.code);
            items.push(s);
          }
        }
      }
      this.renderUnifiedBuys({ items, total: items.length });
    } catch {}
  },

  renderUnifiedBuys(data) {
    const el = document.getElementById('unified-buys-list');
    const labelEl = document.getElementById('unified-source-label');
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = '<div class="empty">暂无推荐，等待分析更新...</div>';
      if (labelEl) labelEl.textContent = '';
      return;
    }
    const sources = data.sources || [];
    const sourceMap = {};
    for (const src of sources) sourceMap[src.code] = src.source;
    if (labelEl) labelEl.textContent = `以分析推荐为准 · ${items.length}只 · ${data.update_time || ''}`;

    let html = '<div style="display:flex;flex-direction:column;gap:8px">';
    items.forEach((item, idx) => {
      const curPrice = item.current_price || item.price || 0;
      const curChg = item.current_change_pct || item.change_pct || 0;
      const chgCls = curChg >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = curChg >= 0 ? '+' : '';
      const est = item.next_day_estimate;
      const estVal = est ? est.estimate : null;
      const estStr = estVal != null ? (estVal >= 0 ? '+' : '') + estVal.toFixed(1) + '%' : '-';
      const estCls = estVal != null ? (estVal >= 0 ? 'text-rise' : 'text-fall') : '';
      const src = item.source || sourceMap[item.code] || '';
      const srcTag = src ? `<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(59,130,246,0.15);color:#60a5fa">${this.esc(src)}</span>` : '';
      const signals = item.signals || [];
      const keySignals = signals.filter(s => ['均线多头排列','MA金叉','MACD金叉','红柱放大','放量','主力资金流入'].some(k => s.includes(k)));
      const reason = item.reason || signals.slice(0, 3).join('、') || '';
      const borderColors = ['#ef4444', '#f87171', '#fbbf24', '#fbbf24', '#fbbf24', '#fbbf24'];

      html += `<div style="background:var(--bg2);border-radius:10px;padding:12px 14px;cursor:pointer;border-left:3px solid ${borderColors[idx] || '#fbbf24'}" onclick="App.openStock('${item.code}')">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-weight:700;font-size:15px">${this.esc(item.name)}</span>
            <span style="color:var(--text3);font-size:11px">${item.code}</span>
            <span class="stock-rec-tag 强烈买入" style="font-size:11px">${item.score}分</span>
            ${srcTag}
          </div>
          <div style="text-align:right">
            <div style="font-weight:700;font-size:18px" class="${chgCls}">${curPrice.toFixed(2)}</div>
            <div style="font-size:11px" class="${chgCls}">${chgSign}${curChg.toFixed(2)}%</div>
          </div>
        </div>
        <div style="display:flex;gap:14px;font-size:11px;color:var(--text3);margin-bottom:6px;flex-wrap:wrap">
          <span>🎯 买入: <span style="color:var(--rise);font-weight:600">${item.buy_point?.toFixed(2) || '-'}</span></span>
          <span>📐 目标: <span style="color:var(--rise)">${item.target_price?.toFixed(2) || '-'}</span></span>
          <span>🛑 止损: <span style="color:var(--fall)">${item.stop_loss?.toFixed(2) || '-'}</span></span>
          <span>📊 预估: <span class="${estCls}" style="font-weight:600">${estStr}</span></span>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:4px">
          ${keySignals.slice(0, 5).map(s => `<span style="font-size:10px;background:rgba(239,68,68,0.12);color:#ef4444;padding:2px 6px;border-radius:4px">${this.esc(s)}</span>`).join('')}
        </div>
        <div style="font-size:11px;color:var(--text2)">💡 ${this.esc(reason)}</div>
        <div style="margin-top:6px;display:flex;justify-content:flex-end">
          <button onclick="event.stopPropagation();App.manualBuy('${item.code}','${this.esc(item.name)}',${item.buy_point || 0},${item.score || 0})" style="padding:4px 14px;background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3);border-radius:6px;cursor:pointer;font-size:12px;font-weight:600">买入</button>
        </div>
      </div>`;
    });
    html += '</div>';
    html += '<div style="text-align:center;padding:8px;font-size:10px;color:var(--text3)">来源于晨间/午间/收盘综合分析 · 趋势≥2信号 · 评分≥75 · RSI过滤 · 风险收益比加权</div>';
    el.innerHTML = html;
  },

  toggleRecDetail() {
    const s = document.getElementById('rec-detail-section');
    const i = document.getElementById('rec-toggle-icon');
    if (s.style.display === 'none') { s.style.display = ''; i.textContent = '▲ 收起'; }
    else { s.style.display = 'none'; i.textContent = '▼ 展开'; }
  },

  // === 统一推荐定时刷新 ===
  startWatchRefresh() {
    const refresh = async () => {
      try {
        const res = await fetch(this.API_BASE + '/api/unified_buys');
        if (!res.ok) return;
        const data = await res.json();
        this.renderUnifiedBuys(data);
      } catch {}
    };
    refresh();
    this.watchTimer = setInterval(refresh, 10000);
  },

  // === 交易通知检测 ===
  startTradeNotification() {
    // 初始化时记录当前交易数
    fetch(this.API_BASE + '/api/latest_trades').then(r => r.json()).then(d => {
      this._lastTradeCount = d.total || 0;
    }).catch(() => {});

    const check = async () => {
      try {
        const res = await fetch(this.API_BASE + '/api/latest_trades');
        if (!res.ok) return;
        const data = await res.json();
        const total = data.total || 0;
        const trades = data.trades || [];

        if (total > this._lastTradeCount && this._lastTradeCount > 0) {
          // 有新交易！
          const newTrades = trades.filter(t => {
            // 按时间戳过滤新的
            // 简单方式：展示所有最新的
            return true;
          });
          // 从最早的新交易开始通知（避免倒序）
          const newCount = total - this._lastTradeCount;
          const recent = trades.slice(-newCount);
          recent.forEach(t => {
            this.showTradeNotification(t);
            this.playTradeSound(t.type === 'buy');
          });
        }

        this._lastTradeCount = total;
      } catch {}
    };
    check();
    this.tradeCheckTimer = setInterval(check, 8000); // 8秒检测一次
  },

  showTradeNotification(trade) {
    const isBuy = trade.type === 'buy';
    const emoji = isBuy ? '✅' : '❌';
    const typeText = isBuy ? '买入成交' : '卖出成交';
    const typeCls = isBuy ? 'buy' : 'sell';

    const pnlHtml = trade.pnl != null ?
      `<div class="notif-pnl ${trade.pnl >= 0 ? 'positive' : 'negative'}">${emoji} 盈亏 ${trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(0)}元 (${trade.pnl >= 0 ? '+' : ''}${trade.pnl_pct.toFixed(1)}%)</div>` : '';

    const html = `
      <div class="notif-close" onclick="event.stopPropagation()">✕</div>
      <div class="notif-header">
        <span class="notif-type ${typeCls}">${emoji} ${typeText}</span>
        <span class="notif-time">${trade.timestamp}</span>
      </div>
      <div class="notif-body">
        <span class="notif-stock">${this.esc(trade.name)}（${trade.code}）</span>
        <span class="notif-price">${trade.qty}股 × ¥${trade.price.toFixed(2)}</span>
        <span>= ¥${(trade.amount || trade.price * trade.qty).toLocaleString('zh-CN', {maximumFractionDigits: 0})}</span>
        ${pnlHtml}
      </div>
      <div class="notif-reason">📋 ${this.esc(trade.reason || '')}</div>
    `;

    const el = document.getElementById('trade-notification');
    el.innerHTML = html;
    el.classList.add('show');

    // 5秒后自动收起，移到历史栈
    clearTimeout(this._notifTimer);
    this._notifTimer = setTimeout(() => this.dismissNotification(), 6000);
  },

  dismissNotification() {
    const el = document.getElementById('trade-notification');
    const html = el.innerHTML;
    if (html && el.classList.contains('show')) {
      // 移到历史栈
      const stack = document.getElementById('notif-stack');
      const item = document.createElement('div');
      item.className = 'notif-stack-item';
      item.innerHTML = html.replace('notif-close" onclick="event.stopPropagation()">✕</div>', '').replace('<div class="notif-header', '<div class="notif-stack-time" style="margin-bottom:4px">' + new Date().toLocaleTimeString() + '</div><div');
      stack.prepend(item);
      // 最多保留5条历史
      while (stack.children.length > 5) stack.removeChild(stack.lastChild);
    }
    el.classList.remove('show');
    clearTimeout(this._notifTimer);
  },

  playTradeSound(isBuy) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (isBuy) {
        // 买入：两声上升音阶
        [440, 660].forEach((freq, i) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.type = 'sine';
          osc.frequency.value = freq;
          gain.gain.setValueAtTime(0.15, ctx.currentTime + i * 0.15);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.15 + 0.3);
          osc.start(ctx.currentTime + i * 0.15);
          osc.stop(ctx.currentTime + i * 0.15 + 0.3);
        });
      } else {
        // 卖出：两声下降音阶
        [660, 440].forEach((freq, i) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.type = 'sine';
          osc.frequency.value = freq;
          gain.gain.setValueAtTime(0.15, ctx.currentTime + i * 0.15);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.15 + 0.3);
          osc.start(ctx.currentTime + i * 0.15);
          osc.stop(ctx.currentTime + i * 0.15 + 0.3);
        });
      }
    } catch (e) { /* 静默失败 */ }
  },

  renderWatchList(data) {
    const card = document.getElementById('watch-card');
    const el = document.getElementById('watch-plan-list');
    const timeEl = document.getElementById('watch-update-time');
    const items = data.items || [];

    if (!items.length) {
      card.style.display = 'none';
      return;
    }

    card.style.display = '';
    const now = new Date();
    timeEl.textContent = `每10秒刷新 · ${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;

    let html = '<div style="display:flex;flex-direction:column;gap:10px">';

    items.forEach(item => {
      const chgCls = item.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = item.change_pct >= 0 ? '+' : '';
      const priceDiff = item.current_price - item.target_price;
      const diffPct = item.target_price > 0 ? (priceDiff / item.target_price * 100) : 0;
      const diffCls = diffPct > 0 ? 'text-rise' : diffPct < -2 ? 'text-fall' : '';
      const diffLabel = diffPct > 0 ? '偏高于目标' : diffPct < -2 ? '低于目标✨' : '接近目标';
      const barInfo = item.bar_count > 0 ? `已采集${item.bar_count}根K线` : '等待开盘采集';

      // 信号标签
      const signals = item.signals || [];
      const buySignals = signals.filter(s => ['均线多头排列','MACD金叉','红柱放大','放量','主力资金流入'].some(k => s.includes(k)));

      html += `<div style="background:var(--bg2);border-radius:10px;padding:12px 14px;cursor:pointer" onclick="App.openStock('${item.code}')">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-weight:700;font-size:15px">${this.esc(item.name)}</span>
            <span style="color:var(--text3);font-size:11px">${item.code}</span>
            <span class="stock-rec-tag 强烈买入" style="font-size:11px">${item.score}分</span>
          </div>
          <div style="text-align:right">
            <div style="font-weight:700;font-size:18px" class="${chgCls}">${item.current_price.toFixed(2)}</div>
            <div style="font-size:12px" class="${chgCls}">${chgSign}${item.change_pct.toFixed(2)}%</div>
          </div>
        </div>
        <div style="display:flex;gap:16px;font-size:11px;color:var(--text3);margin-bottom:8px">
          <span>🎯 目标买入价: <span style="color:var(--fall);font-weight:600">${item.target_price.toFixed(2)}</span></span>
          <span>📍 价差: <span class="${diffCls}" style="font-weight:600">${diffLabel} (${diffPct >= 0 ? '+' : ''}${diffPct.toFixed(1)}%)</span></span>
          <span>📊 ${barInfo}</span>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:4px">
          ${buySignals.slice(0, 4).map(s => `<span style="font-size:10px;background:rgba(239,68,68,0.12);color:#ef4444;padding:2px 6px;border-radius:4px">${this.esc(s)}</span>`).join('')}
          ${buySignals.length > 4 ? `<span style="font-size:10px;color:var(--text3)">+${buySignals.length - 4}</span>` : ''}
        </div>
        <div style="margin-top:6px;font-size:11px;color:var(--text2);line-height:1.5">
          📋 ${this.esc(item.reason || '')}
        </div>
      </div>`;
    });

    html += '</div>';
    html += '<div style="text-align:center;padding:8px;font-size:10px;color:var(--text3)">每分钟技术分析（黄金分割·量价·K线·均线·量能·动量），3维信号共振才买入</div>';

    el.innerHTML = html;
  },

  // === 实时数据刷新 ===
  startRealtimeRefresh() {
    const refresh = async () => {
      try {
        // 获取持仓+推荐的实时数据
        const codes = this._getImportantCodes();
        if (!codes.length) return;
        const res = await fetch(this.API_BASE + '/api/realtime?codes=' + codes.join(','));
        if (!res.ok) return;
        const json = await res.json();
        if (json.data) {
          this.realtimeCache = json.data;
          this._updateDisplayWithRealtime();
        }
      } catch {}
    };
    // 立即刷新一次
    refresh();
    // 每30秒刷新
    this.realtimeTimer = setInterval(refresh, 30000);
  },

  _getImportantCodes() {
    const codes = new Set();
    // 持仓
    (this.allData?.stocks || []).filter(s => s._holding).forEach(s => codes.add(s.code));
    // 推荐
    const rec = this.recData || {};
    [...(rec.strong_buy || []), ...(rec.buy || []), ...(rec.watch || [])].forEach(s => codes.add(s.code));
    return [...codes];
  },

  _updateDisplayWithRealtime() {
    const rt = this.realtimeCache;
    if (!rt || !Object.keys(rt).length) return;

    // 更新首页上的价格和涨幅
    document.querySelectorAll('[data-rt-code]').forEach(el => {
      const code = el.dataset.rtCode;
      const field = el.dataset.rtField;
      const data = rt[code];
      if (!data) return;
      if (field === 'price') {
        el.textContent = data.price.toFixed(2);
      } else if (field === 'change_pct') {
        const sign = data.change_pct >= 0 ? '+' : '';
        el.textContent = sign + data.change_pct.toFixed(2) + '%';
        el.className = data.change_pct >= 0 ? 'text-rise' : 'text-fall';
        if (el.dataset.bold) el.style.fontWeight = '700';
      }
    });

    // 更新持仓卡片
    this._updatePortfolioRealtime(rt);
    // 更新虚拟交易持仓
    this._updateVirtualHoldingsRealtime(rt);
  },

  _updatePortfolioRealtime(rt) {
    document.querySelectorAll('.portfolio-item[data-holding-code]').forEach(el => {
      const code = el.dataset.holdingCode;
      const data = rt[code];
      if (!data) return;
      const cost = parseFloat(el.dataset.holdingCost) || 0;
      const qty = parseInt(el.dataset.holdingQty) || 0;
      const pnl = (data.price - cost) * qty;
      const pnlPct = cost > 0 ? (data.price - cost) / cost * 100 : 0;
      const cls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const sign = pnl >= 0 ? '+' : '';

      const priceEl = el.querySelector('.rt-price');
      const pnlEl = el.querySelector('.rt-pnl');
      const pctEl = el.querySelector('.rt-pct');
      if (priceEl) priceEl.textContent = '现价' + data.price.toFixed(2);
      if (pnlEl) { pnlEl.textContent = sign + pnl.toFixed(0) + '元'; pnlEl.className = 'portfolio-pnl rt-pnl ' + cls; }
      if (pctEl) { pctEl.textContent = sign + pnlPct.toFixed(2) + '%'; pctEl.className = 'portfolio-pnl rt-pct ' + cls; }
    });
  },

  _updateVirtualHoldingsRealtime(rt) {
    document.querySelectorAll('.vh-card[data-code]').forEach(el => {
      const code = el.dataset.code;
      const data = rt[code];
      if (!data) return;
      const cost = parseFloat(el.dataset.cost) || 0;
      const qty = parseInt(el.dataset.qty) || 0;
      const pnl = (data.price - cost) * qty;
      const pnlPct = cost > 0 ? (data.price - cost) / cost * 100 : 0;
      const cls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const sign = pnl >= 0 ? '+' : '';

      const priceSpan = el.querySelector('.vh-price');
      const pnlSpan = el.querySelector('.vh-pnl');
      const pctSpan = el.querySelector('.vh-pct');
      if (priceSpan) priceSpan.textContent = data.price.toFixed(2);
      if (pnlSpan) { pnlSpan.textContent = sign + pnl.toFixed(0) + '元'; pnlSpan.className = 'vh-pnl ' + cls; }
      if (pctSpan) { pctSpan.textContent = sign + pnlPct.toFixed(2) + '%'; pctSpan.className = 'vh-pct ' + cls; }
    });
  },

  // === 加载历史数据 ===
  async loadHistory() {
    try {
      if (this._apiAvailable) {
        const res = await fetch(this.API_BASE + '/api/history_list');
        if (res.ok) {
          this.historyListData = await res.json();
        }
      }
      const res = await fetch('data/history/');
      const text = await res.text();
      const files = text.match(/"[^"]+\.json"/g);
      if (!files) return;
      const fileNames = files.map(f => f.replace(/"/g, '').split('/').pop()).sort().reverse();
      const promises = fileNames.map(f => fetch(`data/history/${f}`, {cache: 'no-store'}).then(r => r.json()).catch(() => null));
      const results = await Promise.all(promises);
      this.historyData = results.filter(Boolean);
      if (this.historyData.length >= 2) this.yesterdayData = this.historyData[1];
    } catch (e) {
      console.log('历史数据加载失败:', e);
    }
  },

  // === 首页渲染 ===
  renderHome() {
    const r = this.recData;
    document.getElementById('update-time').textContent = this.allData.update_time + (this._apiAvailable ? ' · 实时' : '');
    const sentEl = document.getElementById('market-sentiment');
    sentEl.textContent = r.market_sentiment + ' · ' + r.avg_score + '分';
    sentEl.className = 'sentiment ' + r.market_sentiment;

    document.getElementById('stat-strong').textContent = (r.strong_buy || []).length;
    document.getElementById('stat-buy').textContent = (r.buy || []).length;
    document.getElementById('stat-watch').textContent = (r.watch || []).length;

    this.renderRecList('strong-buy-list', r.strong_buy || []);
    this.renderRecList('buy-list', r.buy || []);
    this.renderRecList('watch-buy-list', r.watch || []);

    // 统一推荐买入（主力数据源）
    this.loadUnifiedBuys();

    this.loadMorningAnalysis();
    this.loadMiddayAnalysis();
    this.loadEodAnalysis();
    this.loadClosingAnalysis();
    this.renderStrategies(r);
    this.renderAccuracy();
    this.renderPortfolio();
    this.renderVirtualHoldings();
  },

  // === 晨间综合分析 ===
  async loadMorningAnalysis() {
    try {
      const r = this._apiAvailable
        ? await fetch(`${this.API_BASE}/api/morning_analysis`)
        : await fetch('data/morning_analysis.json');
      if (r.ok) {
        const data = await r.json();
        this.renderMorningAnalysis(data);
      }
    } catch {}
  },

  renderMorningAnalysis(data) {
    if (!data || data.error) return;

    const el = document.getElementById('morning-analysis-section');
    const ts = document.getElementById('morning-update-time');
    if (ts && data.update_time) {
      ts.textContent = data.update_time;  // 显示完整日期+时间
    }

    const strategy = data.strategy || {};
    const riskScore = strategy.risk_score || 50;
    const riskLevel = riskScore >= 70 ? '高' : riskScore >= 55 ? '中高' : riskScore >= 40 ? '中低' : '低';
    const riskColor = riskScore >= 70 ? '#ef4444' : riskScore >= 55 ? '#f59e0b' : '#22c55e';
    const riskBg = riskScore >= 70 ? 'rgba(239,68,68,0.1)' : riskScore >= 55 ? 'rgba(245,158,11,0.1)' : 'rgba(34,197,94,0.1)';

    // 各维度行情
    const usIdx = data.us_indices || {};
    const usImpact = data.us_impact || {};
    const commodities = data.commodities || {};
    const fx = data.fx || {};
    const globalIdx = data.global_indices || {};
    const cnIdx = data.cn_indices || {};

    const _fmtSection = (items) => items.map(([code, info]) => {
      const emoji = info.change_pct >= 0 ? '📈' : '📉';
      const cls = info.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const sign = info.change_pct >= 0 ? '+' : '';
      if (info.unit) return `<span style="margin-right:10px">${emoji} ${info.name} <span class="${cls}">${sign}${info.change_pct.toFixed(2)}%</span></span>`;
      if (code === 'usdcnh') return `<span style="margin-right:10px">💵 ${info.name} ${info.price.toFixed(4)} (<span class="${info.change_pct > 0 ? 'text-fall' : 'text-rise'}">${sign}${info.change_pct.toFixed(2)}%</span>)</span>`;
      return `<span style="margin-right:10px">${emoji} ${info.name} <span class="${cls}">${sign}${info.change_pct.toFixed(2)}%</span></span>`;
    }).join('');

    const usDirection = usImpact.direction || '未知';
    const usColor = usDirection.includes('利空') ? '#ef4444' : usDirection.includes('利好') ? '#22c55e' : '#94a3b8';

    // 外围综合影响总结
    const impactSummary = data.impact_summary || '';
    const impactHtml = impactSummary ? `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:2px;font-size:11px;line-height:1.6;color:var(--text2);white-space:pre-line;overflow:hidden;display:-webkit-box;-webkit-line-clamp:8;-webkit-box-orient:vertical"><span style="font-weight:600;color:var(--text1)">🌐 外围综合影响</span>\n${this.esc(impactSummary)}</div>` : '';

    // 建议买入3只（今日买入明日卖出）
    const topBuys = data.top_buys || [];
    const topBuysHtml = topBuys.length > 0 ? (() => {
      const hdr = `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;margin-top:4px">
        <span style="font-size:12px;font-weight:600">💰 建议买入（${topBuys.length}只 · 今日买明日卖）</span>
        <div style="display:flex;align-items:center;gap:6px;padding:3px 0 1px;margin-top:4px;font-size:10px;color:var(--text3)">
          <span style="min-width:52px">名称</span>
          <span style="min-width:48px">代码</span>
          <span style="min-width:52px;text-align:right">当前涨幅</span>
          <span style="min-width:50px;text-align:right">明日预估</span>
          <span style="min-width:52px;text-align:right">买入价</span>
          <span style="min-width:52px;text-align:right">目标价</span>
          <span style="min-width:46px;text-align:right">止损</span>
          <span style="min-width:34px;text-align:right">评分</span>
        </div>`;
      const rows = topBuys.map((s, i) => {
        const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
        const chgSign = s.change_pct >= 0 ? '+' : '';
        const est = s.next_day_estimate;
        const estVal = est ? est.estimate : null;
        const estStr = estVal != null ? (estVal >= 0 ? '+' : '') + estVal.toFixed(1) + '%' : '-';
        const estCls = estVal != null ? (estVal >= 0 ? 'text-rise' : 'text-fall') : '';
        return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;${i > 0 ? 'border-top:1px solid rgba(255,255,255,0.04)' : ''}">
          <div style="flex:1;cursor:pointer;display:flex;align-items:center;gap:6px" onclick="App.openStock('${s.code}')">
          <span style="font-weight:600;color:var(--text1);min-width:52px;font-size:12px">${this.esc(s.name)}</span>
          <span style="font-size:10px;color:var(--text3);min-width:48px">${s.code}</span>
          <span style="min-width:52px;text-align:right" class="${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</span>
          <span style="min-width:50px;text-align:right;font-size:11px" class="${estCls}">${estStr}</span>
          <span style="min-width:52px;text-align:right;font-size:11px;color:var(--rise)">${s.buy_point?.toFixed(2) || '-'}</span>
          <span style="min-width:52px;text-align:right;font-size:11px;color:var(--rise)">${s.target_price?.toFixed(2) || '-'}</span>
          <span style="min-width:46px;text-align:right;font-size:11px;color:var(--fall)">${s.stop_loss?.toFixed(2) || '-'}</span>
          <span style="min-width:34px;text-align:right;color:var(--text2);font-size:11px">${s.score}</span>
          </div>
          <div style="font-size:10px;color:var(--text2);margin-top:2px;padding-left:106px">💡 ${this.esc(s.reason || s.signals?.slice(0,2).join('、') || '')}</div>
          <button onclick="event.stopPropagation();App.manualBuy('${s.code}','${this.esc(s.name)}',${s.buy_point || 0},${s.score || 0})" style="padding:2px 8px;background:#22c55e22;color:#22c55e;border:1px solid #22c55e44;border-radius:4px;cursor:pointer;font-size:11px;white-space:nowrap">买入</button>
        </div>`;
      }).join('');
      return hdr + '<div style="margin-top:1px">' + rows + '</div></div>';
    })() : '';

    let html = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;margin-bottom:6px">
        <div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
            <span style="font-size:12px;font-weight:600">🇺🇸 美股隔夜</span>
            <span style="font-size:10px;color:${usColor};background:${usColor}15;padding:1px 6px;border-radius:8px">对A股：${usDirection}</span>
          </div>
          <div style="font-size:11px;line-height:1.5">${_fmtSection(Object.entries(usIdx)) || '<span style="color:var(--text3)">暂无数据</span>'}</div>
        </div>
        <div>
          <span style="font-size:12px;font-weight:600">🌏 全球市场</span>
          <div style="font-size:11px;line-height:1.5;margin-top:3px">${_fmtSection(Object.entries(globalIdx)) || '<span style="color:var(--text3)">-</span>'}</div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 16px;margin-bottom:6px;font-size:11px;line-height:1.5">
        ${Object.keys(commodities).length ? `<div><span style="font-size:12px;font-weight:600">📦 大宗商品</span><div style="margin-top:2px">${_fmtSection(Object.entries(commodities))}</div></div>` : '<div></div>'}
        ${Object.keys(fx).length ? `<div><span style="font-size:12px;font-weight:600">💱 汇率</span><div style="margin-top:2px">${_fmtSection(Object.entries(fx))}</div></div>` : '<div></div>'}
      </div>

      <div style="display:grid;grid-template-columns:auto 1fr;gap:8px 12px;border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:2px">
        <div style="display:flex;flex-direction:column;align-items:center;gap:2px">
          <span style="font-size:11px;font-weight:600;color:var(--text2)">🎯 当日风险评估</span>
          <span style="background:${riskBg};color:${riskColor};padding:4px 10px;border-radius:8px;font-size:16px;font-weight:700;line-height:1.2;text-align:center">${riskScore}<div style="font-size:9px;font-weight:400;margin-top:2px">${riskLevel}风险</div></span>
        </div>
        <div style="font-size:11px;line-height:1.5;color:var(--text2);white-space:pre-line;overflow:hidden;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical">${(strategy.strategy_text || '').replace(/\*\*/g, '')}</div>
      </div>

      ${impactHtml}
      ${topBuysHtml}
    `;

    el.innerHTML = html;
  },

  // === 午间综合分析 ===
  async loadMiddayAnalysis() {
    try {
      const r = this._apiAvailable
        ? await fetch(`${this.API_BASE}/api/midday_analysis`)
        : await fetch('data/midday_analysis.json');
      if (r.ok) {
        const data = await r.json();
        this.renderMiddayAnalysis(data);
      }
    } catch {}
  },

  renderMiddayAnalysis(data) {
    if (!data || data.error) return;

    const el = document.getElementById('midday-analysis-section');
    const ts = document.getElementById('midday-update-time');
    if (ts && data.update_time) {
      ts.textContent = data.update_time;  // 显示完整日期+时间
    }

    const strategy = data.strategy || {};
    const riskScore = strategy.risk_score || 50;
    const riskLevel = riskScore >= 70 ? '高' : riskScore >= 55 ? '中高' : riskScore >= 40 ? '中低' : '低';
    const riskColor = riskScore >= 70 ? '#ef4444' : riskScore >= 55 ? '#f59e0b' : '#22c55e';
    const riskBg = riskScore >= 70 ? 'rgba(239,68,68,0.1)' : riskScore >= 55 ? 'rgba(245,158,11,0.1)' : 'rgba(34,197,94,0.1)';

    const usIdx = data.us_indices || {};
    const commodities = data.commodities || {};
    const fx = data.fx || {};
    const globalIdx = data.global_indices || {};
    const cnIdx = data.cn_indices || {};

    const _fmt = (items) => items.map(([code, info]) => {
      const emoji = info.change_pct >= 0 ? '📈' : '📉';
      const cls = info.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const sign = info.change_pct >= 0 ? '+' : '';
      if (info.unit) return `<span style="margin-right:10px">${emoji} ${info.name} <span class="${cls}">${sign}${info.change_pct.toFixed(2)}%</span></span>`;
      return `<span style="margin-right:10px">${emoji} ${info.name} <span class="${cls}">${sign}${info.change_pct.toFixed(2)}%</span></span>`;
    }).join('');

    // 半日市场概况
    let cnHtml = '';
    if (Object.keys(cnIdx).length) {
      cnHtml = `<div style="margin-bottom:6px">
        <span style="font-size:12px;font-weight:600">🇨🇳 A股半日行情</span>
        <div style="font-size:11px;line-height:1.5;margin-top:2px">${_fmt(Object.entries(cnIdx))}</div>
        ${data.market_summary ? `<div style="font-size:10px;color:var(--text3);margin-top:1px">${this.esc(data.market_summary)}</div>` : ''}
      </div>`;
    }

    // 外围综合影响总结
    const midImpactSummary = data.impact_summary || '';
    const midImpactHtml = midImpactSummary ? `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:2px;font-size:11px;line-height:1.6;color:var(--text2);white-space:pre-line;overflow:hidden;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical"><span style="font-weight:600;color:var(--text1)">🌐 外围最新动态</span>\n${this.esc(midImpactSummary)}</div>` : '';

    // 建议买入（今日买入明日卖出）
    const topBuys = data.top_buys || [];
    const topBuysHtml = topBuys.length > 0 ? (() => {
      const hdr = `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;margin-top:4px">
        <span style="font-size:12px;font-weight:600">💰 午后建议买入（${topBuys.length}只 · 今日买明日卖）</span>
        <div style="display:flex;align-items:center;gap:6px;padding:3px 0 1px;margin-top:4px;font-size:10px;color:var(--text3)">
          <span style="min-width:52px">名称</span>
          <span style="min-width:48px">代码</span>
          <span style="min-width:52px;text-align:right">当前涨幅</span>
          <span style="min-width:50px;text-align:right">明日预估</span>
          <span style="min-width:52px;text-align:right">买入价</span>
          <span style="min-width:52px;text-align:right">目标价</span>
          <span style="min-width:46px;text-align:right">止损</span>
          <span style="min-width:34px;text-align:right">评分</span>
        </div>`;
      const rows = topBuys.map((s, i) => {
        const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
        const chgSign = s.change_pct >= 0 ? '+' : '';
        const est = s.next_day_estimate;
        const estVal = est ? est.estimate : null;
        const estStr = estVal != null ? (estVal >= 0 ? '+' : '') + estVal.toFixed(1) + '%' : '-';
        const estCls = estVal != null ? (estVal >= 0 ? 'text-rise' : 'text-fall') : '';
        return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;${i > 0 ? 'border-top:1px solid rgba(255,255,255,0.04)' : ''};flex-wrap:wrap">
          <div style="flex:1;cursor:pointer;display:flex;align-items:center;gap:6px" onclick="App.openStock('${s.code}')">
          <span style="font-weight:600;color:var(--text1);min-width:52px;font-size:12px">${this.esc(s.name)}</span>
          <span style="font-size:10px;color:var(--text3);min-width:48px">${s.code}</span>
          <span style="min-width:52px;text-align:right" class="${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</span>
          <span style="min-width:50px;text-align:right;font-size:11px" class="${estCls}">${estStr}</span>
          <span style="min-width:52px;text-align:right;font-size:11px;color:var(--rise)">${s.buy_point?.toFixed(2) || '-'}</span>
          <span style="min-width:52px;text-align:right;font-size:11px;color:var(--rise)">${s.target_price?.toFixed(2) || '-'}</span>
          <span style="min-width:46px;text-align:right;font-size:11px;color:var(--fall)">${s.stop_loss?.toFixed(2) || '-'}</span>
          <span style="min-width:34px;text-align:right;color:var(--text2);font-size:11px">${s.score}</span>
          </div>
          <div style="width:100%;font-size:10px;color:var(--text2);padding-left:106px">💡 ${this.esc(s.reason || s.signals?.slice(0,2).join('、') || '')}</div>
          <button onclick="event.stopPropagation();App.manualBuy('${s.code}','${this.esc(s.name)}',${s.buy_point || 0},${s.score || 0})" style="padding:2px 8px;background:#22c55e22;color:#22c55e;border:1px solid #22c55e44;border-radius:4px;cursor:pointer;font-size:11px;white-space:nowrap">买入</button>
        </div>`;
      }).join('');
      return hdr + '<div style="margin-top:1px">' + rows + '</div></div>';
    })() : '';

    // 大宗商品+汇率+全球 合并两列
    const extraHtml = (Object.keys(commodities).length || Object.keys(fx).length || Object.keys(globalIdx).length)
      ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 16px;margin-bottom:6px;font-size:11px;line-height:1.5">
          ${(Object.keys(commodities).length || Object.keys(fx).length)
            ? `<div>${Object.keys(commodities).length ? `<span style="font-size:12px;font-weight:600">📦 大宗商品</span><div style="margin-top:2px">${_fmt(Object.entries(commodities))}</div>` : ''}${Object.keys(fx).length ? `<div style="margin-top:3px"><span style="font-size:12px;font-weight:600">💱 汇率</span><div style="margin-top:2px">${_fmt(Object.entries(fx))}</div></div>` : ''}</div>`
            : '<div></div>'}
          ${Object.keys(globalIdx).length
            ? `<div><span style="font-size:12px;font-weight:600">🌏 亚太/欧洲</span><div style="margin-top:2px">${_fmt(Object.entries(globalIdx))}</div></div>`
            : '<div></div>'}
        </div>`
      : '';

    html = cnHtml + extraHtml;

    html += `<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 12px;border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:2px">
      <div style="display:flex;flex-direction:column;align-items:center;gap:2px">
        <span style="font-size:11px;font-weight:600;color:var(--text2)">🎯 午后风险评估</span>
        <span style="background:${riskBg};color:${riskColor};padding:4px 10px;border-radius:8px;font-size:16px;font-weight:700;line-height:1.2;text-align:center">${riskScore}<div style="font-size:9px;font-weight:400;margin-top:2px">${riskLevel}风险</div></span>
      </div>
      <div style="font-size:11px;line-height:1.5;color:var(--text2);white-space:pre-line;overflow:hidden;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical">${(strategy.strategy_text || '').replace(/\*\*/g, '')}</div>
    </div>`;

    html += midImpactHtml;
    html += topBuysHtml;

    el.innerHTML = html;
  },

  // === 尾盘综合分析 ===

  async loadEodAnalysis() {
    try {
      const r = this._apiAvailable
        ? await fetch(`${this.API_BASE}/api/eod_analysis`)
        : await fetch('data/eod_analysis.json');
      if (r.ok) {
        const data = await r.json();
        this.renderEodAnalysis(data);
      }
    } catch {}
  },

  renderEodAnalysis(data) {
    if (!data || data.error) return;

    const el = document.getElementById('eod-analysis-section');
    const ts = document.getElementById('eod-update-time');
    if (ts && data.update_time) {
      ts.textContent = data.update_time;
    }

    const cnIdx = data.cn_indices || {};
    const sentiment = data.sentiment || {};
    const perfs = data.recommended_stocks || [];
    const stats = data.market_stats || {};
    const advices = data.advices || [];

    // A股即时行情
    let cnHtml = '';
    if (Object.keys(cnIdx).length) {
      const items = Object.entries(cnIdx).map(([code, info]) => {
        const emoji = info.change_pct >= 0 ? '📈' : '📉';
        const cls = info.change_pct >= 0 ? 'text-rise' : 'text-fall';
        const sign = info.change_pct >= 0 ? '+' : '';
        return `<span style="margin-right:10px">${emoji} ${info.name} <span class="${cls}">${sign}${info.change_pct.toFixed(2)}%</span></span>`;
      }).join('');
      cnHtml = `<div style="margin-bottom:6px">
        <span style="font-size:12px;font-weight:600">🇨🇳 A股即时行情</span>
        <div style="font-size:11px;line-height:1.5;margin-top:2px">${items}</div>
      </div>`;
    }

    // 市场情绪评级
    let sentimentHtml = '';
    if (Object.keys(sentiment).length) {
      const rows = Object.entries(sentiment).map(([code, s]) => {
        const idx = cnIdx[code] || {};
        return `<span style="display:inline-flex;align-items:center;gap:3px;margin-right:10px;font-size:11px;padding:2px 8px;border-radius:6px;background:rgba(255,255,255,0.04)">
          ${s.emoji} <span style="font-weight:600">${idx.name || code}</span> <span style="color:${s.score >= 60 ? 'var(--rise)' : s.score >= 40 ? '#f59e0b' : 'var(--fall)'}">${s.level}</span>
        </span>`;
      }).join('');
      sentimentHtml = `<div style="margin-bottom:6px"><span style="font-size:12px;font-weight:600">🌡️ 盘中情绪</span><div style="margin-top:2px">${rows}</div></div>`;
    }

    // 市场概况
    let statsHtml = '';
    if (stats.total) {
      const upCls = stats.up_ratio >= 60 ? 'text-rise' : stats.up_ratio >= 40 ? '' : 'text-fall';
      statsHtml = `<div style="margin-bottom:6px;font-size:11px;line-height:1.5;color:var(--text2)">
        📊 涨跌: <span class="text-rise">${stats.up}涨</span> / <span class="text-fall">${stats.down}跌</span> / ${stats.flat}平 · 
        涨停<span style="color:var(--rise)">${stats.limit_up}</span> / 跌停<span style="color:var(--fall)">${stats.limit_down}</span> · 
        赚钱效应 <span class="${upCls}">${stats.up_ratio}%</span> · 平均 <span class="${stats.avg_change >= 0 ? 'text-rise' : 'text-fall'}">${stats.avg_change >= 0 ? '+' : ''}${stats.avg_change}%</span>
      </div>`;
    }

    // 推荐股票表现
    let perfHtml = '';
    if (perfs.length > 0) {
      const hdr = `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;margin-top:4px">
        <span style="font-size:12px;font-weight:600">🎯 推荐股票表现</span>
        <div style="display:flex;align-items:center;gap:6px;padding:3px 0 1px;margin-top:4px;font-size:10px;color:var(--text3)">
          <span style="min-width:52px">名称</span>
          <span style="min-width:48px">代码</span>
          <span style="min-width:52px;text-align:right">现价</span>
          <span style="min-width:52px;text-align:right">涨幅</span>
          <span style="min-width:52px;text-align:right">浮盈</span>
          <span style="flex:1;text-align:right">操作建议</span>
        </div>`;
      const rows = perfs.map((p, i) => {
        const chgCls = p.change_pct >= 0 ? 'text-rise' : 'text-fall';
        const chgSign = p.change_pct >= 0 ? '+' : '';
        const pnlCls = p.pnl_pct >= 0 ? 'text-rise' : 'text-fall';
        const pnlSign = p.pnl_pct >= 0 ? '+' : '';
        const actionColor = p.action_type === '止损' ? 'var(--fall)' : p.action_type === '止盈' ? 'var(--rise)' : p.action_type === '持有' ? '#22c55e' : '#f59e0b';
        return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;${i > 0 ? 'border-top:1px solid rgba(255,255,255,0.04)' : ''}">
          <div style="flex:1;cursor:pointer;display:flex;align-items:center;gap:6px" onclick="App.openStock('${p.code}')">
            <span style="font-weight:600;color:var(--text1);min-width:52px;font-size:12px">${this.esc(p.name)}</span>
            <span style="font-size:10px;color:var(--text3);min-width:48px">${p.code}</span>
            <span style="min-width:52px;text-align:right;font-size:11px">${p.current_price?.toFixed(2) || '-'}</span>
            <span style="min-width:52px;text-align:right" class="${chgCls}">${chgSign}${p.change_pct?.toFixed(2) || '0'}%</span>
            <span style="min-width:52px;text-align:right" class="${pnlCls}">${pnlSign}${p.pnl_pct?.toFixed(1) || '0'}%</span>
          </div>
          <span style="flex:1;text-align:right;font-size:11px;color:${actionColor};white-space:nowrap">${p.action || '-'}</span>
        </div>`;
      }).join('');
      perfHtml = hdr + '<div style="margin-top:1px">' + rows + '</div></div>';
    }

    // 尾盘新推荐股票
    const topBuys = data.top_buys || [];
    let recHtml = '';
    if (topBuys.length > 0) {
      const recHdr = `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;margin-top:4px">
        <span style="font-size:12px;font-weight:600">🎯 尾盘推荐买入</span>
        <div style="display:flex;align-items:center;gap:6px;padding:3px 0 1px;margin-top:4px;font-size:10px;color:var(--text3)">
          <span style="min-width:52px">名称</span>
          <span style="min-width:48px">代码</span>
          <span style="min-width:52px;text-align:right">评分</span>
          <span style="min-width:52px;text-align:right">买点</span>
          <span style="min-width:52px;text-align:right">目标</span>
          <span style="min-width:52px;text-align:right">止损</span>
          <span style="flex:1;text-align:right">趋势信号</span>
        </div>`;
      const recRows = topBuys.map((s, i) => {
        const scoreColor = s.score >= 90 ? 'var(--rise)' : s.score >= 80 ? '#22c55e' : '#f59e0b';
        const signals = (s.signals || []).slice(0, 3).map(sig => {
          if (sig === '均线多头排列') return '多头';
          if (sig === 'MACD金叉') return '金叉';
          if (sig === '放量') return '放量';
          return sig;
        }).join('·');
        return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;${i > 0 ? 'border-top:1px solid rgba(255,255,255,0.04)' : ''}">
          <div style="flex:1;cursor:pointer;display:flex;align-items:center;gap:6px" onclick="App.openStock('${s.code}')">
            <span style="font-weight:600;color:var(--text1);min-width:52px;font-size:12px">${this.esc(s.name)}</span>
            <span style="font-size:10px;color:var(--text3);min-width:48px">${s.code}</span>
            <span style="min-width:52px;text-align:right;font-weight:700;color:${scoreColor};font-size:12px">${s.score}</span>
            <span style="min-width:52px;text-align:right;font-size:11px;color:var(--rise)">${s.buy_point?.toFixed(2) || '-'}</span>
            <span style="min-width:52px;text-align:right;font-size:11px">${s.target_price?.toFixed(2) || '-'}</span>
            <span style="min-width:52px;text-align:right;font-size:11px;color:var(--fall)">${s.stop_loss?.toFixed(2) || '-'}</span>
          </div>
          <span style="flex:1;text-align:right;font-size:10px;color:var(--text2);white-space:nowrap">${signals}</span>
        </div>`;
      }).join('');
      recHtml = recHdr + '<div style="margin-top:1px">' + recRows + '</div></div>';
    }

    // 尾盘操作建议
    let adviceHtml = '';
    if (advices.length > 0) {
      const items = advices.map(a => `<div style="font-size:11px;line-height:1.5;color:var(--text2);padding:2px 0">${a}</div>`).join('');
      adviceHtml = `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:4px">
        <span style="font-size:12px;font-weight:600">💡 尾盘操作建议</span>
        <div style="margin-top:4px">${items}</div>
      </div>`;
    }

    el.innerHTML = cnHtml + sentimentHtml + statsHtml + recHtml + perfHtml + adviceHtml;
  },

  // === 收盘综合分析 ===
  async loadClosingAnalysis() {
    try {
      const r = this._apiAvailable
        ? await fetch(`${this.API_BASE}/api/closing_analysis`)
        : await fetch('data/closing_analysis.json');
      if (r.ok) {
        const data = await r.json();
        this.renderClosingAnalysis(data);
      }
    } catch {}
  },

  renderClosingAnalysis(data) {
    if (!data || data.error) return;

    const el = document.getElementById('closing-analysis-section');
    const ts = document.getElementById('closing-update-time');
    if (ts && data.update_time) {
      ts.textContent = data.update_time;
    }

    const perfs = data.performances || [];
    const cnIdx = data.cn_indices || {};
    const tomorrowRisk = data.tomorrow_risk || {};
    const tomorrowBuys = data.tomorrow_buys || [];
    const summary = data.summary || '';

    const riskScore = tomorrowRisk.risk_score || 50;
    const riskLevel = tomorrowRisk.risk_level || '中低';
    const riskColor = riskScore >= 70 ? '#ef4444' : riskScore >= 55 ? '#f59e0b' : '#22c55e';
    const riskBg = riskScore >= 70 ? 'rgba(239,68,68,0.1)' : riskScore >= 55 ? 'rgba(245,158,11,0.1)' : 'rgba(34,197,94,0.1)';

    // A股收盘
    let cnHtml = '';
    if (Object.keys(cnIdx).length) {
      cnHtml = `<div style="margin-bottom:6px">
        <span style="font-size:12px;font-weight:600">🇨🇳 A股收盘</span>
        <div style="font-size:11px;line-height:1.5;margin-top:2px">${Object.values(cnIdx).map(i => {
          const cls = i.change_pct >= 0 ? 'text-rise' : 'text-fall';
          const sign = i.change_pct >= 0 ? '+' : '';
          return `${i.name} <span class="${cls}">${sign}${i.change_pct.toFixed(2)}%</span>`;
        }).join(' · ')}</div>
      </div>`;
    }

    // 今日总结
    let summaryHtml = '';
    if (summary) {
      summaryHtml = `<div style="font-size:11px;line-height:1.5;color:var(--text2);margin-bottom:6px;white-space:pre-line">${this.esc(summary)}</div>`;
    }

    // 推荐股票表现表格
    let perfHtml = '';
    if (perfs.length > 0) {
      perfHtml = `<div style="margin-bottom:6px">
        <span style="font-size:12px;font-weight:600">📋 今日推荐表现</span>
        <div style="display:flex;gap:6px;padding:3px 0 1px;margin-top:4px;font-size:10px;color:var(--text3)">
          <span style="min-width:52px">名称</span>
          <span style="min-width:42px">来源</span>
          <span style="min-width:48px;text-align:right">推荐时涨幅</span>
          <span style="min-width:48px;text-align:right">收盘涨幅</span>
          <span style="min-width:36px;text-align:right">评价</span>
          <span style="min-width:56px;text-align:right">买入价</span>
          <span style="min-width:44px;text-align:right">是否买入</span>
          <span style="min-width:44px;text-align:right">收益率</span>
        </div>
        <div style="margin-top:1px">${perfs.map((p, i) => {
          const mCls = p.morning_chg >= 0 ? 'text-rise' : 'text-fall';
          const dCls = p.day_chg >= 0 ? 'text-rise' : 'text-fall';
          const mSign = p.morning_chg >= 0 ? '+' : '';
          const dSign = p.day_chg >= 0 ? '+' : '';
          const src = p.source === 'morning' ? '🌅' : '☀️';
          const buyExec = p.buy_triggered || p.held;
          const profit = p.buy_profit;
          return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;${i > 0 ? 'border-top:1px solid rgba(255,255,255,0.04)' : ''};cursor:pointer" onclick="App.openStock('${p.code}')">
            <span style="font-weight:600;color:var(--text1);min-width:52px;font-size:12px">${this.esc(p.name)}</span>
            <span style="font-size:10px;color:var(--text3);min-width:42px">${src}</span>
            <span style="min-width:48px;text-align:right" class="${mCls}">${mSign}${p.morning_chg.toFixed(2)}%</span>
            <span style="min-width:48px;text-align:right" class="${dCls}">${dSign}${p.day_chg.toFixed(2)}%</span>
            <span style="min-width:36px;text-align:right;font-size:11px">${p.icon}</span>
            <span style="min-width:56px;text-align:right;font-size:11px;color:var(--rise)">${p.buy_point?.toFixed(2) || '-'}</span>
            <span style="min-width:44px;text-align:right;font-size:11px;color:${buyExec ? 'var(--rise)' : 'var(--text3)'}">${buyExec ? '✅已买' : '❌未买'}</span>
            <span style="min-width:44px;text-align:right;font-size:11px" class="${profit != null ? (profit >= 0 ? 'text-rise' : 'text-fall') : ''}">${profit != null ? (profit >= 0 ? '+' : '') + profit.toFixed(2) + '%' : '-'}</span>
          </div>`;
        }).join('')}</div>
      </div>`;

      // 持仓管理建议（替代原来的"明日操作建议"）
      const heldPerfs = perfs.filter(p => p.held);
      const allPerfs = perfs;
      let adviceHtml = '';

      // 持仓股票的卖出/持有策略
      if (heldPerfs.length > 0) {
        adviceHtml += `<div style="padding:4px 0"><span style="font-size:12px;font-weight:600">💼 持仓管理策略（触及买入点已建仓）</span>`;
        for (const p of heldPerfs) {
          adviceHtml += `<div style="margin-top:6px;padding:6px 8px;background:rgba(255,255,255,0.03);border-radius:6px;border-left:3px solid ${p.stop_triggered ? 'var(--fall)' : (p.buy_profit > 0 ? 'var(--rise)' : 'var(--gold)')}">
            <div style="font-weight:600;font-size:12px">${this.esc(p.name)} <span style="color:var(--text3)">(${p.code})</span> <span style="font-size:11px">${p.position_status}</span></div>
            <div style="font-size:11px;color:var(--text2);margin-top:2px">${this.esc(p.position_advice || '')}</div>`;
          if (p.sell_strategy) {
            adviceHtml += `<div style="font-size:11px;color:var(--text2);margin-top:4px;white-space:pre-line">${this.esc(p.sell_strategy)}</div>`;
          }
          if (p.hold_conditions) {
            adviceHtml += `<div style="font-size:11px;color:var(--text2);margin-top:4px;white-space:pre-line">${this.esc(p.hold_conditions)}</div>`;
          }
          adviceHtml += `</div>`;
        }
        adviceHtml += `</div>`;
      }

      // 未建仓股票的继续关注建议
      const unheldPerfs = perfs.filter(p => !p.held);
      if (unheldPerfs.length > 0) {
        adviceHtml += `<div style="padding:4px 0"><span style="font-size:12px;font-weight:600">👀 未建仓股票（继续观察）</span>`;
        for (const p of unheldPerfs) {
          adviceHtml += `<div style="display:flex;gap:8px;padding:3px 0;font-size:11px">
            <span style="font-weight:600;color:var(--text1);min-width:60px">${this.esc(p.name)}</span>
            <span style="color:var(--text2)">${this.esc(p.position_advice || p.verdict || '')}</span>
          </div>`;
        }
        adviceHtml += `</div>`;
      }

      if (adviceHtml) {
        perfHtml += `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:4px">
          <span style="font-size:12px;font-weight:600">📝 明日操作建议</span>
          <div style="margin-top:4px">${adviceHtml}</div>
        </div>`;
      }
    }

    // 明日风险 + 策略 并排
    let riskHtml = `<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 12px;border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:4px">
      <div style="display:flex;flex-direction:column;align-items:center;gap:2px">
        <span style="font-size:11px;font-weight:600;color:var(--text2)">🎯 明日风险评估</span>
        <span style="background:${riskBg};color:${riskColor};padding:4px 10px;border-radius:8px;font-size:16px;font-weight:700;line-height:1.2;text-align:center">${riskScore}<div style="font-size:9px;font-weight:400;margin-top:2px">${riskLevel}风险</div></span>
      </div>
      <div style="font-size:11px;line-height:1.5;color:var(--text2);white-space:pre-line;overflow:hidden;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical">${(tomorrowRisk.strategy_text || '').replace(/\*\*/g, '')}</div>
    </div>`;

    // 收盘外围影响总结
    const closingImpact = data.impact_summary || '';
    const closingImpactHtml = closingImpact ? `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;margin-top:2px;font-size:11px;line-height:1.6;color:var(--text2);white-space:pre-line;overflow:hidden;display:-webkit-box;-webkit-line-clamp:6;-webkit-box-orient:vertical"><span style="font-weight:600;color:var(--text1)">🌐 收盘外围动态</span>\n${this.esc(closingImpact)}</div>` : '';

    // 明日推荐
    let buysHtml = '';
    if (tomorrowBuys.length > 0) {
      buysHtml = `<div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;margin-top:4px">
        <span style="font-size:12px;font-weight:600">💰 明日建议买入（${tomorrowBuys.length}只 · 明日买后日卖）</span>
        <div style="display:flex;align-items:center;gap:6px;padding:3px 0 1px;margin-top:4px;font-size:10px;color:var(--text3)">
          <span style="min-width:52px">名称</span>
          <span style="min-width:48px">代码</span>
          <span style="min-width:52px;text-align:right">今日涨幅</span>
          <span style="min-width:50px;text-align:right">明日预估</span>
          <span style="min-width:52px;text-align:right">买入价</span>
          <span style="min-width:52px;text-align:right">目标价</span>
          <span style="min-width:46px;text-align:right">止损</span>
          <span style="min-width:34px;text-align:right">评分</span>
        </div>
        <div style="margin-top:1px">${tomorrowBuys.map((s, i) => {
          const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
          const chgSign = s.change_pct >= 0 ? '+' : '';
          const est = s.next_day_estimate;
          const estVal = est ? est.estimate : null;
          const estStr = estVal != null ? (estVal >= 0 ? '+' : '') + estVal.toFixed(1) + '%' : '-';
          const estCls = estVal != null ? (estVal >= 0 ? 'text-rise' : 'text-fall') : '';
          return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;${i > 0 ? 'border-top:1px solid rgba(255,255,255,0.04)' : ''};flex-wrap:wrap">
            <div style="flex:1;cursor:pointer;display:flex;align-items:center;gap:6px" onclick="App.openStock('${s.code}')">
            <span style="font-weight:600;color:var(--text1);min-width:52px;font-size:12px">${this.esc(s.name)}</span>
            <span style="font-size:10px;color:var(--text3);min-width:48px">${s.code}</span>
            <span style="min-width:52px;text-align:right" class="${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</span>
            <span style="min-width:50px;text-align:right;font-size:11px" class="${estCls}">${estStr}</span>
            <span style="min-width:52px;text-align:right;font-size:11px;color:var(--rise)">${s.buy_point?.toFixed(2) || '-'}</span>
            <span style="min-width:52px;text-align:right;font-size:11px;color:var(--rise)">${s.target_price?.toFixed(2) || '-'}</span>
            <span style="min-width:46px;text-align:right;font-size:11px;color:var(--fall)">${s.stop_loss?.toFixed(2) || '-'}</span>
            <span style="min-width:34px;text-align:right;color:var(--text2);font-size:11px">${s.score}</span>
            </div>
            <div style="width:100%;font-size:10px;color:var(--text2);padding-left:106px">💡 ${this.esc(s.reason || s.signals?.slice(0,2).join('、') || '')}</div>
            <button onclick="event.stopPropagation();App.manualBuy('${s.code}','${this.esc(s.name)}',${s.buy_point || 0},${s.score || 0})" style="padding:2px 8px;background:#22c55e22;color:#22c55e;border:1px solid #22c55e44;border-radius:4px;cursor:pointer;font-size:11px;white-space:nowrap">买入</button>
          </div>`;
        }).join('')}</div>
      </div>`;
    }

    el.innerHTML = cnHtml + summaryHtml + perfHtml + riskHtml + closingImpactHtml + buysHtml;
  },

  // === 左栏推荐列表 ===
  renderRecList(containerId, stocks) {
    const el = document.getElementById(containerId);
    if (!stocks.length) { el.innerHTML = '<div class="empty">暂无</div>'; return; }
    el.innerHTML = stocks.map(s => {
      const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = s.change_pct >= 0 ? '+' : '';
      const est = s.next_day_estimate;
      const estStr = est ? (est.estimate >= 0 ? '+' : '') + est.estimate.toFixed(1) + '%' : '-';
      const estCls = est ? (est.estimate >= 0 ? 'text-rise' : 'text-fall') : '';
      return `<div class="rec-mini" onclick="App.openStock('${s.code}')">
        <div class="rec-mini-left">
          <span class="rec-mini-name">${this.esc(s.name)}</span>
          <span class="rec-mini-code">${s.code}</span>
        </div>
        <div class="rec-mini-right">
          <div class="rec-mini-price ${chgCls}" data-rt-code="${s.code}" data-rt-field="price">${s.price.toFixed(2)}</div>
          <div class="rec-mini-change ${chgCls}" data-rt-code="${s.code}" data-rt-field="change_pct">${chgSign}${s.change_pct.toFixed(2)}%</div>
          <div class="rec-mini-score">明日预估 <span class="${estCls}">${estStr}</span></div>
        </div>
      </div>`;
    }).join('');
  },

  // === 策略 ===
  renderStrategies(r) {
    const strategies = r.strategies || [];
    if (!strategies.length) return;
    document.getElementById('strategy-card').style.display = '';
    document.getElementById('strategies').innerHTML = strategies.map(s =>
      `<div style="margin-bottom:12px">
        <div style="font-size:14px;font-weight:600;margin-bottom:4px">${s.name}</div>
        <div style="font-size:12px;color:var(--text2);margin-bottom:6px">${s.desc}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${(s.stocks || []).map(st =>
          `<span class="stock-rec-tag 买入" style="cursor:pointer" onclick="App.openStock('${st.code}')">${st.name}(${st.score}分)</span>`
        ).join('')}</div>
      </div>`
    ).join('');
  },

  // === 推荐股票列表 ===
  filterRecList() {
    const recFilter = document.getElementById('filter-rec').value;
    const sortBy = document.getElementById('filter-sort').value;

    let list = (this.allData?.stocks || []).filter(s =>
      s.recommendation === '强烈买入' || s.recommendation === '买入' || s.recommendation === '关注'
    );

    if (recFilter !== 'all') {
      list = list.filter(s => s.recommendation === recFilter);
    }

    list.sort((a, b) => {
      switch (sortBy) {
        case 'score_desc': return (b.score || 0) - (a.score || 0);
        case 'estimate_desc': return (b.next_day_estimate?.estimate || 0) - (a.next_day_estimate?.estimate || 0);
        case 'change_desc': return (b.change_pct || 0) - (a.change_pct || 0);
        default: return 0;
      }
    });

    this.recList = list;
    this.recPage = 0;
    this.renderRecListTable();
  },

  renderRecListTable() {
    const end = (this.recPage + 1) * this.recPageSize;
    const slice = this.recList.slice(0, end);
    const total = this.recList.length;

    document.getElementById('rec-count').textContent = total + '只';

    if (!slice.length) {
      document.getElementById('rec-list').innerHTML = '<div class="empty"><div class="empty-icon">📭</div><div>没有符合条件的推荐股票</div></div>';
      document.getElementById('btn-load-more').style.display = 'none';
      return;
    }

    let html = '';
    slice.forEach(s => {
      const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = s.change_pct >= 0 ? '+' : '';
      const est = s.next_day_estimate;
      const estVal = est ? est.estimate : 0;
      const estStr = est ? (estVal >= 0 ? '+' : '') + estVal.toFixed(1) + '%' : '-';
      const estCls = est ? (estVal >= 0 ? 'text-rise' : 'text-fall') : 'color:var(--text3)';

      html += `<div class="rec-row" onclick="App.openStock('${s.code}')">
        <span class="col-name"><span class="rname">${this.esc(s.name)}</span><span class="rcode">${s.code}</span></span>
        <span class="${chgCls}" style="font-weight:600" data-rt-code="${s.code}" data-rt-field="price">${s.price.toFixed(2)}</span>
        <span class="${chgCls}" data-rt-code="${s.code}" data-rt-field="change_pct" data-bold="1">${chgSign}${s.change_pct.toFixed(2)}%</span>
        <span style="color:var(--fall)">${s.buy_point ? s.buy_point.toFixed(2) : '-'}</span>
        <span class="col-buy-t">${s.buy_time ? s.buy_time.replace(/\(.*\)/, '') : '-'}</span>
        <span style="color:var(--fall)">${s.target_price ? s.target_price.toFixed(2) : '-'}</span>
        <span style="color:var(--rise)">${s.stop_loss ? s.stop_loss.toFixed(2) : '-'}</span>
        <span style="${estCls};font-weight:600">${estStr}</span>
        <span class="stock-rec-tag ${s.recommendation}">${s.score}</span>
      </div>`;
    });

    document.getElementById('rec-list').innerHTML = html;
    document.getElementById('btn-load-more').style.display = end < total ? '' : 'none';
  },

  loadMore() { this.recPage++; this.renderRecListTable(); },

  filterByRec(rec) {
    document.getElementById('filter-rec').value = rec;
    App.filterRecList();
    document.querySelector('#page-home .col-center .card:last-child').scrollIntoView({ behavior: 'smooth' });
  },

  // === 右栏 - 准确率统计 ===
  renderAccuracy() {
    const el = document.getElementById('accuracy-section');

    // 从历史数据中收集近3天强烈买入的股票
    let results = [];
    const seen = new Set();
    const now = new Date();
    const threeDaysAgo = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000);
    const threeDaysAgoStr = threeDaysAgo.toISOString().substring(0, 10);

    for (let i = this.historyData.length - 1; i >= 0; i--) {
      const hd = this.historyData[i];
      if (!hd.recommendations) continue;
      const dateStr = hd.update_time?.substring(0, 10);
      if (!dateStr || dateStr < threeDaysAgoStr) continue; // 只看近3天
      const strongBuys = hd.recommendations.strong_buy || [];
      for (const s of strongBuys) {
        if (!s.prediction_result || !s.next_day_actual) continue;
        const key = `${s.code}_${hd.update_time?.substring(0,10)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        results.push({
          code: s.code,
          name: s.name,
          rec: '强烈买入',
          snapshot_price: s.snapshot_price || s.price,
          actual_close: s.next_day_actual.actual_close,
          actual_pct: s.next_day_actual.actual_pct,
          pred_pct: s.next_day_estimate?.estimate || 0,
          pred_result: s.prediction_result,
          update_time: hd.update_time,
          next_date: s.next_day_actual.next_date,
          score: s.score,
        });
      }
    }

    if (!results.length) {
      // 降级：尝试用旧逻辑（比较相邻两次分析的价格）
      if (this.historyData.length >= 2) {
        for (let i = 1; i < this.historyData.length; i++) {
          const hd = this.historyData[i];
          if (!hd.recommendations?.strong_buy?.length) continue;
          const nextHd = this.historyData[i-1];
          const ydStrongBuy = hd.recommendations.strong_buy || [];
          for (const s of ydStrongBuy) {
            const todayStock = this.findStock(s.code) || (nextHd.recommendations?.strong_buy || []).find(x => x.code === s.code);
            if (!todayStock) continue;
            const ydPrice = s.price || s.prev_close;
            const chgPct = todayStock.price > 0 && ydPrice > 0 ? (todayStock.price - ydPrice) / ydPrice * 100 : 0;
            const diff = chgPct - (s.next_day_estimate?.estimate || 0);
            let icon, label;
            if (diff >= 2) { icon = '🔥'; label = '超预期'; }
            else if (diff >= 0.5) { icon = '✓'; label = '超预期'; }
            else if (Math.abs(diff) < 0.5) { icon = '✓'; label = '精准'; }
            else if (diff >= -1) { icon = '≈'; label = '基本符合'; }
            else if (diff >= -3) { icon = '↓'; label = '低于预期'; }
            else { icon = '✗'; label = '远低预期'; }
            results.push({
              code: s.code, name: s.name, rec: '强烈买入',
              snapshot_price: ydPrice, actual_close: todayStock.price,
              actual_pct: chgPct, pred_pct: s.next_day_estimate?.estimate || 0,
              pred_result: { icon, label, hit_dir: chgPct > 0 },
              update_time: hd.update_time, score: s.score,
            });
          }
          break;
        }
      }
    }

    if (!results.length) {
      el.innerHTML = '<div class="empty"><div class="empty-icon">📊</div><div>需要至少2次分析数据才能统计准确率</div></div>';
      return;
    }

    // 统计
    const total = results.length;
    const exceeds = results.filter(r => r.pred_result.icon === '🔥' || r.pred_result.icon === '✓').length;
    const accurate = results.filter(r => r.pred_result.label === '精准命中').length;
    const ok = results.filter(r => r.pred_result.icon === '≈').length;
    const below = results.filter(r => r.pred_result.icon === '↓').length;
    const farBelow = results.filter(r => r.pred_result.icon === '✗').length;
    const avgPnl = results.reduce((s, r) => s + r.actual_pct, 0) / total;
    const exceedRate = (exceeds + accurate) / total * 100;

    let html = `<div style="text-align:center;margin-bottom:10px;font-size:11px;color:var(--text3)">🔥 近3天强烈买入 · 共 ${total} 只</div>`;

    // 摘要卡片
    html += `<div class="accuracy-summary">
      <div class="accuracy-summary-item"><div class="accuracy-summary-num" style="color:${exceedRate >= 60 ? 'var(--rise)' : 'var(--gold)'}">${exceedRate.toFixed(0)}%</div><div class="accuracy-summary-label">超预期率</div></div>
      <div class="accuracy-summary-item"><div class="accuracy-summary-num ${avgPnl >= 0 ? 'text-rise' : 'text-fall'}">${avgPnl >= 0 ? '+' : ''}${avgPnl.toFixed(2)}%</div><div class="accuracy-summary-label">平均涨幅</div></div>
      <div class="accuracy-summary-item"><div class="accuracy-summary-num" style="color:var(--rise)">🔥${exceeds}</div><div class="accuracy-summary-label">超预期</div></div>
    </div>`;

    // 分类统计条
    html += `<div style="display:flex;gap:4px;flex-wrap:wrap;margin:10px 0;font-size:10px">
      <span style="background:rgba(239,68,68,0.12);color:#ef4444;padding:2px 6px;border-radius:4px">🔥超预期${exceeds}</span>
      <span style="background:rgba(34,197,94,0.12);color:#22c55e;padding:2px 6px;border-radius:4px">✓精准${accurate}</span>
      <span style="background:rgba(234,179,8,0.12);color:#eab308;padding:2px 6px;border-radius:4px">≈符合${ok}</span>
      <span style="background:rgba(59,130,246,0.12);color:#3b82f6;padding:2px 6px;border-radius:4px">↓低于${below}</span>
      <span style="background:rgba(156,163,175,0.12);color:#9ca3af;padding:2px 6px;border-radius:4px">✗远低${farBelow}</span>
    </div>`;

    // 明细列表
    html += '<div class="accuracy-detail">';
    // 按涨幅排序（高的在前）
    const sorted = [...results].sort((a, b) => b.actual_pct - a.actual_pct);
    sorted.forEach(d => {
      const chgSign = d.actual_pct >= 0 ? '+' : '';
      const chgCls = d.actual_pct >= 0 ? 'correct' : 'wrong';
      const predIcon = d.pred_result.icon || '?';
      const predLabel = d.pred_result.label || '?';
      const predCls = (predIcon === '🔥' || predIcon === '✓') ? 'correct' : (predIcon === '≈' ? '' : 'wrong');
      const scoreStr = d.score ? `<span style="font-size:9px;color:var(--text3);margin-left:2px">${d.score}分</span>` : '';

      html += `<div class="accuracy-row" onclick="App.openStock('${d.code}')" style="cursor:pointer">
        <span class="name">🔥${this.esc(d.name)}${scoreStr}</span>
        <span class="pred">${d.snapshot_price.toFixed(2)}→${d.actual_close?.toFixed(2) || '?'}</span>
        <span class="actual ${chgCls}">${chgSign}${d.actual_pct.toFixed(2)}%</span>
        <span class="actual ${predCls}">${predIcon} ${predLabel}</span>
      </div>`;
    });
    html += '</div>';
    el.innerHTML = html;

    // 更新准确率时间标签
    const accTimeEl = document.getElementById('accuracy-update-time');
    if (accTimeEl && total > 0) {
      const latestTime = sorted[0]?.next_date || sorted[0]?.update_time?.substring(0,10) || '';
      accTimeEl.textContent = latestTime ? `截止${latestTime}` : '昨日强烈买入';
    }
  },

  // === 右栏 - 持仓 ===
  renderPortfolio() {
    const portfolio = Portfolio.get();
    const el = document.getElementById('portfolio-section');
    const adviceCard = document.getElementById('portfolio-advice-card');

    if (!portfolio.length) {
      el.innerHTML = '<div class="portfolio-empty">暂无持仓，点击上方"添加"录入</div>';
      adviceCard.style.display = 'none';
      return;
    }

    let html = '', adviceHtml = '';
    const totalPnl = portfolio.reduce((sum, pos) => {
      const stock = this.findStock(pos.code);
      return sum + (stock ? (stock.price - pos.cost) * pos.qty : 0);
    }, 0);
    const totalCost = portfolio.reduce((sum, pos) => sum + pos.cost * pos.qty, 0);
    const totalPnlPct = totalCost > 0 ? totalPnl / totalCost * 100 : 0;
    const cls = totalPnl >= 0 ? 'text-rise' : 'text-fall';
    const sign = totalPnl >= 0 ? '+' : '';

    html = `<div style="text-align:center;padding:8px 0 12px;border-bottom:1px solid var(--border);margin-bottom:8px">
      <div style="font-size:11px;color:var(--text3)">总盈亏</div>
      <div style="font-size:20px;font-weight:800" class="${cls}">${sign}${totalPnl.toFixed(0)}元 (${sign}${totalPnlPct.toFixed(2)}%)</div>
    </div>`;

    portfolio.forEach((pos, i) => {
      const stock = this.findStock(pos.code);
      if (!stock) {
        html += `<div class="portfolio-item" data-holding-code="${pos.code}" data-holding-cost="${pos.cost}" data-holding-qty="${pos.qty}">
          <div class="portfolio-left"><span class="stock-name">${this.esc(pos.code)}</span><span class="portfolio-cost">成本 ${pos.cost.toFixed(2)} × ${pos.qty}股</span></div>
          <div class="portfolio-right" style="color:var(--text3);font-size:12px">未找到<button class="btn-add" onclick="event.stopPropagation();Portfolio.remove(${i});App.renderPortfolio()">✕</button></div>
        </div>`;
        return;
      }
      const pnl = stock.price - pos.cost;
      const pnlPct = pos.cost > 0 ? (pnl / pos.cost * 100) : 0;
      const pnlAmt = pnl * pos.qty;
      const pCls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const pSign = pnl >= 0 ? '+' : '';

      html += `<div class="portfolio-item" data-holding-code="${pos.code}" data-holding-cost="${pos.cost}" data-holding-qty="${pos.qty}" onclick="App.openStock('${pos.code}')">
        <div class="portfolio-left">
          <div style="display:flex;align-items:center;gap:6px">
            <span class="stock-name">${this.esc(stock.name)}</span>
            <span class="stock-code">${stock.code}</span>
            <button class="btn-add" onclick="event.stopPropagation();Portfolio.remove(${i});App.renderPortfolio()">✕</button>
          </div>
          <span class="portfolio-cost rt-price">成本${pos.cost.toFixed(2)} × ${pos.qty}股 · 现价${stock.price.toFixed(2)}</span>
        </div>
        <div class="portfolio-right">
          <div class="portfolio-pnl rt-pnl ${pCls}">${pSign}${pnlAmt.toFixed(0)}元</div>
          <div class="portfolio-pnl rt-pct ${pCls}" style="font-size:12px">${pSign}${pnlPct.toFixed(2)}%</div>
          <span class="portfolio-advice stock-rec-tag ${stock.recommendation}">${stock.recommendation}</span>
        </div>
      </div>`;

      const rec = stock.recommendation;
      let advice = '';
      if (pnlPct < -5) advice = `⚠️ ${stock.name} 亏损${Math.abs(pnlPct).toFixed(1)}%，止损位${stock.stop_loss || '未设定'}元`;
      else if (rec === '强烈卖出' || rec === '卖出') advice = `📉 ${stock.name} 建议${rec}(${stock.score}分)，考虑减仓`;
      else if (rec === '强烈买入') advice = `🔥 ${stock.name} 强烈买入(${stock.score}分)，目标${stock.target_price || '-'}元`;
      else if (rec === '买入') advice = `📈 ${stock.name} 建议买入(${stock.score}分)，可持有`;
      else advice = `👀 ${stock.name} 关注(${stock.score}分)，观望`;
      adviceHtml += `<div style="padding:6px 0;border-bottom:1px solid rgba(42,58,80,0.2);font-size:12px;line-height:1.6;cursor:pointer" onclick="App.openStock('${stock.code}')">${advice}</div>`;
    });

    el.innerHTML = html;
    if (adviceHtml) {
      adviceCard.style.display = '';
      document.getElementById('portfolio-advice').innerHTML = adviceHtml;
    }
  },

  // === 右栏 - 虚拟交易持仓（需求2） ===
  async renderVirtualHoldings() {
    const el = document.getElementById('virtual-holdings-section');
    if (!this._apiAvailable) {
      el.innerHTML = '<div class="portfolio-empty">需要启动API服务器</div>';
      return;
    }

    try {
      const res = await fetch(this.API_BASE + '/api/portfolio');
      if (!res.ok) throw new Error('failed');
      const data = await res.json();
      const holdings = data.holdings || [];

      if (!holdings.length) {
        el.innerHTML = '<div class="portfolio-empty">暂无虚拟交易持仓</div>';
        return;
      }

      // 计算总盈亏
      const totalPnl = holdings.reduce((s, h) => s + (h.pnl || 0), 0);
      const totalCost = holdings.reduce((s, h) => s + h.avg_cost * h.qty, 0);
      const totalPnlPct = totalCost > 0 ? totalPnl / totalCost * 100 : 0;
      const cls = totalPnl >= 0 ? 'text-rise' : 'text-fall';
      const sign = totalPnl >= 0 ? '+' : '';

      let html = `<div style="text-align:center;padding:6px 0 10px;border-bottom:1px solid var(--border);margin-bottom:8px">
        <div style="font-size:11px;color:var(--text3)">虚拟交易盈亏</div>
        <div style="font-size:18px;font-weight:800" class="${cls}">${sign}${totalPnl.toFixed(0)}元 (${sign}${totalPnlPct.toFixed(2)}%)</div>
        <div style="font-size:11px;color:var(--text3)">可用资金 ${(data.cash || 0).toLocaleString('zh-CN', {minimumFractionDigits:0, maximumFractionDigits:0})}元</div>
      </div>`;

      holdings.forEach(h => {
        const hCls = (h.pnl || 0) >= 0 ? 'text-rise' : 'text-fall';
        const hSign = (h.pnl || 0) >= 0 ? '+' : '';
        const emoji = (h.pnl || 0) >= 0 ? '🟢' : '🔴';

        html += `<div class="vh-card" data-code="${h.code}" data-cost="${h.avg_cost}" data-qty="${h.qty}" onclick="App.openStock('${h.code}')" style="cursor:pointer;padding:10px 0;border-bottom:1px solid rgba(42,58,80,0.15)">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <span style="font-weight:600;font-size:14px">${this.esc(h.name)}</span>
              <span style="color:var(--text3);font-size:11px;margin-left:4px">${h.code}</span>
              <span style="font-size:11px;color:var(--text3);margin-left:6px">${h.qty}股 × ${h.avg_cost.toFixed(2)}</span>
            </div>
            <div style="text-align:right">
              <div class="vh-price" style="font-weight:600;font-size:14px">${h.current_price.toFixed(2)}</div>
              <div class="vh-pnl ${hCls}" style="font-size:13px;font-weight:700">${emoji} ${hSign}${(h.pnl || 0).toFixed(0)}元</div>
            </div>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px">
            <div style="font-size:11px;color:var(--text3)">
              ${h.buys.length ? '买入' + h.buys.length + '笔' : ''}${h.sells.length ? ' · 卖出' + h.sells.length + '笔' : ''}
            </div>
            <div class="vh-pct ${hCls}" style="font-size:12px">${hSign}${(h.pnl_pct || 0).toFixed(2)}%</div>
          </div>
          <div style="margin-top:4px">
            <button onclick="event.stopPropagation();App.manualSell('${h.code}','${this.esc(h.name)}',${h.qty})" style="padding:2px 8px;background:#ef444422;color:#ef4444;border:1px solid #ef444444;border-radius:4px;cursor:pointer;font-size:11px">卖出</button>
          </div>`;

        // 交易明细（折叠）
        if (h.buys.length || h.sells.length) {
          html += `<div class="vh-trades" style="margin-top:6px;font-size:11px">`;
          // 按时间倒序显示所有交易
          const allTrades = [
            ...h.buys.map(t => ({...t, _type: 'buy'})),
            ...h.sells.map(t => ({...t, _type: 'sell'}))
          ].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
          allTrades.forEach(t => {
            if (t._type === 'buy') {
              html += `<div style="color:var(--text2);padding:2px 0">✅ 买入 ${t.timestamp} ${t.qty}股 × ${t.price.toFixed(2)}</div>`;
            } else {
              const sp = (t.pnl || 0) >= 0 ? '+' : '';
              const sc = (t.pnl || 0) >= 0 ? 'text-rise' : 'text-fall';
              html += `<div style="color:var(--text2);padding:2px 0">❌ 卖出 ${t.timestamp} ${t.qty}股 × ${t.price.toFixed(2)} <span class="${sc}">${sp}${(t.pnl||0).toFixed(0)}元(${sp}${(t.pnl_pct||0).toFixed(1)}%)</span></div>`;
            }
          });
          html += '</div>';
        }
        html += '</div>';
      });

      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = '<div class="portfolio-empty">加载失败</div>';
    }
  },

  // === 历史更新页（需求4：列表+详情+K线） ===
  async renderHistory() {
    const el = document.getElementById('history-content');
    if (this._historyDetailFile) {
      await this._renderHistoryDetail(this._historyDetailFile);
      return;
    }

    try {
      let historyList;
      if (this._apiAvailable) {
        const res = await fetch(this.API_BASE + '/api/history_list');
        if (res.ok) historyList = await res.json();
      }
      if (!historyList) {
        // Fallback: load from directory listing
        const res = await fetch('data/history/');
        const text = await res.text();
        const files = text.match(/"[^"]+\.json"/g);
        if (!files) { el.innerHTML = '<div class="empty">暂无历史记录</div>'; return; }
        const fileNames = files.map(f => f.replace(/"/g, '').split('/').pop()).sort().reverse();
        historyList = fileNames.map(f => ({ file: f, update_time: f.replace('.json', '').replace(/_/g, ' ') }));
      }

      let html = '<div class="history-list-page">';

      // 按日期分组
      const byDate = {};
      historyList.forEach(h => {
        const date = (h.update_time || '').split(' ')[0] || h.file.split('_')[0];
        if (!byDate[date]) byDate[date] = [];
        byDate[date].push(h);
      });

      Object.keys(byDate).sort().reverse().forEach(date => {
        html += `<div class="hl-date-group">
          <div class="hl-date-header">📅 ${date}</div>`;

        byDate[date].forEach(h => {
          const time = (h.update_time || '').split(' ')[1] || '';
          const sentCls = (h.market_sentiment || '') === '偏多' ? 'text-rise' : (h.market_sentiment || '') === '偏空' ? 'text-fall' : '';
          html += `<div class="hl-item" onclick="App.showHistoryDetail('${h.file}')">
            <div class="hl-time">⏰ ${time}</div>
            <div class="hl-stats">
              <span class="hl-stat hl-sb">🔥${h.strong_buy_count || '?'}</span>
              <span class="hl-stat hl-buy">📈${h.buy_count || '?'}</span>
              <span class="hl-stat hl-watch">👀${h.watch_count || '?'}</span>
              <span class="hl-sent ${sentCls}">${h.market_sentiment || ''} ${h.avg_score || ''}分</span>
            </div>
            <div class="hl-action">
              <span class="hl-btn">查看详情 →</span>
            </div>
          </div>`;
        });

        html += '</div>';
      });

      html += '</div>';
      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = '<div class="empty">加载失败</div>';
    }
  },

  showHistoryDetail(file) {
    this._historyDetailFile = file;
    this.renderHistory();
  },

  async _renderHistoryDetail(file) {
    const el = document.getElementById('history-content');

    el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text3)">加载中...</div>';

    try {
      let detail;
      if (this._apiAvailable) {
        const res = await fetch(this.API_BASE + '/api/history_detail?file=' + encodeURIComponent(file));
        if (res.ok) detail = await res.json();
      }
      if (!detail) {
        const res = await fetch('data/history/' + file);
        if (!res.ok) throw new Error('not found');
        const raw = await res.json();
        const rec = raw.recommendations || {};
        detail = {
          update_time: raw.update_time,
          market_sentiment: raw.market_sentiment,
          avg_score: raw.avg_score,
          market_analysis: raw.market_analysis,
          next_day_advice: raw.next_day_advice,
          strategies: raw.strategies || [],
          recommendations: [
            ...(rec.strong_buy || []).map(s => ({...s, recommendation: '强烈买入'})),
            ...(rec.buy || []).map(s => ({...s, recommendation: '买入'})),
            ...(rec.watch || []).map(s => ({...s, recommendation: '关注'})),
            ...(rec.avoid || []).map(s => ({...s, recommendation: '回避'})),
          ],
          macro_indices: raw.macro_indices || {},
        };
      }


      let html = `<div class="hl-detail-page">
        <button class="btn-back" onclick="App._historyDetailFile=null;App.renderHistory()" style="margin-bottom:16px">← 返回列表</button>

        <div class="hl-detail-header">
          <div class="hl-detail-time">${detail.update_time}</div>
          <div class="hl-detail-sent">${detail.market_sentiment} · ${detail.avg_score}分</div>
        </div>`;

      // 推荐股票明细表格（仅强烈买入和建议买入）
      // recommendations 可能是扁平数组（fallback时已展平），也可能是 {strong_buy, buy, ...} 结构
      let allRecs = detail.recommendations || [];
      let recs;
      if (Array.isArray(allRecs)) {
        // 已经是扁平数组，每个元素有 recommendation 字段
        recs = allRecs.filter(s => s.recommendation === '强烈买入' || s.recommendation === '买入');
      } else {
        recs = [
          ...(allRecs.strong_buy || []).map(s => ({...s, recommendation: '强烈买入'})),
          ...(allRecs.buy || []).map(s => ({...s, recommendation: '建议买入'})),
        ];
      }

      html += `<div class="hl-detail-table-section">
        <h3 style="font-size:15px;font-weight:700;margin-bottom:12px">📊 推荐股票明细（${recs.length}只）</h3>
        <div style="overflow-x:auto">
          <table class="hl-detail-table">
            <thead>
              <tr>
                <th>股票名称</th>
                <th>更新时价格</th>
                <th>现价</th>
                <th>更新时涨幅</th>
                <th>当前涨幅</th>
                <th>建议买入价</th>
                <th>买入时间</th>
                <th>目标价</th>
                <th>止损价</th>
                <th>明日预估涨幅</th>
                <th>次日表现</th>
                <th>预测验证</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>`;

      recs.forEach(s => {
        const snapshotPrice = s.snapshot_price || s.price || 0;
        const latestPrice = s.latest_price || s.price || 0;
        const snapshotChg = s.change_pct || 0;
        const latestChg = s.latest_change_pct != null ? s.latest_change_pct : s.change_pct || 0;
        const chgCls = snapshotChg >= 0 ? 'text-rise' : 'text-fall';
        const lChgCls = latestChg >= 0 ? 'text-rise' : 'text-fall';
        const chgSign = snapshotChg >= 0 ? '+' : '';
        const lChgSign = latestChg >= 0 ? '+' : '';
        const est = s.next_day_estimate;
        const estStr = est ? (est.estimate >= 0 ? '+' : '') + est.estimate.toFixed(1) + '%' : '-';
        const estCls = est ? (est.estimate >= 0 ? 'text-rise' : 'text-fall') : '';
        const recTag = `<span class="stock-rec-tag ${s.recommendation}">${s.recommendation}</span>`;

        // 次日表现：用收盘价 vs 更新时价格
        const actual = s.next_day_actual;
        let actualHtml = '待计算';
        if (actual) {
          const aSign = actual.actual_pct >= 0 ? '+' : '';
          const aCls = actual.actual_pct >= 0 ? 'text-rise' : 'text-fall';
          const closeStr = actual.actual_close != null ? actual.actual_close.toFixed(2) : '?';
          const diffFromSnap = (actual.actual_close || 0) - snapshotPrice;
          const diffSign = diffFromSnap >= 0 ? '+' : '';
          actualHtml = `<span class="${aCls}" style="font-weight:700;font-size:14px">${aSign}${actual.actual_pct.toFixed(2)}%</span><br><span style="font-size:10px;color:var(--text3)">${actual.next_date || ''}收盘${closeStr}（${diffSign}${diffFromSnap.toFixed(2)}元）</span>`;
        }

        // 预测验证
        let accHtml = '-';
        const pred = s.prediction_result;
        if (pred) {
          const isPositive = pred.icon === '🔥' || pred.icon === '✓';
          const isNeutral = pred.icon === '≈';
          const vcls = isPositive ? 'text-rise' : (isNeutral ? 'var(--gold)' : 'text-fall');
          accHtml = `<span style="color:${vcls};font-weight:700">${pred.icon} ${pred.label}</span>`;
        }

        html += `<tr>
          <td>${this.esc(s.name)}<br><span style="font-size:11px;color:var(--text3)">${s.code}</span><br>${recTag}</td>
          <td style="font-weight:600">${snapshotPrice.toFixed(2)}</td>
          <td class="rt-price-cell" data-rt-code="${s.code}" data-rt-field="price">${latestPrice.toFixed(2)}</td>
          <td class="${chgCls}">${chgSign}${snapshotChg.toFixed(2)}%</td>
          <td class="${lChgCls} rt-price-cell" data-rt-code="${s.code}" data-rt-field="change_pct" data-bold="1">${lChgSign}${latestChg.toFixed(2)}%</td>
          <td style="color:var(--fall)">${s.buy_point ? s.buy_point.toFixed(2) : '-'}</td>
          <td style="font-size:12px">${s.buy_time ? s.buy_time.replace(/\(.*\)/, '') : '-'}</td>
          <td style="color:var(--rise)">${s.target_price ? s.target_price.toFixed(2) : '-'}</td>
          <td style="color:var(--fall)">${s.stop_loss ? s.stop_loss.toFixed(2) : '-'}</td>
          <td class="${estCls}">${estStr}</td>
          <td>${actualHtml}</td>
          <td>${accHtml}</td>
          <td><button class="btn-tiny" onclick="App.toggleInlineKline('${s.code}','${file}')">📈 走势</button></td>
        </tr>
        <tr id="krow-${s.code}" style="display:none"><td colspan="11" style="padding:8px 12px;background:var(--bg2)">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="font-size:13px;font-weight:600" id="ktitle-${s.code}">📈 ${this.esc(s.name)} 价格走势</span>
            <button class="btn-tiny" onclick="App.toggleInlineKline('${s.code}','${file}')">收起</button>
          </div>
          <div id="kmsg-${s.code}" style="padding:8px;color:var(--text3);font-size:12px;display:none"></div>
          <canvas id="kcanvas-${s.code}" width="800" height="220" style="width:100%;height:220px;background:rgba(255,255,255,0.02);border-radius:6px"></canvas>
        </td></tr>`;
      });

      html += `</tbody></table></div></div>`;

      html += '</div>';
      el.innerHTML = html;

      // 数据已回填，次日表现和预测验证直接显示
      // 实时数据仅更新现价和当前涨幅（通过data-rt-code标记）

    } catch (e) {
      el.innerHTML = '<div class="empty">加载失败: ' + e.message + '</div>';
    }
  },

  async _calcHistoryAccuracy(file, recs) {
    // 找到这条记录所属日期的【下一天】的第一条记录，计算实际涨幅
    try {
      const histDir = 'data/history/';
      const res = await fetch(histDir);
      const text = await res.text();
      const files = (text.match(/"[^"]+\.json"/g) || []).map(f => f.replace(/"/g, '')).sort();
      const idx = files.indexOf(file);
      if (idx < 0 || idx >= files.length - 1) return;

      // 从当前文件名提取日期（如 2026-05-18_1328 -> 2026-05-18）
      const curDate = file.substring(0, 10);

      // 找到下一天的第一条记录（不是同一天的下一条）
      let nextFile = null;
      for (let i = idx + 1; i < files.length; i++) {
        const nextDate = files[i].substring(0, 10);
        if (nextDate > curDate) {
          nextFile = files[i];
          break;
        }
      }
      if (!nextFile) return; // 还没有下一天的数据

      const nextRes = await fetch(histDir + nextFile);
      const nextData = await nextRes.json();
      const nextScores = nextData.scores || {};

      recs.forEach(s => {
        const laterPrice = nextScores[s.code]?.price;
        const prevPrice = s.price || s.prev_close;
        if (laterPrice && prevPrice && prevPrice > 0) {
          const actualPct = (laterPrice - prevPrice) / prevPrice * 100;
          const sign = actualPct >= 0 ? '+' : '';
          const cls = actualPct >= 0 ? 'text-rise' : 'text-fall';

          // 次日表现：显示实际涨幅
          const actualEl = document.getElementById('actual-' + s.code);
          if (actualEl) {
            const est = s.next_day_estimate?.estimate || 0;
            const diff = actualPct - est;
            const diffStr = diff >= 0 ? `+${diff.toFixed(1)}` : `${diff.toFixed(1)}`;
            actualEl.innerHTML = `<span class="${cls}" style="font-weight:600">${sign}${actualPct.toFixed(2)}%</span><br><span style="font-size:10px;color:var(--text3)">vs预估${diffStr}</span>`;
          }

          // 预测验证：方向+幅度综合判断
          const est = s.next_day_estimate?.estimate || 0;
          const predictedUp = est > 0;
          const actualUp = actualPct > 0;
          const hit = predictedUp === actualUp;
          const accEl = document.getElementById('acc-' + s.code);
          if (accEl) {
            // 三级验证：✓命中 / ≈接近 / ✗偏差
            const absDiff = Math.abs(actualPct - est);
            let icon, label, vcls;
            if (hit && absDiff < 1.5) {
              icon = '✓'; label = '精准'; vcls = 'text-rise';
            } else if (hit) {
              icon = '✓'; label = '命中'; vcls = 'text-rise';
            } else if (absDiff < 1) {
              icon = '≈'; label = '接近'; vcls = 'var(--gold)';
            } else {
              icon = '✗'; label = '偏差'; vcls = 'text-fall';
            }
            accEl.innerHTML = `<span style="color:${vcls};font-weight:600">${icon} ${label}</span>`;
          }
        }
      });
    } catch {}
  },

  async toggleInlineKline(code, historyFile) {
    const row = document.getElementById('krow-' + code);
    if (!row) return;
    const show = row.style.display === 'none';
    row.style.display = show ? '' : 'none';
    if (!show) return;

    // Already loaded?
    if (row.dataset.loaded) return;
    row.dataset.loaded = '1';

    const canvas = document.getElementById('kcanvas-' + code);
    const msgEl = document.getElementById('kmsg-' + code);

    try {
      let points = [];
      if (this._apiAvailable) {
        const res = await fetch(this.API_BASE + '/api/price_history?code=' + code + '&days=3');
        if (res.ok) { const data = await res.json(); points = data.points || []; }
      }
      if (points.length < 2) {
        canvas.style.display = 'none';
        msgEl.style.display = '';
        msgEl.textContent = '暂无足够价格记录（需多次分析积累数据）';
        return;
      }
      this._drawPriceLine(canvas, points);
    } catch {
      canvas.style.display = 'none';
      msgEl.style.display = '';
      msgEl.textContent = '数据加载失败';
    }
  },

  _drawPriceLine(canvas, points) {
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const pad = { top: 30, right: 60, bottom: 30, left: 10 };
    const cW = W - pad.left - pad.right;
    const cH = H - pad.top - pad.bottom;
    ctx.clearRect(0, 0, W, H);

    const prices = points.map(p => p.price);
    let minP = Math.min(...prices), maxP = Math.max(...prices);
    const range = maxP - minP || 1;
    minP -= range * 0.08;
    maxP += range * 0.08;
    const totalRange = maxP - minP;
    const toY = p => pad.top + (1 - (p - minP) / totalRange) * cH;
    const toX = i => pad.left + (i / (points.length - 1)) * cW;

    // Grid
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (cH / 4) * i;
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
      const price = maxP - (totalRange / 4) * i;
      ctx.fillStyle = 'rgba(255,255,255,0.4)';
      ctx.font = '11px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(price.toFixed(2), W - pad.right + 5, y + 4);
    }

    // Gradient fill under line
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + cH);
    grad.addColorStop(0, 'rgba(59,130,246,0.25)');
    grad.addColorStop(1, 'rgba(59,130,246,0.02)');
    ctx.beginPath();
    ctx.moveTo(toX(0), toY(points[0].price));
    points.forEach((p, i) => ctx.lineTo(toX(i), toY(p.price)));
    ctx.lineTo(toX(points.length - 1), pad.top + cH);
    ctx.lineTo(toX(0), pad.top + cH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.moveTo(toX(0), toY(points[0].price));
    points.forEach((p, i) => ctx.lineTo(toX(i), toY(p.price)));
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Data points
    points.forEach((p, i) => {
      const x = toX(i), y = toY(p.price);
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#3b82f6';
      ctx.fill();
      ctx.strokeStyle = 'rgba(59,130,246,0.4)';
      ctx.lineWidth = 1;
      ctx.stroke();
    });

    // Time labels
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    const step = Math.max(1, Math.floor(points.length / 6));
    points.forEach((p, i) => {
      if (i % step === 0 || i === points.length - 1) {
        const label = p.time ? p.time.substring(5, 16) : '';
        ctx.fillText(label, toX(i), H - 5);
      }
    });

    // Start/End price info
    const lastP = points[points.length - 1].price;
    const firstP = points[0].price;
    const chgPct = firstP > 0 ? ((lastP - firstP) / firstP * 100) : 0;
    const chgSign = chgPct >= 0 ? '+' : '';
    ctx.fillStyle = chgPct >= 0 ? '#ef4444' : '#22c55e';
    ctx.font = 'bold 12px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`${chgSign}${chgPct.toFixed(2)}% (${firstP.toFixed(2)} -> ${lastP.toFixed(2)})`, pad.left, 18);
  },

  // === 个股详情页 ===
  openStock(code) {
    const stock = this.findStock(code);
    if (!stock) { this.showToast('未找到该股票'); return; }

    const portfolio = Portfolio.get();
    const isHolding = portfolio.some(p => p.code === code);
    const holding = portfolio.find(p => p.code === code);

    this.showPage('detail');
    document.getElementById('detail-title').textContent = stock.name + ' ' + code + (isHolding ? ' 💼' : '');

    const s = stock;
    // Use realtime if available
    const rt = this.realtimeCache[code];
    const displayPrice = rt ? rt.price : s.price;
    const displayChgPct = rt ? rt.change_pct : s.change_pct;

    const chgCls = displayChgPct >= 0 ? 'text-rise' : 'text-fall';
    const chgSign = displayChgPct >= 0 ? '+' : '';

    const buyKw = ['金叉','超卖','放量上涨','多头','突破','低位','偏低','下轨','温和上涨','强势上涨','低PE','红柱'];
    const sellKw = ['死叉','超买','放量下跌','空头','高估','偏高','上轨','回调','大幅下跌','绿柱','缩量'];

    let html = '';

    html += `<div class="detail-section">
      <h3>📊 实时行情</h3>
      <div style="text-align:center;margin-bottom:16px">
        <div style="font-size:36px;font-weight:800" class="${chgCls}">${displayPrice.toFixed(2)}</div>
        <div style="font-size:16px;font-weight:600" class="${chgCls}">${chgSign}${displayChgPct.toFixed(2)}%</div>
        ${this._apiAvailable ? '<div style="font-size:10px;color:var(--text3)">实时数据 · 每30秒刷新</div>' : ''}
        <div style="font-size:24px;font-weight:800;margin-top:8px;color:${this.recColor(s.recommendation)}">${s.recommendation} · ${s.score}分</div>`;

    if (s.next_day_estimate) {
      const est = s.next_day_estimate;
      const estCls = est.estimate >= 0 ? 'text-rise' : 'text-fall';
      const estSign = est.estimate >= 0 ? '+' : '';
      html += `<div style="margin-top:8px;font-size:14px;color:var(--text2)">明日预估涨幅 <span class="${estCls}" style="font-size:20px;font-weight:700">${estSign}${est.estimate.toFixed(1)}%</span></div>`;
      if (est.factors && est.factors.length) {
        html += `<div style="font-size:11px;color:var(--text3);margin-top:4px">依据：${est.factors.join('、')}</div>`;
      }
    }

    html += `</div>
      <div class="detail-grid">
        <div class="detail-grid-item"><div class="detail-grid-label">今开</div><div class="detail-grid-value">${(s.open || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">最高</div><div class="detail-grid-value text-rise">${(s.high || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">最低</div><div class="detail-grid-value text-fall">${(s.low || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">昨收</div><div class="detail-grid-value">${(s.prev_close || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">成交量</div><div class="detail-grid-value">${this.fmtVol(s.volume)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">成交额</div><div class="detail-grid-value">${this.fmtAmt(s.amount)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">换手率</div><div class="detail-grid-value">${(s.turnover_rate || 0).toFixed(2)}%</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">振幅</div><div class="detail-grid-value">${(s.amplitude || 0).toFixed(2)}%</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">PE</div><div class="detail-grid-value">${s.pe ? s.pe.toFixed(1) : '-'}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">PB</div><div class="detail-grid-value">${s.pb ? s.pb.toFixed(2) : '-'}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">总市值</div><div class="detail-grid-value">${this.fmtAmt(s.market_cap)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">评分</div><div class="detail-grid-value" style="color:${this.recColor(s.recommendation)}">${s.score}</div></div>
      </div>
    </div>`;

    if (isHolding && holding) {
      const pnl = displayPrice - holding.cost;
      const pnlPct = holding.cost > 0 ? (pnl / holding.cost * 100) : 0;
      const pnlAmt = pnl * holding.qty;
      const pCls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const pSign = pnl >= 0 ? '+' : '';

      html += `<div class="detail-section" style="border-color:var(--accent)">
        <h3>💼 持仓盈亏分析</h3>
        <div style="padding:12px 16px">
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">成本价</div><div style="font-size:16px;font-weight:700">${holding.cost.toFixed(2)}</div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">现价</div><div style="font-size:16px;font-weight:700" class="${chgCls}">${displayPrice.toFixed(2)}</div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">盈亏</div><div style="font-size:16px;font-weight:700" class="${pCls}">${pSign}${pnlAmt.toFixed(0)}元</div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">盈亏比例</div><div style="font-size:16px;font-weight:700" class="${pCls}">${pSign}${pnlPct.toFixed(2)}%</div></div>
          </div>`;

      if (pnlPct < -5) {
        html += `<div style="background:var(--rise-bg);padding:10px 14px;border-radius:8px;font-size:13px;color:var(--rise)">⚠️ 亏损较大，建议严格执行止损。止损位 ${s.stop_loss || '-'} 元。</div>`;
      } else if (pnlPct > 10) {
        html += `<div style="background:var(--fall-bg);padding:10px 14px;border-radius:8px;font-size:13px;color:var(--fall)">✅ 盈利丰厚！目标价 ${s.target_price || '-'} 元，${s.target_price && displayPrice < s.target_price ? '尚未到达目标，可继续持有。' : '已达到目标区间，建议分批止盈。'}</div>`;
      } else {
        html += `<div style="background:var(--bg2);padding:10px 14px;border-radius:8px;font-size:13px;color:var(--text2)">当前持仓浮${pnl >= 0 ? '盈' : '亏'}${Math.abs(pnlPct).toFixed(1)}%，${s.recommendation === '强烈买入' || s.recommendation === '买入' ? '趋势向好，建议持有等待目标价。' : s.recommendation === '卖出' || s.recommendation === '强烈卖出' ? '技术面转弱，建议逢高减仓。' : '建议继续观察。'}</div>`;
      }
      html += '</div></div>';
    }

    if (s.ma5) {
      html += `<div class="detail-section"><h3>📈 技术指标</h3><div class="detail-grid">
        <div class="detail-grid-item"><div class="detail-grid-label">MA5</div><div class="detail-grid-value">${s.ma5}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">MA10</div><div class="detail-grid-value">${s.ma10}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">MA20</div><div class="detail-grid-value">${s.ma20}</div></div>
        ${s.ma60 ? `<div class="detail-grid-item"><div class="detail-grid-label">MA60</div><div class="detail-grid-value">${s.ma60}</div></div>` : ''}
        ${s.rsi6 ? `<div class="detail-grid-item"><div class="detail-grid-label">RSI6</div><div class="detail-grid-value" style="color:${s.rsi6 < 30 ? 'var(--rise)' : s.rsi6 > 70 ? 'var(--fall)' : ''}">${s.rsi6}</div></div>` : ''}
        ${s.rsi12 ? `<div class="detail-grid-item"><div class="detail-grid-label">RSI12</div><div class="detail-grid-value">${s.rsi12}</div></div>` : ''}
        ${s.kdj_k ? `<div class="detail-grid-item"><div class="detail-grid-label">KDJ-K</div><div class="detail-grid-value">${s.kdj_k}</div></div>` : ''}
        ${s.kdj_j ? `<div class="detail-grid-item"><div class="detail-grid-label">KDJ-J</div><div class="detail-grid-value" style="color:${s.kdj_j < 20 ? 'var(--rise)' : (s.kdj_j > 100 ? 'var(--fall)' : '')}">${s.kdj_j}</div></div>` : ''}
        ${s.macd_dif !== undefined ? `<div class="detail-grid-item"><div class="detail-grid-label">MACD DIF</div><div class="detail-grid-value" style="color:${s.macd_dif >= 0 ? 'var(--rise)' : 'var(--fall)'}">${s.macd_dif}</div></div>` : ''}
        ${s.boll_upper ? `<div class="detail-grid-item"><div class="detail-grid-label">布林上轨</div><div class="detail-grid-value">${s.boll_upper}</div></div>` : ''}
        ${s.boll_middle ? `<div class="detail-grid-item"><div class="detail-grid-label">布林中轨</div><div class="detail-grid-value">${s.boll_middle}</div></div>` : ''}
        ${s.boll_lower ? `<div class="detail-grid-item"><div class="detail-grid-label">布林下轨</div><div class="detail-grid-value">${s.boll_lower}</div></div>` : ''}
      </div></div>`;
    }

    if (s.signals && s.signals.length) {
      html += `<div class="detail-section"><h3>📡 技术信号</h3><div class="signal-tags">${s.signals.map(sig => {
        const isBuy = buyKw.some(k => sig.includes(k));
        const isSell = sellKw.some(k => sig.includes(k));
        return `<span class="signal-tag ${isBuy ? 'buy' : isSell ? 'sell' : 'neutral'}">${sig}</span>`;
      }).join('')}</div></div>`;
    }

    html += `<div class="detail-section"><h3>🎯 操作建议</h3>
      <div class="op-row"><span class="op-label">综合建议</span><span class="op-value" style="color:${this.recColor(s.recommendation)};font-size:16px">${s.recommendation}（${s.score}分）</span></div>
      ${s.trend ? `<div class="op-row"><span class="op-label">趋势判断</span><span class="op-value">${s.trend === '上升' ? '⬆ 上升趋势' : s.trend === '下降' ? '⬇ 下降趋势' : '↔ 横盘震荡'}</span></div>` : ''}
      ${s.buy_point ? `<div class="op-row"><span class="op-label">建议买入区间</span><span class="op-value text-rise">${s.buy_point} 元</span></div>` : ''}
      ${s.buy_time ? `<div class="op-row"><span class="op-label">建议买入时间</span><span class="op-value">${s.buy_time}</span></div>` : ''}
      ${s.stop_loss ? `<div class="op-row"><span class="op-label">止损位</span><span class="op-value text-fall">${s.stop_loss} 元</span></div>` : ''}
      ${s.target_price ? `<div class="op-row"><span class="op-label">目标价位</span><span class="op-value text-rise">${s.target_price} 元</span></div>` : ''}
      ${s.sell_time ? `<div class="op-row"><span class="op-label">建议卖出时间</span><span class="op-value">${s.sell_time}</span></div>` : ''}
      ${s.support ? `<div class="op-row"><span class="op-label">关键支撑</span><span class="op-value">${s.support} 元</span></div>` : ''}
      ${s.resistance ? `<div class="op-row"><span class="op-label">关键压力</span><span class="op-value">${s.resistance} 元</span></div>` : ''}
      ${!isHolding ? `<div style="padding:12px 16px"><button class="btn btn-primary" style="width:100%" onclick="App.addToPortfolio('${s.code}')">➕ 添加到我的持仓</button></div>` : ''}
    </div>`;

    if (s.analysis_text) {
      html += `<div class="detail-section"><h3>📝 分析解读</h3><div class="analysis-text">${s.analysis_text}</div></div>`;
    }

    if (s.main_force_analysis) {
      html += `<div class="detail-section" style="border-color:var(--accent2)"><h3>🧠 主力心理分析</h3><div class="analysis-text">${s.main_force_analysis.replace(/\n/g, '<br>')}</div></div>`;
    }
    if (s.chip_analysis) {
      html += `<div class="detail-section" style="border-color:var(--gold)"><h3>📊 筹码分布分析</h3><div class="analysis-text">${s.chip_analysis.replace(/\n/g, '<br>')}</div></div>`;
    }

    document.getElementById('detail-content').innerHTML = html;
  },

  // === 持仓管理 ===
  showAddPortfolio() {
    document.getElementById('modal-code').value = '';
    document.getElementById('modal-price').value = '';
    document.getElementById('modal-qty').value = '100';
    document.getElementById('add-modal').classList.remove('hidden');
  },

  modalCodeChange() {
    const q = document.getElementById('modal-code').value.trim();
    if (!q) return;
    const stock = this.findStock(q);
    if (stock) document.getElementById('modal-price').value = stock.price.toFixed(2);
  },

  addToPortfolio(code) {
    const stock = this.findStock(code);
    if (!stock) return;
    document.getElementById('modal-code').value = code;
    document.getElementById('modal-price').value = stock.price.toFixed(2);
    document.getElementById('modal-qty').value = '100';
    document.getElementById('add-modal').classList.remove('hidden');
  },

  autoAddPortfolio() {
    const candidates = [...(this.recData?.strong_buy || []), ...(this.recData?.buy || [])];
    if (!candidates.length) { this.showToast('暂无推荐'); return; }
    const portfolio = Portfolio.get();
    const available = candidates.filter(s => !portfolio.some(p => p.code === s.code));
    if (!available.length) { this.showToast('推荐已全部在持仓中'); return; }
    const pick = available[0];
    document.getElementById('modal-code').value = pick.code;
    document.getElementById('modal-price').value = pick.price.toFixed(2);
    this.showToast('已选取：' + pick.name + '(' + pick.score + '分)');
  },

  closeModal() { document.getElementById('add-modal').classList.add('hidden'); },

  confirmAdd() {
    const codeInput = document.getElementById('modal-code').value.trim();
    const price = parseFloat(document.getElementById('modal-price').value) || 0;
    const qty = parseInt(document.getElementById('modal-qty').value) || 100;
    if (!codeInput) { this.showToast('请输入股票代码或名称'); return; }
    let code = codeInput;
    if (!this.findStock(code)) {
      const stock = this.allData?.stocks?.find(s => s.name.includes(code) || s.code.includes(code));
      if (stock) code = stock.code;
      else { this.showToast('未找到该股票'); return; }
    }
    if (price <= 0) { this.showToast('请输入有效价格'); return; }
    Portfolio.add(code, price, qty);
    this.closeModal();
    this.renderPortfolio();
    this.showToast('已添加到持仓');
  },

  // === 页面切换 ===
  showPage(id) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('page-' + id).classList.add('active');
    window.scrollTo(0, 0);
    if (id === 'history') { this._historyDetailFile = null; this.renderHistory(); }
    if (id === 'trading') this.renderTrading();
    if (id === 'strategy') this.renderStrategy();
  },

  back() { this.showPage('home'); },

  // === 策略分析页 ===
  async renderStrategy() {
    const el = document.getElementById('strategy-content');
    if (!el) return;
    el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text3)">加载策略数据...</div>';

    try {
      let data = null;
      if (this._apiAvailable) {
        const res = await fetch(this.API_BASE + '/api/strategy_results');
        if (res.ok) data = await res.json();
      }
      if (!data) {
        // 从 recommendations.json 加载
        try {
          const res = await fetch('data/recommendations.json');
          if (res.ok) {
            const rec = await res.json();
            data = rec.strategy_results || null;
          }
        } catch {}
      }
      if (!data) {
        el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text3)">暂无策略数据，等待下次分析更新</div>';
        return;
      }

      const stats = data.stats || {};
      const results = data.results || {};
      const date = data.date || '';
      document.getElementById('strategy-update-time').textContent = date ? date + ' 筛选' : '';

      // 策略统计排行
      let html = `<div style="margin-bottom:16px">
        <div style="font-size:15px;font-weight:700;margin-bottom:12px">📊 策略表现排行</div>
        <div style="font-size:11px;color:var(--text3);margin-bottom:8px">按胜率排序 · 追踪中 · 30天验证期</div>
        <div style="overflow-x:auto"><table style="width:100%;font-size:12px;border-collapse:collapse">
          <thead><tr style="border-bottom:1px solid var(--border)">
            <th style="padding:6px 8px;text-align:left">策略</th>
            <th style="padding:6px 4px">类别</th>
            <th style="padding:6px 4px">胜率</th>
            <th style="padding:6px 4px">平均收益</th>
            <th style="padding:6px 4px">样本数</th>
            <th style="padding:6px 4px">活跃天数</th>
          </tr></thead><tbody>`;

      const statEntries = Object.entries(stats);
      statEntries.sort((a, b) => (b[1].win_rate || 0) - (a[1].win_rate || 0));

      statEntries.forEach(([sid, st]) => {
        const wr = st.win_rate || 0;
        const wrCls = wr >= 50 ? 'text-rise' : 'text-fall';
        const wrBar = `<div style="height:4px;border-radius:2px;background:${wr >= 50 ? 'var(--rise)' : 'var(--fall)'};width:${Math.min(wr, 100)}%;margin-top:2px"></div>`;
        const avgCls = (st.avg_pnl || 0) >= 0 ? 'text-rise' : 'text-fall';
        html += `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:6px 8px;font-weight:600">${this.esc(st.name)}</td>
          <td style="padding:6px 4px;color:var(--text3)">${st.category || ''}</td>
          <td style="padding:6px 4px"><span class="${wrCls}">${wr}%</span>${wrBar}</td>
          <td style="padding:6px 4px" class="${avgCls}">${st.avg_pnl >= 0 ? '+' : ''}${st.avg_pnl}%</td>
          <td style="padding:6px 4px">${st.total_trades || 0}</td>
          <td style="padding:6px 4px;color:var(--text3)">${st.days_active || 0}</td>
        </tr>`;
      });

      html += '</tbody></table></div></div>';

      // 今日筛选结果
      html += '<div style="margin-top:16px"><div style="font-size:15px;font-weight:700;margin-bottom:12px">🎯 今日筛选结果</div>';

      const resultEntries = Object.entries(results);
      if (resultEntries.length === 0) {
        html += '<div style="padding:20px;text-align:center;color:var(--text3)">今日无匹配策略</div>';
      } else {
        resultEntries.forEach(([sid, stocks]) => {
          const stName = (stats[sid] || {}).name || sid;
          html += `<div style="margin-bottom:12px">
            <div style="font-size:13px;font-weight:600;margin-bottom:6px">📌 ${this.esc(stName)}（${stocks.length}只）</div>`;

          stocks.forEach((s, i) => {
            const chgCls = (s.change_pct || 0) >= 0 ? 'text-rise' : 'text-fall';
            const chgSign = (s.change_pct || 0) >= 0 ? '+' : '';
            html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;background:var(--bg2);border-radius:6px;margin-bottom:4px;font-size:12px">
              <div>
                <span style="font-weight:600">${this.esc(s.name)}</span>
                <span style="color:var(--text3);margin-left:6px">${s.code}</span>
                <span style="color:var(--text3);margin-left:4px">评分${s.score || '-'}</span>
              </div>
              <div style="display:flex;align-items:center;gap:12px">
                <span class="${chgCls}">${s.price?.toFixed(2) || '-'}元 ${chgSign}${(s.change_pct || 0).toFixed(2)}%</span>
                <span style="color:var(--text3);font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${this.esc(s.reason || '')}</span>
              </div>
            </div>`;
          });

          html += '</div>';
        });
      }

      // 策略说明
      html += `<div style="margin-top:20px;padding:12px;background:var(--bg2);border-radius:8px">
        <div style="font-size:12px;color:var(--text3);line-height:1.6">
          🧪 <strong>策略实验室说明</strong><br>
          • 定义了20个短线策略，覆盖趋势、技术、形态、资金、庄家5大类别<br>
          • 每次分析自动筛选符合条件的股票（每策略最多5只）<br>
          • 追踪30天表现，统计各策略胜率和平均收益<br>
          • 不断优化策略权重，目标是筛选出高收益强稳定性的策略<br>
          • 策略基于技术指标和庄家行为分析，捕捉拉升前埋伏和回调吃利机会
        </div>
      </div>`;

      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text3)">加载失败: ' + e.message + '</div>';
    }
  },

  // === 工具 ===
  findStock(code) {
    return this.allData?.stocks?.find(s => s.code === code || s.name === code);
  },

  recColor(rec) {
    return { '强烈买入': '#ef4444', '买入': '#f87171', '关注': '#fbbf24', '卖出': '#4ade80', '强烈卖出': '#22c55e' }[rec] || '#8b949e';
  },

  fmtVol(v) {
    if (!v) return '-';
    if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿';
    if (v >= 1e4) return (v / 1e4).toFixed(1) + '万';
    return v.toString();
  },

  fmtAmt(v) {
    if (!v) return '-';
    if (v >= 1e12) return (v / 1e12).toFixed(1) + '万亿';
    if (v >= 1e8) return (v / 1e8).toFixed(1) + '亿';
    if (v >= 1e4) return (v / 1e4).toFixed(1) + '万';
    return v.toFixed(0);
  },

  esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },

  showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.remove('hidden');
    clearTimeout(this._tt);
    this._tt = setTimeout(() => t.classList.add('hidden'), 2000);
  }
};

// === 持仓管理 (localStorage) ===
const Portfolio = {
  KEY: 'stock_portfolio',
  get() { try { return JSON.parse(localStorage.getItem(this.KEY)) || []; } catch { return []; } },
  save(data) { localStorage.setItem(this.KEY, JSON.stringify(data)); },
  add(code, cost, qty) {
    const list = this.get();
    const existing = list.find(p => p.code === code);
    if (existing) { existing.cost = cost; existing.qty = qty; }
    else list.push({ code, cost, qty });
    this.save(list);
  },
  remove(idx) { const list = this.get(); list.splice(idx, 1); this.save(list); },
  clear() { localStorage.removeItem(this.KEY); App.renderPortfolio(); App.showToast('已清空'); }
};

// ========== 虚拟交易页面 ==========
App.renderTrading = function() {
  const r = App.recData;
  const trading = r?.trading;
  if (!trading) {
    document.getElementById('trading-overview').innerHTML = '<div class="empty">等待首次交易分析...</div>';
    return;
  }
  this.renderTradingOverview(trading);
  this.renderTradingReport(trading);
};

App.showTradingTab = function(tab) {
  document.querySelectorAll('.trading-page').forEach(p => p.style.display = 'none');
  document.getElementById('trading-' + tab).style.display = '';
  document.querySelectorAll('.htab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  if (tab === 'records') this.renderTradingRecords();
  if (tab === 'report') this.renderTradingReportFull();
  if (tab === 'purchased') this.renderPurchasedStocks();
};

App.renderTradingOverview = function(trading) {
  const p = trading.portfolio;
  const stats = trading.stats || {};
  const totalReturn = p.total_return || 0;
  const retSign = totalReturn >= 0 ? '+' : '';
  const retCls = totalReturn >= 0 ? 'text-rise' : 'text-fall';
  const retEmoji = totalReturn >= 0 ? '🚀' : '📉';

  let html = `<div class="trading-overview">
    <div class="trading-account-card">
      <div class="trading-account-header">
        <span class="trading-account-label">虚拟账户</span>
        <span class="trading-account-emoji">${retEmoji}</span>
      </div>
      <div class="trading-account-value">${(p.total_assets || 0).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2})} 元</div>
      <div class="trading-account-return ${retCls}">${retSign}${totalReturn.toFixed(2)}%</div>
      <div class="trading-account-stats">
        <div class="ta-stat"><div class="ta-stat-val">${(p.cash || 0).toLocaleString('zh-CN', {minimumFractionDigits:0, maximumFractionDigits:0})}</div><div class="ta-stat-label">可用资金</div></div>
        <div class="ta-stat"><div class="ta-stat-val">${(p.position_value || 0).toLocaleString('zh-CN', {minimumFractionDigits:0, maximumFractionDigits:0})}</div><div class="ta-stat-label">持仓市值</div></div>
        <div class="ta-stat"><div class="ta-stat-val">${(p.position_ratio || 0).toFixed(1)}%</div><div class="ta-stat-label">仓位比例</div></div>
        <div class="ta-stat"><div class="ta-stat-val ${stats.total_pnl >= 0 ? 'text-rise' : 'text-fall'}">${stats.total_pnl >= 0 ? '+' : ''}${(stats.total_pnl || 0).toLocaleString('zh-CN', {minimumFractionDigits:0, maximumFractionDigits:0})}</div><div class="ta-stat-label">累计盈亏</div></div>
      </div>
    </div>

    <div class="trading-stats-bar">
      <div class="ts-item"><span class="ts-val">${stats.total_trades || 0}</span><span class="ts-label">总交易</span></div>
      <div class="ts-item"><span class="ts-val">${stats.total_trades ? (stats.win_trades / stats.total_trades * 100).toFixed(0) : 0}%</span><span class="ts-label">胜率</span></div>
      <div class="ts-item"><span class="ts-val">${stats.max_drawdown || 0}%</span><span class="ts-label">最大回撤</span></div>
    </div>`;

  const holdings = p.holdings || {};
  const hKeys = Object.keys(holdings);
  if (hKeys.length) {
    html += `<div class="trading-section-title">📈 当前持仓（${hKeys.length}只）</div>`;
    hKeys.forEach(code => {
      const h = holdings[code];
      const cur = h.current_price || h.avg_cost;
      const pnl = (cur - h.avg_cost) * h.qty;
      const pnlPct = (cur - h.avg_cost) / h.avg_cost * 100;
      const pnlSign = pnl >= 0 ? '+' : '';
      const pnlCls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const emoji = pnl >= 0 ? '🟢' : '🔴';

      html += `<div class="trading-holding-card" onclick="App.openStock('${code}')">
        <div class="th-left">
          <div class="th-name">${this.esc(h.name)}<span class="th-code">${code}</span></div>
          <div class="th-detail">${h.qty}股 · 成本${h.avg_cost.toFixed(2)} · 现价${cur.toFixed(2)}</div>
        </div>
        <div class="th-right ${pnlCls}">
          <div class="th-pnl">${emoji} ${pnlSign}${pnl.toLocaleString('zh-CN', {minimumFractionDigits:0, maximumFractionDigits:0})}元</div>
          <div class="th-pct">${pnlSign}${pnlPct.toFixed(2)}%</div>
        </div>
      </div>`;
    });
  } else {
    html += `<div class="trading-empty">空仓观望中</div>`;
  }

  const report = trading.latest_report;
  if (report) {
    html += `<div class="trading-section-title">📝 最近操作</div>`;
    if (report.buys?.length) {
      report.buys.forEach(b => {
        html += `<div class="trading-action buy">
          <span class="ta-type">✅ 买入</span>
          <span class="ta-name">${this.esc(b.name)}（${b.code}）</span>
          <span class="ta-info">${b.qty}股 × ${b.price.toFixed(2)}元 = ${(b.amount||0).toLocaleString('zh-CN', {maximumFractionDigits:0})}元</span>
          <span class="ta-reason">${this.esc(b.reason)}</span>
        </div>`;
      });
    }
    if (report.sells?.length) {
      report.sells.forEach(s => {
        const sp = s.pnl >= 0 ? '+' : '';
        const sc = s.pnl >= 0 ? 'text-rise' : 'text-fall';
        html += `<div class="trading-action sell">
          <span class="ta-type">❌ 卖出</span>
          <span class="ta-name">${this.esc(s.name)}（${s.code}）</span>
          <span class="ta-info">${s.qty}股 × ${s.price.toFixed(2)}元 · <span class="${sc}">${sp}${(s.pnl||0).toFixed(0)}元(${sp}${(s.pnl_pct||0).toFixed(1)}%)</span></span>
          <span class="ta-reason">${this.esc(s.reason)}</span>
        </div>`;
      });
    }
    if (!report.buys?.length && !report.sells?.length) {
      html += `<div class="trading-action">📌 今日无操作（持仓观望）</div>`;
    }
  }

  html += '</div>';
  document.getElementById('trading-overview').innerHTML = html;
};

App.renderTradingReport = function(trading) {
  document.getElementById('trading-report').innerHTML = '<div class="empty">点击"日报"标签查看完整汇报</div>';
};

App.renderTradingReportFull = function() {
  const el = document.getElementById('trading-report');
  fetch('data/portfolio.json').then(r => r.json()).then(data => {
    const reports = data.daily_reports || [];
    if (!reports.length) { el.innerHTML = '<div class="empty">暂无日报</div>'; return; }

    let html = '';
    reports.slice().reverse().forEach(report => {
      const retSign = (report.total_return || 0) >= 0 ? '+' : '';
      const retCls = (report.total_return || 0) >= 0 ? 'text-rise' : 'text-fall';
      const pnlSign = (report.today_pnl || 0) >= 0 ? '+' : '';
      const pnlCls = (report.today_pnl || 0) >= 0 ? 'text-rise' : 'text-fall';

      html += `<div class="report-card">
        <div class="report-header">
          <span class="report-date">${report.date}</span>
          <span class="report-sentiment">${report.market_sentiment}（${report.market_score}分）</span>
        </div>
        <div class="report-nums">
          <div class="rn"><div class="rn-val">${(report.total_assets||0).toLocaleString('zh-CN', {maximumFractionDigits:0})}</div><div class="rn-label">总资产</div></div>
          <div class="rn"><div class="rn-val ${retCls}">${retSign}${(report.total_return||0).toFixed(2)}%</div><div class="rn-label">总收益</div></div>
          <div class="rn"><div class="rn-val ${pnlCls}">${pnlSign}${(report.today_pnl||0).toFixed(0)}元</div><div class="rn-label">今日盈亏</div></div>
          <div class="rn"><div class="rn-val">${(report.position_ratio||0).toFixed(0)}%</div><div class="rn-label">仓位</div></div>
        </div>`;
      if (report.buys?.length) {
        html += `<div class="report-section"><div class="rs-title">✅ 买入</div>`;
        report.buys.forEach(b => { html += `<div class="rs-item"><strong>${this.esc(b.name)}</strong> ${b.qty}股 × ${b.price.toFixed(2)}元<br><span class="rs-reason">${this.esc(b.reason)}</span></div>`; });
        html += '</div>';
      }
      if (report.sells?.length) {
        html += `<div class="report-section"><div class="rs-title">❌ 卖出</div>`;
        report.sells.forEach(s => {
          const sp = (s.pnl||0) >= 0 ? '+' : '';
          const sc = (s.pnl||0) >= 0 ? 'text-rise' : 'text-fall';
          html += `<div class="rs-item"><strong>${this.esc(s.name)}</strong> ${s.qty}股 × ${s.price.toFixed(2)}元 · <span class="${sc}">${sp}${(s.pnl||0).toFixed(0)}元</span><br><span class="rs-reason">${this.esc(s.reason)}</span></div>`;
        });
        html += '</div>';
      }
      if (report.holdings?.length) {
        html += `<div class="report-section"><div class="rs-title">📈 持仓明细</div><div class="rs-grid">`;
        report.holdings.forEach(h => {
          const hc = (h.pnl||0) >= 0 ? 'text-rise' : 'text-fall';
          const hs = (h.pnl||0) >= 0 ? '+' : '';
          html += `<div class="rsg-item"><span class="rsg-name">${this.esc(h.name)}</span><span class="rsg-info">${h.qty}股</span><span class="rsg-pnl ${hc}">${hs}${(h.pnl||0).toFixed(0)}元</span></div>`;
        });
        html += '</div></div>';
      }
      html += '</div>';
    });
    el.innerHTML = html;
  }).catch(() => { el.innerHTML = '<div class="empty">加载失败</div>'; });
};

App.renderTradingRecords = function() {
  const el = document.getElementById('trading-records');
  fetch('data/trade_log.json').then(r => r.json()).then(data => {
    const trades = data.trades || [];
    if (!trades.length) { el.innerHTML = '<div class="empty">暂无交易记录</div>'; return; }
    const verified = data.verified !== false;

    let html = `<div class="records-header"><span>共 ${trades.length} 笔交易</span><span class="records-verify">${verified ? '🔒 记录完整' : '⚠️ 记录异常'}</span></div>`;
    trades.slice().reverse().forEach(t => {
      const isBuy = t.type.includes('buy');
      const pnlSign = (t.pnl || 0) >= 0 ? '+' : '';
      const pnlCls = (t.pnl || 0) >= 0 ? 'text-rise' : 'text-fall';
      html += `<div class="record-item ${isBuy ? 'buy' : 'sell'}">
        <div class="ri-left"><span class="ri-type">${isBuy ? '✅ 买入' : '❌ 卖出'}</span><span class="ri-hash" title="${t.hash}">${(t.hash || '').substring(0, 8)}…</span></div>
        <div class="ri-main">
          <div class="ri-name">${this.esc(t.name)}（${t.code}）</div>
          <div class="ri-detail">${t.qty}股 × ${t.price.toFixed(2)}元 = ${(t.amount||0).toLocaleString('zh-CN', {maximumFractionDigits:0})}元 · 手续费${(t.commission||0).toFixed(1)}元${t.pnl != null ? ` · <span class="${pnlCls}">盈亏${pnlSign}${(t.pnl||0).toFixed(0)}元(${pnlSign}${(t.pnl_pct||0).toFixed(1)}%)</span>` : ''}</div>
          <div class="ri-reason">原因：${this.esc(t.reason)}</div>
        </div>
        <div class="ri-right">
          <div class="ri-time">${t.timestamp}</div>
          <div class="ri-snapshot">资产：${(t.portfolio_snapshot?.total_assets || 0).toLocaleString('zh-CN', {maximumFractionDigits:0})}元</div>
        </div>
      </div>`;
    });
    el.innerHTML = html;
  }).catch(() => { el.innerHTML = '<div class="empty">加载失败</div>'; });
};

// ========== 购买过的股票记录表 ==========
App.renderPurchasedStocks = function() {
  const el = document.getElementById('trading-purchased');
  if (!this._apiAvailable) {
    el.innerHTML = '<div class="empty">需要启动API服务器</div>';
    return;
  }
  el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text3)">加载中...</div>';

  fetch(this.API_BASE + '/api/purchased_stocks').then(r => r.json()).then(data => {
    const stocks = data.stocks || [];
    if (!stocks.length) {
      el.innerHTML = '<div class="empty">暂无购买记录</div>';
      return;
    }

    let html = `<div style="padding:8px 0 16px;border-bottom:1px solid var(--border);margin-bottom:12px">
      <div style="font-size:14px;font-weight:700">📊 购买过的股票记录（${stocks.length}只）</div>
      <div style="font-size:11px;color:var(--text3);margin-top:4px">显示所有曾经买入的股票，含当前价格、买卖明细和K线走势</div>
    </div>`;

    stocks.forEach(s => {
      const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = s.change_pct >= 0 ? '+' : '';
      const statusColor = s.status === '已卖出' ? 'var(--gold)' : 'var(--accent)';
      const statusEmoji = s.status === '已卖出' ? '📦' : '💼';
      const pnlCls = (s.total_pnl || 0) >= 0 ? 'text-rise' : 'text-fall';
      const pnlSign = (s.total_pnl || 0) >= 0 ? '+' : '';

      html += `<div class="ps-card" id="ps-${s.code}">
        <div class="ps-header" onclick="App.togglePsDetail('${s.code}')">
          <div class="ps-left">
            <span style="font-weight:700;font-size:14px">${this.esc(s.name)}</span>
            <span style="color:var(--text3);font-size:11px;margin-left:6px">${s.code}</span>
            <span class="ps-status" style="color:${statusColor};margin-left:8px">${statusEmoji} ${s.status}</span>
          </div>
          <div class="ps-right">
            <span style="font-size:14px;font-weight:600" class="${chgCls}">${s.current_price.toFixed(2)}</span>
            <span style="font-size:12px" class="${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</span>
            <span class="ps-arrow" id="arrow-${s.code}">▼</span>
          </div>
        </div>

        <div class="ps-detail" id="detail-${s.code}" style="display:none">
          <div class="ps-grid">
            <div class="ps-grid-item"><div class="ps-label">买入价格</div><div class="ps-value">${s.buy_price.toFixed(2)}元</div></div>
            <div class="ps-grid-item"><div class="ps-label">买入时间</div><div class="ps-value">${s.buy_time}</div></div>
            <div class="ps-grid-item"><div class="ps-label">买入数量</div><div class="ps-value">${s.buy_qty}股</div></div>
            <div class="ps-grid-item"><div class="ps-label">当前股价</div><div class="ps-value ${chgCls}">${s.current_price.toFixed(2)}元</div></div>
            ${s.sell_price ? `
            <div class="ps-grid-item"><div class="ps-label">卖出价格</div><div class="ps-value">${s.sell_price.toFixed(2)}元</div></div>
            <div class="ps-grid-item"><div class="ps-label">卖出时间</div><div class="ps-value">${s.sell_time}</div></div>
            <div class="ps-grid-item"><div class="ps-label">卖出盈亏</div><div class="ps-value ${pnlCls}">${pnlSign}${(s.total_pnl||0).toFixed(0)}元 (${pnlSign}${(s.sell_pnl_pct||0).toFixed(1)}%)</div></div>
            ` : `
            <div class="ps-grid-item"><div class="ps-label">卖出价格</div><div class="ps-value" style="color:var(--text3)">未卖出</div></div>
            <div class="ps-grid-item"><div class="ps-label">卖出时间</div><div class="ps-value" style="color:var(--text3)">-</div></div>
            <div class="ps-grid-item"><div class="ps-label">浮动盈亏</div><div class="ps-value ${pnlCls}">${pnlSign}${((s.current_price - s.buy_price) * s.buy_qty).toFixed(0)}元</div></div>
            `}
            <div class="ps-grid-item"><div class="ps-label">交易次数</div><div class="ps-value">买入${s.total_buys}次 / 卖出${s.total_sells}次</div></div>
          </div>

          <div style="margin-top:12px">
            <div style="font-size:12px;font-weight:600;margin-bottom:8px">📈 K线走势（买入后近3天 · 60分钟线）</div>
            <canvas id="kline-ps-${s.code}" width="800" height="200" style="width:100%;height:200px;background:var(--bg2);border-radius:8px"></canvas>
          </div>
        </div>
      </div>`;
    });

    el.innerHTML = html;
  }).catch(() => {
    el.innerHTML = '<div class="empty">加载失败</div>';
  });
};

App.togglePsDetail = function(code) {
  const detail = document.getElementById('detail-' + code);
  const arrow = document.getElementById('arrow-' + code);
  if (!detail) return;
  const isVisible = detail.style.display !== 'none';
  detail.style.display = isVisible ? 'none' : '';
  if (arrow) arrow.textContent = isVisible ? '▼' : '▲';

  // 首次展开时加载K线
  if (!isVisible) {
    this.loadPsKline(code);
  }
};

App.loadPsKline = function(code) {
  const canvas = document.getElementById('kline-ps-' + code);
  if (!canvas || canvas.dataset.loaded) return;
  canvas.dataset.loaded = '1';
  if (!this._apiAvailable) return;
  fetch(this.API_BASE + '/api/price_history?code=' + code + '&days=3').then(r => r.json()).then(data => {
    const points = data.points || [];
    if (points.length < 2) {
      canvas.style.display = 'none';
      const parent = canvas.parentElement;
      const msg = document.createElement('div');
      msg.style.cssText = 'padding:12px;color:var(--text3);font-size:12px';
      msg.textContent = '暂无价格记录';
      parent.replaceChild(msg, canvas);
      return;
    }
    this._drawPsPriceLine(canvas, points, code);
  }).catch(() => { canvas.style.display = 'none'; });
};

App._drawPsPriceLine = function(canvas, points, code) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const pad = { top: 20, right: 50, bottom: 25, left: 10 };
  const cW = W - pad.left - pad.right;
  const cH = H - pad.top - pad.bottom;
  ctx.clearRect(0, 0, W, H);

  const prices = points.map(p => p.price);
  let minP = Math.min(...prices), maxP = Math.max(...prices);
  const range = maxP - minP || 1;
  minP -= range * 0.08;
  maxP += range * 0.08;
  const totalRange = maxP - minP;
  const toY = p => pad.top + (1 - (p - minP) / totalRange) * cH;
  const toX = i => pad.left + (i / Math.max(points.length - 1, 1)) * cW;

  // Grid
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= 3; i++) {
    const y = pad.top + (cH / 3) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
    const price = maxP - (totalRange / 3) * i;
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.font = '10px monospace';
    ctx.textAlign = 'left';
    ctx.fillText(price.toFixed(2), W - pad.right + 4, y + 3);
  }

  // Gradient fill
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + cH);
  grad.addColorStop(0, 'rgba(59,130,246,0.2)');
  grad.addColorStop(1, 'rgba(59,130,246,0.02)');
  ctx.beginPath();
  ctx.moveTo(toX(0), toY(points[0].price));
  points.forEach((p, i) => ctx.lineTo(toX(i), toY(p.price)));
  ctx.lineTo(toX(points.length - 1), pad.top + cH);
  ctx.lineTo(toX(0), pad.top + cH);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.moveTo(toX(0), toY(points[0].price));
  points.forEach((p, i) => ctx.lineTo(toX(i), toY(p.price)));
  ctx.strokeStyle = '#3b82f6';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Dots + time
  const step = Math.max(1, Math.floor(points.length / 5));
  points.forEach((p, i) => {
    if (i % step === 0 || i === points.length - 1) {
      const x = toX(i), y = toY(p.price);
      ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = '#3b82f6'; ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.25)';
      ctx.font = '9px monospace'; ctx.textAlign = 'center';
      ctx.fillText(p.time ? p.time.substring(5, 16) : '', x, H - 4);
    }
  });
};

// ========== 手动买入/卖出弹窗 ==========

App._showTradeModal = function(opts) {
  // opts: { mode:'buy'|'sell', code, name, price, qty, maxQty }
  const isBuy = opts.mode === 'buy';
  const title = isBuy ? '买入' : '卖出';
  const priceHint = opts.price ? '参考价: ' + opts.price : '';

  // Create modal if not exists
  let modal = document.getElementById('trade-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'trade-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center';
    document.body.appendChild(modal);
  }

  modal.innerHTML = '<div style="background:var(--bg1);border:1px solid var(--border);border-radius:12px;padding:20px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,0.3)">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">' +
    '<span style="font-size:16px;font-weight:700">' + (isBuy ? '🟢' : '🔴') + ' ' + title + ' ' + this.esc(opts.name) + ' (' + opts.code + ')</span>' +
    '<span style="cursor:pointer;font-size:18px;color:var(--text3)" onclick="App._closeTradeModal()">&#10005;</span>' +
    '</div>' +
    '<div style="margin-bottom:12px;font-size:12px;color:var(--text3)">' + priceHint + (opts.maxQty ? ' · 持有' + opts.maxQty + '股' : '') + '</div>' +
    '<div style="margin-bottom:12px">' +
    '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">' + title + '价格（元）</label>' +
    '<input id="trade-price" type="text" inputmode="decimal" value="' + (opts.price || '') + '" placeholder="输入价格" ' +
    'style="width:100%;padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--text1);font-size:14px;outline:none;box-sizing:border-box" />' +
    '</div>' +
    '<div style="margin-bottom:16px">' +
    '<label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">' + title + '数量（股）</label>' +
    '<input id="trade-qty" type="text" inputmode="numeric" value="' + (opts.qty || '') + '" placeholder="输入股数" ' +
    (isBuy && opts.maxQty ? '' : '') + ' ' +
    'style="width:100%;padding:8px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--text1);font-size:14px;outline:none;box-sizing:border-box" />' +
    '<div id="trade-amount" style="font-size:11px;color:var(--text3);margin-top:4px"></div>' +
    '</div>' +
    '<div style="display:flex;gap:8px">' +
    '<button onclick="App._closeTradeModal()" style="flex:1;padding:10px;background:var(--bg2);border:1px solid var(--border);border-radius:8px;color:var(--text2);cursor:pointer;font-size:14px">取消</button>' +
    '<button id="trade-confirm-btn" style="flex:1;padding:10px;background:' + (isBuy ? '#22c55e' : '#ef4444') + ';border:none;border-radius:8px;color:#fff;cursor:pointer;font-size:14px;font-weight:600">确认' + title + '</button>' +
    '</div>' +
    '<div id="trade-error" style="color:var(--fall);font-size:12px;margin-top:8px;display:none"></div>' +
    '</div>';
  modal.style.display = 'flex';

  // Store context on confirm button
  var confirmBtn = document.getElementById('trade-confirm-btn');
  confirmBtn.onclick = function() { App._confirmTrade(opts.mode, opts.code, opts.name, opts.score || 0); };

  // Auto-calc amount
  var priceInput = document.getElementById('trade-price');
  var qtyInput = document.getElementById('trade-qty');
  var amountDiv = document.getElementById('trade-amount');
  var updateAmount = function() {
    var p = parseFloat(priceInput.value) || 0;
    var q = parseInt(qtyInput.value) || 0;
    if (p > 0 && q > 0) {
      var amt = p * q;
      var comm = Math.max(5, Math.round(amt * 0.0003 * 100) / 100);
      if (isBuy) {
        amountDiv.textContent = '金额: ' + amt.toFixed(2) + '元 · 手续费: ' + comm.toFixed(2) + '元 · 总计: ' + (amt + comm).toFixed(2) + '元';
      } else {
        amountDiv.textContent = '金额: ' + amt.toFixed(2) + '元 · 手续费: ' + comm.toFixed(2) + '元 · 到账: ' + (amt - comm).toFixed(2) + '元';
      }
    } else {
      amountDiv.textContent = '';
    }
  };
  priceInput.addEventListener('input', updateAmount);
  qtyInput.addEventListener('input', updateAmount);
  updateAmount();
  priceInput.focus();
};

App._closeTradeModal = function() {
  var modal = document.getElementById('trade-modal');
  if (modal) modal.style.display = 'none';
};

App._confirmTrade = async function(mode, code, name, score) {
  var price = parseFloat(document.getElementById('trade-price').value);
  var qty = parseInt(document.getElementById('trade-qty').value);
  var errDiv = document.getElementById('trade-error');

  if (!price || price <= 0) { errDiv.textContent = '请输入有效的价格'; errDiv.style.display = 'block'; return; }
  if (!qty || qty <= 0) { errDiv.textContent = '请输入有效的数量'; errDiv.style.display = 'block'; return; }

  var btn = document.getElementById('trade-confirm-btn');
  btn.disabled = true; btn.textContent = '处理中...'; errDiv.style.display = 'none';

  try {
    var res = await fetch(this.API_BASE + (mode === 'buy' ? '/api/manual_buy' : '/api/manual_sell'), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ code: code, name: name, price: price, qty: qty, score: score, reason: mode === 'buy' ? '推荐买入' : '手动卖出' }),
    });
    var data = await res.json();
    if (data.error) { errDiv.textContent = data.error; errDiv.style.display = 'block'; btn.disabled = false; btn.textContent = '确认' + (mode === 'buy' ? '买入' : '卖出'); return; }
    this._closeTradeModal();
    this.showToast(data.message || (mode === 'buy' ? '买入成功' : '卖出成功'));
    this.renderVirtualHoldings();
    this.loadPortfolio();
  } catch (e) {
    errDiv.textContent = '请求失败'; errDiv.style.display = 'block'; btn.disabled = false;
  }
};

App.manualBuy = function(code, name, buyPoint, score) {
  this._showTradeModal({ mode: 'buy', code: code, name: name, price: buyPoint || '', score: score || 0 });
};

App.manualSell = function(code, name, maxQty) {
  this._showTradeModal({ mode: 'sell', code: code, name: name, price: '', maxQty: maxQty });
};

document.addEventListener('DOMContentLoaded', () => App.init());
