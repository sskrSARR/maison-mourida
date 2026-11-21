from django.urls import path

from accounts.views import home, login_view, logout_view, profile_view, register_view

urlpatterns = [
    path("", home, name="home"),
    path("connexion/", login_view, name="login"),
    path("inscription/", register_view, name="register"),
    path("deconnexion/", logout_view, name="logout"),
    path("profil/", profile_view, name="profile"),
]
