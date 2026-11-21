from django.contrib import admin

from catalog.models import Item, Menu, MenuItem


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price_fcfa", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ("title", "start_date", "end_date", "status")
    inlines = [MenuItemInline]


admin.site.register(MenuItem)
