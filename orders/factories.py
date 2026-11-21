from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from catalog.models import Item, Menu, MenuItem
from orders.models import ShopSettings


def make_client(phone="771111111", name="Awa"):
    return User.objects.create_user(phone, "secret", name=name, role="client", default_address="Plateau, Dakar")


def make_vendor(phone="772222222"):
    return User.objects.create_user(phone, "secret", name="Cuisine", role="vendeuse")


def make_dish(name="Yassa poulet", price=2000, category="plat"):
    return Item.objects.create(name=name, description="Oignon et citron.", category=category, price_fcfa=price)


def make_menu_item(item=None, qty=1, day=None):
    item = item or make_dish()
    day = day or timezone.localdate()
    menu = Menu.objects.create(
        title="Menu test",
        start_date=day,
        end_date=day,
        order_deadline=timezone.now() + timedelta(days=1),
        status="publie",
    )
    return MenuItem.objects.create(
        menu=menu,
        item=item,
        service_date=day,
        max_quantity=qty,
        remaining_quantity=qty,
    )


def make_shop():
    shop = ShopSettings.load()
    shop.delivery_fee = 500
    shop.wave_number = "770000099"
    shop.om_number = "780000099"
    shop.beneficiary_name = "Maison"
    shop.whatsapp_number = "221770000099"
    shop.unpaid_timeout_hours = 2
    shop.save()
    return shop
