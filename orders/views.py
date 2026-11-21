import csv
import json
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Case, F, IntegerField, Sum, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Allergy
from catalog.models import MenuItem
from orders.cart import add_to_cart, clear_cart, resolve_cart
from orders.constants import (
    CLIENT_CAN_CANCEL,
    PAID_STATUSES,
    SLOTS,
    STATUS_LABELS,
    STATUS_MESSAGES,
    VENDOR_BUTTONS,
    VENDOR_STATUS_MESSAGES,
    message_for,
)
from orders.models import Order, OrderLine, ShopSettings
from orders.services import (
    change_status,
    create_order,
    expire_unpaid,
    get_order_for,
    guest_from_checkout,
    order_queryset,
    save_preferences,
    user_pref_map,
)
from shopkit import client_required, error_text, vendor_required, wa_link

REMEMBER_COOKIE = "mourida"
REMEMBER_DAYS = 180


def _memory(request):
    raw = request.COOKIES.get(REMEMBER_COOKIE, "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _remember(response, data):
    response.set_cookie(
        REMEMBER_COOKIE,
        json.dumps(data),
        max_age=REMEMBER_DAYS * 24 * 3600,
        httponly=True,
        samesite="Lax",
    )


def _forget(response):
    response.delete_cookie(REMEMBER_COOKIE)


def _apply_details(user, post):
    ids = [int(value) for value in post.getlist("allergies") if str(value).isdigit()]
    user.allergies.set(Allergy.objects.filter(pk__in=ids))
    user.allergy_note = (post.get("allergy_note") or "").strip()[:300]
    user.default_address = (post.get("adresse") or "").strip()[:255]
    name = (post.get("nom") or "").strip()
    fields = ["allergy_note", "default_address", "updated_at"]
    if name and not user.has_usable_password():
        user.name = name[:120]
        fields.append("name")
    user.save(update_fields=fields)


def _safe_next(request, default):
    nxt = request.POST.get("next") or default
    if not isinstance(nxt, str) or not nxt.startswith("/") or nxt.startswith("//"):
        return default
    return nxt


def _prefs_from_post(request, fallback):
    return {
        "piment": request.POST.get("piment") or fallback.get("piment", "aucun"),
        "ketchup": request.POST.get("ketchup") == "on",
        "mayonnaise": request.POST.get("mayonnaise") == "on",
        "sans_oignon": request.POST.get("sans_oignon") == "on",
    }


def menu_view(request):
    today = timezone.localdate()
    category_order = Case(
        When(item__category="plat", then=0),
        When(item__category="jus", then=1),
        When(item__category="dessert", then=2),
        default=9,
        output_field=IntegerField(),
    )
    items = list(
        MenuItem.objects.filter(menu__status="publie", menu__end_date__gte=today, service_date__gte=today)
        .select_related("item", "menu")
        .order_by("service_date", category_order, "item__name")
    )
    days = []
    juices = []
    seen_juices = set()
    titles = []
    for menu_item in items:
        if menu_item.menu.title not in titles:
            titles.append(menu_item.menu.title)
        if menu_item.item.category == "jus":
            if menu_item.item_id in seen_juices:
                continue
            seen_juices.add(menu_item.item_id)
            juices.append(menu_item)
            continue
        if not days or days[-1]["date"] != menu_item.service_date:
            days.append({"date": menu_item.service_date, "items": []})
        days[-1]["items"].append(menu_item)
    deadline = min((menu_item.menu.order_deadline for menu_item in items), default=None)
    heading = titles[0] if len(titles) == 1 else ("Menus publiés" if titles else "Menu")
    return render(
        request,
        "catalog/menu.html",
        {
            "days": days,
            "juices": juices,
            "deadline": deadline,
            "heading": heading,
            "now": timezone.now(),
        },
    )


@require_POST
def cart_add(request):
    try:
        menu_item = get_object_or_404(MenuItem.objects.select_related("item", "menu"), pk=request.POST.get("menu_item"))
        qty = int(request.POST.get("qty", "1"))
        add_to_cart(request, menu_item, qty, mode=request.POST.get("mode") or "add")
    except (TypeError, ValueError):
        messages.error(request, "Quantité invalide.")
    except ValidationError as exc:
        messages.error(request, error_text(exc))
    else:
        if request.POST.get("mode") == "set":
            messages.success(request, "Panier mis à jour.")
        else:
            messages.success(request, f"{menu_item.item.name} ajouté au panier.")
    return redirect(_safe_next(request, "/menu/"))


@require_http_methods(["GET", "POST"])
def cart_view(request):
    if request.method == "POST" and request.POST.get("action") == "vider":
        clear_cart(request)
        return redirect("cart")
    _cart, lines, day, adjusted = resolve_cart(request)
    if adjusted and lines:
        messages.info(request, "Le panier a été ajusté au stock.")
    elif adjusted and not lines:
        messages.info(request, "Le panier a été vidé : ces plats ne sont plus disponibles.")
    shop = ShopSettings.load()
    subtotal = sum(line["price"] * line["qty"] for line in lines)
    signed_in = request.user.is_authenticated and request.user.role == "client"
    memory = {} if signed_in else _memory(request)
    prefs = user_pref_map(request.user) if signed_in else memory
    if signed_in:
        selected = set(request.user.allergies.values_list("pk", flat=True))
        name = request.user.name
        phone = request.user.phone
        address = request.user.default_address
        allergy_note = request.user.allergy_note
    else:
        selected = {int(value) for value in memory.get("allergies", []) if str(value).isdigit()}
        name = memory.get("nom", "")
        phone = memory.get("telephone", "")
        address = memory.get("adresse", "")
        allergy_note = memory.get("allergy_note", "")
    return render(
        request,
        "orders/cart.html",
        {
            "lines": lines,
            "day": day,
            "shop": shop,
            "subtotal": subtotal,
            "total": subtotal + (shop.delivery_fee if lines else 0),
            "slots": SLOTS,
            "piment": prefs.get("piment", "aucun"),
            "ketchup": prefs.get("ketchup") == "oui",
            "mayonnaise": prefs.get("mayonnaise") == "oui",
            "sans_oignon": prefs.get("sans_oignon") == "oui",
            "address": address,
            "client_name": name,
            "client_phone": phone,
            "allergy_note": allergy_note,
            "allergies": Allergy.objects.order_by("label"),
            "selected_allergies": selected,
            "remembered": bool(memory),
            "signed_in": signed_in,
        },
    )


@require_http_methods(["GET", "POST"])
def orders_collection(request):
    if request.method == "POST":
        return _create(request)
    if not request.user.is_authenticated:
        return redirect("menu")
    if request.user.role == "vendeuse" or request.user.is_superuser:
        return redirect("manage_orders")
    orders = get_order_for_list(request.user)
    return render(request, "orders/list.html", {"orders": orders})


def get_order_for_list(user):
    from orders.services import order_queryset

    return order_queryset().filter(client=user)


def _remember_guest(request, order):
    if request.user.is_authenticated:
        return
    guest_orders = request.session.get("guest_orders", [])
    if order.id not in guest_orders:
        guest_orders.append(order.id)
    request.session["guest_orders"] = guest_orders
    request.session.modified = True


def visible_order(request, order_id):
    if request.user.is_authenticated:
        return get_order_for(request.user, order_id)
    if order_id not in request.session.get("guest_orders", []):
        raise PermissionDenied
    return get_object_or_404(order_queryset(), pk=order_id)


def _create(request):
    signed_in = request.user.is_authenticated
    if signed_in and request.user.role != "client":
        raise PermissionDenied
    if signed_in:
        buyer = request.user
    else:
        try:
            buyer = guest_from_checkout(request.POST.get("nom", ""), request.POST.get("telephone", ""))
        except ValidationError as exc:
            messages.error(request, error_text(exc))
            return redirect("cart")
    _cart, lines, _day, _adjusted = resolve_cart(request)
    prefs = _prefs_from_post(request, user_pref_map(request.user) if signed_in else {})
    if prefs["piment"] not in {"aucun", "doux", "fort"}:
        prefs["piment"] = "aucun"
    try:
        _apply_details(buyer, request.POST)
        order = create_order(
            buyer,
            [{"menu_item_id": line["menu_item"].id, "qty": line["qty"]} for line in lines],
            request.POST.get("adresse", ""),
            request.POST.get("creneau", ""),
            request.POST.get("note", ""),
            prefs,
        )
    except ValidationError as exc:
        messages.error(request, error_text(exc))
        return redirect("cart")
    if signed_in and request.POST.get("souvenir"):
        save_preferences(user=request.user, data=prefs)
    _remember_guest(request, order)
    clear_cart(request)
    messages.success(request, f"Commande {order} enregistrée.")
    response = redirect("order_detail", order.id)
    if request.POST.get("souvenir"):
        _remember(
            response,
            {
                "nom": (request.POST.get("nom") or buyer.name).strip(),
                "telephone": buyer.phone,
                "adresse": order.address,
                "allergies": [str(pk) for pk in buyer.allergies.values_list("pk", flat=True)],
                "allergy_note": buyer.allergy_note,
                "piment": prefs["piment"],
                "ketchup": "oui" if prefs["ketchup"] else "non",
                "mayonnaise": "oui" if prefs["mayonnaise"] else "non",
                "sans_oignon": "oui" if prefs["sans_oignon"] else "non",
            },
        )
    else:
        _forget(response)
    return response


def order_detail(request, order_id):
    order = visible_order(request, order_id)
    shop = ShopSettings.load()
    whatsapp = ""
    if shop.whatsapp_number:
        whatsapp = wa_link(shop.whatsapp_number, message_for(order, order.status))
    is_vendor = request.user.is_authenticated and (request.user.role == "vendeuse" or request.user.is_superuser)
    messages_by_status = VENDOR_STATUS_MESSAGES if is_vendor else STATUS_MESSAGES
    return render(
        request,
        "orders/detail.html",
        {
            "order": order,
            "shop": shop,
            "whatsapp": whatsapp,
            "status_message": messages_by_status.get(order.status, ""),
            "vendor_buttons": VENDOR_BUTTONS.get(order.status, []),
            "is_vendor": is_vendor,
            "can_cancel": not is_vendor and order.status in CLIENT_CAN_CANCEL,
        },
    )


@require_POST
def order_cancel(request, order_id):
    order = visible_order(request, order_id)
    try:
        author = request.user if request.user.is_authenticated else order.client
        change_status(order, "annulee", author, note=request.POST.get("note", ""))
    except ValidationError as exc:
        messages.error(request, error_text(exc))
    else:
        messages.success(request, "Commande annulée.")
    return redirect("order_detail", order.id)


@client_required
@require_POST
def reorder(request, order_id):
    order = get_order_for(request.user, order_id)
    item_ids = [line.menu_item.item_id for line in order.lines.all()]
    today = timezone.localdate()
    candidates = (
        MenuItem.objects.filter(
            item_id__in=item_ids,
            menu__status="publie",
            service_date__gte=today,
            menu__order_deadline__gt=timezone.now(),
            remaining_quantity__gt=0,
        )
        .select_related("item")
        .order_by("service_date")
    )
    by_day = {}
    for menu_item in candidates:
        by_day.setdefault(menu_item.service_date, {})[menu_item.item_id] = menu_item
    best_map = {}
    best_day = None
    for day, mapping in by_day.items():
        if len(mapping) > len(best_map):
            best_map = mapping
            best_day = day
    if not best_map:
        messages.error(request, "Ces plats ne sont pas au menu en ce moment.")
        return redirect("order_detail", order.id)
    clear_cart(request)
    skipped = []
    for line in order.lines.all():
        menu_item = best_map.get(line.menu_item.item_id)
        if menu_item is None:
            skipped.append(line.menu_item.item.name)
            continue
        add_to_cart(request, menu_item, min(line.quantity, menu_item.remaining_quantity, 20), mode="set")
    if skipped:
        messages.info(request, "Pas au menu ce jour-là : " + ", ".join(skipped) + ".")
    messages.success(request, f"Panier prêt pour le {best_day:%d/%m}.")
    return redirect("cart")


@vendor_required
def manage_orders(request):
    from orders.services import order_queryset

    orders = order_queryset()
    day = request.GET.get("date") or ""
    status = request.GET.get("statut") or ""
    query = (request.GET.get("q") or "").strip()
    if day:
        orders = orders.filter(delivery_date=day)
    if status:
        orders = orders.filter(status=status)
    if query:
        orders = orders.filter(client__name__icontains=query) | orders.filter(client__phone__icontains=query)
    return render(
        request,
        "orders/manage_list.html",
        {
            "orders": orders[:200],
            "filters": {"date": day, "statut": status, "q": query},
            "statuses": STATUS_LABELS,
        },
    )


@vendor_required
@require_POST
def set_status(request, order_id):
    order = get_order_for(request.user, order_id)
    try:
        change_status(order, request.POST.get("statut", ""), request.user, note=request.POST.get("note", ""))
    except ValidationError as exc:
        messages.error(request, error_text(exc))
    else:
        messages.success(request, "Statut mis à jour.")
    return redirect("order_detail", order.id)


@vendor_required
def kitchen(request):
    from orders.services import order_queryset

    raw = request.GET.get("date")
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date() if raw else timezone.localdate()
    except ValueError:
        day = timezone.localdate()
    orders = (
        order_queryset()
        .filter(delivery_date=day, status__in=PAID_STATUSES)
        .order_by("slot", "client__name")
    )
    totals = (
        OrderLine.objects.filter(order__in=orders)
        .values("menu_item__item__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")
    )
    pending = Order.objects.filter(delivery_date=day, status="paiement_a_verifier").count()
    return render(
        request,
        "orders/kitchen.html",
        {"day": day, "prev": day - timedelta(days=1), "next": day + timedelta(days=1), "orders": orders, "totals": totals, "pending": pending},
    )


def _bounds(day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timedelta(days=1)


def _revenue(start, end):
    total = Order.objects.filter(status__in=PAID_STATUSES, paid_at__gte=start, paid_at__lt=end).aggregate(
        value=Coalesce(Sum("total"), 0)
    )
    return total["value"]


@vendor_required
def dashboard(request):
    today = timezone.localdate()
    day_start, day_end = _bounds(today)
    week_start, _week_end = _bounds(today - timedelta(days=today.weekday()))
    month_start, _month_end = _bounds(today.replace(day=1))
    next_month_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    next_month, _after = _bounds(next_month_day)
    top = (
        OrderLine.objects.filter(order__status__in=PAID_STATUSES, order__paid_at__gte=month_start, order__paid_at__lt=next_month)
        .values("menu_item__item__name")
        .annotate(qty=Sum("quantity"), amount=Sum(F("quantity") * F("unit_price")))
        .order_by("-qty")[:5]
    )
    return render(
        request,
        "orders/dashboard.html",
        {
            "today": today,
            "revenue_today": _revenue(day_start, day_end),
            "revenue_week": _revenue(week_start, day_end),
            "revenue_month": _revenue(month_start, next_month),
            "top": top,
            "unpaid": Order.objects.filter(status="en_attente_paiement").count(),
            "to_check": Order.objects.filter(status="paiement_a_verifier").count(),
            "alerts": request.user.notifications.all()[:8],
        },
    )


@vendor_required
def export_csv(request):
    from orders.services import order_queryset

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="commandes.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        ["Référence", "Créée le", "Livraison", "Créneau", "Client", "Téléphone", "Adresse", "Total", "Statut", "Paiement", "Allergies", "Préférences", "Note"]
    )
    for order in order_queryset().order_by("-created_at"):
        allergies = ", ".join(allergy.label for allergy in order.allergies.all())
        if order.allergy_note:
            allergies = f"{allergies} — {order.allergy_note}".strip(" —")
        writer.writerow(
            [
                str(order),
                timezone.localtime(order.created_at).strftime("%Y-%m-%d %H:%M"),
                order.delivery_date.isoformat(),
                order.slot_label,
                order.client.name,
                order.client.phone,
                order.address,
                order.total,
                STATUS_LABELS.get(order.status, order.status),
                order.payment_status,
                allergies,
                order.preference_phrase,
                order.note,
            ]
        )
    return response


@vendor_required
@require_http_methods(["GET", "POST"])
def shop_settings(request):
    shop = ShopSettings.load()
    if request.method == "POST":
        shop.wave_number = request.POST.get("wave_number", "").strip()
        shop.om_number = request.POST.get("om_number", "").strip()
        shop.beneficiary_name = request.POST.get("beneficiary_name", "").strip()
        shop.whatsapp_number = request.POST.get("whatsapp_number", "").strip()
        try:
            shop.delivery_fee = max(0, int(request.POST.get("delivery_fee") or 0))
            shop.unpaid_timeout_hours = max(1, int(request.POST.get("unpaid_timeout_hours") or 2))
        except ValueError:
            messages.error(request, "Montant ou délai invalide.")
            return redirect("shop_settings")
        shop.save()
        messages.success(request, "Réglages enregistrés.")
        return redirect("shop_settings")
    return render(request, "orders/settings.html", {"shop": shop})


@csrf_exempt
@require_POST
def daily_tasks(request):
    from subscriptions.services import expire_subscriptions, generate_due_orders

    token = request.headers.get("X-Task-Token", "")
    if not settings.TASK_TOKEN or token != settings.TASK_TOKEN:
        return JsonResponse({"detail": "interdit"}, status=403)
    return JsonResponse(
        {
            "commandes_expirees": expire_unpaid(),
            "abonnements_generes": generate_due_orders(),
            "abonnements_echus": expire_subscriptions(),
        }
    )
