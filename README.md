# 🇨🇳 A股智能分析系统

## 在线访问

👉 **[https://abbymayun.github.io/stock-analyzer/](https://abbymayun.github.io/stock-analyzer/)**

## 功能

- 🔍 全市场主板股票自动筛选（去除科创板/创业板/ST/北交所/停牌）
- 📈 多维度技术分析：MA(5/10/20/60)、MACD、RSI(6/12/24)、KDJ、布林带
- 🎯 综合评分系统（0-100分）+ 五档操作建议
- 💰 买入/卖出点位分析 + 操作时间段建议
- 🛡️ 动态止损位计算（基于近期支撑位）
- ⏰ 每日4次自动更新（8:30 / 12:00 / 14:00 / 15:30）
- 📊 历史数据对比（保留最近7天）
- 🔎 个股搜索（支持名称和代码）
- 💼 持仓管理 + 实时操作建议
- 📐 可行性策略自动生成
- 🌙 深色主题 + 移动端适配

## 架构

```
GitHub Actions (cron)
  └── Python脚本 → 获取数据 → 技术分析 → 生成JSON → 提交到仓库
GitHub Pages
  └── 前端加载JSON → 渲染分析结果
```

## 手动设置 GitHub Actions

由于 token 权限限制，需要手动创建 workflow 文件：

1. 打开 https://github.com/Abbymayun/stock-analyzer
2. 点击 "Add file" → "Create new file"
3. 文件名输入：`.github/workflows/analyze.yml`
4. 粘贴以下内容：

```yaml
name: Stock Analysis
on:
  schedule:
    - cron: '30 0 * * 1-5'
    - cron: '0 4 * * 1-5'
    - cron: '0 6 * * 1-5'
    - cron: '30 7 * * 1-5'
  workflow_dispatch:
permissions:
  contents: write
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r scripts/requirements.txt
      - name: Run analysis
        run: python scripts/analyze.py
      - name: Commit data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --cached --quiet; then echo "No changes"; else git commit -m "📊 $(date -u +%Y-%m-%d\ %H:%M)" && git push; fi
```

5. 点击 "Commit changes"
6. 然后到 Actions 页面，点击 "Stock Analysis" → "Run workflow" 手动触发第一次分析

## 本地运行分析

```bash
pip install -r scripts/requirements.txt
python scripts/analyze.py
```

分析结果会保存到 `data/` 目录。
