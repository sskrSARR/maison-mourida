from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from shopkit import TimeStamped, normalize_phone


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Téléphone requis")
        extra_fields.setdefault("is_active", True)
        user = self.model(phone=normalize_phone(phone), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "vendeuse")
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField("téléphone", max_length=15, unique=True)
    name = models.CharField("nom", max_length=120)
    email = models.EmailField("email", blank=True)
    role = models.CharField(
        "rôle",
        max_length=20,
        choices=[("client", "Client"), ("vendeuse", "Vendeuse")],
        default="client",
    )
    default_address = models.CharField("adresse", max_length=255, blank=True)
    allergy_note = models.TextField("précision allergie", blank=True)
    allergies = models.ManyToManyField("Allergy", blank=True, related_name="users", db_table="users_allergies")
    is_active = models.BooleanField("actif", default=True)
    is_staff = models.BooleanField("accès administration", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]
    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "utilisateur"

    def __str__(self):
        return f"{self.name} ({self.phone})"


class Allergy(TimeStamped):
    label = models.CharField("libellé", max_length=80, unique=True)

    class Meta:
        db_table = "allergies"
        ordering = ["label"]
        verbose_name = "allergie"

    def __str__(self):
        return self.label
