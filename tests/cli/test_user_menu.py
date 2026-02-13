from unittest.mock import MagicMock, patch

from landlord.models.user import User


class TestUserManagementMenu:
    @patch("landlord.cli.user_menu.questionary")
    def test_back_exits(self, mock_q):
        from landlord.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.return_value = "Voltar"
        mock_service = MagicMock()
        user_management_menu(mock_service)

    @patch("landlord.cli.user_menu.questionary")
    def test_none_exits(self, mock_q):
        from landlord.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.return_value = None
        mock_service = MagicMock()
        user_management_menu(mock_service)

    @patch("landlord.cli.user_menu._create_user")
    @patch("landlord.cli.user_menu.questionary")
    def test_route_criar_usuario(self, mock_q, mock_create):
        """Cover line 26-27: route to Criar Usuário."""
        from landlord.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.side_effect = ["Criar Usuário", "Voltar"]
        mock_service = MagicMock()
        user_management_menu(mock_service)
        mock_create.assert_called_once_with(mock_service)

    @patch("landlord.cli.user_menu._change_password")
    @patch("landlord.cli.user_menu.questionary")
    def test_route_alterar_senha(self, mock_q, mock_change):
        """Cover line 28-29: route to Alterar Senha."""
        from landlord.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.side_effect = ["Alterar Senha", "Voltar"]
        mock_service = MagicMock()
        user_management_menu(mock_service)
        mock_change.assert_called_once_with(mock_service)

    @patch("landlord.cli.user_menu._list_users")
    @patch("landlord.cli.user_menu.questionary")
    def test_route_listar_usuarios(self, mock_q, mock_list):
        """Cover line 30-31: route to Listar Usuários."""
        from landlord.cli.user_menu import user_management_menu

        mock_q.select.return_value.ask.side_effect = ["Listar Usuários", "Voltar"]
        mock_service = MagicMock()
        user_management_menu(mock_service)
        mock_list.assert_called_once_with(mock_service)


class TestCreateUser:
    @patch("landlord.cli.user_menu.questionary")
    def test_cancel_empty_username(self, mock_q):
        from landlord.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = ""
        mock_service = MagicMock()
        _create_user(mock_service)
        mock_service.create_user.assert_not_called()

    @patch("landlord.cli.user_menu.questionary")
    def test_cancel_empty_password(self, mock_q):
        from landlord.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.return_value = ""
        mock_service = MagicMock()
        _create_user(mock_service)
        mock_service.create_user.assert_not_called()

    @patch("landlord.cli.user_menu.questionary")
    def test_password_mismatch(self, mock_q):
        from landlord.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["pass1", "pass2"]
        mock_service = MagicMock()
        _create_user(mock_service)
        mock_service.create_user.assert_not_called()

    @patch("landlord.cli.user_menu.questionary")
    def test_success(self, mock_q):
        from landlord.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["secret", "secret"]
        mock_service = MagicMock()
        mock_service.create_user.return_value = User(username="admin")
        _create_user(mock_service)
        mock_service.create_user.assert_called_once_with("admin", "secret")

    @patch("landlord.cli.user_menu.questionary")
    def test_exception_handled(self, mock_q):
        from landlord.cli.user_menu import _create_user

        mock_q.text.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["secret", "secret"]
        mock_service = MagicMock()
        mock_service.create_user.side_effect = Exception("DB error")
        _create_user(mock_service)


class TestListUsers:
    @patch("landlord.cli.user_menu.questionary")
    def test_empty(self, mock_q):
        from landlord.cli.user_menu import _list_users

        mock_service = MagicMock()
        mock_service.list_users.return_value = []
        _list_users(mock_service)

    @patch("landlord.cli.user_menu.questionary")
    def test_with_users(self, mock_q):
        from datetime import datetime

        from landlord.cli.user_menu import _list_users

        mock_service = MagicMock()
        mock_service.list_users.return_value = [
            User(id=1, username="admin", created_at=datetime(2025, 1, 1)),
            User(id=2, username="user2", created_at=None),
        ]
        _list_users(mock_service)


class TestChangePassword:
    @patch("landlord.cli.user_menu.questionary")
    def test_no_users(self, mock_q):
        from landlord.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = []
        _change_password(mock_service)
        mock_service.change_password.assert_not_called()

    @patch("landlord.cli.user_menu.questionary")
    def test_cancel_select(self, mock_q):
        from landlord.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "Voltar"
        _change_password(mock_service)
        mock_service.change_password.assert_not_called()

    @patch("landlord.cli.user_menu.questionary")
    def test_cancel_empty_password(self, mock_q):
        from landlord.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.return_value = ""
        _change_password(mock_service)
        mock_service.change_password.assert_not_called()

    @patch("landlord.cli.user_menu.questionary")
    def test_password_mismatch(self, mock_q):
        from landlord.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["new1", "new2"]
        _change_password(mock_service)
        mock_service.change_password.assert_not_called()

    @patch("landlord.cli.user_menu.questionary")
    def test_success(self, mock_q):
        from landlord.cli.user_menu import _change_password

        mock_service = MagicMock()
        mock_service.list_users.return_value = [User(username="admin")]
        mock_q.select.return_value.ask.return_value = "admin"
        mock_q.password.return_value.ask.side_effect = ["newpass", "newpass"]
        _change_password(mock_service)
        mock_service.change_password.assert_called_once_with("admin", "newpass")
