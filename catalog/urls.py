from django.urls import path

from catalog.views import dish_create, dish_edit, dish_list, dish_photo, menu_create, menu_detail, menu_list

urlpatterns = [
    path("plats/<int:item_id>/photo/", dish_photo, name="dish_photo"),
    path("gestion/plats/", dish_list, name="dishes"),
    path("gestion/plats/nouveau/", dish_create, name="dish_create"),
    path("gestion/plats/<int:item_id>/", dish_edit, name="dish_edit"),
    path("gestion/menus/", menu_list, name="menus"),
    path("gestion/menus/nouveau/", menu_create, name="menu_create"),
    path("gestion/menus/<int:menu_id>/", menu_detail, name="menu_detail"),
]
