from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from catalog.models import MenuItem
from notifications.models import Notification
from orders.constants import ALLOWED, CLIENT_CAN_CANCEL, SLOTS, message_for
from orders.models import Order, OrderLine, OrderStatusHistory, Preference, ShopSettings


def notify(user, content, channel="app"):
    return Notification.objects.create(recipient=user, channel=channel, content=content, state="enregistre")


def notify_vendors(content):
    from accounts.models import User

    for vendor in User.objects.filter(role="vendeuse", is_active=True):
        notify(vendor, content)


def save_preferences(*, user=None, order=None, data):
    if order is not None:
        Preference.objects.filter(order=order).delete()
        owner = {"order": order}
    else:
        Preference.objects.filter(user=user, order__isnull=True).delete()
        owner = {"user": user}
    Preference.objects.bulk_create(
        [
            Preference(key="piment", value=data.get("piment") or "aucun", **owner),
            Preference(key="ketchup", value="oui" if data.get("ketchup") else "non", **owner),
            Preference(key="mayonnaise", value="oui" if data.get("mayonnaise") else "non", **owner),
            Preference(key="sans_oignon", value="oui" if data.get("sans_oignon") else "non", **owner),
        ]
    )


def user_pref_map(user):
    if not getattr(user, "is_authenticated", False):
        return {}
    return {pref.key: pref.value for pref in user.preferences.filter(order__isnull=True)}


def guest_from_checkout(name, phone):
    from accounts.models import User
    from shopkit import normalize_phone, valid_phone

    cleaned = normalize_phone(phone)
    if not valid_phone(cleaned):
        raise ValidationError("Indiquez un numéro sénégalais à 9 chiffres, par exemple 77 123 45 67.")
    label = (name or "").strip()
    if len(label) < 2:
        raise ValidationError("Indiquez votre nom.")
    user = User.objects.filter(phone=cleaned).first()
    if user and (user.role == "vendeuse" or user.is_staff):
        raise ValidationError("Ce numéro est réservé à la cuisine.")
    if user is None:
        user = User(phone=cleaned, name=label, role="client")
        user.set_unusable_password()
        user.save()
    elif user.name != label:
        user.name = label
        user.save(update_fields=["name", "updated_at"])
    return user


def _write_snapshot(order, user, preferences):
    order.allergies.set(user.allergies.all())
    order.allergy_note = user.allergy_note
    order.save(update_fields=["allergy_note", "updated_at"])
    save_preferences(order=order, data=preferences)


def _record(order, old_status, new_status, author, note):
    OrderStatusHistory.objects.create(
        order=order,
        old_status=old_status,
        new_status=new_status,
        author=author,
        note=note[:255],
    )
    notify(order.client, message_for(order, new_status, note))


@transaction.atomic
def create_order(user, lines, address, slot, note, preferences):
    if not lines:
        raise ValidationError("Le panier est vide.")
    address = (address or "").strip()
    if not address:
        raise ValidationError("Indiquez une adresse de livraison.")
    if slot not in {key for key, _ in SLOTS}:
        raise ValidationError("Créneau invalide.")
    shop = ShopSettings.load()
    locked = []
    days = set()
    for line in lines:
        try:
            qty = int(line["qty"])
        except (TypeError, ValueError, KeyError) as exc:
            raise ValidationError("Quantité invalide.") from exc
        if qty < 1 or qty > 20:
            raise ValidationError("Quantité invalide.")
        try:
            menu_item = (
                MenuItem.objects.select_for_update()
                .select_related("item", "menu")
                .get(pk=line["menu_item_id"])
            )
        except MenuItem.DoesNotExist as exc:
            raise ValidationError("Un plat du panier n'est plus disponible.") from exc
        if menu_item.menu.status != "publie":
            raise ValidationError(f"{menu_item.item.name} n'est plus au menu.")
        if timezone.now() > menu_item.menu.order_deadline:
            raise ValidationError("La date limite de commande est passée.")
        if menu_item.service_date < timezone.localdate():
            raise ValidationError("Ce jour est passé.")
        if menu_item.remaining_quantity < qty:
            raise ValidationError(f"Stock insuffisant pour {menu_item.item.name}.")
        if menu_item.item.category != "jus":
            days.add(menu_item.service_date)
        locked.append((menu_item, qty))
    if len(days) > 1:
        raise ValidationError("Le panier doit concerner un seul jour.")
    if days:
        delivery_date = next(iter(days))
    else:
        delivery_date = timezone.localdate()
        menu = locked[0][0].menu
        if delivery_date < menu.start_date:
            delivery_date = menu.start_date
        elif delivery_date > menu.end_date:
            delivery_date = menu.end_date
    subtotal = sum(menu_item.unit_price * qty for menu_item, qty in locked)
    order = Order.objects.create(
        client=user,
        delivery_date=delivery_date,
        slot=slot,
        address=address,
        delivery_fee=shop.delivery_fee,
        total=subtotal + shop.delivery_fee,
        status="en_attente_paiement",
        payment_status="en_attente",
        note=(note or "").strip(),
    )
    for menu_item, qty in locked:
        OrderLine.objects.create(
            order=order,
            menu_item=menu_item,
            quantity=qty,
            unit_price=menu_item.unit_price,
        )
        menu_item.remaining_quantity -= qty
        menu_item.save(update_fields=["remaining_quantity", "updated_at"])
    _write_snapshot(order, user, preferences)
    _record(order, "", "en_attente_paiement", user, "")
    return order


