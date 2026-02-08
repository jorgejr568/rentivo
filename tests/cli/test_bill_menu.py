from unittest.mock import MagicMock, patch

from landlord.cli.bill_menu import _format_amount_input
from landlord.models.bill import Bill, BillLineItem
from landlord.models.billing import Billing, BillingItem, ItemType


class TestFormatAmountInput:
    def test_basic(self):
        assert _format_amount_input(8550) == "85.50"

    def test_zero(self):
        assert _format_amount_input(0) == "0.00"

    def test_whole_number(self):
        assert _format_amount_input(10000) == "100.00"


class TestListBillsMenu:
    @patch("landlord.cli.bill_menu.questionary")
    def test_empty_list(self, mock_q):
        from landlord.cli.bill_menu import list_bills_menu

        billing = Billing(id=1, name="Apt 101")
        mock_service = MagicMock()
        mock_service.list_bills.return_value = []

        list_bills_menu(billing, mock_service)

    @patch("landlord.cli.bill_menu.questionary")
    def test_select_back(self, mock_q):
        from landlord.cli.bill_menu import list_bills_menu

        billing = Billing(id=1, name="Apt 101")
        mock_service = MagicMock()
        mock_service.list_bills.return_value = [
            Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u"),
        ]
        mock_service.get_invoice_url.return_value = ""
        mock_q.select.return_value.ask.return_value = "Voltar"

        list_bills_menu(billing, mock_service)

    @patch("landlord.cli.bill_menu.questionary")
    def test_select_none(self, mock_q):
        from landlord.cli.bill_menu import list_bills_menu

        billing = Billing(id=1, name="Apt 101")
        mock_service = MagicMock()
        mock_service.list_bills.return_value = [
            Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u"),
        ]
        mock_service.get_invoice_url.return_value = ""
        mock_q.select.return_value.ask.return_value = None

        list_bills_menu(billing, mock_service)

    @patch("landlord.cli.bill_menu.questionary")
    def test_select_bill_then_back(self, mock_q):
        from landlord.cli.bill_menu import list_bills_menu

        billing = Billing(id=1, name="Apt 101")
        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u", pdf_path="/f.pdf")
        mock_service = MagicMock()
        mock_service.list_bills.return_value = [bill]
        mock_service.get_bill.return_value = bill
        mock_service.get_invoice_url.return_value = "/path"
        mock_q.select.return_value.ask.side_effect = [
            "1 - Março/2025",  # select bill
            "Voltar",          # detail -> back
        ]

        list_bills_menu(billing, mock_service)

    @patch("landlord.cli.bill_menu.questionary")
    def test_select_bill_not_found(self, mock_q):
        from landlord.cli.bill_menu import list_bills_menu

        billing = Billing(id=1, name="Apt 101")
        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u")
        mock_service = MagicMock()
        mock_service.list_bills.return_value = [bill]
        mock_service.get_bill.return_value = None
        mock_service.get_invoice_url.return_value = ""
        mock_q.select.return_value.ask.return_value = "1 - Março/2025"

        list_bills_menu(billing, mock_service)


