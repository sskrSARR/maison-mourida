from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from catalog.forms import DishForm, MenuForm, MenuItemForm
from catalog.models import Item, Menu, MenuItem
from shopkit import content_type_for, stored_image, vendor_required


def _save_dish(form, upload):
    item = form.save(commit=False)
    if upload:
        content, _digest = stored_image(upload)
        item.photo.save(content.name, content, save=False)
    item.save()
    return item


@vendor_required
def dish_list(request):
    return render(request, "catalog/dishes.html", {"items": Item.objects.all()})


@vendor_required
def dish_create(request):
    form = DishForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        _save_dish(form, request.FILES.get("photo"))
        messages.success(request, "Plat enregistré.")
        return redirect("dishes")
    return render(request, "catalog/dish_form.html", {"form": form, "item": None})


@vendor_required
def dish_edit(request, item_id):
    item = get_object_or_404(Item, pk=item_id)
    form = DishForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == "POST" and form.is_valid():
        _save_dish(form, request.FILES.get("photo"))
        messages.success(request, "Plat enregistré.")
        return redirect("dishes")
    return render(request, "catalog/dish_form.html", {"form": form, "item": item})


@login_required
def dish_photo(request, item_id):
    item = get_object_or_404(Item, pk=item_id)
    if not item.photo:
        raise Http404
    return FileResponse(item.photo.open("rb"), content_type=content_type_for(item.photo.name))


@vendor_required
def menu_list(request):
    return render(request, "catalog/menus.html", {"menus": Menu.objects.all()})


@vendor_required
def menu_create(request):
    form = MenuForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        menu = form.save()
        messages.success(request, "Menu créé.")
        return redirect("menu_detail", menu.id)
    return render(request, "catalog/menu_form.html", {"form": form})


@vendor_required
def menu_detail(request, menu_id):
    menu = get_object_or_404(Menu, pk=menu_id)
    edit_form = MenuForm(instance=menu)
    item_form = MenuItemForm(menu=menu)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            edit_form = MenuForm(request.POST, instance=menu)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Menu enregistré.")
                return redirect("menu_detail", menu.id)
        elif action == "add":
            item_form = MenuItemForm(request.POST, menu=menu)
            if item_form.is_valid():
                _menu_item, created = item_form.save()
                if created:
                    messages.success(request, "Plat ajouté.")
                else:
                    messages.error(request, "Ce plat est déjà au menu ce jour-là.")
                return redirect("menu_detail", menu.id)
        else:
            _menu_action(request, menu, action)
            return redirect("menu_detail", menu.id)
    items = menu.items.select_related("item").order_by("service_date", "item__category", "item__name")
    return render(
        request,
        "catalog/menu_detail.html",
        {"menu": menu, "items": items, "edit_form": edit_form, "item_form": item_form},
    )


def _menu_action(request, menu, action):
    try:
        with transaction.atomic():
            if action == "publish":
                if menu.status == "clos":
                    messages.error(request, "Ce menu est clos.")
                    return
                if not menu.items.exists():
                    messages.error(request, "Ajoutez au moins un plat.")
                    return
                menu.status = "publie"
                menu.save(update_fields=["status", "updated_at"])
                messages.success(request, "Menu publié.")
            elif action == "close":
                menu.status = "clos"
                menu.save(update_fields=["status", "updated_at"])
                messages.success(request, "Menu clos.")
            elif action == "stock":
                menu_item = get_object_or_404(MenuItem, pk=request.POST.get("menu_item"), menu=menu)
                qty = int(request.POST.get("remaining", ""))
                if qty < 0:
                    raise ValueError
                menu_item.remaining_quantity = qty
                if qty > menu_item.max_quantity:
                    menu_item.max_quantity = qty
                menu_item.save(update_fields=["remaining_quantity", "max_quantity", "updated_at"])
                messages.success(request, "Stock mis à jour.")
            elif action == "remove":
                menu_item = get_object_or_404(MenuItem, pk=request.POST.get("menu_item"), menu=menu)
                menu_item.delete()
                messages.success(request, "Retiré du menu.")
    except ProtectedError:
        messages.error(request, "Ce plat a déjà été commandé.")
    except Http404:
        raise
    except (TypeError, ValueError):
        messages.error(request, "Quantité invalide.")
