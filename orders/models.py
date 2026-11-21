from django.db import models

from orders.constants import SLOT_LABELS, reference
from shopkit import TimeStamped


class ShopSettings(TimeStamped):
    wave_number = models.CharField("numéro Wave", max_length=20, blank=True)
    om_number = models.CharField("numéro Orange Money", max_length=20, blank=True)
    beneficiary_name = models.CharField("bénéficiaire", max_length=120, blank=True)
    whatsapp_number = models.CharField("WhatsApp", max_length=20, blank=True)
    delivery_fee = models.PositiveIntegerField("frais de livraison", default=0)
    unpaid_timeout_hours = models.PositiveIntegerField("délai de paiement (heures)", default=2)

    class Meta:
        db_table = "settings"
        verbose_name = "réglages"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Order(TimeStamped):
    client = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="orders")
    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    delivery_date = models.DateField("jour de livraison")
    slot = models.CharField("créneau", max_length=20)
    address = models.CharField("adresse", max_length=255)
    delivery_fee = models.PositiveIntegerField("frais de livraison", default=0)
    total = models.PositiveIntegerField("total")
    status = models.CharField("statut", max_length=32, default="en_attente_paiement")
    payment_status = models.CharField("paiement", max_length=32, default="en_attente")
    paid_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField("note", blank=True)
    allergy_note = models.TextField("précision allergie", blank=True)
    allergies = models.ManyToManyField(
        "accounts.Allergy",
        blank=True,
        related_name="orders",
        db_table="orders_allergies",
    )
    stock_restored = models.BooleanField(default=False)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["delivery_date", "status"]),
            models.Index(fields=["client", "created_at"]),
        ]
        verbose_name = "commande"

    def __str__(self):
        return reference(self.pk) if self.pk else "Commande"

    @property
    def slot_label(self):
        return SLOT_LABELS.get(self.slot, self.slot)

    @property
    def lines_total(self):
        return sum(line.quantity * line.unit_price for line in self.lines.all())

    @property
    def preference_phrase(self):
        from orders.constants import preferences_phrase

        return preferences_phrase(self.preferences.all())


class OrderLine(TimeStamped):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    menu_item = models.ForeignKey("catalog.MenuItem", on_delete=models.PROTECT, related_name="order_lines")
    quantity = models.PositiveIntegerField("quantité")
    unit_price = models.PositiveIntegerField("prix unitaire")

    class Meta:
        db_table = "order_lines"
        verbose_name = "ligne"

    def __str__(self):
        return f"{self.menu_item} × {self.quantity}"


class Preference(TimeStamped):
    user = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.CASCADE, related_name="preferences")
    key = models.CharField(max_length=40)
    value = models.CharField(max_length=40)

    class Meta:
        db_table = "preferences"
        verbose_name = "préférence"


class OrderStatusHistory(TimeStamped):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    old_status = models.CharField(max_length=32, blank=True)
    new_status = models.CharField(max_length=32)
    author = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="status_changes",
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "order_status_history"
        ordering = ["created_at"]
        verbose_name = "historique"
