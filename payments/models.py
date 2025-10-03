from django.db import models
from django.contrib.postgres.fields import JSONField  # Django 3.x; for 4.x use models.JSONField

class PaymentSession(models.Model):
    class Meta:
        db_table = "payment_session"

    payment_session_id = models.BigAutoField(primary_key=True)
    gateway = models.CharField(max_length=32, default="PAYMONGO")
    method = models.CharField(max_length=32, default="GCASH")
    provider_session_id = models.CharField(max_length=128, unique=True, null=True, blank=True)  # chksn_xxx
    provider_payment_id = models.CharField(max_length=128, null=True, blank=True)               # pay_xxx
    status = models.CharField(max_length=16, default="PENDING")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default="PHP")
    checkout_url = models.TextField(null=True, blank=True)
    success_url = models.TextField(null=True, blank=True)
    cancel_url = models.TextField(null=True, blank=True)
    renewal_request_id = models.BigIntegerField(null=True, blank=True)
    business_id = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    raw_provider = models.JSONField(null=True, blank=True)

    # refund fields
    refund_status = models.CharField(max_length=16, default="NONE") # NONE|PENDING|SUCCEEDED|FAILED
    refund_id = models.CharField(max_length=128, null=True, blank=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    refund_reason = models.TextField(null=True, blank=True)
    refund_requested_at = models.DateTimeField(null=True, blank=True)
    refund_settled_at = models.DateTimeField(null=True, blank=True)


class PaymentWebhookEvent(models.Model):
    class Meta:
        db_table = "payment_webhook_event"
        constraints = [models.UniqueConstraint(fields=["event_id"], name="uq_paymongo_event_id")]

    payment_webhook_event_id = models.BigAutoField(primary_key=True)
    gateway = models.CharField(max_length=16, default="PAYMONGO")
    event_type = models.CharField(max_length=64)
    event_id = models.CharField(max_length=128)
    signature = models.TextField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField()
