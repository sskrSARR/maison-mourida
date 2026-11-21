from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from accounts.models import Allergy, User
from orders.constants import PIMENT_CHOICES
from shopkit import BaseForm, normalize_phone, valid_phone


class AdminUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("phone", "name", "role")


class AdminUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class LoginForm(BaseForm, forms.Form):
    phone = forms.CharField(label="Téléphone")
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not valid_phone(phone):
            raise forms.ValidationError("Indiquez un numéro sénégalais à 9 chiffres, par exemple 77 123 45 67.")
        return phone


class RegisterForm(LoginForm):
    field_order = ["name", "phone", "password", "default_address"]
    name = forms.CharField(label="Nom", max_length=120)
    default_address = forms.CharField(label="Adresse de livraison", required=False)

    def __init__(self, *args, **kwargs):
        self.existing = None
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if len(password) < 6:
            raise forms.ValidationError("6 caractères minimum.")
        return password

    def clean_phone(self):
        phone = super().clean_phone()
        existing = User.objects.filter(phone=phone).first()
        if existing and existing.has_usable_password():
            raise forms.ValidationError("Ce numéro a déjà un compte. Connectez-vous.")
        self.existing = existing
        return phone


class ProfileForm(BaseForm, forms.Form):
    name = forms.CharField(label="Nom", max_length=120)
    email = forms.EmailField(label="Email", required=False)
    default_address = forms.CharField(label="Adresse de livraison", required=False)
    allergies = forms.ModelMultipleChoiceField(
        label="Allergies",
        queryset=Allergy.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="La cuisine les verra sur chaque commande.",
    )
    allergy_note = forms.CharField(
        label="Autre allergie ou précision",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    piment = forms.ChoiceField(label="Piment", choices=PIMENT_CHOICES, widget=forms.RadioSelect)
    ketchup = forms.BooleanField(label="Ketchup", required=False)
    mayonnaise = forms.BooleanField(label="Mayonnaise", required=False)
    sans_oignon = forms.BooleanField(label="Sans oignon", required=False)
    password1 = forms.CharField(label="Nouveau mot de passe", required=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmation", required=False, widget=forms.PasswordInput)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        from orders.services import user_pref_map

        prefs = user_pref_map(user)
        kwargs.setdefault("initial", {})
        kwargs["initial"].update(
            {
                "name": user.name,
                "email": user.email,
                "default_address": user.default_address,
                "allergy_note": user.allergy_note,
                "allergies": list(user.allergies.values_list("pk", flat=True)),
                "piment": prefs.get("piment", "aucun"),
                "ketchup": prefs.get("ketchup") == "oui",
                "mayonnaise": prefs.get("mayonnaise") == "oui",
                "sans_oignon": prefs.get("sans_oignon") == "oui",
            }
        )
        super().__init__(*args, **kwargs)
        self.fields["allergies"].queryset = Allergy.objects.order_by("label")

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password or cleaned.get("password2"):
            if password != cleaned.get("password2"):
                self.add_error("password2", "Les mots de passe diffèrent.")
            elif password:
                password_validation.validate_password(password, self.user)
        return cleaned

    def save(self, request):
        data = self.cleaned_data
        user = self.user
        user.name = data["name"]
        user.email = data["email"]
        user.default_address = data["default_address"]
        user.allergy_note = data["allergy_note"]
        if data["password1"]:
            user.set_password(data["password1"])
        user.save()
        user.allergies.set(data["allergies"])
        from orders.services import save_preferences

        save_preferences(user=user, data=data)
        if data["password1"]:
            from django.contrib.auth import update_session_auth_hash

            update_session_auth_hash(request, user)
        return user
