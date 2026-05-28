#!/usr/bin/env python3
"""
综合买入策略生成器 v1.0
结合外围影响 + A股实时走势 + 技术面信号，生成精准的买入建议。

核心功能：
1. 综合外围影响判断开盘方向（高开/低开/平开）
2. 根据开盘实际走势动态调整买入价位
3. 给出具体的买入时机和价格区间
4. 结合午盘走势给出午盘低吸策略
"""

import json
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')


def _load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def generate_comprehensive_buy_strategy(morning_data, midday_data=None):
    """
    生成综合买入策略。
    
    参数:
      morning_data: 晨间分析数据（包含外围影响、风险评分、top_buys）
      midday_data: 午间分析数据（可选，午盘时使用）
    
    返回:
      comprehensive_strategy: 综合策略字典
    """
    
    if not morning_data:
        return {'error': '缺少晨间分析数据'}
    
    us_impact = morning_data.get('us_impact', {})
    commodity_impact = morning_data.get('commodity_impact', {})
    fx_impact = morning_data.get('fx_impact', {})
    global_impact = morning_data.get('global_impact', {})
    strategy = morning_data.get('strategy', {})
    risk_score = strategy.get('risk_score', 50)
    top_buys = morning_data.get('top_buys', [])
    
    # === 1. 判断开盘方向 ===
    open_forecast = _assess_open_direction(us_impact, commodity_impact, fx_impact, global_impact)
    
    # === 2. 确定操作模式 ===
    operation_mode = _determine_operation_mode(open_forecast, risk_score)
    
    # === 3. 为每只推荐股票生成精准买入策略 ===
    buy_strategies = []
    for stock in top_buys:
        bs = _generate_stock_buy_strategy(stock, open_forecast, operation_mode, risk_score)
        buy_strategies.append(bs)
    
    # === 4. 综合建议文本 ===
    advice_text = _generate_advice_text(open_forecast, operation_mode, risk_score, buy_strategies)
    
    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'open_forecast': open_forecast,
        'operation_mode': operation_mode,
        'risk_score': risk_score,
        'buy_strategies': buy_strategies,
        'advice_text': advice_text,
        'us_direction': us_impact.get('direction', '未知'),
        'us_level': us_impact.get('level', 'low'),
        'commodity_summary': commodity_impact.get('summary', ''),
        'fx_summary': fx_impact.get('summary', ''),
    }
    
    return result


