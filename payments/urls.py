from django.urls import path

from payments.views import proof_file, reject_view, submit_payment, validate_view

urlpatterns = [
    path("commandes/<int:order_id>/paiement/", submit_payment, name="submit_payment"),
    path("paiements/<int:payment_id>/fichier/", proof_file, name="proof_file"),
    path("gestion/paiements/<int:payment_id>/valider/", validate_view, name="payment_validate"),
    path("gestion/paiements/<int:payment_id>/rejeter/", reject_view, name="payment_reject"),
]
