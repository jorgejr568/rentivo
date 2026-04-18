from contextlib import nullcontext
from unittest.mock import MagicMock, patch


class TestBuildServices:
    def test_returns_tuple(self):
        from rentivo.cli.app import _build_services

        services = MagicMock()
        result = _build_services(services)
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_returns_correct_types(self):
        from rentivo.cli.app import _build_services
        from rentivo.services.audit_service import AuditService
        from rentivo.services.bill_service import BillService
        from rentivo.services.billing_service import BillingService
        from rentivo.services.user_service import UserService

        services = MagicMock(
            billing_service=MagicMock(spec=BillingService),
            bill_service=MagicMock(spec=BillService),
            user_service=MagicMock(spec=UserService),
            audit_service=MagicMock(spec=AuditService),
        )
        billing_svc, bill_svc, user_svc, audit_svc = _build_services(services)
        assert isinstance(billing_svc, BillingService)
        assert isinstance(bill_svc, BillService)
        assert isinstance(user_svc, UserService)
        assert isinstance(audit_svc, AuditService)


class TestMainMenu:
    @patch("rentivo.cli.app.ConnectionServices.open")
    @patch("rentivo.cli.app._build_services")
    @patch("rentivo.cli.app.questionary")
    def test_exit_immediately(self, mock_q, mock_build, mock_open_services):
        from rentivo.cli.app import main_menu

        mock_open_services.return_value = nullcontext(MagicMock())
        mock_build.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_q.select.return_value.ask.return_value = "Sair"

        main_menu()
        mock_q.select.return_value.ask.assert_called()

    @patch("rentivo.cli.app.ConnectionServices.open")
    @patch("rentivo.cli.app._build_services")
    @patch("rentivo.cli.app.questionary")
    def test_none_exits(self, mock_q, mock_build, mock_open_services):
        from rentivo.cli.app import main_menu

        mock_open_services.return_value = nullcontext(MagicMock())
        mock_build.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_q.select.return_value.ask.return_value = None

        main_menu()

    @patch("rentivo.cli.app.ConnectionServices.open")
    @patch("rentivo.cli.app._build_services")
    @patch("rentivo.cli.app.questionary")
    @patch("rentivo.cli.app.list_billings_menu")
    def test_list_billings(self, mock_list, mock_q, mock_build, mock_open_services):
        from rentivo.cli.app import main_menu

        mock_open_services.return_value = nullcontext(MagicMock())
        mock_build.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_q.select.return_value.ask.side_effect = ["Listar Cobranças", "Sair"]

        main_menu()
        mock_list.assert_called_once()

    @patch("rentivo.cli.app.ConnectionServices.open")
    @patch("rentivo.cli.app._build_services")
    @patch("rentivo.cli.app.questionary")
    @patch("rentivo.cli.app.create_billing_menu")
    def test_create_billing(self, mock_create, mock_q, mock_build, mock_open_services):
        from rentivo.cli.app import main_menu

        mock_open_services.return_value = nullcontext(MagicMock())
        mock_build.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_q.select.return_value.ask.side_effect = ["Criar Nova Cobrança", "Sair"]

        main_menu()
        mock_create.assert_called_once()

    @patch("rentivo.cli.app.ConnectionServices.open")
    @patch("rentivo.cli.app._build_services")
    @patch("rentivo.cli.app.questionary")
    @patch("rentivo.cli.app.user_management_menu")
    def test_user_management(self, mock_user, mock_q, mock_build, mock_open_services):
        from rentivo.cli.app import main_menu

        mock_open_services.return_value = nullcontext(MagicMock())
        mock_build.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_q.select.return_value.ask.side_effect = ["Gerenciar Usuários", "Sair"]

        main_menu()
        mock_user.assert_called_once()

    @patch("rentivo.cli.app.ConnectionServices.open")
    @patch("rentivo.cli.app._build_services")
    @patch("rentivo.cli.app.questionary")
    def test_unrecognized_choice_loops(self, mock_q, mock_build, mock_open_services):
        """Cover branch 60->42: unrecognized choice loops back to menu."""
        from rentivo.cli.app import main_menu

        mock_open_services.return_value = nullcontext(MagicMock())
        mock_build.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        mock_q.select.return_value.ask.side_effect = ["Unknown Option", "Sair"]

        main_menu()
