from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render

from accounts.forms import LoginForm, ProfileForm
from accounts.models import User


def home(request):
    if request.user.is_authenticated and (request.user.role == "vendeuse" or request.user.is_superuser):
        return redirect("dashboard")
    return redirect("menu")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"]
        failures = cache.get(f"loginfail:{phone}", 0)
        if failures >= 8:
            form.add_error(None, "Trop de tentatives. Réessayez dans quelques minutes.")
        else:
            user = authenticate(request, username=phone, password=form.cleaned_data["password"])
            if user is None or not user.is_active:
                cache.set(f"loginfail:{phone}", failures + 1, 900)
                form.add_error(None, "Téléphone ou mot de passe incorrect.")
            else:
                cache.delete(f"loginfail:{phone}")
                login(request, user)
                return redirect("home")
    return render(request, "accounts/login.html", {"form": form, "show_demo": settings.DEBUG})


def register_view(request):
    return redirect("menu")


def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("menu")


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save(request)
        messages.success(request, "Profil enregistré.")
        return redirect("profile")
    return render(request, "accounts/profile.html", {"form": form})


def forbidden(request, exception=None):
    return render(request, "403.html", status=403)


def missing(request, exception=None):
    return render(request, "404.html", status=404)
