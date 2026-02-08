import re

from django import forms
from django.forms import formset_factory


class BRLField(forms.CharField):
    """Field that accepts BRL-formatted input (e.g. '2850,00' or '2.850,00')
    and converts to centavos (int)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return 0
        # Remove R$ prefix, spaces, and thousand separators
        value = value.replace("R$", "").replace(" ", "").replace(".", "")
        # Replace comma with dot for float parsing
        value = value.replace(",", ".")
        try:
            reais = float(value)
        except ValueError:
            raise forms.ValidationError("Valor inválido. Use o formato: 1.250,00")
        return int(round(reais * 100))


class BillingForm(forms.Form):
    name = forms.CharField(
        label="Nome",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        label="Descrição",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
    pix_key = forms.CharField(
        label="Chave PIX",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


ITEM_TYPE_CHOICES = [
    ("fixed", "Fixo"),
    ("variable", "Variável"),
]


class BillingItemForm(forms.Form):
    description = forms.CharField(
        label="Descrição",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Descrição do item"}),
    )
    item_type = forms.ChoiceField(
        label="Tipo",
        choices=ITEM_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = BRLField(
        label="Valor (R$)",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "0,00"}),
    )
    sort_order = forms.IntegerField(widget=forms.HiddenInput(), required=False)


BillingItemFormSet = formset_factory(BillingItemForm, extra=1, can_delete=True)


class BillGenerateForm(forms.Form):
    reference_month = forms.CharField(
        label="Mês de Referência",
        max_length=7,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "AAAA-MM", "pattern": r"\d{4}-\d{2}"}
        ),
        help_text="Formato: AAAA-MM (ex: 2025-01)",
    )
    notes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
    due_date = forms.CharField(
        label="Data de Vencimento",
        required=False,
        max_length=20,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "DD/MM/AAAA"}
        ),
    )


class VariableAmountForm(forms.Form):
    """Dynamic form for variable billing item amounts."""

    item_id = forms.IntegerField(widget=forms.HiddenInput())
    description = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control-plaintext", "readonly": True}),
        required=False,
    )
    amount = BRLField(
        label="Valor (R$)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "0,00"}),
    )


VariableAmountFormSet = formset_factory(VariableAmountForm, extra=0)


class ExtraExpenseForm(forms.Form):
    description = forms.CharField(
        label="Descrição",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Descrição do extra"}),
    )
    amount = BRLField(
        label="Valor (R$)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "0,00"}),
    )


ExtraExpenseFormSet = formset_factory(ExtraExpenseForm, extra=0, can_delete=True)


class BillEditForm(forms.Form):
    notes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
    due_date = forms.CharField(
        label="Data de Vencimento",
        required=False,
        max_length=20,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "DD/MM/AAAA"}
        ),
    )


class BillLineItemEditForm(forms.Form):
    line_item_id = forms.IntegerField(widget=forms.HiddenInput())
    description = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control-plaintext", "readonly": True}),
        required=False,
    )
    item_type = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control-plaintext", "readonly": True}),
        required=False,
    )
    amount = BRLField(
        label="Valor (R$)",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


BillLineItemEditFormSet = formset_factory(BillLineItemEditForm, extra=0)