def _assess_open_direction(us_impact, commodity_impact, fx_impact, global_impact):
    """综合外围因素判断开盘方向和幅度"""
    
    # 权重因子
    us_score = 0      # 美股影响（权重最高）
    com_score = 0     # 商品影响
    fx_score = 0      # 汇率影响
    global_score = 0  # 全球市场影响
    
    # 美股影响评分 (-5 到 +5)
    us_avg_pct = us_impact.get('avg_pct', 0)
    if us_avg_pct > 2:
        us_score = 5
    elif us_avg_pct > 1:
        us_score = 3
    elif us_avg_pct > 0.5:
        us_score = 1.5
    elif us_avg_pct > 0:
        us_score = 0.5
    elif us_avg_pct < -2:
        us_score = -5
    elif us_avg_pct < -1:
        us_score = -3
    elif us_avg_pct < -0.5:
        us_score = -1.5
    elif us_avg_pct < 0:
        us_score = -0.5
    
    us_level = us_impact.get('level', 'low')
    if us_level == 'high':
        us_score *= 1.5
    elif us_level == 'low':
        us_score *= 0.6
    
    # 商品影响（油价暴跌/金价大涨等显著事件才计入）
    com_summary = commodity_impact.get('summary', '')
    if '金价大涨' in com_summary or '金价飙升' in com_summary:
        com_score = 0.5  # 金价涨对大盘中性偏正面
    if '油价暴跌' in com_summary or '油价大跌' in com_summary:
        com_score = 1.0  # 油价跌利好制造业/航空，偏正面
    if '油价飙升' in com_summary:
        com_score = -1.0  # 油价涨增加成本压力
    
    # 汇率影响
    fx_summary = fx_impact.get('summary', '')
    if '人民币贬值' in fx_summary:
        fx_score = -0.5  # 外资可能流出
    elif '人民币走强' in fx_summary or '人民币升值' in fx_summary:
        fx_score = 0.5
    
    # 全球市场影响
    global_summary = global_impact.get('summary', '')
    if '带动' in global_summary and '开盘情绪' in global_summary:
        global_score = 0.3
    
    # 加权综合评分
    total_score = us_score * 0.5 + com_score * 0.15 + fx_score * 0.15 + global_score * 0.2
    
    # 判断开盘方向
    if total_score > 2:
        direction = '大幅高开'
        amplitude = min(total_score * 0.2, 1.2)  # 预计高开幅度
    elif total_score > 0.8:
        direction = '小幅高开'
        amplitude = min(total_score * 0.15, 0.6)
    elif total_score > 0.2:
        direction = '平开偏强'
        amplitude = total_score * 0.08
    elif total_score > -0.2:
        direction = '平开'
        amplitude = 0
    elif total_score > -0.8:
        direction = '平开偏弱'
        amplitude = total_score * 0.08
    elif total_score > -2:
        direction = '小幅低开'
        amplitude = abs(total_score) * 0.15
    else:
        direction = '大幅低开'
        amplitude = min(abs(total_score) * 0.2, 1.2)
    
    return {
        'direction': direction,
        'score': round(total_score, 2),
        'amplitude': round(amplitude, 2),
        'us_score': round(us_score, 2),
        'com_score': round(com_score, 2),
        'fx_score': round(fx_score, 2),
        'global_score': round(global_score, 2),
        'description': f"综合外围评分{total_score:+.2f}，预计{direction}（{'约' + f'{amplitude:.1f}%' if amplitude > 0.05 else '±0.1%'}）",
    }