def restore_stock(order):
    if order.stock_restored:
        return
    for line in order.lines.select_related("menu_item"):
        menu_item = MenuItem.objects.select_for_update().get(pk=line.menu_item_id)
        menu_item.remaining_quantity += line.quantity
        menu_item.save(update_fields=["remaining_quantity", "updated_at"])
    order.stock_restored = True


@transaction.atomic
def change_status(order, new_status, author, note=""):
    order = Order.objects.select_for_update().get(pk=order.pk)
    old = order.status
    if new_status not in ALLOWED.get(old, ()):
        raise ValidationError("Cette transition n'est pas autorisée.")
    if new_status == "annulee" and author is not None and author.role != "vendeuse" and not author.is_superuser:
        if old not in CLIENT_CAN_CANCEL:
            raise ValidationError("Vous ne pouvez plus annuler cette commande.")
    if new_status == "annulee":
        restore_stock(order)
        if note:
            extra = f"Annulation : {note}"
            order.note = f"{order.note}\n{extra}".strip() if order.note else extra
    order.status = new_status
    if new_status == "paiement_a_verifier":
        order.payment_status = "en_verification"
    elif new_status == "payee":
        order.payment_status = "valide"
        order.paid_at = timezone.now()
    elif new_status == "en_attente_paiement" and old == "paiement_a_verifier":
        order.payment_status = "rejete"
    order.save()
    _record(order, old, new_status, author, note)
    return order


@transaction.atomic
def create_prepaid_order(user, menu_item, address, slot, preferences, subscription, note="Abonné"):
    menu_item = MenuItem.objects.select_for_update().select_related("item").get(pk=menu_item.pk)
    if menu_item.remaining_quantity < 1:
        raise ValidationError("Stock insuffisant.")
    price = menu_item.unit_price
    order = Order.objects.create(
        client=user,
        subscription=subscription,
        delivery_date=menu_item.service_date,
        slot=slot,
        address=address,
        delivery_fee=0,
        total=price,
        status="payee",
        payment_status="valide",
        paid_at=timezone.now(),
        note=note,
    )
    OrderLine.objects.create(order=order, menu_item=menu_item, quantity=1, unit_price=price)
    menu_item.remaining_quantity -= 1
    menu_item.save(update_fields=["remaining_quantity", "updated_at"])
    _write_snapshot(order, user, preferences)
    _record(order, "", "payee", None, "Abonnement")
    return order


def expire_unpaid():
    shop = ShopSettings.load()
    limit = timezone.now() - timedelta(hours=shop.unpaid_timeout_hours)
    expired = 0
    for order in Order.objects.filter(status="en_attente_paiement", created_at__lt=limit):
        change_status(order, "annulee", None, note="Délai de paiement dépassé")
        expired += 1
    return expired


def order_queryset():
    return Order.objects.select_related("client", "subscription").prefetch_related(
        "lines__menu_item__item",
        "allergies",
        "preferences",
        "payments",
        "history__author",
    )


def get_order_for(user, order_id):
    from django.shortcuts import get_object_or_404

    queryset = order_queryset()
    if user.role == "vendeuse" or user.is_superuser:
        return get_object_or_404(queryset, pk=order_id)
    return get_object_or_404(queryset, pk=order_id, client=user)
