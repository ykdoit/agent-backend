"""
Time Oracle: 统一时间解析服务

设计原则:
1. 单一入口：所有时间解析统一通过 time_oracle 处理
2. 智能推断：自动判断返回时间点还是时间范围
3. 口语化全覆盖：支持所有中文口语化时间表达

使用方式:
    from app.utils.time_oracle import time_oracle, get_system_time_context
    
    result = time_oracle("明天", mode="point")  # 返回时间点
    result = time_oracle("本周", mode="range")  # 返回时间范围
"""
from datetime import datetime, timedelta
from typing import Literal, Optional
import re

import dateparser


# 时间范围关键词映射（用于自动判断模式）
RANGE_KEYWORDS = {
    # 周级别
    "本周", "这周", "这一周", "this_week",
    "下周", "下一周", "this week", "next week",
    "上周", "上一周", "last week",
    # 月级别
    "本月", "这个月", "this_month",
    "下月", "下个月", "next_month",
    "上月", "上个月", "last month",
    # 季度
    "本季度", "本季", "this_quarter",
    # 默认查询范围
    "未来7天", "未来七天", "下周的计划", "接下来的",
}

# 中文星期映射
WEEKDAY_CN_MAP = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
}


def parse_chinese_time(expression: str, now: datetime) -> Optional[datetime]:
    """
    增强的中文时间解析器 - 补充 dateparser 不支持的中文表达式。
    
    支持的表达式：
    - 相对天数：后天、大后天、外后天（4天后）
    - 下周X：下周二、下周三
    - 下下X：下下周三
    - N天后：3天后、7天后
    - N天前：2天前（用于历史查询）
    - N周后：2周后
    - 本周X：本周五
    
    Args:
        expression: 口语化时间表达式
        now: 当前时间基准
        
    Returns:
        解析后的 datetime 对象，解析失败返回 None
    """
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    expr = expression.strip()
    
    # 1. 相对天数：后天、大后天、外后天
    relative_days = {
        "后天": 2,
        "大后天": 3,
        "外后天": 4,
        "大大后天": 4,
    }
    if expr in relative_days:
        return today + timedelta(days=relative_days[expr])
    
    # 2. 下周X / 下下X周X
    next_week_match = re.match(r"^(下+)(周|星期)([一二三四五六七日天])$", expr)
    if next_week_match:
        num_next = len(next_week_match.group(1))
        weekday_char = next_week_match.group(3)
        target_weekday = WEEKDAY_CN_MAP.get(weekday_char)
        
        if target_weekday is not None:
            current_weekday = today.weekday()
            days_until_next_week = 7 - current_weekday
            days_to_target = days_until_next_week + target_weekday
            extra_weeks = (num_next - 1) * 7
            return today + timedelta(days=days_to_target + extra_weeks)
    
    # 3. 本周X（本周内的某天）
    this_week_match = re.match(r"^本(周|星期)([一二三四五六七日天])$", expr)
    if this_week_match:
        weekday_char = this_week_match.group(2)
        target_weekday = WEEKDAY_CN_MAP.get(weekday_char)
        if target_weekday is not None:
            current_weekday = today.weekday()
            days_diff = target_weekday - current_weekday
            return today + timedelta(days=days_diff)
    
    # 4. N天后 / N天前
    days_match = re.match(r"^(\d+)天(前|后)$", expr)
    if days_match:
        num_days = int(days_match.group(1))
        direction = days_match.group(2)
        if direction == "后":
            return today + timedelta(days=num_days)
        else:
            return today - timedelta(days=num_days)
    
    # 5. N周后
    weeks_match = re.match(r"^(\d+)周后$", expr)
    if weeks_match:
        num_weeks = int(weeks_match.group(1))
        return today + timedelta(weeks=num_weeks)
    
    return None


def get_system_time_context() -> dict:
    """
    获取系统当前时间及业务日期上下文。
    所有销售行动计划的日期计算必须以此工具为准。
    
    Returns:
        包含当前时间、今日、明日、星期等基准信息
    """
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    tomorrow = today + timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    
    return {
        "current_time": now.strftime('%Y-%m-%d %H:%M:%S'),
        "today": today.strftime('%Y-%m-%d'),
        "tomorrow": tomorrow.strftime('%Y-%m-%d'),
        "day_of_week": weekday_names[today.weekday()],
        "week_start": week_start.strftime('%Y-%m-%d'),
        "week_end": week_end.strftime('%Y-%m-%d'),
    }


