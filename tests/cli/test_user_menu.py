from unittest.mock import MagicMock, patch

from rentivo.models.user import User


class TestUserManagementMenu:
    @patch("rentivo.cli.user_menu.questionary")
    def test_back_exits(self, mock_q):
        from rentivo.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.return_value = "Voltar"
        mock_service = MagicMock()
        user_management_menu(mock_service, MagicMock())

    @patch("rentivo.cli.user_menu.questionary")
    def test_none_exits(self, mock_q):
        from rentivo.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.return_value = None
        mock_service = MagicMock()
        user_management_menu(mock_service, MagicMock())

    @patch("rentivo.cli.user_menu._create_user")
    @patch("rentivo.cli.user_menu.questionary")
    def test_route_criar_usuario(self, mock_q, mock_create):
        """Cover line 26-27: route to Criar Usuário."""
        from rentivo.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.side_effect = ["Criar Usuário", "Voltar"]
        mock_service = MagicMock()
        mock_audit = MagicMock()
        user_management_menu(mock_service, mock_audit)
        mock_create.assert_called_once_with(mock_service, mock_audit)

    @patch("rentivo.cli.user_menu._change_password")
    @patch("rentivo.cli.user_menu.questionary")
    def test_route_alterar_senha(self, mock_q, mock_change):
        """Cover line 28-29: route to Alterar Senha."""
        from rentivo.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.side_effect = ["Alterar Senha", "Voltar"]
        mock_service = MagicMock()
        mock_audit = MagicMock()
        user_management_menu(mock_service, mock_audit)
        mock_change.assert_called_once_with(mock_service, mock_audit)

    @patch("rentivo.cli.user_menu._list_users")
    @patch("rentivo.cli.user_menu.questionary")
    def test_route_listar_usuarios(self, mock_q, mock_list):
        """Cover line 30-31: route to Listar Usuários."""
        from rentivo.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.side_effect = ["Listar Usuários", "Voltar"]
        mock_service = MagicMock()
        user_management_menu(mock_service, MagicMock())
        mock_list.assert_called_once_with(mock_service)


class TestCreateUser:
    @patch("rentivo.cli.user_menu.questionary")
    def test_cancel_empty_username(self, mock_q):
        from rentivo.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = ""
        mock_service = MagicMock()
        _create_user(mock_service, MagicMock())
        mock_service.create_user.assert_not_called()

    @patch("rentivo.cli.user_menu.questionary")
    def test_cancel_empty_password(self, mock_q):
        from rentivo.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.return_value = ""
        mock_service = MagicMock()
        _create_user(mock_service, MagicMock())
        mock_service.create_user.assert_not_called()

    @patch("rentivo.cli.user_menu.questionary")
    def test_password_mismatch(self, mock_q):
        from rentivo.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["pass1", "pass2"]
        mock_service = MagicMock()
        _create_user(mock_service, MagicMock())
        mock_service.create_user.assert_not_called()

    @patch("rentivo.cli.user_menu.questionary")
    def test_success(self, mock_q):
        from rentivo.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["secret", "secret"]
        mock_service = MagicMock()
        mock_service.create_user.return_value = User(username="admin")
        _create_user(mock_service, MagicMock())
        mock_service.create_user.assert_called_once_with("admin", "secret")

    @patch("rentivo.cli.user_menu.questionary")
    def test_exception_handled(self, mock_q):
        from rentivo.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["secret", "secret"]
        mock_service = MagicMock()
        mock_service.create_user.side_effect = Exception("DB error")
        _create_user(mock_service, MagicMock())


class TestListUsers:
    @patch("rentivo.cli.user_menu.questionary")
    def test_empty(self, mock_q):
        from rentivo.cli.user_menu import _list_users

        mock_service = MagicMock()
        mock_service.list_users.return_value = []
        _list_users(mock_service)

    @patch("rentivo.cli.user_menu.questionary")
    def test_with_users(self, mock_q):
        from datetime import datetime

        from rentivo.cli.user_menu import _list_users

        mock_service = MagicMock()
        mock_service.list_users.return_value = [
            User(id=1, username="admin", created_at=datetime(2025, 1, 1)),
            User(id=2, username="user2", created_at=None),
        ]
        _list_users(mock_service)


class TestUserMenuUnrecognized:
    @patch("rentivo.cli.user_menu.questionary")
    def test_unrecognized_choice_loops(self, mock_q):
        """Cover branch 33->16: unrecognized choice loops back to menu."""
        from rentivo.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.side_effect = ["Unknown", "Voltar"]
        mock_service = MagicMock()
        user_management_menu(mock_service, MagicMock())


class TestChangePassword:
    @patch("rentivo.cli.user_menu.questionary")
    def test_no_users(self, mock_q):
        from rentivo.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = []
        _change_password(mock_service, MagicMock())
        mock_service.change_password.assert_not_called()

    @patch("rentivo.cli.user_menu.questionary")
    def test_cancel_select(self, mock_q):
        from rentivo.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "Voltar"
        _change_password(mock_service, MagicMock())
        mock_service.change_password.assert_not_called()

    @patch("rentivo.cli.user_menu.questionary")
    def test_cancel_empty_password(self, mock_q):
        from rentivo.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.return_value = ""
        _change_password(mock_service, MagicMock())
        mock_service.change_password.assert_not_called()

    @patch("rentivo.cli.user_menu.questionary")
    def test_password_mismatch(self, mock_q):
        from rentivo.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["new1", "new2"]
        _change_password(mock_service, MagicMock())
        mock_service.change_password.assert_not_called()

    @patch("rentivo.cli.user_menu.questionary")
    def test_success(self, mock_q):
        from rentivo.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["newpass", "newpass"]
        _change_password(mock_service, MagicMock())
        mock_service.change_password.assert_called_once_with("admin", "newpass")

    @patch("rentivo.cli.user_menu.questionary")
    def test_target_user_not_found_skips_audit(self, mock_q):
        """Cover branch 101->110: target_user is None, audit log is skipped."""
        from rentivo.cli.user_menu import _change_password

        mock_service = MagicMock()
        # list_users returns users but the selected username doesn't match
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "other_user"
        mock_q.password.return_value.ask.side_effect = ["newpass", "newpass"]
        mock_audit = MagicMock()
        _change_password(mock_service, mock_audit)
        mock_service.change_password.assert_called_once_with("other_user", "newpass")
        mock_audit.safe_log.assert_not_called()
