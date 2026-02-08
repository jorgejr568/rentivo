import uuid as uuid_mod

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from landlord.models import format_brl
from landlord.models.bill import BillLineItem as PydanticBillLineItem
from landlord.pdf.invoice import InvoicePDF
from landlord.pix import generate_pix_payload, generate_pix_qrcode_png
from landlord.settings import settings as landlord_settings
from landlord.storage.factory import get_storage

from .adapters import to_pydantic_bill, to_pydantic_billing
from .forms import (
    BillEditForm,
    BillGenerateForm,
    BillLineItemEditForm,
    BillLineItemEditFormSet,
    BillingForm,
    BillingItemForm,
    BillingItemFormSet,
    ExtraExpenseFormSet,
    VariableAmountFormSet,
)
from .models import Bill, BillLineItem, Billing, BillingItem


# -- Billing views --


@login_required
def billing_list(request):
    billings = Billing.objects.filter(deleted_at__isnull=True).order_by("-created_at")
    return render(request, "billing/list.html", {"billings": billings})


@login_required
def billing_create(request):
    if request.method == "POST":
        form = BillingForm(request.POST)
        item_formset = BillingItemFormSet(request.POST, prefix="items")

        if form.is_valid() and item_formset.is_valid():
            billing = Billing.objects.create(
                uuid=str(uuid_mod.uuid4()),
                name=form.cleaned_data["name"],
                description=form.cleaned_data["description"],
                pix_key=form.cleaned_data["pix_key"],
            )

            sort = 0
            for item_form in item_formset:
                if item_form.cleaned_data and not item_form.cleaned_data.get("DELETE"):
                    desc = item_form.cleaned_data.get("description")
                    if not desc:
                        continue
                    BillingItem.objects.create(
                        billing=billing,
                        description=desc,
                        item_type=item_form.cleaned_data["item_type"],
                        amount=item_form.cleaned_data.get("amount") or 0,
                        sort_order=sort,
                    )
                    sort += 1

            messages.success(request, f'Cobrança "{billing.name}" criada com sucesso.')
            return redirect("billing_detail", billing_id=billing.id)
    else:
        form = BillingForm()
        item_formset = BillingItemFormSet(prefix="items")

    return render(request, "billing/create.html", {
        "form": form,
        "item_formset": item_formset,
    })


@login_required
def billing_detail(request, billing_id):
    billing = get_object_or_404(Billing, id=billing_id, deleted_at__isnull=True)
    items = billing.items.all()
    bills = billing.bills.all()
    return render(request, "billing/detail.html", {
        "billing": billing,
        "items": items,
        "bills": bills,
    })


@login_required
def billing_edit(request, billing_id):
    billing = get_object_or_404(Billing, id=billing_id, deleted_at__isnull=True)
    existing_items = list(billing.items.all())

    if request.method == "POST":
        form = BillingForm(request.POST)
        item_formset = BillingItemFormSet(request.POST, prefix="items")

        if form.is_valid() and item_formset.is_valid():
            billing.name = form.cleaned_data["name"]
            billing.description = form.cleaned_data["description"]
            billing.pix_key = form.cleaned_data["pix_key"]
            billing.save()

            # Delete old items and recreate
            billing.items.all().delete()

            sort = 0
            for item_form in item_formset:
                if item_form.cleaned_data and not item_form.cleaned_data.get("DELETE"):
                    desc = item_form.cleaned_data.get("description")
                    if not desc:
                        continue
                    BillingItem.objects.create(
                        billing=billing,
                        description=desc,
                        item_type=item_form.cleaned_data["item_type"],
                        amount=item_form.cleaned_data.get("amount") or 0,
                        sort_order=sort,
                    )
                    sort += 1

            messages.success(request, "Cobrança atualizada com sucesso.")
            return redirect("billing_detail", billing_id=billing.id)
    else:
        form = BillingForm(initial={
            "name": billing.name,
            "description": billing.description,
            "pix_key": billing.pix_key,
        })

        initial_items = []
        for item in existing_items:
            amount_display = ""
            if item.amount:
                reais = item.amount / 100
                amount_display = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            initial_items.append({
                "description": item.description,
                "item_type": item.item_type,
                "amount": amount_display,
                "sort_order": item.sort_order,
            })

        item_formset = BillingItemFormSet(
            prefix="items",
            initial=initial_items,
        )
        # Set extra to 0 when we have initial data
        item_formset.extra = 0

    return render(request, "billing/edit.html", {
        "billing": billing,
        "form": form,
        "item_formset": item_formset,
    })