class TestGenerateBillMenu:
    @patch("landlord.cli.bill_menu.questionary")
    def test_generate_fixed_only(self, mock_q):
        from landlord.cli.bill_menu import generate_bill_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[
            BillingItem(id=1, description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.text.return_value.ask.side_effect = [
            "2025-03",   # reference month
            "",          # due date
            "",          # notes
        ]
        mock_q.confirm.return_value.ask.return_value = False  # no extras

        mock_service = MagicMock()
        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u", pdf_path="/f.pdf")
        mock_service.generate_bill.return_value = bill
        mock_service.get_invoice_url.return_value = "/path"

        generate_bill_menu(billing, mock_service)
        mock_service.generate_bill.assert_called_once()

    @patch("landlord.cli.bill_menu.questionary")
    def test_generate_with_variable(self, mock_q):
        from landlord.cli.bill_menu import generate_bill_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[
            BillingItem(id=1, description="Rent", amount=100000, item_type=ItemType.FIXED),
            BillingItem(id=2, description="Water", amount=0, item_type=ItemType.VARIABLE),
        ])
        mock_q.text.return_value.ask.side_effect = [
            "2025-03",  # reference month
            "50.00",    # variable amount
            "",         # due date
            "",         # notes
        ]
        mock_q.confirm.return_value.ask.return_value = False

        mock_service = MagicMock()
        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=105000, uuid="u", pdf_path="/f.pdf")
        mock_service.generate_bill.return_value = bill
        mock_service.get_invoice_url.return_value = "/path"

        generate_bill_menu(billing, mock_service)
        mock_service.generate_bill.assert_called_once()

    @patch("landlord.cli.bill_menu.questionary")
    def test_generate_with_extras(self, mock_q):
        from landlord.cli.bill_menu import generate_bill_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[
            BillingItem(id=1, description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.text.return_value.ask.side_effect = [
            "2025-03",    # reference month
            "Repair",     # extra desc
            "150.00",     # extra amount
            "",           # due date
            "",           # notes
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, False]  # add extra, stop

        mock_service = MagicMock()
        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=115000, uuid="u", pdf_path="/f.pdf")
        mock_service.generate_bill.return_value = bill
        mock_service.get_invoice_url.return_value = "/path"

        generate_bill_menu(billing, mock_service)
        mock_service.generate_bill.assert_called_once()

    @patch("landlord.cli.bill_menu.questionary")
    def test_generate_extra_empty_desc_skipped(self, mock_q):
        from landlord.cli.bill_menu import generate_bill_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[
            BillingItem(id=1, description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.text.return_value.ask.side_effect = [
            "2025-03",  # reference month
            "",         # empty extra desc -> skip
            "",         # due date
            "",         # notes
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, False]

        mock_service = MagicMock()
        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u", pdf_path="/f.pdf")
        mock_service.generate_bill.return_value = bill
        mock_service.get_invoice_url.return_value = ""

        generate_bill_menu(billing, mock_service)


class TestBillDetailMenu:
    @patch("landlord.cli.bill_menu.questionary")
    def test_toggle_paid(self, mock_q):
        from landlord.cli.bill_menu import _bill_detail_menu

        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u")
        billing = Billing(id=1, name="Apt 101")
        mock_q.select.return_value.ask.side_effect = ["Marcar como Pago", "Voltar"]

        mock_service = MagicMock()
        from datetime import datetime
        from landlord.models.bill import SP_TZ
        mock_service.toggle_paid.return_value = Bill(
            id=1, billing_id=1, reference_month="2025-03", total_amount=100000,
            uuid="u", paid_at=datetime.now(SP_TZ),
        )
        mock_service.get_invoice_url.return_value = ""
        _bill_detail_menu(bill, billing, mock_service)

    @patch("landlord.cli.bill_menu.questionary")
    def test_regenerate_pdf(self, mock_q):
        from landlord.cli.bill_menu import _bill_detail_menu

        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u", pdf_path="/f.pdf")
        billing = Billing(id=1, name="Apt 101")
        mock_q.select.return_value.ask.side_effect = ["Regenerar PDF", "Voltar"]

        mock_service = MagicMock()
        mock_service.regenerate_pdf.return_value = bill
        mock_service.get_invoice_url.return_value = "/path"
        _bill_detail_menu(bill, billing, mock_service)
        mock_service.regenerate_pdf.assert_called_once()

    @patch("landlord.cli.bill_menu.questionary")
    def test_delete_bill(self, mock_q):
        from landlord.cli.bill_menu import _bill_detail_menu

        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u")
        billing = Billing(id=1, name="Apt 101")
        mock_q.select.return_value.ask.return_value = "Excluir Fatura"
        mock_q.confirm.return_value.ask.return_value = True

        mock_service = MagicMock()
        mock_service.get_invoice_url.return_value = ""
        _bill_detail_menu(bill, billing, mock_service)
        mock_service.delete_bill.assert_called_once_with(1)

    @patch("landlord.cli.bill_menu.questionary")
    def test_delete_bill_cancel(self, mock_q):
        from landlord.cli.bill_menu import _bill_detail_menu

        bill = Bill(id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u")
        billing = Billing(id=1, name="Apt 101")
        mock_q.select.return_value.ask.side_effect = ["Excluir Fatura", "Voltar"]
        mock_q.confirm.return_value.ask.return_value = False

        mock_service = MagicMock()
        mock_service.get_invoice_url.return_value = ""
        _bill_detail_menu(bill, billing, mock_service)
        mock_service.delete_bill.assert_not_called()

    @patch("landlord.cli.bill_menu.questionary")
    def test_edit_bill(self, mock_q):
        from landlord.cli.bill_menu import _bill_detail_menu

        bill = Bill(
            id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u",
            line_items=[BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0)],
        )
        billing = Billing(id=1, name="Apt 101")
        mock_q.select.return_value.ask.side_effect = ["Editar Fatura", "Voltar"]
        mock_q.text.return_value.ask.side_effect = [
            "100000",  # update amount
            "",        # due date
            "",        # notes
        ]
        mock_q.confirm.return_value.ask.return_value = False

        mock_service = MagicMock()
        mock_service.update_bill.return_value = bill
        mock_service.get_invoice_url.return_value = ""
        _bill_detail_menu(bill, billing, mock_service)
        mock_service.update_bill.assert_called_once()


class TestEditBillMenu:
    @patch("landlord.cli.bill_menu.questionary")
    def test_edit_with_extras(self, mock_q):
        from landlord.cli.bill_menu import edit_bill_menu

        bill = Bill(
            id=1, billing_id=1, reference_month="2025-03", total_amount=115000, uuid="u",
            line_items=[
                BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
                BillLineItem(description="Repair", amount=15000, item_type=ItemType.EXTRA, sort_order=1),
            ],
        )
        billing = Billing(id=1, name="Apt 101")
        mock_q.text.return_value.ask.side_effect = [
            "100000",  # update fixed amount
            "",        # due date
            "",        # notes
        ]
        mock_q.select.return_value.ask.return_value = "Manter"  # keep extra
        mock_q.confirm.return_value.ask.return_value = False  # no new extras

        mock_service = MagicMock()
        mock_service.update_bill.return_value = bill
        mock_service.get_invoice_url.return_value = ""

        edit_bill_menu(bill, billing, mock_service)
        mock_service.update_bill.assert_called_once()

    @patch("landlord.cli.bill_menu.questionary")
    def test_edit_remove_extra(self, mock_q):
        from landlord.cli.bill_menu import edit_bill_menu

        bill = Bill(
            id=1, billing_id=1, reference_month="2025-03", total_amount=115000, uuid="u",
            line_items=[
                BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
                BillLineItem(description="Repair", amount=15000, item_type=ItemType.EXTRA, sort_order=1),
            ],
        )
        billing = Billing(id=1, name="Apt 101")
        mock_q.text.return_value.ask.side_effect = [
            "100000",  # update fixed
            "",        # due date
            "",        # notes
        ]
        mock_q.select.return_value.ask.return_value = "Remover"  # remove extra
        mock_q.confirm.return_value.ask.return_value = False

        mock_service = MagicMock()
        mock_service.update_bill.return_value = bill
        mock_service.get_invoice_url.return_value = ""

        edit_bill_menu(bill, billing, mock_service)
        mock_service.update_bill.assert_called_once()

    @patch("landlord.cli.bill_menu.questionary")
    def test_edit_extra_amount(self, mock_q):
        from landlord.cli.bill_menu import edit_bill_menu

        bill = Bill(
            id=1, billing_id=1, reference_month="2025-03", total_amount=115000, uuid="u",
            line_items=[
                BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
                BillLineItem(description="Repair", amount=15000, item_type=ItemType.EXTRA, sort_order=1),
            ],
        )
        billing = Billing(id=1, name="Apt 101")
        mock_q.text.return_value.ask.side_effect = [
            "100000",  # update fixed
            "200.00",  # edit extra amount
            "",        # due date
            "",        # notes
        ]
        mock_q.select.return_value.ask.return_value = "Editar valor"
        mock_q.confirm.return_value.ask.return_value = False

        mock_service = MagicMock()
        mock_service.update_bill.return_value = bill
        mock_service.get_invoice_url.return_value = ""

        edit_bill_menu(bill, billing, mock_service)
        mock_service.update_bill.assert_called_once()

    @patch("landlord.cli.bill_menu.questionary")
    def test_edit_add_new_extra(self, mock_q):
        from landlord.cli.bill_menu import edit_bill_menu

        bill = Bill(
            id=1, billing_id=1, reference_month="2025-03", total_amount=100000, uuid="u",
            line_items=[
                BillLineItem(description="Rent", amount=100000, item_type=ItemType.FIXED, sort_order=0),
            ],
        )
        billing = Billing(id=1, name="Apt 101")
        mock_q.text.return_value.ask.side_effect = [
            "100000",   # update fixed
            "Cleaning",  # new extra desc
            "50.00",     # new extra amount
            "",          # due date
            "",          # notes
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, False]

        mock_service = MagicMock()
        mock_service.update_bill.return_value = bill
        mock_service.get_invoice_url.return_value = ""

        edit_bill_menu(bill, billing, mock_service)
        mock_service.update_bill.assert_called_once()
