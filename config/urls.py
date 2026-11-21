from django.contrib import admin
from django.http import FileResponse, HttpResponse
from django.urls import include, path

admin.site.site_header = "Maison Mourida"
admin.site.site_title = "Maison Mourida"
admin.site.index_title = "Maintenance"


def health(request):
    return HttpResponse("ok")


def service_worker(request):
    from django.conf import settings

    path_file = settings.BASE_DIR / "static" / "sw.js"
    return FileResponse(path_file.open("rb"), content_type="application/javascript")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("sante/", health, name="health"),
    path("sw.js", service_worker, name="service_worker"),
    path("", include("accounts.urls")),
    path("", include("catalog.urls")),
    path("", include("orders.urls")),
    path("", include("payments.urls")),
    path("", include("subscriptions.urls")),
]

handler403 = "accounts.views.forbidden"
handler404 = "accounts.views.missing"
