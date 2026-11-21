import hashlib
import io
import re
from functools import wraps
from urllib.parse import quote
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import models
from PIL import Image


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


PHONE_RE = re.compile(r"7\d{8}")


def normalize_phone(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("221") and len(digits) == 12:
        digits = digits[3:]
    return digits


def valid_phone(value):
    return bool(PHONE_RE.fullmatch(normalize_phone(value)))


def content_type_for(name):
    lowered = str(name).lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def parse_image(upload, max_bytes=5 * 1024 * 1024):
    data = upload.read()
    if hasattr(upload, "seek"):
        upload.seek(0)
    if len(data) > max_bytes:
        raise ValidationError("Fichier trop lourd (5 Mo maximum).")
    digest = hashlib.sha256(data).hexdigest()
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = (probe.format or "").upper()
        probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Ce fichier n'est pas une image lisible.") from exc
    if fmt not in {"JPEG", "PNG", "WEBP"}:
        raise ValidationError("Formats acceptés : JPEG, PNG, WebP.")
    if image.width > 1600:
        height = max(1, round(image.height * 1600 / image.width))
        image = image.resize((1600, height), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    if fmt == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=82, optimize=True)
        ext = "jpg"
    elif fmt == "PNG":
        image.save(buffer, format="PNG", optimize=True)
        ext = "png"
    else:
        image.save(buffer, format="WEBP", quality=82)
        ext = "webp"
    return buffer.getvalue(), ext, digest


def stored_image(upload):
    content, ext, digest = parse_image(upload)
    return ContentFile(content, name=f"{uuid4().hex}.{ext}"), digest


def wa_link(number, text):
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    if len(digits) == 9 and digits.startswith("7"):
        digits = "221" + digits
    return f"https://wa.me/{digits}?text={quote(text)}"


def style_form(form):
    from django import forms

    for field in form.fields.values():
        if isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
            continue
        field.widget.attrs.setdefault("class", "input")
    return form


class BaseForm:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)


def vendor_required(view):
    from django.contrib.auth.decorators import login_required

    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if user.role != "vendeuse" and not user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def client_required(view):
    from django.contrib.auth.decorators import login_required

    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != "client":
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def error_text(exc):
    if hasattr(exc, "messages"):
        return " ".join(exc.messages)
    return str(exc)
