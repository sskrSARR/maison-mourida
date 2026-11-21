from django.urls import path

from subscriptions.views import plans_view

urlpatterns = [
    path("abonnements/", plans_view, name="subscriptions"),
]
