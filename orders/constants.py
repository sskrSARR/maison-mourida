PAID_STATUSES = ["payee", "en_preparation", "prete", "en_livraison", "livree"]

STATUS_LABELS = {
    "en_attente_paiement": "En attente de paiement",
    "paiement_a_verifier": "Paiement à vérifier",
    "payee": "Payée",
    "en_preparation": "En préparation",
    "prete": "Prête",
    "en_livraison": "En livraison",
    "livree": "Livrée",
    "annulee": "Annulée",
}

STATUS_MESSAGES = {
    "en_attente_paiement": "Récapitulatif de votre commande. Payez avec la référence indiquée.",
    "paiement_a_verifier": "Nous vérifions votre paiement.",
    "payee": "Paiement confirmé.",
    "en_preparation": "Votre repas est en préparation.",
    "prete": "Votre commande est prête.",
    "en_livraison": "Votre commande est en route.",
    "livree": "Commande livrée.",
    "annulee": "Votre commande est annulée.",
}

VENDOR_STATUS_MESSAGES = {
    "en_attente_paiement": "Le client n'a pas encore envoyé sa capture.",
    "paiement_a_verifier": "Vérifiez le montant, l'opérateur et la référence.",
    "payee": "Paiement confirmé. La commande peut partir en cuisine.",
    "en_preparation": "En cuisine.",
    "prete": "Prête à partir.",
    "en_livraison": "En route vers le client.",
    "livree": "Livraison terminée.",
    "annulee": "Commande annulée.",
}

ALLOWED = {
    "en_attente_paiement": {"paiement_a_verifier", "annulee"},
    "paiement_a_verifier": {"payee", "en_attente_paiement"},
    "payee": {"en_preparation", "annulee"},
    "en_preparation": {"prete", "annulee"},
    "prete": {"en_livraison"},
    "en_livraison": {"livree"},
    "livree": set(),
    "annulee": set(),
}

VENDOR_BUTTONS = {
    "payee": [("en_preparation", "Passer en préparation"), ("annulee", "Annuler")],
    "en_preparation": [("prete", "Marquer prête"), ("annulee", "Annuler")],
    "prete": [("en_livraison", "Partir en livraison")],
    "en_livraison": [("livree", "Marquer livrée")],
}

CLIENT_CAN_CANCEL = {"en_attente_paiement", "paiement_a_verifier", "payee"}

SLOTS = [
    ("11:30-12:30", "11 h 30 – 12 h 30"),
    ("12:30-13:30", "12 h 30 – 13 h 30"),
    ("13:30-14:30", "13 h 30 – 14 h 30"),
]

SLOT_LABELS = dict(SLOTS)

PIMENT_CHOICES = [("aucun", "Aucun"), ("doux", "Doux"), ("fort", "Fort")]


def reference(order_or_id):
    pk = getattr(order_or_id, "pk", order_or_id)
    return f"CMD-{int(pk):04d}"


def message_for(order, status, note=""):
    text = f"{reference(order)} · {STATUS_MESSAGES.get(status, '')}"
    if note:
        text = f"{text} {note}"
    return text


def preferences_phrase(prefs):
    bits = []
    labels = {
        "ketchup": "ketchup",
        "mayonnaise": "mayonnaise",
        "sans_oignon": "sans oignon",
    }
    for pref in prefs:
        if pref.key == "piment" and pref.value in {"doux", "fort"}:
            bits.append(f"piment {pref.value}")
        elif pref.value == "oui":
            bits.append(labels.get(pref.key, pref.key))
    return " · ".join(bits)
