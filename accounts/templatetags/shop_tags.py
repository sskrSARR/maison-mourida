from django import template

from orders.constants import STATUS_LABELS, reference as order_reference
from shopkit import normalize_phone

register = template.Library()


@register.filter
def fcfa(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    grouped = f"{number:,}".replace(",", " ")
    return f"{grouped}\u00a0F"


@register.filter
def status_label(value):
    return STATUS_LABELS.get(value, value)


@register.filter
def reference(order):
    return order_reference(order)


@register.filter
def multiply(value, arg):
    try:
        return int(value) * int(arg)
    except (TypeError, ValueError):
        return value


@register.filter
def tel(value):
    digits = normalize_phone(value)
    if len(digits) == 9:
        return f"{digits[0:2]} {digits[2:5]} {digits[5:7]} {digits[7:9]}"
    return value
