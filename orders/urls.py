from django.urls import path

from orders.views import (
    cart_add,
    cart_view,
    daily_tasks,
    dashboard,
    export_csv,
    kitchen,
    manage_orders,
    menu_view,
    order_cancel,
    order_detail,
    orders_collection,
    reorder,
    set_status,
    shop_settings,
)

urlpatterns = [
    path("menu/", menu_view, name="menu"),
    path("panier/ajouter/", cart_add, name="cart_add"),
    path("panier/", cart_view, name="cart"),
    path("commandes/", orders_collection, name="orders"),
    path("commandes/<int:order_id>/", order_detail, name="order_detail"),
    path("commandes/<int:order_id>/annuler/", order_cancel, name="order_cancel"),
    path("commandes/<int:order_id>/recommander/", reorder, name="reorder"),
    path("gestion/commandes/", manage_orders, name="manage_orders"),
    path("gestion/commandes/<int:order_id>/statut/", set_status, name="set_status"),
    path("gestion/cuisine/", kitchen, name="kitchen"),
    path("gestion/tableau-de-bord/", dashboard, name="dashboard"),
    path("gestion/tableau-de-bord/export.csv", export_csv, name="export_csv"),
    path("gestion/reglages/", shop_settings, name="shop_settings"),
    path("taches/quotidiennes/", daily_tasks, name="daily_tasks"),
]
