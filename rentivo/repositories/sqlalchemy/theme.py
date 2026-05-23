from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from ulid import ULID

from rentivo.models.theme import Theme
from rentivo.repositories.base import ThemeRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyThemeRepository(ThemeRepository):
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    @staticmethod
    def _row_to_theme(row: RowMapping) -> Theme:
        return Theme(
            id=row["id"],
            uuid=row["uuid"],
            owner_type=row["owner_type"],
            owner_id=row["owner_id"],
            name=row["name"],
            header_font=row["header_font"],
            text_font=row["text_font"],
            primary=row["primary_color"],
            primary_light=row["primary_light"],
            secondary=row["secondary"],
            secondary_dark=row["secondary_dark"],
            text_color=row["text_color"],
            text_contrast=row["text_contrast"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, theme: Theme) -> Theme:
        theme_uuid = str(ULID())
        now = _now()
        self.conn.execute(
            text(
                "INSERT INTO themes (uuid, owner_type, owner_id, name, header_font, text_font, "
                "primary_color, primary_light, secondary, secondary_dark, text_color, text_contrast, "
                "created_at, updated_at) "
                "VALUES (:uuid, :owner_type, :owner_id, :name, :header_font, :text_font, "
                ":primary_color, :primary_light, :secondary, :secondary_dark, :text_color, :text_contrast, "
                ":created_at, :updated_at)"
            ),
            {
                "uuid": theme_uuid,
                "owner_type": theme.owner_type,
                "owner_id": theme.owner_id,
                "name": theme.name,
                "header_font": theme.header_font,
                "text_font": theme.text_font,
                "primary_color": theme.primary,
                "primary_light": theme.primary_light,
                "secondary": theme.secondary,
                "secondary_dark": theme.secondary_dark,
                "text_color": theme.text_color,
                "text_contrast": theme.text_contrast,
                "created_at": now,
                "updated_at": now,
            },
        )
        self.conn.commit()
        return self.get_by_owner(theme.owner_type, theme.owner_id)  # type: ignore

    def get_by_id(self, theme_id: int) -> Theme | None:
        row = self.conn.execute(text("SELECT * FROM themes WHERE id = :id"), {"id": theme_id}).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_theme(row)

    def get_by_uuid(self, uuid: str) -> Theme | None:
        row = self.conn.execute(text("SELECT * FROM themes WHERE uuid = :uuid"), {"uuid": uuid}).mappings().fetchone()
        if row is None:
            return None
        return self._row_to_theme(row)

    def get_by_owner(self, owner_type: str, owner_id: int) -> Theme | None:
        row = (
            self.conn.execute(
                text("SELECT * FROM themes WHERE owner_type = :owner_type AND owner_id = :owner_id"),
                {"owner_type": owner_type, "owner_id": owner_id},
            )
            .mappings()
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_theme(row)

    def update(self, theme: Theme) -> Theme:
        self.conn.execute(
            text(
                "UPDATE themes SET name = :name, header_font = :header_font, text_font = :text_font, "
                "primary_color = :primary_color, primary_light = :primary_light, secondary = :secondary, "
                "secondary_dark = :secondary_dark, text_color = :text_color, text_contrast = :text_contrast, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            {
                "name": theme.name,
                "header_font": theme.header_font,
                "text_font": theme.text_font,
                "primary_color": theme.primary,
                "primary_light": theme.primary_light,
                "secondary": theme.secondary,
                "secondary_dark": theme.secondary_dark,
                "text_color": theme.text_color,
                "text_contrast": theme.text_contrast,
                "updated_at": _now(),
                "id": theme.id,
            },
        )
        self.conn.commit()
        if theme.id is None:
            raise ValueError("Cannot update theme without an id")
        result = self.get_by_id(theme.id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve theme after update (id={theme.id})")
        return result

    def delete(self, theme_id: int) -> None:
        self.conn.execute(text("DELETE FROM themes WHERE id = :id"), {"id": theme_id})
        self.conn.commit()
