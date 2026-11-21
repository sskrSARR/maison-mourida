from django.db import models

from shopkit import TimeStamped


class Payment(TimeStamped):
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    operator = models.CharField(
        "opérateur",
        max_length=20,
        choices=[("wave", "Wave"), ("orange_money", "Orange Money")],
    )
    declared_amount = models.PositiveIntegerField("montant déclaré")
    proof = models.FileField("preuve", upload_to="preuves/")
    file_hash = models.CharField(max_length=64, db_index=True)
    reference = models.CharField("référence de transaction", max_length=80, blank=True)
    status = models.CharField(
        "statut",
        max_length=20,
        choices=[("en_attente", "En attente"), ("valide", "Validé"), ("rejete", "Rejeté")],
        default="en_attente",
    )
    reject_reason = models.CharField("motif de rejet", max_length=255, blank=True)
    validated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="validated_payments",
    )
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]
        verbose_name = "paiement"

    def __str__(self):
        return f"{self.order} · {self.get_operator_display()}"
