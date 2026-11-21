from django.contrib import admin

from orders.models import Order, OrderLine, OrderStatusHistory, Preference, ShopSettings


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "delivery_date", "status", "total")
    list_filter = ("status", "delivery_date")
    search_fields = ("client__name", "client__phone")
    inlines = [OrderLineInline]


admin.site.register(OrderStatusHistory)
admin.site.register(Preference)
admin.site.register(ShopSettings)