def _determine_operation_mode(open_forecast, risk_score):
    """根据开盘预测和风险评分确定操作模式"""
    
    direction = open_forecast.get('direction', '平开')
    amplitude = open_forecast.get('amplitude', 0)
    score = open_forecast.get('score', 0)
    
    mode = {
        'name': '观望',
        'description': '',
        'buy_timing': '',
        'position': 0,
        'key_action': '',
        'scenarios': {},
    }
    
    if direction in ('大幅低开', '小幅低开'):
        # 低开场景
        if risk_score >= 70:
            mode['name'] = '防御观望'
            mode['description'] = '外围利空+高风险，开盘不操作，观察30分钟'
            mode['buy_timing'] = '不买入'
            mode['position'] = 0
            mode['key_action'] = '空仓观望，等待企稳信号'
            mode['scenarios'] = {
                '开盘快速下跌': '坚决不抄底，等分时走平',
                '低开后反弹': '观察反弹力度，缩量反弹不加仓',
                '低开后震荡': '等午后企稳再看',
            }
        elif risk_score >= 55:
            mode['name'] = '低开低吸'
            mode['description'] = f'外围偏空但非极端，预计低开{amplitude:.1f}%，可在午盘低点附近低吸'
            mode['buy_timing'] = '午盘低吸 (10:30-11:00 或 13:00-13:30)'
            mode['position'] = 0.2
            mode['key_action'] = '等低开后分时企稳，在支撑位低吸，不追涨'
            mode['scenarios'] = {
                '开盘快速下杀': f'不急，等跌到{amplitude*1.5:.1f}%左右看是否有承接',
                '低开后横盘30分钟': '可小仓位试探买入（≤2成）',
                '低开后快速反弹': '不追，等回落确认支撑再入',
                '午盘继续下跌': '不抄底，收盘前看是否有企稳迹象',
            }
        else:
            mode['name'] = '低开买入'
            mode['description'] = f'外围偏空但整体风险可控，预计低开{amplitude:.1f}%，低开即买入机会'
            mode['buy_timing'] = '开盘30分钟后 (10:00-10:30) 或 午盘低点 (13:00-13:30)'
            mode['position'] = 0.4
            mode['key_action'] = '低开是买入良机，在均线支撑位附近分批买入'
            mode['scenarios'] = {
                '低开后快速反弹': '等第一波回踩到分时均线附近买入',
                '低开后横盘': '横盘即底部确认，可直接买入',
                '低开后继续下探': f'等跌幅达到{amplitude*1.5:.1f}%附近开始建仓',
                '低开后V型反转': '等回到平盘附近买入（确定性更高）',
            }
    
    elif direction in ('大幅高开', '小幅高开'):
        # 高开场景
        if risk_score >= 70:
            mode['name'] = '高开回避'
            mode['description'] = f'虽有外围利好但系统风险高，高开后不追'
            mode['buy_timing'] = '不买入'
            mode['position'] = 0
            mode['key_action'] = '高开不追，等回落再说'
            mode['scenarios'] = {
                '高开高走': '不追涨，等下午回调',
                '高开回落': '回落到均线附近观察，但不急于买入',
                '高开横盘': '谨慎观望，量能不足则回避',
            }
        elif risk_score >= 55:
            mode['name'] = '高开等回踩'
            mode['description'] = f'外围利好但需谨慎，预计高开{amplitude:.1f}%，等回踩均线再买入'
            mode['buy_timing'] = '回踩买入 (10:00-10:30 回踩到分时均线)'
            mode['position'] = 0.3
            mode['key_action'] = '高开不追，等回踩到MA5或分时均线附近低吸'
            mode['scenarios'] = {
                '高开后持续上涨': '不追！等回调',
                '高开后回落到均线': '均线企稳可买入',
                '高开低走翻绿': '观望，等午后企稳',
                '午盘在均线附近震荡': '可试探买入',
            }
        else:
            mode['name'] = '高开低吸'
            mode['description'] = f'外围利好+低风险环境，预计高开{amplitude:.1f}%，等回踩后积极买入'
            mode['buy_timing'] = '回踩买入 (9:45-10:30) 或 午盘低吸 (13:00-13:30)'
            mode['position'] = 0.5
            mode['key_action'] = '高开别急，等回踩到支撑位后分批买入'
            mode['scenarios'] = {
                '高开后横盘': '横盘即强势，回踩到开盘价附近买入',
                '高开后回落': '回落到昨收或MA5附近是买点',
                '高开后低走': '低走是更好的买入机会，跌幅0.5%以上可入',
                '持续强势不回调': '不追！宁可错过',
            }
    
    else:
        # 平开场景
        if risk_score >= 70:
            mode['name'] = '谨慎观望'
            mode['description'] = '外围中性但系统风险高，不建议操作'
            mode['buy_timing'] = '不买入'
            mode['position'] = 0
            mode['key_action'] = '观望为主，关注盘面变化'
            mode['scenarios'] = {
                '开盘走强': '不追，可能是诱多',
                '开盘走弱': '不抄底',
                '窄幅震荡': '观望',
            }
        elif risk_score >= 55:
            mode['name'] = '观望等方向'
            mode['description'] = '外围影响中性，开盘后30分钟观察方向再决定'
            mode['buy_timing'] = '方向明确后 (10:00后)'
            mode['position'] = 0.2
            mode['key_action'] = '开盘观察，等方向明确（放量突破或放量下跌）'
            mode['scenarios'] = {
                '放量上涨': '可跟随买入强势股',
                '放量下跌': '观望，不加仓',
                '窄幅震荡': '不操作',
            }
        else:
            mode['name'] = '正常买入'
            mode['description'] = '外围中性+低风险，按原计划正常买入推荐股票'
            mode['buy_timing'] = '开盘30分钟内 (9:30-10:00)'
            mode['position'] = 0.4
            mode['key_action'] = '按计划在买点附近买入，分批建仓'
            mode['scenarios'] = {
                '开盘走强': '正常买入，买点附近即可',
                '开盘微跌': '是更好的买入机会，可适当加仓',
                '开盘大幅波动': '等稳定后再操作',
            }
    
    return mode


