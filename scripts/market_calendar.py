#!/usr/bin/env python3
"""
A股交易日历
包含2026年法定节假日休市安排。
每年初更新一次即可。

来源：国务院办公厅关于部分节假日安排的通知
"""

from datetime import datetime, timedelta


# 2026年A股休市日期（周末之外的法定假日及调休）
# 格式: 'YYYY-MM-DD'
HOLIDAYS_2026 = [
    # 元旦：2025年12月31日 - 2026年1月2日（周三-周五）
    '2025-12-31',
    '2026-01-01',
    '2026-01-02',
    # 春节：2026年2月14日 - 2月20日（周六-周五，含调休）
    # 春节初一：2026年2月17日（农历正月初一，火马年）
    '2026-02-14',
    '2026-02-15',
    '2026-02-16',
    '2026-02-17',
    '2026-02-18',
    '2026-02-19',
    '2026-02-20',
    # 清明节：2026年4月4日 - 4月6日（周六-周一）
    '2026-04-04',
    '2026-04-05',
    '2026-04-06',
    # 劳动节：2026年5月1日 - 5月5日（周五-周二）
    '2026-05-01',
    '2026-05-02',
    '2026-05-03',
    '2026-05-04',
    '2026-05-05',
    # 端午节：2026年5月30日 - 6月1日（周六-周一）
    # 端午节：农历五月初五，2026年对应6月19日（周六），一般连周末+周一
    # 更正：2026年端午节是6月19日，放假6月19日-6月21日
    '2026-06-19',
    '2026-06-20',
    '2026-06-21',
    # 中秋节：2026年9月25日（农历八月十五），放假9月25日-9月27日（周五-周日）
    '2026-09-25',
    '2026-09-26',
    '2026-09-27',
    # 国庆节：2026年10月1日 - 10月7日（周四-周三）
    '2026-10-01',
    '2026-10-02',
    '2026-10-03',
    '2026-10-04',
    '2026-10-05',
    '2026-10-06',
    '2026-10-07',
]

# 调休上班日（周末但需上班/开市的日期）
# 注意：不是所有调休日都开市，但一般国务院调休安排的补班日股市也会开市
EXTRA_TRADING_DAYS_2026 = [
    # 春节调休：2月21日（周六）补班
    '2026-02-21',
    '2026-02-22',
    # 国庆调休：10月10日（周六）补班
    '2026-10-10',
]

# 合并所有年份的假日
ALL_HOLIDAYS = set(HOLIDAYS_2026)
ALL_EXTRA_TRADING_DAYS = set(EXTRA_TRADING_DAYS_2026)


def is_trading_day(date=None):
    """
    判断指定日期是否为交易日。
    规则：
    1. 周末（周六、周日）默认非交易日
    2. 法定节假日非交易日
    3. 调休上班日（虽是周末但被安排上班）为交易日
    """
    if date is None:
        date = datetime.now()
    elif isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d')
    
    date_str = date.strftime('%Y-%m-%d')
    weekday = date.weekday()  # 0=周一, 6=周日
    
    # 调休上班日（周末但开市）
    if date_str in ALL_EXTRA_TRADING_DAYS:
        return True
    
    # 周末不开市
    if weekday >= 5:
        return False
    
    # 法定节假日
    if date_str in ALL_HOLIDAYS:
        return False
    
    return True


def is_trading_time(dt=None):
    """
    判断当前时间是否处于A股可交易时段。
    上午: 9:30 - 11:30
    下午: 13:00 - 15:00
    
    在集合竞价期间（9:15-9:25）返回False，因为此时不能撤单/改单，
    实际撮合在9:25，我们保守起见从9:30开始。
    """
    if dt is None:
        dt = datetime.now()
    
    # 先判断是否交易日
    if not is_trading_day(dt):
        return False
    
    h, m = dt.hour, dt.minute
    t = h * 60 + m
    # 上午 9:30-11:30
    if 570 <= t <= 690:
        return True
    # 下午 13:00-15:00
    if 780 <= t <= 900:
        return True
    return False


if __name__ == '__main__':
    # 测试：列出2026年5月的交易日
    print("2026年5月交易日:")
    for day in range(1, 32):
        try:
            d = datetime(2026, 5, day)
            if is_trading_day(d):
                weekday_names = ['一', '二', '三', '四', '五', '六', '日']
                extra = ' (调休)' if d.strftime('%Y-%m-%d') in ALL_EXTRA_TRADING_DAYS else ''
                print(f"  5月{day:2d} 周{weekday_names[d.weekday()]}{extra}")
        except ValueError:
            pass
    
    print(f"\n今天 {datetime.now().strftime('%Y-%m-%d')} 是交易日: {is_trading_day()}")
    print(f"现在处于交易时间: {is_trading_time()}")
