/* === A股智能分析系统 v2 - 三栏仪表板 === */

const App = {
  allData: null,
  recData: null,
  historyData: [],     // 所有历史快照
  yesterdayData: null, // 昨日快照（用于准确率）
  filtered: [],
  page: 0,
  pageSize: 50,

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
      await this.loadHistory();
      this.renderHome();
    } catch (e) {
      document.getElementById('update-time').textContent = '暂无数据';
      document.getElementById('market-analysis').innerHTML =
        '<div class="empty"><div class="empty-icon">⏳</div><div>等待首次分析数据...</div><div style="font-size:12px;margin-top:8px;color:var(--text3)">GitHub Actions 将在交易日的 8:30/12:00/14:00/15:30 自动运行分析</div></div>';
    }
  },

  // === 加载历史数据 ===
  async loadHistory() {
    try {
      const res = await fetch('data/history/');
      const text = await res.text();
      // 解析目录列表中的JSON文件链接
      const files = text.match(/"[^"]+\.json"/g);
      if (!files) return;
      const fileNames = files.map(f => f.replace(/"/g, '').split('/').pop()).sort().reverse();
      
      const promises = fileNames.map(f => fetch(`data/history/${f}`).then(r => r.json()).catch(() => null));
      const results = await Promise.all(promises);
      this.historyData = results.filter(Boolean);
      
      // 找昨日数据（取倒数第二个时间点的最新数据）
      if (this.historyData.length >= 2) {
        this.yesterdayData = this.historyData[1];
      } else if (this.historyData.length === 1) {
        // 只有今天的数据，无法对比
        this.yesterdayData = null;
      }
    } catch (e) {
      console.log('历史数据加载失败:', e);
    }
  },

  // === 首页渲染 ===
  renderHome() {
    const r = this.recData;
    
    // 时间和情绪
    document.getElementById('update-time').textContent = this.allData.update_time;
    const sentEl = document.getElementById('market-sentiment');
    sentEl.textContent = r.market_sentiment + ' · ' + r.avg_score + '分';
    sentEl.className = 'sentiment ' + r.market_sentiment;

    // 统计数字
    document.getElementById('stat-strong').textContent = (r.strong_buy || []).length;
    document.getElementById('stat-buy').textContent = (r.buy || []).length;
    document.getElementById('stat-watch').textContent = (r.watch || []).length;
    const sellCount = (r.avoid || []).length;
    document.getElementById('stat-sell').textContent = sellCount;

    // 左栏推荐列表
    this.renderRecList('strong-buy-list', r.strong_buy || []);
    this.renderRecList('buy-list', r.buy || []);
    this.renderRecList('watch-list', r.watch || []);

    // 中栏 - 大盘分析
    this.renderMarketAnalysis(r);

    // 中栏 - 策略
    this.renderStrategies(r);

    // 中栏 - 全市场列表
    document.getElementById('stock-count').textContent = this.allData.total + '只';
    this.filter();

    // 右栏 - 准确率
    this.renderAccuracy();

    // 右栏 - 持仓
    this.renderPortfolio();
  },

  // === 左栏推荐列表 ===
  renderRecList(containerId, stocks) {
    const el = document.getElementById(containerId);
    if (!stocks.length) {
      el.innerHTML = '<div class="empty">暂无</div>';
      return;
    }
    el.innerHTML = stocks.map(s => {
      const chgCls = s.change_pct >= 0 ? 'text-rise' : 'text-fall';
      const chgSign = s.change_pct >= 0 ? '+' : '';
      const signals = (s.signals || []).slice(0, 2);
      return `<div class="rec-mini" onclick="App.openStock('${s.code}')">
        <div class="rec-mini-left">
          <span class="rec-mini-name">${this.esc(s.name)}</span>
          <span class="rec-mini-code">${s.code} ${s.industry || ''}</span>
          <div style="display:flex;gap:3px;margin-top:2px">${signals.map(t => `<span class="stock-rec-tag ${s.recommendation}" style="font-size:10px">${t}</span>`).join('')}</div>
        </div>
        <div class="rec-mini-right">
          <div class="rec-mini-price ${chgCls}">${s.price.toFixed(2)}</div>
          <div class="rec-mini-change ${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</div>
          <div class="rec-mini-score">${s.score}分</div>
        </div>
      </div>`;
    }).join('');
  },

  // === 中栏 - 大盘分析 ===
  renderMarketAnalysis(r) {
    const el = document.getElementById('market-analysis');
    document.getElementById('analysis-update-time').textContent = r.update_time || '';

    // 涨跌统计
    const stocks = this.allData.stocks || [];
    const rise = stocks.filter(s => s.change_pct > 0).length;
    const fall = stocks.filter(s => s.change_pct < 0).length;
    const flat = stocks.length - rise - fall;
    const zt = stocks.filter(s => s.change_pct >= 9.8).length;
    const dt = stocks.filter(s => s.change_pct <= -9.8).length;
    const avgChg = stocks.length ? (stocks.reduce((a, s) => a + s.change_pct, 0) / stocks.length) : 0;

    let html = `<div class="market-sentiment-badge ${r.market_sentiment}">
      ${r.market_sentiment === '偏多' ? '📈' : r.market_sentiment === '偏空' ? '📉' : '➡️'} 
      市场情绪：${r.market_sentiment} · 综合评分 ${r.avg_score}分
    </div>`;

    html += `<div class="market-stats-row">
      <div class="market-stat-item">
        <div class="market-stat-val text-rise">${rise}</div>
        <div class="market-stat-label">上涨</div>
      </div>
      <div class="market-stat-item">
        <div class="market-stat-val text-fall">${fall}</div>
        <div class="market-stat-label">下跌</div>
      </div>
      <div class="market-stat-item">
        <div class="market-stat-val">${flat}</div>
        <div class="market-stat-label">平盘</div>
      </div>
      <div class="market-stat-item">
        <div class="market-stat-val ${avgChg >= 0 ? 'text-rise' : 'text-fall'}">${avgChg >= 0 ? '+' : ''}${avgChg.toFixed(2)}%</div>
        <div class="market-stat-label">平均涨幅</div>
      </div>
      <div class="market-stat-item">
        <div class="market-stat-val text-rise">${zt}</div>
        <div class="market-stat-label">涨停</div>
      </div>
      <div class="market-stat-item">
        <div class="market-stat-val text-fall">${dt}</div>
        <div class="market-stat-label">跌停</div>
      </div>
    </div>`;

    // 市场分析文本
    if (r.market_analysis) {
      html += `<div class="market-text">${this.esc(r.market_analysis)}</div>`;
    }

    el.innerHTML = html;

    // 明日建议
    if (r.next_day_advice) {
      document.getElementById('next-day-card').style.display = '';
      document.getElementById('next-day-advice').textContent = r.next_day_advice;
    }
  },

  // === 策略 ===
  renderStrategies(r) {
    const strategies = r.strategies || [];
    if (!strategies.length) return;
    const sec = document.getElementById('strategy-card');
    sec.style.display = '';
    let html = '';
    strategies.forEach(s => {
      html += `<div style="margin-bottom:12px">
        <div style="font-size:14px;font-weight:600;margin-bottom:4px">${s.name}</div>
        <div style="font-size:12px;color:var(--text2);margin-bottom:6px">${s.desc}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${(s.stocks || []).map(st =>
          `<span class="stock-rec-tag 买入" style="cursor:pointer" onclick="App.openStock('${st.code}')">${st.name}(${st.score}分)</span>`
        ).join('')}</div>
      </div>`;
    });
    document.getElementById('strategies').innerHTML = html;
  },

  // === 右栏 - 准确率统计 ===
  renderAccuracy() {
    const el = document.getElementById('accuracy-section');

    if (!this.yesterdayData || !this.yesterdayData.recommendations) {
      // 如果只有今天的数据，或者还没有历史
      if (this.historyData.length >= 1) {
        // 尝试取最早的作为"昨日"
        const earliest = this.historyData[this.historyData.length - 1];
        if (earliest !== this.historyData[0]) {
          this.yesterdayData = earliest;
        } else {
          el.innerHTML = '<div class="empty"><div class="empty-icon">📊</div><div>需要至少2次分析数据才能统计准确率</div><div style="font-size:11px;margin-top:4px">系统每日自动运行4次分析</div></div>';
          return;
        }
      } else {
        el.innerHTML = '<div class="empty"><div class="empty-icon">📊</div><div>需要至少2次分析数据才能统计准确率</div><div style="font-size:11px;margin-top:4px">系统每日自动运行4次分析</div></div>';
        return;
      }
    }

    const ydRec = this.yesterdayData.recommendations;
    const ydStrongBuy = ydRec.strong_buy || [];
    const todayTime = this.historyData[0]?.update_time || '';
    const ydTime = this.yesterdayData.update_time || '';

    if (!ydStrongBuy.length) {
      el.innerHTML = '<div class="empty">暂无昨日强烈买入数据</div>';
      return;
    }

    // 对比：昨日强烈买入的股票今日是否上涨
    let correct = 0;
    let wrong = 0;
    let totalPnl = 0;
    let details = [];

    ydStrongBuy.forEach(s => {
      const todayStock = this.findStock(s.code);
      if (!todayStock) {
        details.push({ name: s.name, code: s.code, pred_price: s.price, actual: null });
        return;
      }
      // 昨日预测的买入，今日是否上涨
      const ydPrice = s.price || s.prev_close;
      const todayPrice = todayStock.price;
      const chgPct = todayPrice > 0 && ydPrice > 0 ? (todayPrice - ydPrice) / ydPrice * 100 : 0;
      if (chgPct > 0) correct++;
      else wrong++;
      totalPnl += chgPct;
      details.push({ name: s.name, code: s.code, pred_price: ydPrice, actual: todayPrice, chg_pct: chgPct, hit: chgPct > 0 });
    });

    const total = correct + wrong;
    const accuracy = total > 0 ? (correct / total * 100) : 0;
    const avgPnl = total > 0 ? totalPnl / total : 0;

    let html = `<div style="text-align:center;margin-bottom:8px;font-size:11px;color:var(--text3)">
      ${ydTime} 预测 → ${todayTime} 实际
    </div>`;

    html += `<div class="accuracy-summary">
      <div class="accuracy-summary-item">
        <div class="accuracy-summary-num" style="color:${accuracy >= 60 ? 'var(--fall)' : accuracy >= 40 ? 'var(--gold)' : 'var(--rise)'}">${accuracy.toFixed(0)}%</div>
        <div class="accuracy-summary-label">胜率</div>
      </div>
      <div class="accuracy-summary-item">
        <div class="accuracy-summary-num ${avgPnl >= 0 ? 'text-rise' : 'text-fall'}">${avgPnl >= 0 ? '+' : ''}${avgPnl.toFixed(2)}%</div>
        <div class="accuracy-summary-label">平均收益</div>
      </div>
      <div class="accuracy-summary-item">
        <div class="accuracy-summary-num" style="color:var(--accent)">${correct}/${total}</div>
        <div class="accuracy-summary-label">正确/总计</div>
      </div>
    </div>`;

    // 逐只对比
    html += '<div class="accuracy-detail">';
    details.forEach(d => {
      if (d.actual === null) {
        html += `<div class="accuracy-row" onclick="App.openStock('${d.code}')" style="cursor:pointer">
          <span class="name">${this.esc(d.name)}</span>
          <span class="pred">${d.pred_price?.toFixed(2) || '-'}</span>
          <span class="actual" style="color:var(--text3)">未找到</span>
        </div>`;
      } else {
        const chgSign = d.chg_pct >= 0 ? '+' : '';
        html += `<div class="accuracy-row" onclick="App.openStock('${d.code}')" style="cursor:pointer">
          <span class="name">${this.esc(d.name)}</span>
          <span class="pred">${d.pred_price.toFixed(2)}</span>
          <span class="actual ${d.hit ? 'correct' : 'wrong'}">${chgSign}${d.chg_pct.toFixed(2)}% ${d.hit ? '✓' : '✗'}</span>
        </div>`;
      }
    });
    html += '</div>';

    el.innerHTML = html;
  },

  // === 右栏 - 持仓 ===
  renderPortfolio() {
    const portfolio = Portfolio.get();
    const el = document.getElementById('portfolio-section');
    const adviceEl = document.getElementById('portfolio-advice');
    const adviceCard = document.getElementById('portfolio-advice-card');

    if (!portfolio.length) {
      el.innerHTML = '<div class="portfolio-empty">暂无持仓，点击上方"添加"录入</div>';
      adviceCard.style.display = 'none';
      return;
    }

    let html = '';
    let adviceHtml = '';

    portfolio.forEach((pos, i) => {
      const stock = this.findStock(pos.code);
      if (!stock) {
        html += `<div class="portfolio-item">
          <div class="portfolio-left">
            <span class="stock-name">${this.esc(pos.code)}</span>
            <span class="portfolio-cost">成本 ${pos.cost.toFixed(2)} × ${pos.qty}股</span>
          </div>
          <div class="portfolio-right" style="color:var(--text3);font-size:12px">
            未找到数据
            <button class="btn-add" onclick="event.stopPropagation();Portfolio.remove(${i});App.renderPortfolio()">✕</button>
          </div>
        </div>`;
        return;
      }

      const pnl = stock.price - pos.cost;
      const pnlPct = pos.cost > 0 ? (pnl / pos.cost * 100) : 0;
      const pnlAmt = pnl * pos.qty;
      const pnlCls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const pnlSign = pnl >= 0 ? '+' : '';

      html += `<div class="portfolio-item" onclick="App.openStock('${pos.code}')">
        <div class="portfolio-left">
          <div style="display:flex;align-items:center;gap:6px">
            <span class="stock-name">${this.esc(stock.name)}</span>
            <span class="stock-code">${stock.code}</span>
            <button class="btn-add" onclick="event.stopPropagation();Portfolio.remove(${i});App.renderPortfolio()">✕</button>
          </div>
          <span class="portfolio-cost">成本 ${pos.cost.toFixed(2)} × ${pos.qty}股 · 现价 ${stock.price.toFixed(2)}</span>
        </div>
        <div class="portfolio-right">
          <div class="portfolio-pnl ${pnlCls}">${pnlSign}${pnlAmt.toFixed(0)}元</div>
          <div class="portfolio-pnl ${pnlCls}" style="font-size:12px">${pnlSign}${pnlPct.toFixed(2)}%</div>
          <span class="portfolio-advice stock-rec-tag ${stock.recommendation}">${stock.recommendation}</span>
        </div>
      </div>`;

      // 生成持仓操作建议
      let advice = '';
      const rec = stock.recommendation;
      if (pnlPct < -5) {
        advice = `⚠️ ${stock.name} 亏损${Math.abs(pnlPct).toFixed(1)}%，建议关注止损位${stock.stop_loss || '未设定'}元`;
      } else if (rec === '强烈卖出' || rec === '卖出') {
        advice = `📉 ${stock.name} 建议${rec}，当前评分${stock.score}分，考虑减仓`;
      } else if (rec === '强烈买入') {
        advice = `🔥 ${stock.name} 强烈买入(${stock.score}分)，目标${stock.target_price || '-'}元`;
      } else if (rec === '买入') {
        advice = `📈 ${stock.name} 建议买入(${stock.score}分)，可持有观察`;
      } else {
        advice = `👀 ${stock.name} 关注(${stock.score}分)，建议观望`;
      }
      adviceHtml += `<div style="padding:6px 0;border-bottom:1px solid rgba(42,58,80,0.2);font-size:12px;line-height:1.6;cursor:pointer" onclick="App.openStock('${stock.code}')">${advice}</div>`;
    });

    // 总盈亏
    const totalPnl = portfolio.reduce((sum, pos) => {
      const stock = this.findStock(pos.code);
      if (!stock) return sum;
      return sum + (stock.price - pos.cost) * pos.qty;
    }, 0);
    const totalCost = portfolio.reduce((sum, pos) => sum + pos.cost * pos.qty, 0);
    const totalPnlPct = totalCost > 0 ? totalPnl / totalCost * 100 : 0;
    const cls = totalPnl >= 0 ? 'text-rise' : 'text-fall';
    const sign = totalPnl >= 0 ? '+' : '';
    html = `<div style="text-align:center;padding:8px 0 12px;border-bottom:1px solid var(--border);margin-bottom:8px">
      <div style="font-size:11px;color:var(--text3)">总盈亏</div>
      <div style="font-size:20px;font-weight:800" class="${cls}">${sign}${totalPnl.toFixed(0)}元 (${sign}${totalPnlPct.toFixed(2)}%)</div>
    </div>` + html;

    el.innerHTML = html;

    // 持仓操作建议
    if (adviceHtml) {
      adviceCard.style.display = '';
      adviceEl.innerHTML = adviceHtml;
    }
  },

  // === 历史更新页 ===
  async renderHistory() {
    const el = document.getElementById('history-content');
    
    // 尝试加载历史文件列表
    try {
      const res = await fetch('data/history/');
      const text = await res.text();
      const files = text.match(/"[^"]+\.json"/g);
      if (!files) {
        el.innerHTML = '<div class="empty">暂无历史记录</div>';
        return;
      }
      const fileNames = files.map(f => f.replace(/"/g, '').split('/').pop()).sort().reverse();

      const promises = fileNames.map(f => fetch(`data/history/${f}`).then(r => r.json()).catch(() => null));
      const results = await Promise.all(promises);
      const validResults = results.filter(Boolean);

      let html = '';
      validResults.forEach(h => {
        const rec = h.recommendations || {};
        const strongBuy = rec.strong_buy || [];
        const buy = rec.buy || [];
        const avoid = rec.avoid || [];
        html += `<div class="history-item">
          <div class="history-time">📊 ${h.update_time} · 情绪：${h.market_sentiment || '-'} · 均分：${h.avg_score || '-'}</div>
          <div style="margin-bottom:8px">
            <span style="color:var(--rise);font-size:12px;font-weight:600">强烈买入 ${strongBuy.length}只：</span>
            <div class="history-stocks" style="margin-top:4px">${strongBuy.map(s => 
              `<span class="history-stock-tag" style="cursor:pointer" onclick="App.showPage('home');App.openStock('${s.code}')">${s.name}(${s.score}分)</span>`
            ).join('')}</div>
          </div>
          <div style="margin-bottom:8px">
            <span style="color:#f87171;font-size:12px;font-weight:600">建议买入 ${buy.length}只：</span>
            <div class="history-stocks" style="margin-top:4px">${buy.map(s => 
              `<span class="history-stock-tag" style="cursor:pointer" onclick="App.showPage('home');App.openStock('${s.code}')">${s.name}(${s.score}分)</span>`
            ).join('')}</div>
          </div>
          <div>
            <span style="color:var(--fall);font-size:12px;font-weight:600">建议回避 ${avoid.length}只：</span>
            <div class="history-stocks" style="margin-top:4px">${avoid.map(s => 
              `<span class="history-stock-tag" onclick="App.showPage('home');App.openStock('${s.code}')">${s.name}(${s.score}分)</span>`
            ).join('')}</div>
          </div>
        </div>`;
      });

      el.innerHTML = html || '<div class="empty">暂无历史记录</div>';
    } catch (e) {
      el.innerHTML = '<div class="empty">加载历史记录失败</div>';
    }
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

  filterByRec(rec) {
    document.getElementById('filter-rec').value = rec;
    App.filter();
    // 滚动到列表位置
    document.querySelector('#page-home .col-center .card:last-child').scrollIntoView({ behavior: 'smooth' });
  },

  // === 过滤 & 排序 ===
  filter() {
    const recFilter = document.getElementById('filter-rec').value;
    const sortBy = document.getElementById('filter-sort').value;
    let list = [...(this.allData?.stocks || [])];

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
    const end = (this.page + 1) * this.pageSize;
    const slice = this.filtered.slice(0, end);

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
          <div><span class="stock-name">${this.esc(s.name)}</span><span class="stock-code">${s.code}</span></div>
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
          <div><span class="stock-name">${this.esc(s.name)}</span><span class="stock-code">${s.code}</span></div>
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
      <div style="padding:12px 16px">
        <button class="btn btn-primary" style="width:100%" onclick="App.addToPortfolio('${s.code}')">➕ 添加到我的持仓</button>
      </div>
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
  showAddPortfolio() {
    document.getElementById('modal-code').value = '';
    document.getElementById('modal-price').value = '';
    document.getElementById('modal-qty').value = '100';
    document.getElementById('add-modal').classList.remove('hidden');
  },

  modalCodeChange() {
    // 输入代码/名称时自动查询现价
    const q = document.getElementById('modal-code').value.trim();
    if (!q) return;
    const stock = this.findStock(q);
    if (stock) {
      document.getElementById('modal-price').value = stock.price.toFixed(2);
    }
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
    // AI自动分析：从强烈买入和买入推荐中选取
    const strongBuy = this.recData?.strong_buy || [];
    const buyList = this.recData?.buy || [];
    const candidates = [...strongBuy, ...buyList];
    
    if (!candidates.length) {
      this.showToast('暂无推荐股票');
      return;
    }

    const portfolio = Portfolio.get();
    const ownedCodes = new Set(portfolio.map(p => p.code));
    const available = candidates.filter(s => !ownedCodes.has(s.code));
    
    if (!available.length) {
      this.showToast('推荐股票已全部在持仓中');
      return;
    }

    // 选评分最高的
    const pick = available[0];
    document.getElementById('modal-code').value = pick.code;
    document.getElementById('modal-price').value = pick.price.toFixed(2);
    document.getElementById('modal-qty').value = '100';
    this.showToast(`已选取：${pick.name}(${pick.score}分)`);
  },

  closeModal() {
    document.getElementById('add-modal').classList.add('hidden');
  },

  confirmAdd() {
    const codeInput = document.getElementById('modal-code').value.trim();
    const price = parseFloat(document.getElementById('modal-price').value) || 0;
    const qty = parseInt(document.getElementById('modal-qty').value) || 100;

    // 尝试匹配代码
    let code = codeInput;
    if (!code) { this.showToast('请输入股票代码或名称'); return; }
    if (!this.findStock(code)) {
      // 尝试模糊匹配
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
    if (id === 'history') this.renderHistory();
  },

  back() {
    this.showPage('home');
  },

  // === 工具方法 ===
  findStock(code) {
    if (!this.allData) return null;
    return this.allData.stocks.find(s => s.code === code || s.name === code);
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
    const existing = list.find(p => p.code === code);
    if (existing) { existing.cost = cost; existing.qty = qty; }
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