def _generate_stock_buy_strategy(stock, open_forecast, operation_mode, risk_score):
    """为单只股票生成精准买入策略"""
    
    code = stock.get('code', '')
    name = stock.get('name', '')
    price = stock.get('price', 0)
    buy_point = stock.get('buy_point', 0)
    stop_loss = stock.get('stop_loss', 0)
    target_price = stock.get('target_price', 0)
    change_pct = stock.get('change_pct', 0)
    score = stock.get('score', 0)
    signals = stock.get('signals', [])
    entry_score = stock.get('entry_score', 0)
    
    direction = open_forecast.get('direction', '平开')
    amplitude = open_forecast.get('amplitude', 0)
    mode_name = operation_mode.get('name', '观望')
    mode_position = operation_mode.get('position', 0)
    
    if price <= 0:
        return {'code': code, 'name': name, 'error': '价格数据异常'}
    
    # === 计算各场景买入价位 ===
    strategy = {
        'code': code,
        'name': name,
        'score': score,
        'yesterday_close': round(price, 2),
        'yesterday_change': round(change_pct, 2),
        'original_buy_point': buy_point,
        'original_stop_loss': stop_loss,
        'original_target': target_price,
        'signals': signals[:5],
    }
    
    # 根据开盘预测调整买入价
    # 低开 → 买入价可以更低（等更低的价格）
    # 高开 → 买入价需要更低（不能追高，等回踩）
    
    if direction in ('大幅低开', '小幅低开'):
        # 低开场景：在更低的位置买入
        open_price = round(price * (1 - amplitude / 100), 2)
        
        # 第一买点：开盘价附近（低开直接买）
        first_buy = round(open_price, 2)
        
        # 第二买点：如果继续下跌，在昨日收盘价的 -amplitude*1.5 位置低吸
        deep_buy = round(price * (1 - amplitude * 1.5 / 100), 2)
        
        # 止损：比第一买点低 3-5%
        stop = round(first_buy * 0.97, 2)
        
        # 目标价保持不变
        target = target_price if target_price > 0 else round(price * 1.03, 2)
        
        if mode_name in ('低开低吸', '低开买入'):
            strategy.update({
                'mode': mode_name,
                'scenario': '低开低吸策略',
                'open_est': open_price,
                'buy_points': [
                    {
                        'label': '第一买点（开盘低吸）',
                        'price': first_buy,
                        'timing': '9:30-9:45 开盘即买',
                        'condition': '低开后分时不再继续下杀',
                        'confidence': 'medium',
                    },
                    {
                        'label': '第二买点（午盘深跌低吸）',
                        'price': deep_buy,
                        'timing': '10:30-11:00 或 13:00-13:30',
                        'condition': '继续下跌到此价位且有企稳迹象（下影线、缩量）',
                        'confidence': 'low',
                    },
                ],
                'stop_loss': stop,
                'target': target,
                'position_pct': min(mode_position, 0.3),
                'key_note': f'低开是机会，在{first_buy}元附近买入，跌到{deep_buy}元可加仓',
            })
        elif mode_name == '防御观望':
            strategy.update({
                'mode': mode_name,
                'scenario': '防御策略',
                'open_est': open_price,
                'buy_points': [],
                'stop_loss': stop,
                'target': target,
                'position_pct': 0,
                'key_note': '高风险环境，即使低开也不建议买入，等待大盘企稳',
            })
        else:
            strategy.update({
                'mode': mode_name,
                'scenario': '观望策略',
                'open_est': open_price,
                'buy_points': [
                    {
                        'label': '观察买点（企稳后）',
                        'price': deep_buy,
                        'timing': '午后 13:30-14:00',
                        'condition': '大盘+个股均出现企稳信号',
                        'confidence': 'low',
                    },
                ],
                'stop_loss': stop,
                'target': target,
                'position_pct': 0.1,
                'key_note': '谨慎参与，小仓位试探',
            })
    
    elif direction in ('大幅高开', '小幅高开'):
        # 高开场景：不能追高，等回踩
        open_price = round(price * (1 + amplitude / 100), 2)
        
        # 回踩买入点：回到昨日收盘价或MA5附近
        pullback_buy = buy_point if buy_point > 0 else round(price * 0.99, 2)
        
        # 深度回踩：回到昨日收盘价下方
        deep_pullback = round(price * 0.98, 2)
        
        # 止损
        stop = stop_loss if stop_loss > 0 else round(pullback_buy * 0.97, 2)
        target = target_price if target_price > 0 else round(price * 1.03, 2)
        
        if mode_name in ('高开等回踩', '高开低吸'):
            strategy.update({
                'mode': mode_name,
                'scenario': '高开回踩买入策略',
                'open_est': open_price,
                'buy_points': [
                    {
                        'label': '回踩买入（分时均线附近）',
                        'price': pullback_buy,
                        'timing': '9:45-10:30 分时回踩到均线',
                        'condition': '回踩到均线后企稳，不再继续下跌',
                        'confidence': 'medium',
                    },
                    {
                        'label': '深度回踩买入',
                        'price': deep_pullback,
                        'timing': '10:30-11:00 或 13:00-13:30',
                        'condition': '跌破昨收后出现缩量企稳',
                        'confidence': 'medium',
                    },
                ],
                'stop_loss': stop,
                'target': target,
                'position_pct': min(mode_position, 0.3),
                'key_note': f'高开不追！等回踩到{pullback_buy}元附近买入',
            })
        else:
            strategy.update({
                'mode': mode_name,
                'scenario': '高开回避策略',
                'open_est': open_price,
                'buy_points': [],
                'stop_loss': stop,
                'target': target,
                'position_pct': 0,
                'key_note': '不建议在高开时操作',
            })
    
    else:
        # 平开场景
        if buy_point > 0:
            first_buy = buy_point
        else:
            first_buy = round(price, 2)
        
        stop = stop_loss if stop_loss > 0 else round(first_buy * 0.97, 2)
        target = target_price if target_price > 0 else round(price * 1.03, 2)
        
        if mode_name == '正常买入':
            strategy.update({
                'mode': mode_name,
                'scenario': '平开正常买入策略',
                'open_est': price,
                'buy_points': [
                    {
                        'label': '开盘买入',
                        'price': first_buy,
                        'timing': '9:30-10:00',
                        'condition': '开盘价接近买入价',
                        'confidence': 'high',
                    },
                    {
                        'label': '回调加仓',
                        'price': round(price * 0.985, 2),
                        'timing': '10:00-10:30 回调时',
                        'condition': '小幅回调后在支撑位加仓',
                        'confidence': 'medium',
                    },
                ],
                'stop_loss': stop,
                'target': target,
                'position_pct': min(mode_position, 0.3),
                'key_note': f'正常买入，在{first_buy}元附近建仓',
            })
        else:
            strategy.update({
                'mode': mode_name,
                'scenario': '观望等方向策略',
                'open_est': price,
                'buy_points': [
                    {
                        'label': '方向明确后买入',
                        'price': first_buy,
                        'timing': '10:00后 方向明确',
                        'condition': '大盘放量突破或个股出现明确买入信号',
                        'confidence': 'low',
                    },
                ],
                'stop_loss': stop,
                'target': target,
                'position_pct': 0.1,
                'key_note': '观察为主，方向明确再操作',
            })
    
    # 风险/收益比
    if strategy.get('buy_points'):
        best_buy = strategy['buy_points'][0]['price']
        if stop > 0 and target > 0 and best_buy > 0:
            risk = best_buy - stop
            reward = target - best_buy
            if risk > 0:
                strategy['risk_reward_ratio'] = round(reward / risk, 2)
            else:
                strategy['risk_reward_ratio'] = 0
    
    return strategy


