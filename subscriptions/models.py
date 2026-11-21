from django.db import models

from shopkit import TimeStamped


class Plan(TimeStamped):
    name = models.CharField("nom", max_length=80)
    frequency = models.CharField(
        "fréquence",
        max_length=20,
        choices=[("hebdomadaire", "Hebdomadaire"), ("mensuelle", "Mensuelle")],
    )
    price_fcfa = models.PositiveIntegerField("prix")
    description = models.TextField("contenu", blank=True)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        db_table = "subscription_plans"
        verbose_name = "formule"

    def __str__(self):
        return self.name


class Subscription(TimeStamped):
    client = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    start_date = models.DateField("début")
    end_date = models.DateField("fin")
    weekdays = models.CharField("jours", max_length=20)
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="subscriptions")
    replacement_item = models.ForeignKey(
        "catalog.Item",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replacement_subscriptions",
    )
    address = models.CharField("adresse", max_length=255)
    slot = models.CharField("créneau", max_length=20)
    piment = models.CharField("piment", max_length=10, default="aucun")
    ketchup = models.BooleanField(default=False)
    mayonnaise = models.BooleanField(default=False)
    sans_oignon = models.BooleanField(default=False)
    status = models.CharField(
        "statut",
        max_length=20,
        choices=[
            ("actif", "Actif"),
            ("pause", "En pause"),
            ("resilie", "Résilié"),
            ("expire", "Expiré"),
        ],
        default="actif",
    )

    class Meta:
        db_table = "subscriptions"
        verbose_name = "abonnement"

    def __str__(self):
        return f"{self.client} · {self.plan}"
