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

  // === 观察中股票刷新 ===
  startWatchRefresh() {
    const refresh = async () => {
      try {
        const res = await fetch(this.API_BASE + '/api/buy_plan');
        if (!res.ok) return;
        const data = await res.json();
        this.renderWatchList(data);
      } catch {}
    };
    refresh();
    this.watchTimer = setInterval(refresh, 10000); // 10秒刷新
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
      const promises = fileNames.map(f => fetch(`data/history/${f}`).then(r => r.json()).catch(() => null));
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

    this.renderMarketAnalysis(r);
    this.renderStrategies(r);
    this.filterRecList();

    this.renderAccuracy();
    this.renderPortfolio();
    this.renderVirtualHoldings();
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

  // === 中栏 - 大盘分析 ===
  renderMarketAnalysis(r) {
    const el = document.getElementById('market-analysis');
    document.getElementById('analysis-update-time').textContent = r.update_time || '';

    const macro = r.macro_indices || {};
    const idxMap = {
      'sh000001': ['sh000001', '000001'],
      'sz399001': ['sz399001', '399001'],
      'sz399006': ['sz399006', '399006'],
      'int_dji': ['int_dji'],
      'int_nasdaq': ['int_nasdaq'],
      'int_sp500': ['int_sp500'],
    };
    const getIdx = (code) => {
      const keys = idxMap[code] || [code];
      for (const k of keys) { if (macro[k]) return macro[k]; }
      return null;
    };

    let html = `<div class="market-sentiment-badge ${r.market_sentiment}">
      ${r.market_sentiment === '偏多' ? '📈' : r.market_sentiment === '偏空' ? '📉' : '➡️'} 
      市场情绪：${r.market_sentiment} · 综合评分 ${r.avg_score}分
    </div>`;

    html += `<div class="indices-row">`;
    const idxList = [
      { code: 'sh000001', label: '上证' },
      { code: 'sz399001', label: '深证' },
      { code: 'sz399006', label: '创业板' },
      { code: 'int_dji', label: '道琼斯' },
      { code: 'int_nasdaq', label: '纳斯达克' },
      { code: 'int_sp500', label: '标普500' },
    ];
    idxList.forEach(idx => {
      const info = getIdx(idx.code);
      if (info) {
        const cls = info.change_pct >= 0 ? 'text-rise' : 'text-fall';
        const sign = info.change_pct >= 0 ? '+' : '';
        const tag = idx.code.startsWith('int') ? 'us' : '';
        html += `<div class="idx-item ${tag}"><div class="idx-label">${idx.label}</div><div class="idx-val ${cls}">${info.price?.toFixed(2) || '-'}</div><div class="idx-chg ${cls}">${sign}${info.change_pct.toFixed(2)}%</div></div>`;
      }
    });
    html += '</div>';

    const stocks = this.allData.stocks || [];
    const rise = stocks.filter(s => s.change_pct > 0).length;
    const fall = stocks.filter(s => s.change_pct < 0).length;
    const flat = stocks.length - rise - fall;
    const zt = stocks.filter(s => s.change_pct >= 9.8).length;
    const dt = stocks.filter(s => s.change_pct <= -9.8).length;

    html += `<div class="market-stats-row">
      <div class="market-stat-item"><div class="market-stat-val text-rise">${rise}</div><div class="market-stat-label">上涨</div></div>
      <div class="market-stat-item"><div class="market-stat-val text-fall">${fall}</div><div class="market-stat-label">下跌</div></div>
      <div class="market-stat-item"><div class="market-stat-val">${flat}</div><div class="market-stat-label">平盘</div></div>
      <div class="market-stat-item"><div class="market-stat-val text-rise">${zt}</div><div class="market-stat-label">涨停</div></div>
      <div class="market-stat-item"><div class="market-stat-val text-fall">${dt}</div><div class="market-stat-label">跌停</div></div>
    </div>`;

    if (r.market_analysis) {
      html += `<div class="market-text">${this.esc(r.market_analysis)}</div>`;
    }

    el.innerHTML = html;

    if (r.next_day_advice) {
      document.getElementById('next-day-card').style.display = '';
      document.getElementById('next-day-advice').textContent = r.next_day_advice;
    }
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
    if (!this.yesterdayData || !this.yesterdayData.recommendations) {
      if (this.historyData.length >= 2) {
        for (let i = 1; i < this.historyData.length; i++) {
          if (this.historyData[i].recommendations?.strong_buy?.length) { this.yesterdayData = this.historyData[i]; break; }
        }
      }
      if (!this.yesterdayData || !this.yesterdayData.recommendations?.strong_buy?.length) {
        el.innerHTML = '<div class="empty"><div class="empty-icon">📊</div><div>需要至少2次分析数据才能统计准确率</div></div>';
        return;
      }
    }

    const ydStrongBuy = this.yesterdayData.recommendations.strong_buy || [];
    const todayTime = this.historyData[0]?.update_time || '';
    const ydTime = this.yesterdayData.update_time || '';

    if (!ydStrongBuy.length) { el.innerHTML = '<div class="empty">暂无数据</div>'; return; }

    let correct = 0, wrong = 0, totalPnl = 0, details = [];
    ydStrongBuy.forEach(s => {
      const todayStock = this.findStock(s.code);
      if (!todayStock) { details.push({ name: s.name, code: s.code, pred_price: s.price, actual: null }); return; }
      const ydPrice = s.price || s.prev_close;
      const chgPct = todayStock.price > 0 && ydPrice > 0 ? (todayStock.price - ydPrice) / ydPrice * 100 : 0;
      if (chgPct > 0) correct++; else wrong++;
      totalPnl += chgPct;
      details.push({ name: s.name, code: s.code, pred_price: ydPrice, actual: todayStock.price, chg_pct: chgPct, hit: chgPct > 0 });
    });

    const total = correct + wrong;
    const accuracy = total > 0 ? (correct / total * 100) : 0;
    const avgPnl = total > 0 ? totalPnl / total : 0;

    let html = `<div style="text-align:center;margin-bottom:8px;font-size:11px;color:var(--text3)">${ydTime} 预测 → ${todayTime} 实际</div>`;
    html += `<div class="accuracy-summary">
      <div class="accuracy-summary-item"><div class="accuracy-summary-num" style="color:${accuracy >= 60 ? 'var(--fall)' : 'var(--gold)'}">${accuracy.toFixed(0)}%</div><div class="accuracy-summary-label">胜率</div></div>
      <div class="accuracy-summary-item"><div class="accuracy-summary-num ${avgPnl >= 0 ? 'text-rise' : 'text-fall'}">${avgPnl >= 0 ? '+' : ''}${avgPnl.toFixed(2)}%</div><div class="accuracy-summary-label">平均收益</div></div>
      <div class="accuracy-summary-item"><div class="accuracy-summary-num" style="color:var(--accent)">${correct}/${total}</div><div class="accuracy-summary-label">正确/总计</div></div>
    </div>`;

    html += '<div class="accuracy-detail">';
    details.forEach(d => {
      if (d.actual === null) {
        html += `<div class="accuracy-row" onclick="App.openStock('${d.code}')" style="cursor:pointer"><span class="name">${this.esc(d.name)}</span><span class="pred">${d.pred_price?.toFixed(2) || '-'}</span><span class="actual" style="color:var(--text3)">未找到</span></div>`;
      } else {
        const chgSign = d.chg_pct >= 0 ? '+' : '';
        html += `<div class="accuracy-row" onclick="App.openStock('${d.code}')" style="cursor:pointer"><span class="name">${this.esc(d.name)}</span><span class="pred">${d.pred_price.toFixed(2)}</span><span class="actual ${d.hit ? 'correct' : 'wrong'}">${chgSign}${d.chg_pct.toFixed(2)}% ${d.hit ? '✓' : '✗'}</span></div>`;
      }
    });
    html += '</div>';
    el.innerHTML = html;
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
      const allRecs = detail.recommendations || [];
      const recs = [
        ...(allRecs.strong_buy || []).map(s => ({...s, recommendation: '强烈买入'})),
        ...(allRecs.buy || []).map(s => ({...s, recommendation: '建议买入'})),
      ];

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

        // 次日表现：优先用已回填的数据
        const actual = s.next_day_actual;
        let actualHtml = '待计算';
        if (actual) {
          const aSign = actual.actual_pct >= 0 ? '+' : '';
          const aCls = actual.actual_pct >= 0 ? 'text-rise' : 'text-fall';
          const vsEst = actual.vs_estimate != null ? (actual.vs_estimate >= 0 ? '+' : '') + actual.vs_estimate.toFixed(1) : '';
          actualHtml = `<span class="${aCls}" style="font-weight:600">${aSign}${actual.actual_pct.toFixed(2)}%</span><br><span style="font-size:10px;color:var(--text3)">${actual.next_date || ''} ${vsEst ? 'vs预估' + vsEst : ''}</span>`;
        }

        // 预测验证
        let accHtml = '-';
        const pred = s.prediction_result;
        if (pred) {
          const vcls = pred.hit_dir ? 'text-rise' : (pred.label === '接近' ? 'var(--gold)' : 'text-fall');
          accHtml = `<span style="color:${vcls};font-weight:600">${pred.icon} ${pred.label}</span>`;
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

document.addEventListener('DOMContentLoaded', () => App.init());
