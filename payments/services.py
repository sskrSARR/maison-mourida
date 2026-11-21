from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from orders.constants import reference
from orders.models import Order
from orders.services import change_status, notify_vendors
from payments.models import Payment
from shopkit import stored_image


@transaction.atomic
def submit_proof(order, user, upload, operator, tx_reference=""):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.client_id != user.id:
        raise ValidationError("Cette commande ne vous appartient pas.")
    if order.status != "en_attente_paiement":
        raise ValidationError("Cette commande n'attend pas de paiement.")
    if operator not in {"wave", "orange_money"}:
        raise ValidationError("Choisissez Wave ou Orange Money.")
    if order.payments.filter(status="en_attente").exists():
        raise ValidationError("Une capture est déjà en cours de vérification.")
    content, digest = stored_image(upload)
    if Payment.objects.filter(file_hash=digest).exclude(order=order).exists():
        raise ValidationError("Cette capture a déjà été utilisée pour une autre commande.")
    payment = Payment(
        order=order,
        operator=operator,
        declared_amount=order.total,
        file_hash=digest,
        reference=(tx_reference or "").strip(),
        status="en_attente",
    )
    payment.proof.save(content.name, content, save=False)
    payment.save()
    change_status(order, "paiement_a_verifier", user)
    notify_vendors(f"{reference(order)} · nouvelle preuve de paiement à vérifier.")
    return payment


@transaction.atomic
def validate_payment(payment_id, vendor):
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status != "en_attente":
        raise ValidationError("Ce paiement a déjà été traité.")
    change_status(payment.order, "payee", vendor)
    payment.status = "valide"
    payment.validated_by = vendor
    payment.validated_at = timezone.now()
    payment.save()
    return payment


@transaction.atomic
def reject_payment(payment_id, vendor, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Indiquez un motif.")
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status != "en_attente":
        raise ValidationError("Ce paiement a déjà été traité.")
    payment.status = "rejete"
    payment.reject_reason = reason[:255]
    payment.validated_by = vendor
    payment.validated_at = timezone.now()
    payment.save()
    change_status(payment.order, "en_attente_paiement", vendor, note=reason)
    return payment
