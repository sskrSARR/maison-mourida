from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from catalog.models import MenuItem
from orders.services import create_prepaid_order, notify, notify_vendors
from subscriptions.models import Subscription


def _available(item, day):
    if item is None:
        return None
    return (
        MenuItem.objects.filter(item=item, service_date=day, menu__status="publie", remaining_quantity__gte=1)
        .select_related("item")
        .first()
    )


def generate_due_orders(for_date=None):
    for_date = for_date or (timezone.localdate() + timedelta(days=1))
    weekday = str(for_date.weekday())
    created = 0
    subscriptions = Subscription.objects.filter(
        status="actif",
        start_date__lte=for_date,
        end_date__gte=for_date,
    ).select_related("client", "item", "replacement_item", "plan")
    for subscription in subscriptions:
        if weekday not in subscription.weekdays.split(","):
            continue
        if subscription.orders.filter(delivery_date=for_date).exists():
            continue
        menu_item = _available(subscription.item, for_date)
        if menu_item is None:
            menu_item = _available(subscription.replacement_item, for_date)
        if menu_item is None:
            notify_vendors(
                f"Abonnement de {subscription.client.name} : plat épuisé le {for_date:%d/%m}."
            )
            notify(subscription.client, f"Votre plat du {for_date:%d/%m} n'a pas pu être réservé.")
            continue
        try:
            create_prepaid_order(
                subscription.client,
                menu_item,
                subscription.address,
                subscription.slot,
                {
                    "piment": subscription.piment,
                    "ketchup": subscription.ketchup,
                    "mayonnaise": subscription.mayonnaise,
                    "sans_oignon": subscription.sans_oignon,
                },
                subscription,
            )
            created += 1
        except ValidationError:
            notify_vendors(f"Abonnement de {subscription.client.name} : commande du {for_date:%d/%m} impossible.")
    return created


def expire_subscriptions():
    today = timezone.localdate()
    ended = Subscription.objects.filter(status="actif", end_date__lt=today).update(status="expire")
    soon = today + timedelta(days=5)
    for subscription in Subscription.objects.filter(status="actif", end_date=soon).select_related("client"):
        notify(
            subscription.client,
            f"Votre abonnement se termine le {subscription.end_date:%d/%m}. Pensez à le renouveler.",
        )
    return ended
