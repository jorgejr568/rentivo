from django.db import models


class Billing(models.Model):
    uuid = models.CharField(max_length=36, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(default="", blank=True)
    pix_key = models.CharField(max_length=255, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "billings"

    def __str__(self):
        return self.name

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class BillingItem(models.Model):
    billing = models.ForeignKey(
        Billing, on_delete=models.CASCADE, related_name="items"
    )
    description = models.CharField(max_length=255)
    amount = models.IntegerField(default=0)
    item_type = models.CharField(max_length=20)
    sort_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "billing_items"
        ordering = ["sort_order"]

    def __str__(self):
        return self.description


class Bill(models.Model):
    uuid = models.CharField(max_length=36, unique=True)
    billing = models.ForeignKey(
        Billing, on_delete=models.CASCADE, related_name="bills"
    )
    reference_month = models.CharField(max_length=7)
    total_amount = models.IntegerField(default=0)
    pdf_path = models.CharField(max_length=512, null=True, blank=True)
    notes = models.TextField(default="", blank=True)
    due_date = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "bills"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.billing.name} - {self.reference_month}"


class BillLineItem(models.Model):
    bill = models.ForeignKey(
        Bill, on_delete=models.CASCADE, related_name="line_items"
    )
    description = models.CharField(max_length=255)
    amount = models.IntegerField()
    item_type = models.CharField(max_length=20)
    sort_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "bill_line_items"
        ordering = ["sort_order"]

    def __str__(self):
        return self.description
