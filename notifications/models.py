from django.db import models

from shopkit import TimeStamped


class Notification(TimeStamped):
    recipient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=20, default="app")
    content = models.TextField()
    state = models.CharField(max_length=20, default="enregistre")

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        verbose_name = "notification"

    def __str__(self):
        return self.content[:80]
