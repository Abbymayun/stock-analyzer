/* === A股智能分析系统 v2.1 === */

const App = {
  allData: null,
  recData: null,
  historyData: [],
  yesterdayData: null,
  recList: [],     // 过滤后的推荐列表
  recPage: 0,
  recPageSize: 50,

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
        '<div class="empty"><div class="empty-icon">⏳</div><div>等待首次分析数据...</div><div style="font-size:12px;margin-top:8px;color:var(--text3)">GitHub Actions 将在每个交易日的 8:30/12:00/14:00/15:30 自动运行分析</div></div>';
    }
  },

  // === 加载历史数据 ===
  async loadHistory() {
    try {
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
    document.getElementById('update-time').textContent = this.allData.update_time;
    const sentEl = document.getElementById('market-sentiment');
    sentEl.textContent = r.market_sentiment + ' · ' + r.avg_score + '分';
    sentEl.className = 'sentiment ' + r.market_sentiment;

    // 统计（去掉建议回避，加强烈卖出）
    document.getElementById('stat-strong').textContent = (r.strong_buy || []).length;
    document.getElementById('stat-buy').textContent = (r.buy || []).length;
    document.getElementById('stat-watch').textContent = (r.watch || []).length;
    const strongSell = (this.allData.stocks || []).filter(s => s.recommendation === '强烈卖出').length;
    document.getElementById('stat-strong-sell').textContent = strongSell;

    // 左栏推荐列表
    this.renderRecList('strong-buy-list', r.strong_buy || []);
    this.renderRecList('buy-list', r.buy || []);
    this.renderRecList('watch-list', r.watch || []);

    // 中栏
    this.renderMarketAnalysis(r);
    this.renderStrategies(r);
    this.filterRecList();

    // 右栏
    this.renderAccuracy();
    this.renderPortfolio();
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
          <div class="rec-mini-price ${chgCls}">${s.price.toFixed(2)}</div>
          <div class="rec-mini-change ${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</div>
          <div class="rec-mini-score">明日预估 <span class="${estCls}">${estStr}</span></div>
        </div>
      </div>`;
    }).join('');
  },

  // === 中栏 - 大盘分析 ===
  renderMarketAnalysis(r) {
    const el = document.getElementById('market-analysis');
    document.getElementById('analysis-update-time').textContent = r.update_time || '';

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
      <div class="market-stat-item"><div class="market-stat-val text-rise">${rise}</div><div class="market-stat-label">上涨</div></div>
      <div class="market-stat-item"><div class="market-stat-val text-fall">${fall}</div><div class="market-stat-label">下跌</div></div>
      <div class="market-stat-item"><div class="market-stat-val">${flat}</div><div class="market-stat-label">平盘</div></div>
      <div class="market-stat-item"><div class="market-stat-val ${avgChg >= 0 ? 'text-rise' : 'text-fall'}">${avgChg >= 0 ? '+' : ''}${avgChg.toFixed(2)}%</div><div class="market-stat-label">平均涨幅</div></div>
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

  // === 推荐股票列表（只显示推荐的） ===
  filterRecList() {
    const recFilter = document.getElementById('filter-rec').value;
    const sortBy = document.getElementById('filter-sort').value;

    // 只取推荐的股票
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
        <span class="${chgCls}" style="font-weight:600">${s.price.toFixed(2)}</span>
        <span class="${chgCls}">${chgSign}${s.change_pct.toFixed(2)}%</span>
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

  loadMore() {
    this.recPage++;
    this.renderRecListTable();
  },

  filterByRec(rec) {
    document.getElementById('filter-rec').value = rec;
    App.filterRecList();
    document.querySelector('#page-home .col-center .card:last-child').scrollIntoView({ behavior: 'smooth' });
  },

  // === 右栏 - 准确率统计 ===
  renderAccuracy() {
    const el = document.getElementById('accuracy-section');

    if (!this.yesterdayData || !this.yesterdayData.recommendations) {
      // 尝试从更多历史中找
      if (this.historyData.length >= 2) {
        // 找不同日期的
        for (let i = 1; i < this.historyData.length; i++) {
          if (this.historyData[i].recommendations?.strong_buy?.length) {
            this.yesterdayData = this.historyData[i];
            break;
          }
        }
      }
      if (!this.yesterdayData || !this.yesterdayData.recommendations?.strong_buy?.length) {
        el.innerHTML = '<div class="empty"><div class="empty-icon">📊</div><div>需要至少2次分析数据才能统计准确率</div><div style="font-size:11px;margin-top:4px">系统每日自动运行4次分析（8:30/12:00/14:00/15:30）</div></div>';
        return;
      }
    }

    const ydStrongBuy = this.yesterdayData.recommendations.strong_buy || [];
    const todayTime = this.historyData[0]?.update_time || '';
    const ydTime = this.yesterdayData.update_time || '';

    if (!ydStrongBuy.length) {
      el.innerHTML = '<div class="empty">暂无昨日强烈买入数据</div>';
      return;
    }

    let correct = 0, wrong = 0, totalPnl = 0, details = [];
    ydStrongBuy.forEach(s => {
      const todayStock = this.findStock(s.code);
      if (!todayStock) {
        details.push({ name: s.name, code: s.code, pred_price: s.price, actual: null });
        return;
      }
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
        html += `<div class="portfolio-item">
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

      html += `<div class="portfolio-item" onclick="App.openStock('${pos.code}')">
        <div class="portfolio-left">
          <div style="display:flex;align-items:center;gap:6px">
            <span class="stock-name">${this.esc(stock.name)}</span>
            <span class="stock-code">${stock.code}</span>
            <button class="btn-add" onclick="event.stopPropagation();Portfolio.remove(${i});App.renderPortfolio()">✕</button>
          </div>
          <span class="portfolio-cost">成本${pos.cost.toFixed(2)} × ${pos.qty}股 · 现价${stock.price.toFixed(2)}</span>
        </div>
        <div class="portfolio-right">
          <div class="portfolio-pnl ${pCls}">${pSign}${pnlAmt.toFixed(0)}元</div>
          <div class="portfolio-pnl ${pCls}" style="font-size:12px">${pSign}${pnlPct.toFixed(2)}%</div>
          <span class="portfolio-advice stock-rec-tag ${stock.recommendation}">${stock.recommendation}</span>
        </div>
      </div>`;

      // 持仓建议
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

  // === 历史更新页（需求5：去掉建议回避，去掉均分情绪，显示准确率） ===
  async renderHistory() {
    const el = document.getElementById('history-content');
    try {
      const res = await fetch('data/history/');
      const text = await res.text();
      const files = text.match(/"[^"]+\.json"/g);
      if (!files) { el.innerHTML = '<div class="empty">暂无历史记录</div>'; return; }
      const fileNames = files.map(f => f.replace(/"/g, '').split('/').pop()).sort().reverse();
      const promises = fileNames.map(f => fetch(`data/history/${f}`).then(r => r.json()).catch(() => null));
      const results = await Promise.all(promises);
      const valid = results.filter(Boolean);

      let html = '';
      // 按日期分组
      const byDate = {};
      valid.forEach(h => {
        const date = (h.update_time || '').split(' ')[0];
        if (!byDate[date]) byDate[date] = [];
        byDate[date].push(h);
      });

      Object.keys(byDate).sort().reverse().forEach(date => {
        const daySnapshots = byDate[date];
        const latest = daySnapshots[0];
        const prev = daySnapshots.length > 1 ? daySnapshots[daySnapshots.length - 1] : null;

        html += `<div class="history-item">
          <div class="history-time">📅 ${date}</div>`;

        // 准确率统计（当天第一次分析 vs 最后一次，或 vs 前一天最后一次）
        if (prev && prev.recommendations?.strong_buy?.length) {
          const ydStrongBuy = prev.recommendations.strong_buy;
          const todayStocks = valid[0];
          let correct = 0, wrong = 0, totalPnl = 0;

          ydStrongBuy.forEach(s => {
            // 找该股票在latest中的价格
            const laterSnapshot = daySnapshots[daySnapshots.length - 1];
            const scores = laterSnapshot?.scores || {};
            const info = scores[s.code];
            if (info && info.price) {
              const ydPrice = s.price || s.prev_close;
              const chg = (info.price - ydPrice) / ydPrice * 100;
              if (chg > 0) correct++; else wrong++;
              totalPnl += chg;
            }
          });

          const total = correct + wrong;
          if (total > 0) {
            const acc = (correct / total * 100).toFixed(0);
            const avg = (totalPnl / total).toFixed(2);
            html += `<div style="display:flex;gap:16px;margin:8px 0;padding:10px;background:var(--bg2);border-radius:8px;font-size:13px">
              <div><span style="color:var(--text3)">准确率</span><br><strong style="color:${acc >= 60 ? 'var(--fall)' : 'var(--gold)'}">${acc}%</strong></div>
              <div><span style="color:var(--text3)">平均收益</span><br><strong class="${totalPnl >= 0 ? 'text-rise' : 'text-fall'}">${totalPnl >= 0 ? '+' : ''}${avg}%</strong></div>
              <div><span style="color:var(--text3)">命中</span><br><strong style="color:var(--accent)">${correct}/${total}</strong></div>
            </div>`;
          }
        }

        // 各时间点的推荐
        daySnapshots.forEach(h => {
          const rec = h.recommendations || {};
          const strongBuy = rec.strong_buy || [];
          const buy = rec.buy || [];
          const time = (h.update_time || '').split(' ')[1] || '';

          html += `<div style="margin-bottom:10px;padding-left:12px;border-left:3px solid var(--border)">
            <div style="font-size:12px;color:var(--text3);margin-bottom:6px">⏰ ${time}</div>
            <div style="margin-bottom:4px">
              <span style="color:var(--rise);font-size:12px;font-weight:600">强烈买入 ${strongBuy.length}只：</span>
              <div class="history-stocks" style="margin-top:4px">${strongBuy.map(s =>
                `<span class="history-stock-tag" style="cursor:pointer" onclick="App.showPage('home');App.openStock('${s.code}')">${s.name}(${s.score}分·${s.price?.toFixed(2) || '-'})</span>`
              ).join('')}</div>
            </div>
            <div>
              <span style="color:#f87171;font-size:12px;font-weight:600">建议买入 ${buy.length}只：</span>
              <div class="history-stocks" style="margin-top:4px">${buy.map(s =>
                `<span class="history-stock-tag" style="cursor:pointer" onclick="App.showPage('home');App.openStock('${s.code}')">${s.name}(${s.score}分)</span>`
              ).join('')}</div>
            </div>
          </div>`;
        });

        html += '</div>';
      });

      el.innerHTML = html || '<div class="empty">暂无历史记录</div>';
    } catch (e) {
      el.innerHTML = '<div class="empty">加载失败</div>';
    }
  },

  // === 个股详情页（需求4：持仓股票详情加强） ===
  openStock(code) {
    const stock = this.findStock(code);
    if (!stock) { this.showToast('未找到该股票'); return; }

    // 判断是否在持仓中
    const portfolio = Portfolio.get();
    const isHolding = portfolio.some(p => p.code === code);
    const holding = portfolio.find(p => p.code === code);

    this.showPage('detail');
    document.getElementById('detail-title').textContent = `${stock.name} ${code}${isHolding ? ' 💼' : ''}`;

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

    // 持仓盈亏（如果持仓中）
    if (isHolding && holding) {
      const pnl = s.price - holding.cost;
      const pnlPct = holding.cost > 0 ? (pnl / holding.cost * 100) : 0;
      const pnlAmt = pnl * holding.qty;
      const pCls = pnl >= 0 ? 'text-rise' : 'text-fall';
      const pSign = pnl >= 0 ? '+' : '';

      html += `<div class="detail-section" style="border-color:var(--accent)">
        <h3>💼 持仓盈亏分析</h3>
        <div style="padding:12px 16px">
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px">
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">成本价</div><div style="font-size:16px;font-weight:700">${holding.cost.toFixed(2)}</div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">现价</div><div style="font-size:16px;font-weight:700" class="${chgCls}">${s.price.toFixed(2)}</div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">盈亏</div><div style="font-size:16px;font-weight:700" class="${pCls}">${pSign}${pnlAmt.toFixed(0)}元</div></div>
            <div style="text-align:center"><div style="font-size:11px;color:var(--text3)">盈亏比例</div><div style="font-size:16px;font-weight:700" class="${pCls}">${pSign}${pnlPct.toFixed(2)}%</div></div>
          </div>`;

      // 持仓操作建议
      if (pnlPct < -5) {
        html += `<div style="background:var(--rise-bg);padding:10px 14px;border-radius:8px;font-size:13px;color:var(--rise)">
          ⚠️ 亏损较大，建议严格执行止损。止损位 ${s.stop_loss || '-'} 元，距止损 ${s.stop_loss ? ((s.price - s.stop_loss) / s.price * 100).toFixed(1) + '%' : '-'}。
          若基本面无变化且技术面出现企稳信号，可考虑补仓降低成本。
        </div>`;
      } else if (pnlPct > 10) {
        html += `<div style="background:var(--fall-bg);padding:10px 14px;border-radius:8px;font-size:13px;color:var(--fall)">
          ✅ 盈利丰厚！目标价 ${s.target_price || '-'} 元，${s.target_price && s.price < s.target_price ? '尚未到达目标，可继续持有。' : '已达到目标区间，建议分批止盈。'}
          ${s.sell_time ? '建议卖出时间：' + s.sell_time : ''}
        </div>`;
      } else {
        html += `<div style="background:var(--bg2);padding:10px 14px;border-radius:8px;font-size:13px;color:var(--text2)">
          当前持仓浮${pnl >= 0 ? '盈' : '亏'}${Math.abs(pnlPct).toFixed(1)}%，${s.recommendation === '强烈买入' || s.recommendation === '买入' ? '趋势向好，建议持有等待目标价。' : s.recommendation === '卖出' || s.recommendation === '强烈卖出' ? '技术面转弱，建议逢高减仓。' : '建议继续观察。'}
        </div>`;
      }

      html += '</div></div>';
    }

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
          ${s.kdj_j ? `<div class="detail-grid-item"><div class="detail-grid-label">KDJ-J</div><div class="detail-grid-value" style="color:${s.kdj_j < 20 ? 'var(--rise)' : s.kdj_j > 100 ? 'var(--fall)' : ''}">${s.kdj_j}</div></div>` : ''}
          ${s.macd_dif !== undefined ? `<div class="detail-grid-item"><div class="detail-grid-label">MACD DIF</div><div class="detail-grid-value" style="color:${s.macd_dif >= 0 ? 'var(--rise)' : 'var(--fall)'}">${s.macd_dif}</div></div>` : ''}
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
          return `<span class="signal-tag ${isBuy ? 'buy' : isSell ? 'sell' : 'neutral'}">${sig}</span>`;
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
      ${!isHolding ? `<div style="padding:12px 16px"><button class="btn btn-primary" style="width:100%" onclick="App.addToPortfolio('${s.code}')">➕ 添加到我的持仓</button></div>` : ''}
    </div>`;

    // 分析文本
    if (s.analysis_text) {
      html += `<div class="detail-section">
        <h3>📝 分析解读</h3>
        <div class="analysis-text">${s.analysis_text}</div>
      </div>`;
    }

    // === 持仓增强分析（需求4） ===
    // 主力心理分析
    if (s.main_force_analysis) {
      html += `<div class="detail-section" style="border-color:var(--accent2)">
        <h3>🧠 主力心理分析</h3>
        <div class="analysis-text">${s.main_force_analysis.replace(/\n/g, '<br>')}</div>
      </div>`;
    }

    // 筹码分布分析
    if (s.chip_analysis) {
      html += `<div class="detail-section" style="border-color:var(--gold)">
        <h3>📊 筹码分布分析</h3>
        <div class="analysis-text">${s.chip_analysis.replace(/\n/g, '<br>')}</div>
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
    this.showToast(`已选取：${pick.name}(${pick.score}分)`);
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
    if (id === 'history') this.renderHistory();
  },

  back() { this.showPage('home'); },

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

document.addEventListener('DOMContentLoaded', () => App.init());
