from unittest.mock import MagicMock, patch

from landlord.models.billing import Billing, BillingItem, ItemType


class TestCreateBillingMenu:
    @patch("landlord.cli.billing_menu.questionary")
    def test_cancel_on_empty_name(self, mock_q):
        from landlord.cli.billing_menu import create_billing_menu

        mock_q.text.return_value.ask.return_value = ""
        mock_service = MagicMock()
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_not_called()

    @patch("landlord.cli.billing_menu.questionary")
    def test_cancel_on_none_name(self, mock_q):
        from landlord.cli.billing_menu import create_billing_menu

        mock_q.text.return_value.ask.return_value = None
        mock_service = MagicMock()
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_not_called()

    @patch("landlord.cli.billing_menu.questionary")
    def test_no_items_doesnt_create(self, mock_q):
        from landlord.cli.billing_menu import create_billing_menu

        mock_q.text.return_value.ask.side_effect = ["Apt 101", "desc", ""]
        mock_q.confirm.return_value.ask.return_value = False
        mock_service = MagicMock()
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_not_called()

    @patch("landlord.settings.settings")
    @patch("landlord.cli.billing_menu.questionary")
    def test_create_with_fixed_item(self, mock_q, mock_settings):
        from landlord.cli.billing_menu import create_billing_menu

        mock_settings.pix_key = ""
        mock_q.text.return_value.ask.side_effect = [
            "Apt 101",  # name
            "desc",     # description
            "Rent",     # item description
            "2850.00",  # item amount
            "",         # pix key
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, False]  # add item? yes, add more? no
        mock_q.select.return_value.ask.return_value = "Fixo"

        mock_service = MagicMock()
        mock_service.create_billing.return_value = Billing(name="Apt 101")
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_called_once()

    @patch("landlord.settings.settings")
    @patch("landlord.cli.billing_menu.questionary")
    def test_create_with_variable_item(self, mock_q, mock_settings):
        from landlord.cli.billing_menu import create_billing_menu

        mock_settings.pix_key = ""
        mock_q.text.return_value.ask.side_effect = [
            "Apt 101", "desc", "Water", "",
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, False]
        mock_q.select.return_value.ask.return_value = "Variável"

        mock_service = MagicMock()
        mock_service.create_billing.return_value = Billing(name="Apt 101")
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_called_once()

    @patch("landlord.settings.settings")
    @patch("landlord.cli.billing_menu.questionary")
    def test_create_with_global_pix_override(self, mock_q, mock_settings):
        from landlord.cli.billing_menu import create_billing_menu

        mock_settings.pix_key = "global@pix.com"
        mock_q.text.return_value.ask.side_effect = [
            "Apt 101", "desc", "Rent", "1000", "custom@pix.com",
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, False, True]  # add item, stop, override pix
        mock_q.select.return_value.ask.return_value = "Fixo"

        mock_service = MagicMock()
        mock_service.create_billing.return_value = Billing(name="Apt 101")
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_called_once()

    @patch("landlord.settings.settings")
    @patch("landlord.cli.billing_menu.questionary")
    def test_create_skip_empty_item_desc(self, mock_q, mock_settings):
        from landlord.cli.billing_menu import create_billing_menu

        mock_settings.pix_key = ""
        # First item has empty desc, second has valid desc
        mock_q.text.return_value.ask.side_effect = [
            "Apt 101", "desc",
            "",         # empty item desc -> skip
            "Rent",     # valid item desc
            "1000",     # amount
            "",         # pix key
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, True, False]  # add, add again, stop
        mock_q.select.return_value.ask.return_value = "Fixo"

        mock_service = MagicMock()
        mock_service.create_billing.return_value = Billing(name="Apt 101")
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_called_once()


