from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.forms import AdminUserChangeForm, AdminUserCreationForm
from accounts.models import Allergy, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    model = User
    ordering = ("phone",)
    list_display = ("phone", "name", "role", "is_staff", "is_active")
    search_fields = ("phone", "name")
    list_filter = ("role", "is_staff")
    filter_horizontal = ("allergies", "groups", "user_permissions")
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Profil", {"fields": ("name", "email", "role", "default_address", "allergy_note", "allergies")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "name", "role", "password1", "password2")}),
    )


@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    search_fields = ("label",)