def time_oracle(
    time_expression: str,
    mode: Literal["auto", "point", "range"] = "auto"
) -> dict:
    """
    统一时间解析器 - 支持时间点和时间范围的智能解析。
    
    将口语化的时间描述智能转换为标准日期或时间范围，
    同时服务于创建计划（时间点）和查询列表（时间范围）两种场景。
    
    **调用时机**：
    - 需要调用：用户输入非标准日期（如"明天"、"大后天"、"下周二"、"本月"）
    - 无需调用：用户已提供标准格式 YYYY-MM-DD（如"2026-02-15"）
    
    Args:
        time_expression: 口语化时间表达式，例如：
            - 时间点："明天"、"下周二"、"大后天"、"3天后"、"2月20日"
            - 时间范围："本周"、"下周"、"未来7天"、"本月"
        mode: 解析模式
            - "auto": 自动判断（默认）- 根据表达式自动返回时间点或范围
            - "point": 强制返回时间点
            - "range": 强制返回时间范围
    
    Returns:
        解析结果字典：
        - 时间点模式: {"mode": "point", "date": "2026-02-15", ...}
        - 时间范围模式: {"mode": "range", "startTime": "...", "endTime": "...", ...}
    """
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 判断是否为时间范围关键词
    is_range_keyword = time_expression.strip() in RANGE_KEYWORDS
    
    if mode == "range":
        return _parse_as_range(time_expression, today)
    elif mode == "point":
        return _parse_as_point(time_expression, now)
    else:  # auto 模式
        if is_range_keyword:
            return _parse_as_range(time_expression, today)
        else:
            point_result = _parse_as_point(time_expression, now)
            if point_result["success"]:
                return point_result
            else:
                return _parse_as_range(time_expression, today)


def _parse_as_point(expression: str, now: datetime) -> dict:
    """解析为时间点（YYYY-MM-DD）"""
    dt = parse_chinese_time(expression, now)
    
    if dt is None:
        dt = dateparser.parse(
            expression,
            languages=['zh'],
            settings={
                'RELATIVE_BASE': now,
                'PREFER_DATES_FROM': 'future',
                'RETURN_AS_TIMEZONE_AWARE': False,
            }
        )
    
    if dt:
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return {
            "mode": "point",
            "success": True,
            "input": expression,
            "date": dt.strftime('%Y-%m-%d'),
            "day_of_week": weekday_names[dt.weekday()],
            "display": f"{dt.strftime('%Y-%m-%d')} ({weekday_names[dt.weekday()]})",
        }
    else:
        return {
            "mode": "point",
            "success": False,
            "input": expression,
            "error": f"无法识别时间 '{expression}'，请提供更准确的日期（如：明天、下周二、2月15日）。"
        }


def _parse_as_range(expression: str, today: datetime) -> dict:
    """解析为时间范围（startTime ~ endTime）"""
    
    predefined_ranges = _get_predefined_ranges(today)
    
    if expression in predefined_ranges:
        start, end, display = predefined_ranges[expression]
        return _build_range_result(expression, start, end, display)
    
    # 尝试解析为时间点
    dt = parse_chinese_time(expression, today)
    
    if dt is None:
        dt = dateparser.parse(
            expression,
            languages=['zh'],
            settings={
                'RELATIVE_BASE': today,
                'PREFER_DATES_FROM': 'future',
                'RETURN_AS_TIMEZONE_AWARE': False,
            }
        )
    
    if dt:
        point_date = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        start = point_date
        end = point_date + timedelta(days=1) - timedelta(seconds=1)
        display = f"{dt.strftime('%Y-%m-%d')} 全天"
        return _build_range_result(expression, start, end, display)
    
    return {
        "mode": "range",
        "success": False,
        "input": expression,
        "error": f"无法识别时间范围 '{expression}'，请使用：今天、明天、本周、下周、未来7天等。"
    }


def _get_predefined_ranges(today: datetime) -> dict:
    """获取预设时间范围"""
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    next_week_start = week_start + timedelta(days=7)
    next_week_end = week_end + timedelta(days=7)
    
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(day=31)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    return {
        "今天": (today, today + timedelta(days=1) - timedelta(seconds=1), "今天"),
        "today": (today, today + timedelta(days=1) - timedelta(seconds=1), "今天"),
        "明天": (today + timedelta(days=1), today + timedelta(days=2) - timedelta(seconds=1), "明天"),
        "tomorrow": (today + timedelta(days=1), today + timedelta(days=2) - timedelta(seconds=1), "明天"),
        "本周": (week_start, week_end + timedelta(hours=23, minutes=59, seconds=59), "本周"),
        "这周": (week_start, week_end + timedelta(hours=23, minutes=59, seconds=59), "本周"),
        "this_week": (week_start, week_end + timedelta(hours=23, minutes=59, seconds=59), "本周"),
        "下周": (next_week_start, next_week_end + timedelta(hours=23, minutes=59, seconds=59), "下周"),
        "next_week": (next_week_start, next_week_end + timedelta(hours=23, minutes=59, seconds=59), "下周"),
        "本月": (month_start, month_end + timedelta(hours=23, minutes=59, seconds=59), "本月"),
        "this_month": (month_start, month_end + timedelta(hours=23, minutes=59, seconds=59), "本月"),
        "未来7天": (today, today + timedelta(days=7) - timedelta(seconds=1), "未来7天"),
        "next_7_days": (today, today + timedelta(days=7) - timedelta(seconds=1), "未来7天"),
    }


def _build_range_result(expression: str, start: datetime, end: datetime, display: str) -> dict:
    """构建时间范围返回结果"""
    return {
        "mode": "range",
        "success": True,
        "input": expression,
        "startTime": start.strftime('%Y-%m-%d %H:%M:%S'),
        "endTime": end.strftime('%Y-%m-%d %H:%M:%S'),
        "display_range": display,
        "days_count": (end.date() - start.date()).days + 1,
    }
