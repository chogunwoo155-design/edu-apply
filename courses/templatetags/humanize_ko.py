from django import template

register = template.Library()


@register.filter
def won(value):
    """30000 -> '30,000원', 0 -> '무료'"""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return value
    return "무료" if value == 0 else f"{value:,}원"
