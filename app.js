/* === A股智能分析系统 - 前端逻辑 === */

const App = {
  allData: null,
  recData: null,
  filtered: [],
  page: 0,
  pageSize: 50,
  pendingStock: null,

  // === 初始化 ===
  async init() {
    try {
      const [allRes, recRes] = await Promise.all([
        fetch('data/all_stocks.json'),
        fetch('data/recommendations.json')
      ]);
      if (!allRes.ok || !recRes.ok) throw new Error('数据未就绪');
      this.allData = await allRes.json();
      this.recData = await recRes.json();
      this.renderHome();
    } catch (e) {
      document.getElementById('update-time').textContent = '暂无数据';
      document.getElementById('recommendations').innerHTML =
        '<div class="empty"><div class="empty-icon">⏳</div><div>等待首次分析数据...</div><div style="font-size:12px;margin-top:8px;color:var(--text3)">GitHub Actions 将在交易日的 8:30/12:00/14:00/15:30 自动运行分析</div></div>';
      document.getElementById('stock-list').innerHTML = '';
    }
  },

  // === 首页渲染 ===
  renderHome() {
    // 时间和情绪
    document.getElementById('update-time').textContent = this.allData.update_time;
    const sentEl = document.getElementById('market-sentiment');
    sentEl.textContent = this.recData.market_sentiment + ' ' + this.recData.avg_score + '分';
    sentEl.className = 'sentiment ' + this.recData.market_sentiment;

    // 持仓
    this.renderPortfolio();

    // 推荐
    this.renderRecommendations();

    // 策略
    this.renderStrategies();

    // 股票列表
    document.getElementById('stock-count').textContent = this.allData.total + '只';
    this.filter();
  },

  // === 推荐 ===
  renderRecommendations() {
    const r = this.recData;
    const groups = [
      { key: 'strong_buy', label: '🔥 强烈买入' },
      { key: 'buy', label: '📈 建议买入' },
      { key: 'watch', label: '👀 值得关注' },
      { key: 'avoid', label: '⚠️ 建议回避' }
    ];

    let html = '';
    groups.forEach(g => {
      const stocks = r[g.key] || [];
      if (!stocks.length) return;
      html += `<div class="rec-group"><div class="rec-group-title ${g.key === 'avoid' ? '卖出' : (g.key === 'watch' ? '关注' : g.key === 'buy' ? '买入' : '强烈买入')}">${g.label}</div><div class="rec-cards">`;
      stocks.forEach(s => {
        const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
        const chgSign = s.change_pct >= 0 ? '+' : '';
        const signals = (s.signals || []).slice(0, 3);
        html += `<div class="rec-card" onclick="App.openStock('${s.code}')">
          <div class="rec-left">
            <div><span class="rec-name">${this.esc(s.name)}</span><span class="rec-code">${s.code}</span></div>
            <div class="rec-info">${s.industry || ''}</div>
            <div class="rec-signals">${signals.map(t => `<span class="rec-signal-tag">${t}</span>`).join('')}</div>
          </div>
          <div class="rec-right">
            <div class="rec-price ${chgCls}">${s.price.toFixed(2)}</div>
            <div class="rec-change ${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</div>
            <div class="rec-score">评分 ${s.score}</div>
          </div>
        </div>`;
      });
      html += '</div></div>';
    });

    document.getElementById('recommendations').innerHTML = html || '<div class="empty"><div class="empty-icon">📋</div><div>暂无推荐</div></div>';
  },

  // === 策略 ===
  renderStrategies() {
    const strategies = this.recData.strategies || [];
    if (!strategies.length) return;
    const sec = document.getElementById('strategy-section');
    sec.style.display = '';
    let html = '';
    strategies.forEach(s => {
      html += `<div class="strategy-card">
        <div class="strategy-name">${s.name}</div>
        <div class="strategy-desc">${s.desc}</div>
        <div class="strategy-stocks">${(s.stocks || []).map(st =>
          `<span class="strategy-stock" onclick="App.openStock('${st.code}')">${st.name}(${st.score}分)</span>`
        ).join('')}</div>
      </div>`;
    });
    document.getElementById('strategies').innerHTML = html;
  },

  // === 持仓 ===
  renderPortfolio() {
    const portfolio = Portfolio.get();
    const sec = document.getElementById('portfolio-section');
    if (!portfolio.length) { sec.style.display = 'none'; return; }
    sec.style.display = '';
    let html = '';
    portfolio.forEach((pos, i) => {
      const stock = this.findStock(pos.code);
      if (!stock) return;
      const pnl = stock.price - pos.cost;
      const pnlPct = pos.cost > 0 ? (pnl / pos.cost * 100) : 0;
      const pnlCls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const pnlSign = pnl >= 0 ? '+' : '';
      html += `<div class="portfolio-item" onclick="App.openStock('${pos.code}')">
        <div class="portfolio-left">
          <div class="stock-name-row"><span class="stock-name">${this.esc(stock.name)}</span><span class="stock-code">${stock.code}</span>
          <button class="btn-add" onclick="event.stopPropagation();Portfolio.remove(${i})">✕</button></div>
          <div class="portfolio-cost">成本 ${pos.cost.toFixed(2)} × ${pos.qty}股</div>
        </div>
        <div class="portfolio-right">
          <div class="portfolio-pnl ${pnlCls}">${pnlSign}${pnl.toFixed(2)}</div>
          <div class="portfolio-pnl ${pnlCls}" style="font-size:13px">${pnlSign}${pnlPct.toFixed(2)}%</div>
          <div style="font-size:12px;color:${this.recColor(stock.recommendation)};margin-top:2px">${stock.recommendation}</div>
        </div>
      </div>`;
    });
    document.getElementById('portfolio-list').innerHTML = html;
  },

  // === 搜索 ===
  search() {
    const q = document.getElementById('search-input').value.trim();
    if (!q) return;
    const stock = this.findStock(q);
    if (!stock) {
      document.getElementById('search-result').innerHTML = '<div class="empty" style="padding:20px">未找到该股票，请确认名称或代码</div>';
      return;
    }
    this.openStock(stock.code);
  },

  // === 过滤 & 排序 ===
  filter() {
    const recFilter = document.getElementById('filter-rec').value;
    const sortBy = document.getElementById('filter-sort').value;
    let list = [...(this.allData.stocks || [])];

    if (recFilter !== 'all') {
      list = list.filter(s => s.recommendation === recFilter);
    }

    list.sort((a, b) => {
      switch (sortBy) {
        case 'score_desc': return (b.score || 0) - (a.score || 0);
        case 'score_asc': return (a.score || 0) - (b.score || 0);
        case 'change_desc': return (b.change_pct || 0) - (a.change_pct || 0);
        case 'change_asc': return (a.change_pct || 0) - (b.change_pct || 0);
        case 'turnover_desc': return (b.turnover_rate || 0) - (a.turnover_rate || 0);
        default: return 0;
      }
    });

    this.filtered = list;
    this.page = 0;
    this.renderList();
  },

  renderList() {
    const start = 0;
    const end = (this.page + 1) * this.pageSize;
    const slice = this.filtered.slice(start, end);

    if (!slice.length) {
      document.getElementById('stock-list').innerHTML = '<div class="empty"><div class="empty-icon">📭</div><div>没有符合条件的股票</div></div>';
      document.getElementById('btn-load-more').style.display = 'none';
      return;
    }

    let html = '';
    slice.forEach(s => {
      const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = s.change_pct >= 0 ? '+' : '';
      html += `<div class="stock-item" onclick="App.openStock('${s.code}')">
        <div class="stock-left">
          <div class="stock-name-row"><span class="stock-name">${this.esc(s.name)}</span><span class="stock-code">${s.code}</span></div>
          <div class="stock-sub">${s.industry || ''} · 换手${(s.turnover_rate || 0).toFixed(1)}%</div>
        </div>
        <div class="stock-right">
          <div class="stock-price ${chgCls}">${(s.price || 0).toFixed(2)}</div>
          <div class="stock-change ${chgCls}">${chgSign}${(s.change_pct || 0).toFixed(2)}%</div>
          <span class="stock-rec-tag ${s.recommendation}">${s.recommendation}</span>
        </div>
      </div>`;
    });
    document.getElementById('stock-list').innerHTML = html;
    document.getElementById('btn-load-more').style.display = end < this.filtered.length ? '' : 'none';
  },

  loadMore() {
    this.page++;
    const start = this.page * this.pageSize;
    const end = start + this.pageSize;
    const slice = this.filtered.slice(start, end);
    if (!slice.length) return;

    let html = '';
    slice.forEach(s => {
      const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = s.change_pct >= 0 ? '+' : '';
      html += `<div class="stock-item" onclick="App.openStock('${s.code}')">
        <div class="stock-left">
          <div class="stock-name-row"><span class="stock-name">${this.esc(s.name)}</span><span class="stock-code">${s.code}</span></div>
          <div class="stock-sub">${s.industry || ''} · 换手${(s.turnover_rate || 0).toFixed(1)}%</div>
        </div>
        <div class="stock-right">
          <div class="stock-price ${chgCls}">${(s.price || 0).toFixed(2)}</div>
          <div class="stock-change ${chgCls}">${chgSign}${(s.change_pct || 0).toFixed(2)}%</div>
          <span class="stock-rec-tag ${s.recommendation}">${s.recommendation}</span>
        </div>
      </div>`;
    });
    document.getElementById('stock-list').insertAdjacentHTML('beforeend', html);
    if (end >= this.filtered.length) {
      document.getElementById('btn-load-more').style.display = 'none';
    }
  },

  // === 个股详情 ===
  openStock(code) {
    const stock = this.findStock(code);
    if (!stock) { this.showToast('未找到该股票'); return; }
    this.showPage('detail');
    document.getElementById('detail-title').textContent = `${stock.name} ${code}`;

    const s = stock;
    const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
    const chgSign = s.change_pct >= 0 ? '+' : '';

    // 判断信号正负面
    const buyKw = ['金叉','超卖','放量上涨','多头','突破','低位','偏低','下轨','温和上涨','强势上涨','低PE','红柱'];
    const sellKw = ['死叉','超买','放量下跌','空头','高估','偏高','上轨','回调','大幅下跌','绿柱','缩量'];

    let html = '';

    // 核心数据
    html += `<div class="detail-section">
      <h3>📊 实时行情</h3>
      <div style="text-align:center;margin-bottom:16px">
        <div style="font-size:36px;font-weight:800" class="${chgCls}">${(s.price || 0).toFixed(2)}</div>
        <div style="font-size:16px;font-weight:600" class="${chgCls}">${chgSign}${(s.change_pct || 0).toFixed(2)}%</div>
        <div style="font-size:24px;font-weight:800;margin-top:8px;color:${this.recColor(s.recommendation)}">${s.recommendation} · ${s.score}分</div>
      </div>
      <div class="detail-grid">
        <div class="detail-grid-item"><div class="detail-grid-label">今开</div><div class="detail-grid-value">${(s.open || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">最高</div><div class="detail-grid-value text-rise">${(s.high || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">最低</div><div class="detail-grid-value text-fall">${(s.low || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">昨收</div><div class="detail-grid-value">${(s.prev_close || 0).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">成交量</div><div class="detail-grid-value">${this.fmtVol(s.volume)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">成交额</div><div class="detail-grid-value">${this.fmtAmt(s.amount)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">换手率</div><div class="detail-grid-value">${(s.turnover_rate || 0).toFixed(2)}%</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">量比</div><div class="detail-grid-value">${(s.volume_ratio || 1).toFixed(2)}</div></div>
        <div class="detail-grid-item"><div class="detail-grid-label">振幅</div><div class="detail-grid-value">${(s.amplitude || 0).toFixed(2)}%</div></div>
      </div>
      ${s.pe ? `<div class="op-row"><span class="op-label">市盈率(动态)</span><span class="op-value">${s.pe.toFixed(1)}</span></div>` : ''}
      ${s.pb ? `<div class="op-row"><span class="op-label">市净率</span><span class="op-value">${s.pb.toFixed(2)}</span></div>` : ''}
      ${s.market_cap ? `<div class="op-row"><span class="op-label">总市值</span><span class="op-value">${this.fmtAmt(s.market_cap)}</span></div>` : ''}
    </div>`;

    // 技术指标
    if (s.ma5) {
      html += `<div class="detail-section">
        <h3>📈 技术指标</h3>
        <div class="detail-grid">
          <div class="detail-grid-item"><div class="detail-grid-label">MA5</div><div class="detail-grid-value">${s.ma5}</div></div>
          <div class="detail-grid-item"><div class="detail-grid-label">MA10</div><div class="detail-grid-value">${s.ma10}</div></div>
          <div class="detail-grid-item"><div class="detail-grid-label">MA20</div><div class="detail-grid-value">${s.ma20}</div></div>
          ${s.ma60 ? `<div class="detail-grid-item"><div class="detail-grid-label">MA60</div><div class="detail-grid-value">${s.ma60}</div></div>` : ''}
          ${s.rsi6 ? `<div class="detail-grid-item"><div class="detail-grid-label">RSI6</div><div class="detail-grid-value" style="color:${s.rsi6 < 30 ? 'var(--rise)' : s.rsi6 > 70 ? 'var(--fall)' : ''}">${s.rsi6}</div></div>` : ''}
          ${s.rsi12 ? `<div class="detail-grid-item"><div class="detail-grid-label">RSI12</div><div class="detail-grid-value">${s.rsi12}</div></div>` : ''}
          ${s.kdj_k ? `<div class="detail-grid-item"><div class="detail-grid-label">KDJ-K</div><div class="detail-grid-value">${s.kdj_k}</div></div>` : ''}
          ${s.kdj_d ? `<div class="detail-grid-item"><div class="detail-grid-label">KDJ-D</div><div class="detail-grid-value">${s.kdj_d}</div></div>` : ''}
          ${s.kdj_j ? `<div class="detail-grid-item"><div class="detail-grid-label">KDJ-J</div><div class="detail-grid-value" style="color:${s.kdj_j < 20 ? 'var(--rise)' : s.kdj_j > 100 ? 'var(--fall)' : ''}">${s.kdj_j}</div></div>` : ''}
          ${s.macd_dif !== undefined ? `<div class="detail-grid-item"><div class="detail-grid-label">MACD DIF</div><div class="detail-grid-value" style="color:${s.macd_dif >= 0 ? 'var(--rise)' : 'var(--fall)'}">${s.macd_dif}</div></div>` : ''}
          ${s.macd_dea !== undefined ? `<div class="detail-grid-item"><div class="detail-grid-label">MACD DEA</div><div class="detail-grid-value">${s.macd_dea}</div></div>` : ''}
          ${s.boll_upper ? `<div class="detail-grid-item"><div class="detail-grid-label">布林上轨</div><div class="detail-grid-value">${s.boll_upper}</div></div>` : ''}
          ${s.boll_middle ? `<div class="detail-grid-item"><div class="detail-grid-label">布林中轨</div><div class="detail-grid-value">${s.boll_middle}</div></div>` : ''}
          ${s.boll_lower ? `<div class="detail-grid-item"><div class="detail-grid-label">布林下轨</div><div class="detail-grid-value">${s.boll_lower}</div></div>` : ''}
        </div>
      </div>`;
    }

    // 信号
    if (s.signals && s.signals.length) {
      html += `<div class="detail-section">
        <h3>📡 技术信号</h3>
        <div class="signal-tags">${s.signals.map(sig => {
          const isBuy = buyKw.some(k => sig.includes(k));
          const isSell = sellKw.some(k => sig.includes(k));
          const cls = isBuy ? 'buy' : isSell ? 'sell' : 'neutral';
          return `<span class="signal-tag ${cls}">${sig}</span>`;
        }).join('')}</div>
      </div>`;
    }

    // 操作建议
    html += `<div class="detail-section">
      <h3>🎯 操作建议</h3>
      <div class="op-row"><span class="op-label">综合建议</span><span class="op-value" style="color:${this.recColor(s.recommendation)};font-size:16px">${s.recommendation}（${s.score}分）</span></div>
      ${s.trend ? `<div class="op-row"><span class="op-label">趋势判断</span><span class="op-value">${s.trend === '上升' ? '⬆ 上升趋势' : s.trend === '下降' ? '⬇ 下降趋势' : '↔ 横盘震荡'}</span></div>` : ''}
      ${s.buy_point ? `<div class="op-row"><span class="op-label">建议买入区间</span><span class="op-value text-rise">${s.buy_point} 元</span></div>` : ''}
      ${s.buy_time ? `<div class="op-row"><span class="op-label">建议买入时间</span><span class="op-value">${s.buy_time}</span></div>` : ''}
      ${s.stop_loss ? `<div class="op-row"><span class="op-label">止损位</span><span class="op-value text-fall">${s.stop_loss} 元</span></div>` : ''}
      ${s.target_price ? `<div class="op-row"><span class="op-label">目标价位</span><span class="op-value text-rise">${s.target_price} 元</span></div>` : ''}
      ${s.sell_time ? `<div class="op-row"><span class="op-label">建议卖出时间</span><span class="op-value">${s.sell_time}</span></div>` : ''}
      ${s.support ? `<div class="op-row"><span class="op-label">关键支撑</span><span class="op-value">${s.support} 元</span></div>` : ''}
      ${s.resistance ? `<div class="op-row"><span class="op-label">关键压力</span><span class="op-value">${s.resistance} 元</span></div>` : ''}
      <button class="btn btn-primary" style="width:100%;margin-top:12px" onclick="App.addPortfolio('${s.code}')">➕ 添加到我的持仓</button>
    </div>`;

    // 分析文本
    if (s.analysis_text) {
      html += `<div class="detail-section">
        <h3>📝 分析解读</h3>
        <div class="analysis-text">${s.analysis_text}</div>
      </div>`;
    }

    document.getElementById('detail-content').innerHTML = html;
  },

  // === 持仓管理 ===
  addPortfolio(code) {
    this.pendingStock = code;
    const stock = this.findStock(code);
    document.getElementById('modal-price').value = stock ? stock.price.toFixed(2) : '';
    document.getElementById('modal-qty').value = '100';
    document.getElementById('add-modal').classList.remove('hidden');
  },

  closeModal() {
    document.getElementById('add-modal').classList.add('hidden');
    this.pendingStock = null;
  },

  confirmAdd() {
    const code = this.pendingStock;
    const price = parseFloat(document.getElementById('modal-price').value) || 0;
    const qty = parseInt(document.getElementById('modal-qty').value) || 100;
    if (!code || price <= 0) { this.showToast('请输入有效价格'); return; }
    Portfolio.add(code, price, qty);
    this.closeModal();
    this.renderPortfolio();
    this.showToast('已添加到持仓');
  },

  // === 工具方法 ===
  findStock(code) {
    if (!this.allData) return null;
    return this.allData.stocks.find(s => s.code === code || s.name === code);
  },

  showPage(id) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('page-' + id).classList.add('active');
    window.scrollTo(0, 0);
  },

  back() {
    this.showPage('home');
  },

  recColor(rec) {
    const map = { '强烈买入': '#ef4444', '买入': '#f87171', '关注': '#fbbf24', '卖出': '#4ade80', '强烈卖出': '#22c55e' };
    return map[rec] || '#8b949e';
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
  get() {
    try { return JSON.parse(localStorage.getItem(this.KEY)) || []; }
    catch { return []; }
  },
  save(data) {
    localStorage.setItem(this.KEY, JSON.stringify(data));
  },
  add(code, cost, qty) {
    const list = this.get();
    if (list.find(p => p.code === code)) { list.find(p => p.code === code).cost = cost; list.find(p => p.code === code).qty = qty; }
    else { list.push({ code, cost, qty }); }
    this.save(list);
  },
  remove(idx) {
    const list = this.get();
    list.splice(idx, 1);
    this.save(list);
  },
  clear() {
    localStorage.removeItem(this.KEY);
    App.renderPortfolio();
    App.showToast('持仓已清空');
  }
};

// 启动
document.addEventListener('DOMContentLoaded', () => App.init());