def _generate_advice_text(open_forecast, operation_mode, risk_score, buy_strategies):
    """生成综合建议文本"""
    
    lines = []
    
    # 开盘预测
    direction = open_forecast.get('direction', '未知')
    amplitude = open_forecast.get('amplitude', 0)
    desc = open_forecast.get('description', '')
    
    lines.append(f"📊 开盘预测：{desc}")
    lines.append(f"🎯 操作模式：{operation_mode['name']} — {operation_mode['description']}")
    
    # 买入时机
    buy_timing = operation_mode.get('buy_timing', '')
    if buy_timing:
        lines.append(f"⏰ 买入时机：{buy_timing}")
    
    # 建议仓位
    position = operation_mode.get('position', 0)
    if position > 0:
        pos_text = f"{int(position * 100)}%" if position < 1 else "满仓"
        lines.append(f"💰 建议仓位：{pos_text}")
    else:
        lines.append(f"💰 建议仓位：空仓观望")
    
    # 关键操作
    key_action = operation_mode.get('key_action', '')
    if key_action:
        lines.append(f"🔑 关键操作：{key_action}")
    
    # 场景分析
    scenarios = operation_mode.get('scenarios', {})
    if scenarios:
        lines.append("")
        lines.append("📋 盘中场景应对：")
        for scenario, action in scenarios.items():
            lines.append(f"  • {scenario} → {action}")
    
    # 个股策略
    valid_strategies = [s for s in buy_strategies if 'error' not in s and s.get('buy_points')]
    if valid_strategies:
        lines.append("")
        lines.append(f"🎯 推荐股票买入策略（{len(valid_strategies)}只）：")
        
        for i, s in enumerate(valid_strategies, 1):
            lines.append(f"\n  {i}. {s['name']}({s['code']}) | 评分{s['score']} | 模式: {s.get('mode', '-')}")
            
            # 昨收
            lines.append(f"     昨收: {s['yesterday_close']} ({s['yesterday_change']:+.2f}%)")
            
            # 预估开盘价
            open_est = s.get('open_est', 0)
            if open_est and open_est != s['yesterday_close']:
                lines.append(f"     预估开盘: {open_est}")
            
            # 买入点
            for bp in s.get('buy_points', []):
                conf = {'high': '✅', 'medium': '🟡', 'low': '🔴'}.get(bp.get('confidence', 'medium'), '⚪')
                lines.append(f"     {conf} {bp['label']}: {bp['price']}元 ({bp['timing']})")
                lines.append(f"        条件: {bp['condition']}")
            
            # 止损和目标
            if s.get('stop_loss'):
                lines.append(f"     🛑 止损: {s['stop_loss']}元")
            if s.get('target'):
                lines.append(f"     🎯 目标: {s['target']}元")
            
            # 风险/收益
            rr = s.get('risk_reward_ratio', 0)
            if rr > 0:
                rr_cls = '🟢' if rr >= 3 else '🟡' if rr >= 2 else '🔴'
                lines.append(f"     {rr_cls} 风险/收益比: 1:{rr}")
            
            # 关键提示
            if s.get('key_note'):
                lines.append(f"     💡 {s['key_note']}")
    
    # 底部提醒
    lines.append("")
    lines.append("⚠️ 风险提醒：")
    lines.append("  • 以上建议基于技术分析和外围数据，不构成投资建议")
    lines.append("  • 买入时严格执行止损，触发止损立即卖出")
    lines.append("  • 单票仓位不超过总资金30%")
    lines.append("  • 若大盘走势与预期严重不符，暂停操作")
    
    return '\n'.join(lines)