@login_required
def billing_delete(request, billing_id):
    if request.method == "POST":
        billing = get_object_or_404(Billing, id=billing_id, deleted_at__isnull=True)
        billing.deleted_at = timezone.now()
        billing.save()
        messages.success(request, f'Cobrança "{billing.name}" excluída.')
        return redirect("billing_list")
    return redirect("billing_list")


# -- Bill views --


def _get_pix_data(billing_pydantic, total_centavos):
    """Get PIX QR code data for invoice generation."""
    pix_key = billing_pydantic.pix_key or landlord_settings.pix_key
    if not pix_key:
        return None, "", ""

    merchant_name = landlord_settings.pix_merchant_name
    merchant_city = landlord_settings.pix_merchant_city
    if not merchant_name or not merchant_city:
        return None, "", ""

    amount = total_centavos / 100
    payload = generate_pix_payload(
        pix_key=pix_key,
        merchant_name=merchant_name,
        merchant_city=merchant_city,
        amount=amount,
    )
    png = generate_pix_qrcode_png(
        pix_key=pix_key,
        merchant_name=merchant_name,
        merchant_city=merchant_city,
        amount=amount,
    )
    return png, pix_key, payload


def _generate_and_save_pdf(bill_obj, billing_obj):
    """Generate PDF and save to storage. Updates bill.pdf_path."""
    billing_pydantic = to_pydantic_billing(billing_obj)
    bill_pydantic = to_pydantic_bill(bill_obj)

    pix_png, pix_key, pix_payload = _get_pix_data(billing_pydantic, bill_obj.total_amount)

    pdf_gen = InvoicePDF()
    pdf_bytes = pdf_gen.generate(
        bill_pydantic, billing_pydantic.name,
        pix_qrcode_png=pix_png, pix_key=pix_key, pix_payload=pix_payload,
    )

    storage = get_storage()
    key = f"{billing_obj.uuid}/{bill_obj.uuid}.pdf"
    path = storage.save(key, pdf_bytes)

    bill_obj.pdf_path = path
    bill_obj.save(update_fields=["pdf_path"])


@login_required
def bill_generate(request, billing_id):
    billing = get_object_or_404(Billing, id=billing_id, deleted_at__isnull=True)
    items = list(billing.items.all())
    fixed_items = [i for i in items if i.item_type == "fixed"]
    variable_items = [i for i in items if i.item_type == "variable"]

    variable_initial = [
        {"item_id": item.id, "description": item.description, "amount": ""}
        for item in variable_items
    ]

    if request.method == "POST":
        form = BillGenerateForm(request.POST)
        variable_formset = VariableAmountFormSet(request.POST, prefix="variable", initial=variable_initial)
        extras_formset = ExtraExpenseFormSet(request.POST, prefix="extras")

        if form.is_valid() and variable_formset.is_valid() and extras_formset.is_valid():
            # Build variable amounts map
            variable_amounts = {}
            for vf in variable_formset:
                if vf.cleaned_data:
                    variable_amounts[vf.cleaned_data["item_id"]] = vf.cleaned_data.get("amount") or 0

            # Build line items
            line_items_data = []
            sort = 0

            for item in items:
                if item.item_type == "fixed":
                    amount = item.amount
                else:
                    amount = variable_amounts.get(item.id, 0)
                line_items_data.append({
                    "description": item.description,
                    "amount": amount,
                    "item_type": item.item_type,
                    "sort_order": sort,
                })
                sort += 1

            # Add extras
            for ef in extras_formset:
                if ef.cleaned_data and not ef.cleaned_data.get("DELETE"):
                    desc = ef.cleaned_data.get("description")
                    amt = ef.cleaned_data.get("amount") or 0
                    if desc and amt:
                        line_items_data.append({
                            "description": desc,
                            "amount": amt,
                            "item_type": "extra",
                            "sort_order": sort,
                        })
                        sort += 1

            total = sum(li["amount"] for li in line_items_data)

            # Create bill
            bill = Bill.objects.create(
                uuid=str(uuid_mod.uuid4()),
                billing=billing,
                reference_month=form.cleaned_data["reference_month"],
                total_amount=total,
                notes=form.cleaned_data.get("notes") or "",
                due_date=form.cleaned_data.get("due_date") or None,
            )

            # Create line items
            for li_data in line_items_data:
                BillLineItem.objects.create(bill=bill, **li_data)

            # Generate PDF
            _generate_and_save_pdf(bill, billing)

            messages.success(
                request,
                f"Fatura {bill.reference_month} gerada com sucesso. Total: {format_brl(total)}",
            )
            return redirect("bill_detail", bill_id=bill.id)
    else:
        form = BillGenerateForm()
        variable_formset = VariableAmountFormSet(prefix="variable", initial=variable_initial)
        extras_formset = ExtraExpenseFormSet(prefix="extras")

    return render(request, "bill/generate.html", {
        "billing": billing,
        "form": form,
        "fixed_items": fixed_items,
        "variable_formset": variable_formset,
        "extras_formset": extras_formset,
    })


