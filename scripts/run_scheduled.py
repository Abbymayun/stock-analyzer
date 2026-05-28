#!/usr/bin/env python3
"""
统一定时调度脚本 v2.0
由 GitHub Actions 或 crontab 调用，根据当前时间自动执行对应的分析任务。

支持的环境变量：
  TASK: 手动指定任务 (all/morning/analyze/midday/eod/closing)
  FORCE: 强制执行（忽略非交易日检查）

北京时间调度：
  8:00  → 晨间综合分析（外围影响 + 当日策略）
  8:30  → 全市场个股分析（选股推荐）
  12:00 → 午间综合分析（半日复盘 + 午后策略）
  14:20 → 尾盘综合分析（盘中介入 + 尾盘操作）
  15:30 → 收盘综合分析（全天复盘 + 明日策略）
"""

import os
import sys
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_script(name, script_path):
    """运行一个分析脚本"""
    if not os.path.exists(script_path):
        print(f"  ⚠️ 脚本不存在: {script_path}")
        return False

    print(f"\n{'='*60}")
    print(f"  🚀 运行 {name}  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True, text=True, timeout=300,
        cwd=SCRIPT_DIR
    )

    # 打印输出
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode == 0:
        print(f"  ✅ {name} 完成")
        return True
    else:
        print(f"  ❌ {name} 失败 (exit code: {result.returncode})")
        return False


def get_beijing_hour():
    """获取北京时间的小时数（GitHub Actions 默认 UTC）"""
    now = datetime.utcnow()
    # 北京时间 = UTC + 8
    beijing = now.hour + 8
    if beijing >= 24:
        beijing -= 24
    return beijing


def is_trading_day():
    """简单判断今天是否为交易日"""
    try:
        from market_calendar import is_trading_day as _is_trading_day
        return _is_trading_day()
    except ImportError:
        # fallback: 只排除周末
        return datetime.now().weekday() < 5


def main():
    task = os.environ.get('TASK', '').lower().strip()
    force = os.environ.get('FORCE', '').lower() in ('1', 'true', 'yes')

    # 检查是否交易日
    if not force and not is_trading_day():
        print(f"📅 今天不是交易日，跳过分析 ({datetime.now().strftime('%Y-%m-%d')})")
        sys.exit(0)

    # 根据任务参数或时间自动选择要运行的脚本
    tasks = []

    if task == 'all':
        tasks = ['morning', 'analyze', 'midday', 'eod', 'closing']
    elif task == 'morning':
        tasks = ['morning']
    elif task == 'analyze':
        tasks = ['analyze']
    elif task == 'midday':
        tasks = ['midday']
    elif task == 'eod':
        tasks = ['eod']
    elif task == 'closing':
        tasks = ['closing']
    else:
        # 根据北京时间自动选择
        hour = get_beijing_hour()

        if 7 <= hour < 9:
            # 8:00 区间 → 晨间分析 + 全市场分析
            tasks = ['morning', 'analyze']
        elif 11 <= hour < 13:
            # 12:00 区间 → 午间分析 + 全市场分析
            tasks = ['midday', 'analyze']
        elif 13 <= hour < 15:
            # 14:20 区间 → 尾盘分析
            tasks = ['eod']
        elif 15 <= hour < 17:
            # 15:30 区间 → 收盘分析
            tasks = ['closing']
        elif 0 <= hour < 1:
            # UTC 0:00 = 北京 8:00 → 晨间分析
            tasks = ['morning', 'analyze']
        else:
            print(f"  ⏰ 当前北京时间 {hour}:00 不在定时任务区间，跳过")
            sys.exit(0)

    if not tasks:
        print("  ⚠️ 没有需要运行的任务")
        sys.exit(0)

    print(f"📋 待执行任务: {', '.join(tasks)}")

    # 脚本映射
    script_map = {
        'morning': ('晨间综合分析', 'morning_analysis.py'),
        'analyze':  ('全市场个股分析', 'analyze.py'),
        'midday':   ('午间综合分析', 'midday_analysis.py'),
        'eod':      ('尾盘综合分析', 'eod_analysis.py'),
        'closing':  ('收盘综合分析', 'closing_analysis.py'),
    }

    results = {}
    for t in tasks:
        if t in script_map:
            name, script = script_map[t]
            results[t] = run_script(name, script)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  📊 执行结果汇总")
    print(f"{'='*60}")
    for t, ok in results.items():
        status = '✅' if ok else '❌'
        print(f"  {status} {script_map[t][0]}")

    all_ok = all(results.values())
    print(f"\n  总体: {'全部成功' if all_ok else '部分失败'}")
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
