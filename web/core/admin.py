from django.contrib import admin

from landlord.models import format_brl

from .models import Bill, BillLineItem, Billing, BillingItem


class BillingItemInline(admin.TabularInline):
    model = BillingItem
    extra = 1
    fields = ("description", "item_type", "amount", "sort_order")


@admin.register(Billing)
class BillingAdmin(admin.ModelAdmin):
    list_display = ("name", "uuid", "pix_key", "created_at", "deleted_at")
    list_filter = ("deleted_at",)
    search_fields = ("name", "uuid")
    readonly_fields = ("uuid", "created_at", "updated_at")
    inlines = [BillingItemInline]


class BillLineItemInline(admin.TabularInline):
    model = BillLineItem
    extra = 0
    fields = ("description", "item_type", "amount", "amount_display", "sort_order")
    readonly_fields = ("amount_display",)

    @admin.display(description="Valor (R$)")
    def amount_display(self, obj):
        if obj.pk:
            return format_brl(obj.amount)
        return "-"


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = (
        "billing",
        "reference_month",
        "total_display",
        "due_date",
        "created_at",
    )
    list_filter = ("reference_month",)
    search_fields = ("uuid", "billing__name")
    readonly_fields = ("uuid", "created_at", "total_display")
    inlines = [BillLineItemInline]

    @admin.display(description="Total (R$)")
    def total_display(self, obj):
        return format_brl(obj.total_amount)