@login_required
def bill_detail(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    line_items = bill.line_items.all()
    return render(request, "bill/detail.html", {
        "bill": bill,
        "line_items": line_items,
    })


@login_required
def bill_edit(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    billing = bill.billing
    existing_line_items = list(bill.line_items.all())

    if request.method == "POST":
        form = BillEditForm(request.POST)
        line_item_formset = BillLineItemEditFormSet(request.POST, prefix="lineitems")

        if form.is_valid() and line_item_formset.is_valid():
            # Update line item amounts
            for lif in line_item_formset:
                if lif.cleaned_data:
                    li_id = lif.cleaned_data["line_item_id"]
                    new_amount = lif.cleaned_data["amount"]
                    BillLineItem.objects.filter(id=li_id).update(amount=new_amount)

            # Recalculate total
            bill.refresh_from_db()
            bill.total_amount = sum(li.amount for li in bill.line_items.all())
            bill.notes = form.cleaned_data.get("notes") or ""
            bill.due_date = form.cleaned_data.get("due_date") or None
            bill.save(update_fields=["total_amount", "notes", "due_date"])

            # Regenerate PDF
            _generate_and_save_pdf(bill, billing)

            messages.success(request, "Fatura atualizada e PDF regenerado com sucesso.")
            return redirect("bill_detail", bill_id=bill.id)
    else:
        form = BillEditForm(initial={
            "notes": bill.notes,
            "due_date": bill.due_date or "",
        })

        TYPE_LABELS = {"fixed": "Fixo", "variable": "Variável", "extra": "Extra"}

        initial_line_items = []
        for li in existing_line_items:
            reais = li.amount / 100
            amount_display = f"{reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            initial_line_items.append({
                "line_item_id": li.id,
                "description": li.description,
                "item_type": TYPE_LABELS.get(li.item_type, li.item_type),
                "amount": amount_display,
            })

        line_item_formset = BillLineItemEditFormSet(
            prefix="lineitems",
            initial=initial_line_items,
        )

    return render(request, "bill/edit.html", {
        "bill": bill,
        "form": form,
        "line_item_formset": line_item_formset,
    })


@login_required
def bill_invoice(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    if not bill.pdf_path:
        messages.warning(request, "Nenhum PDF disponível para esta fatura.")
        return redirect("bill_detail", bill_id=bill.id)

    storage = get_storage()

    # For local storage, serve the file directly
    if landlord_settings.storage_backend == "local":
        import os
        file_path = bill.pdf_path
        if os.path.isfile(file_path):
            return FileResponse(
                open(file_path, "rb"),
                content_type="application/pdf",
                as_attachment=False,
                filename=f"fatura-{bill.reference_month}.pdf",
            )
        messages.error(request, "Arquivo PDF não encontrado.")
        return redirect("bill_detail", bill_id=bill.id)

    # For S3 storage, redirect to presigned URL
    url = storage.get_presigned_url(bill.pdf_path)
    return HttpResponseRedirect(url)
