import io
import threading
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image

from orders.factories import make_client, make_dish, make_menu_item, make_shop, make_vendor
from orders.models import Order
from orders.services import change_status, create_order, expire_unpaid
from payments.services import reject_payment, submit_proof

User = get_user_model()


def png(color=(20, 40, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format="PNG")
    return buffer.getvalue()


def order_for(user, menu_item, qty=1):
    return create_order(
        user,
        [{"menu_item_id": menu_item.id, "qty": qty}],
        "Sacré-Cœur, Dakar",
        "12:30-13:30",
        "Sans trop de sel",
        {"piment": "fort", "ketchup": True, "mayonnaise": False, "sans_oignon": True},
    )


class OrderFlowTests(TestCase):
    def setUp(self):
        make_shop()
        self.client_user = make_client()
        self.other = make_client("771111112", "Moussa")
        self.vendor = make_vendor()
        self.menu_item = make_menu_item(qty=2)

    def test_stock_price_and_total(self):
        order = order_for(self.client_user, self.menu_item)
        self.menu_item.refresh_from_db()
        self.assertEqual(self.menu_item.remaining_quantity, 1)
        self.assertEqual(order.lines.get().unit_price, 2000)
        self.assertEqual(order.total, 2500)
        self.menu_item.item.price_fcfa = 9000
        self.menu_item.item.save()
        self.assertEqual(order.lines.get().unit_price, 2000)
        self.assertEqual(order.preferences.get(key="piment").value, "fort")
        self.assertIn("sans oignon", order.preference_phrase)

    def test_second_order_cannot_oversell(self):
        order_for(self.client_user, self.menu_item, qty=2)
        with self.assertRaises(ValidationError):
            order_for(self.other, self.menu_item, qty=1)
        self.menu_item.refresh_from_db()
        self.assertEqual(self.menu_item.remaining_quantity, 0)

    def test_cancel_restores_stock_until_preparation(self):
        order = order_for(self.client_user, self.menu_item)
        change_status(order, "annulee", self.client_user)
        self.menu_item.refresh_from_db()
        self.assertEqual(self.menu_item.remaining_quantity, 2)
        order = order_for(self.client_user, self.menu_item)
        change_status(order, "paiement_a_verifier", self.client_user)
        change_status(order, "payee", self.vendor)
        change_status(order, "en_preparation", self.vendor)
        with self.assertRaises(ValidationError):
            change_status(order, "annulee", self.client_user)
        change_status(order, "annulee", self.vendor, note="Client absent")
        order.refresh_from_db()
        self.assertEqual(order.status, "annulee")
        self.menu_item.refresh_from_db()
        self.assertEqual(self.menu_item.remaining_quantity, 2)

    def test_status_path_and_illegal_jump(self):
        order = order_for(self.client_user, self.menu_item)
        with self.assertRaises(ValidationError):
            change_status(order, "livree", self.vendor)
        for status in ("paiement_a_verifier", "payee", "en_preparation", "prete", "en_livraison", "livree"):
            author = self.client_user if status == "paiement_a_verifier" else self.vendor
            order = change_status(order, status, author)
        self.assertEqual(order.status, "livree")

    def test_unpaid_orders_expire(self):
        order = order_for(self.client_user, self.menu_item)
        fresh = order_for(self.other, self.menu_item)
        order.created_at = timezone.now() - timedelta(hours=5)
        order.save(update_fields=["created_at"])
        self.assertEqual(expire_unpaid(), 1)
        order.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(order.status, "annulee")
        self.assertEqual(fresh.status, "en_attente_paiement")

    def test_pages_and_access(self):
        order = order_for(self.client_user, self.menu_item)
        self.client.force_login(self.client_user)
        menu = self.client.get("/menu/")
        self.assertContains(menu, "Yassa poulet")
        detail = self.client.get(f"/commandes/{order.id}/")
        self.assertContains(detail, "CMD-")
        self.assertContains(detail, "Wave")
        self.assertEqual(self.client.get("/gestion/tableau-de-bord/").status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/commandes/{order.id}/").status_code, 404)
        self.client.force_login(self.vendor)
        kitchen = self.client.get("/gestion/cuisine/")
        self.assertEqual(kitchen.status_code, 200)

    def test_login_with_spaced_phone(self):
        response = self.client.post(
            "/connexion/",
            {"phone": "77 111 11 11", "password": "secret"},
            follow=True,
        )
        self.assertContains(response, "Yassa poulet")


class PaymentTests(TestCase):
    def setUp(self):
        make_shop()
        self.client_user = make_client()
        self.other = make_client("771111112", "Moussa")
        self.vendor = make_vendor()
        self.menu_item = make_menu_item(qty=3)

    def test_proof_validation_reject_and_duplicate(self):
        order = order_for(self.client_user, self.menu_item)
        other_order = order_for(self.other, self.menu_item)
        upload = SimpleUploadedFile("preuve.png", png(), content_type="image/png")
        submit_proof(order, self.client_user, upload, "wave", "TX1")
        order.refresh_from_db()
        self.assertEqual(order.status, "paiement_a_verifier")
        again = SimpleUploadedFile("preuve.png", png(), content_type="image/png")
        with self.assertRaises(ValidationError):
            submit_proof(other_order, self.other, again, "orange_money")
        payment = order.payments.get()
        reject_payment(payment.id, self.vendor, "Capture illisible")
        order.refresh_from_db()
        self.assertEqual(order.status, "en_attente_paiement")
        self.assertEqual(order.payment_status, "rejete")
        replacement = SimpleUploadedFile("autre.png", png((1, 2, 3)), content_type="image/png")
        submit_proof(order, self.client_user, replacement, "wave")
        self.client.force_login(self.vendor)
        response = self.client.post(f"/gestion/paiements/{order.payments.filter(status='en_attente').get().id}/valider/")
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, "payee")


class TaskTests(TestCase):
    @override_settings(TASK_TOKEN="secret")
    def test_daily_task_token(self):
        refused = self.client.post("/taches/quotidiennes/", HTTP_X_TASK_TOKEN="non")
        self.assertEqual(refused.status_code, 403)
        allowed = self.client.post("/taches/quotidiennes/", HTTP_X_TASK_TOKEN="secret")
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("commandes_expirees", allowed.json())


class SubscriptionTests(TestCase):
    def test_generation_is_idempotent(self):
        from subscriptions.models import Plan, Subscription
        from subscriptions.services import expire_subscriptions, generate_due_orders

        make_shop()
        client = make_client()
        tomorrow = timezone.localdate() + timedelta(days=1)
        item = make_dish(name="Mafé", price=3000)
        menu_item = make_menu_item(item=item, qty=1, day=tomorrow)
        plan = Plan.objects.create(name="Semaine 5 jours", frequency="hebdomadaire", price_fcfa=15000)
        Subscription.objects.create(
            client=client,
            plan=plan,
            start_date=timezone.localdate(),
            end_date=tomorrow + timedelta(days=6),
            weekdays=str(tomorrow.weekday()),
            item=item,
            address="Ouakam",
            slot="11:30-12:30",
            status="actif",
        )
        self.assertEqual(generate_due_orders(tomorrow), 1)
        self.assertEqual(generate_due_orders(tomorrow), 0)
        order = Order.objects.get(client=client)
        self.assertEqual(order.status, "payee")
        self.assertEqual(order.note, "Abonné")
        menu_item.refresh_from_db()
        self.assertEqual(menu_item.remaining_quantity, 0)
        ending = Subscription.objects.get()
        ending.end_date = timezone.localdate() + timedelta(days=5)
        ending.save(update_fields=["end_date"])
        expire_subscriptions()
        self.assertTrue(client.notifications.filter(content__icontains="renouveler").exists())


class ConcurrentStockTests(TransactionTestCase):
    def test_two_buyers_one_dish(self):
        make_shop()
        first = make_client()
        second = make_client("771111112", "Moussa")
        menu_item = make_menu_item(qty=1)
        lines = [{"menu_item_id": menu_item.id, "qty": 1}]
        barrier = threading.Barrier(2)
        results = []

        def buy(user_id):
            try:
                barrier.wait(timeout=5)
                user = User.objects.get(pk=user_id)
                create_order(
                    user,
                    lines,
                    "Dakar",
                    "12:30-13:30",
                    "",
                    {"piment": "aucun"},
                )
                results.append("ok")
            except ValidationError:
                results.append("no")
            finally:
                connection.close()

        threads = [threading.Thread(target=buy, args=(user.id,)) for user in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), ["no", "ok"])
        menu_item.refresh_from_db()
        self.assertEqual(menu_item.remaining_quantity, 0)
        self.assertEqual(Order.objects.exclude(status="annulee").count(), 1)
