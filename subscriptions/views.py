from django.contrib import messages
from django.shortcuts import redirect, render


def plans_view(request):
    if request.method == "POST":
        messages.info(request, "Les abonnements ne sont pas encore ouverts.")
        return redirect("subscriptions")
    formulas = [
        ("Hebdomadaire", "15 000 F", "Plat du jour du lundi au vendredi, et un jus offert."),
        ("Mensuel", "60 000 F", "Plat du jour et un jus offert, sur le mois."),
        ("Jus local", "500 F", "Format 250 ml : bouye au lait, bouye fraise, cocktail ou ditakh."),
    ]
    return render(request, "subscriptions/list.html", {"formulas": formulas})
