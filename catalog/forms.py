from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from catalog.models import Item, Menu, MenuItem
from shopkit import BaseForm, parse_image


class DishForm(BaseForm, forms.ModelForm):
    class Meta:
        model = Item
        fields = ["name", "description", "category", "price_fcfa", "photo", "is_active"]

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if isinstance(photo, UploadedFile):
            parse_image(photo)
        return photo


class MenuForm(BaseForm, forms.ModelForm):
    order_deadline = forms.DateTimeField(
        label="Date limite de commande",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = Menu
        fields = ["title", "start_date", "end_date", "order_deadline"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_order_deadline(self):
        value = self.cleaned_data["order_deadline"]
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "La fin est avant le début.")
        return cleaned


class MenuItemForm(BaseForm, forms.Form):
    item = forms.ModelChoiceField(label="Plat", queryset=Item.objects.none())
    service_date = forms.DateField(label="Jour", widget=forms.DateInput(attrs={"type": "date"}))
    max_quantity = forms.IntegerField(label="Quantité maximale", min_value=1)
    day_price = forms.IntegerField(
        label="Prix du jour",
        required=False,
        min_value=0,
        help_text="Laisser vide pour garder le prix du catalogue.",
    )

    def __init__(self, *args, menu, **kwargs):
        self.menu = menu
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(is_active=True).order_by("category", "name")

    def clean_service_date(self):
        day = self.cleaned_data["service_date"]
        if not (self.menu.start_date <= day <= self.menu.end_date):
            raise forms.ValidationError("Le jour doit être dans les dates du menu.")
        return day

    def save(self):
        data = self.cleaned_data
        menu_item, created = MenuItem.objects.get_or_create(
            menu=self.menu,
            item=data["item"],
            service_date=data["service_date"],
            defaults={
                "max_quantity": data["max_quantity"],
                "remaining_quantity": data["max_quantity"],
                "day_price": data["day_price"],
            },
        )
        return menu_item, created
