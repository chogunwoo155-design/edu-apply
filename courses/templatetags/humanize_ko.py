from django import template

from applications import rules

register = template.Library()


@register.filter
def won(value):
    """30000 -> '30,000원', 0 -> '무료'"""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return value
    return "무료" if value == 0 else f"{value:,}원"


@register.filter
def dday(value):
    """마감일까지: 'D-3', 오늘이면 'D-day', 지났으면 '마감'"""
    if not value:
        return ""
    diff = (value - rules.today()).days
    if diff > 0:
        return f"D-{diff}"
    return "D-day" if diff == 0 else "마감"


@register.filter
def contact_dday(value):
    """연락일 기준 (관리 화면): 오늘 / 내일 / D-3 / 3일 지남"""
    if not value:
        return ""
    diff = (value - rules.today()).days
    if diff == 0:
        return "오늘"
    if diff == 1:
        return "내일"
    return f"D-{diff}" if diff > 0 else f"{-diff}일 지남"


@register.filter
def mask_email(value):
    """apply@example.com -> ap***@example.com"""
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    return f"{local[:2]}***@{domain}"


@register.filter
def get_item(mapping, key):
    return mapping.get(key, "") if mapping else ""


WEEKDAYS = "월화수목금토일"


@register.filter
def kday(value):
    """요일 한 글자: 월, 화 … (Django 'D'는 한국어에서 '화요일'로 나온다)"""
    return WEEKDAYS[value.weekday()] if value else ""


@register.filter
def kdate(value):
    """12월 1일 (화)"""
    return f"{value.month}월 {value.day}일 ({WEEKDAYS[value.weekday()]})" if value else ""