def generate_midday_buy_adjustment(morning_data, midday_data):
    """
    午盘时根据上午实际走势调整买入策略。
    比如早盘预测低开低走，但实际高开高走，需要调整策略。
    """
    
    if not midday_data:
        return None
    
    cn_indices = midday_data.get('cn_indices', {})
    sh = cn_indices.get('000001', {})
    actual_chg = sh.get('change_pct', 0)
    
    # 获取晨间预测
    morning_strategy = morning_data.get('strategy', {})
    morning_risk = morning_strategy.get('risk_score', 50)
    
    # 获取午间分析
    midday_strategy = midday_data.get('strategy', {})
    midday_risk = midday_strategy.get('risk_score', 50)
    
    adjustments = []
    
    # 对比预测 vs 实际
    if actual_chg > 1:
        adjustments.append(f"📈 上证实际涨{actual_chg:+.2f}%，走势强于预期，午后可适度参与")
    elif actual_chg > 0.3:
        adjustments.append(f"↗️ 上证实际涨{actual_chg:+.2f}%，走势符合预期，维持原策略")
    elif actual_chg > -0.3:
        adjustments.append(f"➡️ 上证实际{actual_chg:+.2f}%，走势平稳，观望为主")
    elif actual_chg > -1:
        adjustments.append(f"↘️ 上证实际跌{abs(actual_chg):.2f}%，走势偏弱，控制仓位")
    else:
        adjustments.append(f"📉 上证实际跌{abs(actual_chg):.2f}%，走势偏弱，不建议买入")
    
    # 风险评分变化
    risk_change = midday_risk - morning_risk
    if risk_change > 10:
        adjustments.append(f"⚠️ 风险评分从{morning_risk}升至{midday_risk}，风险显著增加，建议减仓或空仓")
    elif risk_change > 5:
        adjustments.append(f"🟡 风险评分从{morning_risk}升至{midday_risk}，适度谨慎")
    elif risk_change < -10:
        adjustments.append(f"✅ 风险评分从{morning_risk}降至{midday_risk}，风险降低，可适度加仓")
    elif risk_change < -5:
        adjustments.append(f"🟢 风险评分从{morning_risk}降至{midday_risk}，环境改善")
    
    # 午后操作建议
    if midday_risk >= 70:
        adjustments.append("")
        adjustments.append("🔴 午后操作：不加仓、不追高，持仓股弱势则减仓")
    elif midday_risk >= 55:
        adjustments.append("")
        adjustments.append("🟡 午后操作：不开新仓，持仓观望，等企稳信号")
    elif midday_risk >= 40:
        adjustments.append("")
        if actual_chg < 0:
            adjustments.append("🟢 午后操作：大盘低走但风险可控，可在13:00-13:30低吸优质标的")
            # 计算低吸价位
            if morning_data.get('top_buys'):
                for s in morning_data['top_buys']:
                    bp = s.get('buy_point', 0)
                    price = s.get('price', 0)
                    if bp > 0 and price > 0:
                        midday_buy = round(bp * 0.99, 2)  # 在买点再低1%买入
                        adjustments.append(f"  • {s['name']}({s['code']}) 午盘低吸参考价: {midday_buy}元")
        else:
            adjustments.append("🟢 午后操作：大盘偏强，可在回调时分批建仓")
    else:
        adjustments.append("")
        adjustments.append("🟢 午后操作：低风险环境，可积极参与")
    
    return {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'actual_sh_change': actual_chg,
        'morning_risk': morning_risk,
        'midday_risk': midday_risk,
        'risk_change': risk_change,
        'adjustments': adjustments,
        'advice_text': '\n'.join(adjustments),
    }


if __name__ == '__main__':
    # 测试：加载晨间分析数据，生成综合策略
    data_dir = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')
    morning = _load_json(os.path.join(data_dir, 'morning_analysis.json'))
    
    if morning:
        print("=== 生成综合买入策略 ===")
        result = generate_comprehensive_buy_strategy(morning)
        
        print(f"\n开盘预测: {result['open_forecast']['description']}")
        print(f"操作模式: {result['operation_mode']['name']} — {result['operation_mode']['description']}")
        print(f"风险评分: {result['risk_score']}/100")
        
        print(f"\n{result['advice_text']}")
        
        # 午间调整
        midday = _load_json(os.path.join(data_dir, 'midday_analysis.json'))
        if midday:
            adj = generate_midday_buy_adjustment(morning, midday)
            if adj:
                print(f"\n=== 午间策略调整 ===")
                print(adj['advice_text'])
        
        # 保存
        output_path = os.path.join(data_dir, 'comprehensive_strategy.json')
        os.makedirs(data_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 综合策略已保存到 {output_path}")
    else:
        print("⚠️ 未找到晨间分析数据")
