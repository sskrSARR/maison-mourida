from datetime import date

from django.core.exceptions import ValidationError
from django.utils import timezone

from catalog.models import MenuItem


def empty_cart():
    return {"day": None, "lines": {}}


def get_cart(request):
    cart = request.session.get("cart")
    if not isinstance(cart, dict) or "lines" not in cart:
        return empty_cart()
    return cart


def save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


def clear_cart(request):
    save_cart(request, empty_cart())


def add_to_cart(request, menu_item, qty, mode="add"):
    if mode == "add" and qty < 1:
        raise ValidationError("Quantité invalide.")
    if menu_item.menu.status != "publie":
        raise ValidationError("Ce menu n'est pas publié.")
    if menu_item.menu.order_deadline <= timezone.now():
        raise ValidationError("La date limite de commande est passée.")
    if menu_item.service_date < timezone.localdate():
        raise ValidationError("Ce jour est passé.")
    cart = get_cart(request)
    day = None if menu_item.item.category == "jus" else menu_item.service_date.isoformat()
    if day and cart["lines"] and cart.get("day") and cart["day"] != day:
        raise ValidationError("Le panier est pour un autre jour. Validez-le ou videz-le d'abord.")
    key = str(menu_item.id)
    current_qty = cart["lines"].get(key, {}).get("qty", 0)
    new_qty = qty if mode == "set" else current_qty + qty
    if new_qty <= 0:
        cart["lines"].pop(key, None)
    else:
        if new_qty > 20:
            raise ValidationError("Quantité maximale : 20.")
        if new_qty > menu_item.remaining_quantity:
            raise ValidationError(f"Il reste {menu_item.remaining_quantity} pour {menu_item.item.name}.")
        cart["lines"][key] = {
            "qty": new_qty,
            "name": menu_item.item.name,
            "price": menu_item.unit_price,
        }
    if not cart["lines"]:
        cart["day"] = None
    elif day:
        cart["day"] = day
    save_cart(request, cart)
    return cart


def resolve_cart(request):
    cart = get_cart(request)
    lines = []
    adjusted = False
    for key in list(cart["lines"].keys()):
        line = cart["lines"][key]
        try:
            menu_item = MenuItem.objects.select_related("item", "menu").get(pk=int(key))
        except (MenuItem.DoesNotExist, TypeError, ValueError):
            cart["lines"].pop(key, None)
            adjusted = True
            continue
        qty = min(int(line.get("qty", 0)), menu_item.remaining_quantity)
        if qty < 1 or menu_item.menu.status != "publie" or menu_item.service_date < timezone.localdate():
            cart["lines"].pop(key, None)
            adjusted = True
            continue
        if qty != line.get("qty"):
            adjusted = True
        cart["lines"][key] = {"qty": qty, "name": menu_item.item.name, "price": menu_item.unit_price}
        lines.append({"menu_item": menu_item, "qty": qty, "price": menu_item.unit_price, "key": key})
    if not cart["lines"]:
        cart["day"] = None
    day = date.fromisoformat(cart["day"]) if cart.get("day") else None
    save_cart(request, cart)
    return cart, lines, day, adjusted
