from django.db import models

from catalog.constants import CATEGORIES, MENU_STATUS
from shopkit import TimeStamped


class Item(TimeStamped):
    name = models.CharField("nom", max_length=120)
    description = models.TextField("description", blank=True)
    category = models.CharField("catégorie", max_length=20, choices=CATEGORIES)
    price_fcfa = models.PositiveIntegerField("prix")
    photo = models.ImageField("photo", upload_to="plats/", blank=True)
    is_active = models.BooleanField("au catalogue", default=True)

    class Meta:
        db_table = "items"
        ordering = ["category", "name"]
        verbose_name = "plat"

    def __str__(self):
        return self.name


class Menu(TimeStamped):
    title = models.CharField("titre", max_length=140)
    start_date = models.DateField("début")
    end_date = models.DateField("fin")
    order_deadline = models.DateTimeField("date limite de commande")
    status = models.CharField("statut", max_length=20, choices=MENU_STATUS, default="brouillon")

    class Meta:
        db_table = "menus"
        ordering = ["-start_date"]
        verbose_name = "menu"

    def __str__(self):
        return self.title


class MenuItem(TimeStamped):
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="menu_items")
    service_date = models.DateField("jour")
    max_quantity = models.PositiveIntegerField("quantité maximale")
    remaining_quantity = models.PositiveIntegerField("quantité restante")
    day_price = models.PositiveIntegerField("prix du jour", null=True, blank=True)

    class Meta:
        db_table = "menu_items"
        ordering = ["service_date", "item__name"]
        constraints = [
            models.UniqueConstraint(fields=["menu", "item", "service_date"], name="unique_menu_item_day"),
            models.CheckConstraint(check=models.Q(remaining_quantity__gte=0), name="remaining_non_negative"),
        ]

    def __str__(self):
        return f"{self.item.name} · {self.service_date}"

    @property
    def unit_price(self):
        if self.day_price is not None:
            return self.day_price
        return self.item.price_fcfa
