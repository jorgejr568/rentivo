from unittest.mock import MagicMock

from rentivo.models.billing import Billing
from rentivo.models.theme import DEFAULT_THEME, Theme
from rentivo.services.theme_service import ThemeService


class TestThemeService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = ThemeService(self.mock_repo)

    def test_get_theme_for_owner(self):
        expected = Theme(id=1, uuid="t-uuid", owner_type="user", owner_id=10, name="User Theme")
        self.mock_repo.get_by_owner.return_value = expected

        result = self.service.get_theme_for_owner("user", 10)

        self.mock_repo.get_by_owner.assert_called_once_with("user", 10)
        assert result is expected

    def test_resolve_theme_for_billing_with_billing_theme(self):
        """When billing has its own theme, returns it."""
        billing = Billing(id=1, uuid="b-uuid", name="Apt", owner_type="user", owner_id=10)
        billing_theme = Theme(id=5, uuid="bt-uuid", owner_type="billing", owner_id=1, name="Billing Theme")

        self.mock_repo.get_by_owner.return_value = billing_theme

        result = self.service.resolve_theme_for_billing(billing)

        self.mock_repo.get_by_owner.assert_called_once_with("billing", 1)
        assert result is billing_theme

    def test_resolve_theme_for_billing_falls_to_owner(self):
        """When billing has no theme but owner does, returns owner theme."""
        billing = Billing(id=1, uuid="b-uuid", name="Apt", owner_type="user", owner_id=10)
        owner_theme = Theme(id=3, uuid="ot-uuid", owner_type="user", owner_id=10, name="Owner Theme")

        def side_effect(owner_type, owner_id):
            if owner_type == "billing" and owner_id == 1:
                return None
            if owner_type == "user" and owner_id == 10:
                return owner_theme
            return None

        self.mock_repo.get_by_owner.side_effect = side_effect

        result = self.service.resolve_theme_for_billing(billing)

        assert result is owner_theme

    def test_resolve_theme_for_billing_falls_to_default(self):
        """When nothing found, returns DEFAULT_THEME."""
        billing = Billing(id=1, uuid="b-uuid", name="Apt", owner_type="user", owner_id=10)

        self.mock_repo.get_by_owner.return_value = None

        result = self.service.resolve_theme_for_billing(billing)

        assert result is DEFAULT_THEME

    def test_create_or_update_creates_new(self):
        """When no existing theme, creates a new one."""
        self.mock_repo.get_by_owner.return_value = None
        new_theme = Theme(id=1, uuid="new-uuid", owner_type="user", owner_id=10, primary="#FF0000")
        self.mock_repo.create.return_value = new_theme

        result = self.service.create_or_update_theme("user", 10, primary="#FF0000")

        self.mock_repo.create.assert_called_once()
        self.mock_repo.update.assert_not_called()
        assert result is new_theme

    def test_create_or_update_updates_existing(self):
        """When theme exists, updates it."""
        existing = Theme(id=1, uuid="ex-uuid", owner_type="user", owner_id=10, primary="#000000")
        self.mock_repo.get_by_owner.return_value = existing
        updated = Theme(id=1, uuid="ex-uuid", owner_type="user", owner_id=10, primary="#FF0000")
        self.mock_repo.update.return_value = updated

        result = self.service.create_or_update_theme("user", 10, primary="#FF0000")

        self.mock_repo.update.assert_called_once()
        self.mock_repo.create.assert_not_called()
        assert result is updated

    def test_delete_theme_success(self):
        """When theme exists, deletes it and returns True."""
        existing = Theme(id=7, uuid="del-uuid", owner_type="user", owner_id=10)
        self.mock_repo.get_by_owner.return_value = existing

        result = self.service.delete_theme("user", 10)

        self.mock_repo.delete.assert_called_once_with(7)
        assert result is True

    def test_delete_theme_not_found(self):
        """When no theme exists, returns False."""
        self.mock_repo.get_by_owner.return_value = None

        result = self.service.delete_theme("user", 10)

        self.mock_repo.delete.assert_not_called()
        assert result is False

    def test_get_by_uuid(self):
        """Cover line 60: get_by_uuid delegates to repo."""
        expected = Theme(id=1, uuid="t-uuid", owner_type="user", owner_id=10)
        self.mock_repo.get_by_uuid.return_value = expected

        result = self.service.get_by_uuid("t-uuid")

        self.mock_repo.get_by_uuid.assert_called_once_with("t-uuid")
        assert result is expected

    def test_get_by_uuid_not_found(self):
        """Cover line 60: get_by_uuid returns None when not found."""
        self.mock_repo.get_by_uuid.return_value = None

        result = self.service.get_by_uuid("nonexistent")

        assert result is None