class TestListBillingsMenu:
    @patch("landlord.cli.billing_menu.questionary")
    def test_empty_list(self, mock_q):
        from landlord.cli.billing_menu import list_billings_menu

        mock_billing_svc = MagicMock()
        mock_billing_svc.list_billings.return_value = []
        mock_bill_svc = MagicMock()
        list_billings_menu(mock_billing_svc, mock_bill_svc)

    @patch("landlord.cli.billing_menu.questionary")
    def test_select_back(self, mock_q):
        from landlord.cli.billing_menu import list_billings_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_billing_svc = MagicMock()
        mock_billing_svc.list_billings.return_value = [billing]
        mock_q.select.return_value.ask.return_value = "Voltar"
        mock_bill_svc = MagicMock()

        list_billings_menu(mock_billing_svc, mock_bill_svc)

    @patch("landlord.cli.billing_menu.questionary")
    def test_select_none(self, mock_q):
        from landlord.cli.billing_menu import list_billings_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_billing_svc = MagicMock()
        mock_billing_svc.list_billings.return_value = [billing]
        mock_q.select.return_value.ask.return_value = None
        list_billings_menu(mock_billing_svc, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_select_billing(self, mock_q):
        from landlord.cli.billing_menu import list_billings_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_billing_svc = MagicMock()
        mock_billing_svc.list_billings.return_value = [billing]
        mock_billing_svc.get_billing.return_value = billing
        # First select billing, then from detail menu select Voltar
        mock_q.select.return_value.ask.side_effect = [
            "1 - Apt 101",  # select billing
            "Voltar",       # detail menu -> back
        ]
        list_billings_menu(mock_billing_svc, MagicMock())



class TestBillingDetailMenu:
    @patch("landlord.cli.billing_menu.questionary")
    def test_generate_bill(self, mock_q):
        from landlord.cli.billing_menu import _billing_detail_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[
            BillingItem(id=1, description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = ["Gerar Nova Fatura", "Voltar"]

        with patch("landlord.cli.billing_menu.generate_bill_menu") as mock_gen:
            _billing_detail_menu(billing, MagicMock(), MagicMock())
            mock_gen.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_view_bills(self, mock_q):
        from landlord.cli.billing_menu import _billing_detail_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Ver Faturas Anteriores", "Voltar"]

        with patch("landlord.cli.billing_menu.list_bills_menu") as mock_list:
            _billing_detail_menu(billing, MagicMock(), MagicMock())
            mock_list.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_delete_billing(self, mock_q):
        from landlord.cli.billing_menu import _billing_detail_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[])
        mock_q.select.return_value.ask.return_value = "Excluir Cobrança"
        mock_q.confirm.return_value.ask.return_value = True

        mock_billing_svc = MagicMock()
        _billing_detail_menu(billing, mock_billing_svc, MagicMock())
        mock_billing_svc.delete_billing.assert_called_once_with(1)

    @patch("landlord.cli.billing_menu.questionary")
    def test_delete_billing_cancel(self, mock_q):
        from landlord.cli.billing_menu import _billing_detail_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Excluir Cobrança", "Voltar"]
        mock_q.confirm.return_value.ask.return_value = False

        mock_billing_svc = MagicMock()
        _billing_detail_menu(billing, mock_billing_svc, MagicMock())
        mock_billing_svc.delete_billing.assert_not_called()

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_billing(self, mock_q):
        from landlord.cli.billing_menu import _billing_detail_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Editar Cobrança", "Voltar", "Voltar"]

        mock_billing_svc = MagicMock()
        _billing_detail_menu(billing, mock_billing_svc, MagicMock())


class TestCreateBillingMenuEdgeCases:
    @patch("landlord.settings.settings")
    @patch("landlord.cli.billing_menu.questionary")
    def test_invalid_fixed_amount_then_valid(self, mock_q, mock_settings):
        """Cover line 53: invalid amount retries in create billing."""
        from landlord.cli.billing_menu import create_billing_menu

        mock_settings.pix_key = ""
        mock_q.text.return_value.ask.side_effect = [
            "Apt 101",  # name
            "desc",     # description
            "Rent",     # item description
            "abc",      # invalid amount -> retry
            "2850.00",  # valid amount
            "",         # pix key
        ]
        mock_q.confirm.return_value.ask.side_effect = [True, False]
        mock_q.select.return_value.ask.return_value = "Fixo"

        mock_service = MagicMock()
        mock_service.create_billing.return_value = Billing(name="Apt 101")
        create_billing_menu(mock_service)
        mock_service.create_billing.assert_called_once()


class TestBillingDetailMenuEdgeCases:
    @patch("landlord.cli.billing_menu.questionary")
    def test_description_printed(self, mock_q):
        """Cover line 129: billing.description is printed when present."""
        from landlord.cli.billing_menu import _billing_detail_menu

        billing = Billing(id=1, uuid="u", name="Apt 101", description="A nice apartment", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.return_value = "Voltar"
        _billing_detail_menu(billing, MagicMock(), MagicMock())


class TestEditBillingMenuEdgeCases:
    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_cancel_amount(self, mock_q):
        """Cover line 249: cancel amount input returns billing."""
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Editar Item",
            "Rent (R$ 1.000,00)",
            "Fixo",
            "Voltar",
        ]
        mock_q.text.return_value.ask.side_effect = ["Rent", None]  # desc ok, amount cancel

        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_invalid_amount_then_valid(self, mock_q):
        """Cover line 254: invalid amount retries in edit item."""
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Editar Item",
            "Rent (R$ 1.000,00)",
            "Fixo",
            "Voltar",
        ]
        mock_q.text.return_value.ask.side_effect = ["Rent", "abc", "2000.00"]

        mock_svc = MagicMock()
        mock_svc.update_billing.return_value = billing
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_add_item_cancel_amount(self, mock_q):
        """Cover line 281: cancel amount in add item."""
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Adicionar Item", "Fixo", "Voltar"]
        mock_q.text.return_value.ask.side_effect = ["Water", None]  # desc ok, amount cancel

        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_add_item_invalid_amount_then_valid(self, mock_q):
        """Cover line 286: invalid amount retries in add item."""
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Adicionar Item", "Fixo", "Voltar"]
        mock_q.text.return_value.ask.side_effect = ["Water", "abc", "50.00"]

        mock_svc = MagicMock()
        mock_svc.update_billing.return_value = billing
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_called_once()


class TestEditBillingMenu:
    @patch("landlord.cli.billing_menu.questionary")
    def test_back_exits(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[])
        mock_q.select.return_value.ask.return_value = "Voltar"
        result = _edit_billing_menu(billing, MagicMock())
        assert result is billing

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_pix_key(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", pix_key="old@pix", items=[])
        mock_q.select.return_value.ask.side_effect = ["Editar Chave PIX", "Voltar"]
        mock_q.text.return_value.ask.return_value = "new@pix"

        mock_svc = MagicMock()
        updated = Billing(id=1, name="Apt 101", pix_key="new@pix", items=[])
        mock_svc.update_billing.return_value = updated
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_pix_key_cancel(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", pix_key="old", items=[])
        mock_q.select.return_value.ask.side_effect = ["Editar Chave PIX", "Voltar"]
        mock_q.text.return_value.ask.return_value = None

        mock_svc = MagicMock()
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_not_called()

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_no_items(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Editar Item", "Voltar"]
        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_add_item(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = ["Adicionar Item", "Fixo", "Voltar"]
        mock_q.text.return_value.ask.side_effect = ["Water", "50.00"]

        mock_svc = MagicMock()
        mock_svc.update_billing.return_value = billing
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_add_item_cancel_empty_desc(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Adicionar Item", "Voltar"]
        mock_q.text.return_value.ask.return_value = ""

        mock_svc = MagicMock()
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_not_called()

    @patch("landlord.cli.billing_menu.questionary")
    def test_remove_item(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
            BillingItem(description="Water", amount=0, item_type=ItemType.VARIABLE),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Remover Item",
            "Rent (R$ 1.000,00)",  # select item
            "Voltar",
        ]
        mock_q.confirm.return_value.ask.return_value = True

        mock_svc = MagicMock()
        mock_svc.update_billing.return_value = billing
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_remove_item_no_items(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Remover Item", "Voltar"]
        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_remove_last_item_blocked(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Remover Item",
            "Rent (R$ 1.000,00)",
            "Voltar",
        ]

        mock_svc = MagicMock()
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_not_called()

    @patch("landlord.cli.billing_menu.questionary")
    def test_remove_item_cancel(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
            BillingItem(description="Water", amount=0, item_type=ItemType.VARIABLE),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Remover Item",
            "Rent (R$ 1.000,00)",
            "Voltar",
        ]
        mock_q.confirm.return_value.ask.return_value = False

        mock_svc = MagicMock()
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_not_called()

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_back(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Editar Item",
            "Voltar",  # select item -> back
            "Voltar",  # main -> back
        ]
        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_success(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Editar Item",
            "Rent (R$ 1.000,00)",  # select item
            "Fixo",               # type
            "Voltar",             # back to edit menu
        ]
        mock_q.text.return_value.ask.side_effect = ["Updated Rent", "2000.00"]

        mock_svc = MagicMock()
        mock_svc.update_billing.return_value = billing
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_to_variable(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Editar Item",
            "Rent (R$ 1.000,00)",
            "Variável",
            "Voltar",
        ]
        mock_q.text.return_value.ask.return_value = "Water"

        mock_svc = MagicMock()
        mock_svc.update_billing.return_value = billing
        _edit_billing_menu(billing, mock_svc)
        mock_svc.update_billing.assert_called_once()

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_cancel_desc(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Editar Item",
            "Rent (R$ 1.000,00)",
            "Voltar",
        ]
        mock_q.text.return_value.ask.return_value = None

        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_add_item_cancel_type(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[])
        mock_q.select.return_value.ask.side_effect = ["Adicionar Item", None, "Voltar"]
        mock_q.text.return_value.ask.return_value = "Water"

        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_remove_item_select_back(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Remover Item",
            "Voltar",
            "Voltar",
        ]
        _edit_billing_menu(billing, MagicMock())

    @patch("landlord.cli.billing_menu.questionary")
    def test_edit_item_cancel_type(self, mock_q):
        from landlord.cli.billing_menu import _edit_billing_menu

        billing = Billing(id=1, name="Apt 101", items=[
            BillingItem(description="Rent", amount=100000, item_type=ItemType.FIXED),
        ])
        mock_q.select.return_value.ask.side_effect = [
            "Editar Item",
            "Rent (R$ 1.000,00)",
            None,  # cancel type selection
            "Voltar",
        ]
        mock_q.text.return_value.ask.return_value = "Rent"
        _edit_billing_menu(billing, MagicMock())
