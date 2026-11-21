from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Allergy, User
from catalog.models import Item, Menu, MenuItem
from orders.models import ShopSettings

DAY_PLATS = [
    ("Poulet à la crème", "Purée de pomme de terre.", 3000),
    ("Kefta viande", "Pain arabe, frites, salade de tomate et concombre.", 3000),
    ("Brochettes de poulet au miel et basilic", "Gratin dauphinois.", 3000),
    ("Poisson farci aux légumes et crevettes", "", 3000),
    ("Nems viande crevettes", "10 pièces, avec salade.", 2500),
]
JUICES = [
    ("Bouye au lait", "Format 250 ml."),
    ("Bouye fraise", "Format 250 ml."),
    ("Cocktail", "Format 250 ml."),
    ("Ditakh", "Format 250 ml."),
]

def ensure_user(phone, password, **fields):
    user, created = User.objects.get_or_create(phone=phone, defaults=fields)
    if created:
        user.set_password(password)
        user.save()
    return user


class Command(BaseCommand):
    help = "Crée les comptes de démonstration et un menu publié."

    def handle(self, *args, **options):
        for label in ["Arachide", "Gluten", "Fruits de mer", "Lactose", "Œuf", "Poisson"]:
            Allergy.objects.get_or_create(label=label)
        ensure_user("770000000", "maintenance", name="Maintenance", role="vendeuse", is_staff=True, is_superuser=True)
        ensure_user("770000001", "cuisine", name="Démo vendeuse", role="vendeuse", default_address="Dakar")
        ensure_user(
            "771234567",
            "client",
            name="Démo client",
            role="client",
            default_address="Sacré-Cœur 3, Dakar",
        )
        shop = ShopSettings.load()
        if shop.beneficiary_name in ("", "Démo vendeuse") or shop.wave_number in ("", "770000001"):
            shop.beneficiary_name = "Maison Mourida"
            shop.whatsapp_number = "221771970967"
            if shop.wave_number in ("", "770000001"):
                shop.wave_number = "771970967"
                shop.om_number = "768160977"
            shop.unpaid_timeout_hours = shop.unpaid_timeout_hours or 2
            shop.save()
        plats = []
        for name, description, price in DAY_PLATS:
            item, _created = Item.objects.get_or_create(
                name=name,
                defaults={"description": description, "category": "plat", "price_fcfa": price, "is_active": True},
            )
            plats.append(item)
        juices = []
        for name, description in JUICES:
            item, _created = Item.objects.get_or_create(
                name=name,
                defaults={"description": description, "category": "jus", "price_fcfa": 500, "is_active": True},
            )
            juices.append(item)
        _collapse_juices()
        today = timezone.localdate()
        if today.weekday() >= 5:
            start = today + timedelta(days=(7 - today.weekday()))
        else:
            start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=4)
        if Menu.objects.filter(title="Menu déjeuner", start_date=start).exists():
            self.stdout.write("Données prêtes.")
            return
        Menu.objects.filter(status="publie", title__startswith="Semaine du").update(status="clos")
        deadline = timezone.make_aware(datetime.combine(end, time(10, 0)), timezone.get_current_timezone())
        menu = Menu.objects.create(
            title="Menu déjeuner",
            start_date=start,
            end_date=end,
            order_deadline=deadline,
            status="publie",
        )
        for offset, plat in enumerate(plats):
            day = start + timedelta(days=offset)
            MenuItem.objects.get_or_create(
                menu=menu,
                item=plat,
                service_date=day,
                defaults={"max_quantity": 20, "remaining_quantity": 20},
            )
        for juice in juices:
            MenuItem.objects.get_or_create(
                menu=menu,
                item=juice,
                service_date=end,
                defaults={"max_quantity": 30, "remaining_quantity": 30},
            )
        self.stdout.write("Données prêtes.")


def _collapse_juices():
    for menu in Menu.objects.filter(status="publie"):
        grouped = {}
        for row in MenuItem.objects.filter(menu=menu, item__category="jus"):
            grouped.setdefault(row.item_id, []).append(row)
        for group in grouped.values():
            keeper = max(group, key=lambda row: (row.service_date == menu.end_date, row.id))
            for other in group:
                if other.id == keeper.id:
                    continue
                other.order_lines.all().update(menu_item=keeper)
                other.delete()
            if keeper.service_date != menu.end_date:
                keeper.service_date = menu.end_date
                keeper.save(update_fields=["service_date", "updated_at"])
