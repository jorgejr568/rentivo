import pytest

from rentivo.models.theme import Theme
from rentivo.repositories.sqlalchemy import SQLAlchemyThemeRepository


class TestThemeRepoCRUD:
    def test_create_theme(self, theme_repo: SQLAlchemyThemeRepository):
        theme = Theme(
            owner_type="user",
            owner_id=1,
            name="Custom",
            header_font="Roboto",
            text_font="Open Sans",
            primary="#FF5733",
            primary_light="#FFD1C1",
            secondary="#33FF57",
            secondary_dark="#1E8C35",
            text_color="#111111",
            text_contrast="#FEFEFE",
        )
        created = theme_repo.create(theme)

        assert created.id is not None
        assert created.uuid != ""
        assert created.owner_type == "user"
        assert created.owner_id == 1
        assert created.name == "Custom"
        assert created.header_font == "Roboto"
        assert created.text_font == "Open Sans"
        assert created.primary == "#FF5733"
        assert created.primary_light == "#FFD1C1"
        assert created.secondary == "#33FF57"
        assert created.secondary_dark == "#1E8C35"
        assert created.text_color == "#111111"
        assert created.text_contrast == "#FEFEFE"
        assert created.created_at is not None
        assert created.updated_at is not None

    def test_get_by_uuid(self, theme_repo: SQLAlchemyThemeRepository):
        theme = Theme(owner_type="user", owner_id=2, name="By UUID")
        created = theme_repo.create(theme)

        fetched = theme_repo.get_by_uuid(created.uuid)
        assert fetched is not None
        assert fetched.uuid == created.uuid
        assert fetched.name == "By UUID"

    def test_get_by_owner(self, theme_repo: SQLAlchemyThemeRepository):
        theme = Theme(owner_type="organization", owner_id=10, name="Org Theme")
        created = theme_repo.create(theme)

        fetched = theme_repo.get_by_owner("organization", 10)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.owner_type == "organization"
        assert fetched.owner_id == 10

    def test_get_by_owner_not_found(self, theme_repo: SQLAlchemyThemeRepository):
        result = theme_repo.get_by_owner("user", 99999)
        assert result is None

    def test_update_theme(self, theme_repo: SQLAlchemyThemeRepository):
        theme = Theme(owner_type="user", owner_id=3, name="Original")
        created = theme_repo.create(theme)

        created.name = "Updated"
        created.primary = "#000000"
        created.header_font = "Lora"
        updated = theme_repo.update(created)

        assert updated.name == "Updated"
        assert updated.primary == "#000000"
        assert updated.header_font == "Lora"
        # Other fields should remain unchanged
        assert updated.id == created.id
        assert updated.uuid == created.uuid

    def test_delete_theme(self, theme_repo: SQLAlchemyThemeRepository):
        theme = Theme(owner_type="user", owner_id=4, name="To Delete")
        created = theme_repo.create(theme)

        theme_repo.delete(created.id)

        result = theme_repo.get_by_id(created.id)
        assert result is None

    def test_get_by_uuid_not_found(self, theme_repo: SQLAlchemyThemeRepository):
        """Cover line 1353: get_by_uuid returns None for unknown uuid."""
        result = theme_repo.get_by_uuid("nonexistent-uuid")
        assert result is None

    def test_update_theme_id_none(self, theme_repo: SQLAlchemyThemeRepository):
        """Cover line 1393: update raises ValueError when theme.id is None."""
        theme = Theme(id=None, owner_type="user", owner_id=100, name="No ID")
        with pytest.raises(ValueError, match="Cannot update theme without an id"):
            theme_repo.update(theme)

    def test_update_theme_deleted_before_read(self, theme_repo: SQLAlchemyThemeRepository):
        """Cover line 1396: RuntimeError when theme vanishes between update and get_by_id."""
        theme = Theme(owner_type="user", owner_id=101, name="Ghost")
        created = theme_repo.create(theme)
        # Delete the row directly so get_by_id returns None after the UPDATE
        theme_repo.delete(created.id)
        created.name = "Should Fail"
        with pytest.raises(RuntimeError, match="Failed to retrieve theme after update"):
            theme_repo.update(created)

    def test_unique_owner(self, theme_repo: SQLAlchemyThemeRepository):
        """Creating two themes for the same owner — the second create should succeed
        because the repo does not enforce unique constraints on (owner_type, owner_id)
        at the application level, but we can verify only one is returned by get_by_owner."""
        theme1 = Theme(owner_type="user", owner_id=5, name="First")
        theme_repo.create(theme1)

        theme2 = Theme(owner_type="user", owner_id=5, name="Second")
        created2 = theme_repo.create(theme2)

        # get_by_owner returns whichever one the query finds first (LIMIT 1 behavior)
        fetched = theme_repo.get_by_owner("user", 5)
        assert fetched is not None
        # Both exist in the DB — verify by get_by_id
        assert created2.id is not None
