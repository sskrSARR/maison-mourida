from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from orders.views import visible_order
from payments.models import Payment
from payments.services import reject_payment, submit_proof, validate_payment
from shopkit import content_type_for, error_text, vendor_required


@require_POST
def submit_payment(request, order_id):
    order = visible_order(request, order_id)
    actor = request.user if request.user.is_authenticated else order.client
    upload = request.FILES.get("preuve")
    if upload is None:
        messages.error(request, "Ajoutez la capture d'écran.")
        return redirect("order_detail", order.id)
    try:
        submit_proof(order, actor, upload, request.POST.get("operateur", ""), request.POST.get("reference", ""))
    except ValidationError as exc:
        messages.error(request, error_text(exc))
    else:
        messages.success(request, "Capture envoyée. Nous vérifions le paiement.")
    return redirect("order_detail", order.id)


def proof_file(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("order"), pk=payment_id)
    user = request.user
    if user.is_authenticated:
        if user.role != "vendeuse" and not user.is_superuser and payment.order.client_id != user.id:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
    elif payment.order_id not in request.session.get("guest_orders", []):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    return FileResponse(payment.proof.open("rb"), content_type=content_type_for(payment.proof.name))


@vendor_required
@require_POST
def validate_view(request, payment_id):
    try:
        payment = validate_payment(payment_id, request.user)
    except (ValidationError, Payment.DoesNotExist) as exc:
        messages.error(request, error_text(exc))
        return redirect("manage_orders")
    messages.success(request, "Paiement validé.")
    return redirect("order_detail", payment.order_id)


@vendor_required
@require_POST
def reject_view(request, payment_id):
    try:
        payment = reject_payment(payment_id, request.user, request.POST.get("motif", ""))
    except (ValidationError, Payment.DoesNotExist) as exc:
        messages.error(request, error_text(exc))
        return redirect("manage_orders")
    messages.success(request, "Paiement rejeté.")
    return redirect("order_detail", payment.order_id)
