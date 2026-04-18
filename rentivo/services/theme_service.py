from __future__ import annotations

import logging

from sqlalchemy import Connection

from rentivo.models.theme import DEFAULT_THEME, Theme
from rentivo.repositories.base import ThemeRepository
from rentivo.services._transaction import validate_transaction_binding

logger = logging.getLogger(__name__)


class ThemeService:
    def __init__(self, theme_repo: ThemeRepository, db_conn: Connection | None = None) -> None:
        self.theme_repo = theme_repo
        self.db_conn = db_conn
        validate_transaction_binding(self.db_conn, self.theme_repo)

    @property
    def transactional(self) -> bool:
        return self.db_conn is not None

    def _commit_transaction(self) -> None:
        if self.db_conn is not None:
            self.db_conn.commit()

    def _rollback_transaction(self) -> None:
        if self.db_conn is not None:
            self.db_conn.rollback()

    def get_theme_for_owner(self, owner_type: str, owner_id: int) -> Theme | None:
        return self.theme_repo.get_by_owner(owner_type, owner_id)

    def resolve_theme_for_billing(self, billing) -> Theme:
        """Resolve theme using hierarchy: billing -> org -> user -> DEFAULT_THEME.

        The billing object must have: id, owner_type, owner_id.
        For org-owned billings, checks both billing-level and org-level themes.
        """
        # 1. Check billing-level theme
        if billing.id is not None:
            theme = self.theme_repo.get_by_owner("billing", billing.id)
            if theme is not None:
                return theme

        # 2. Check owner-level theme (org or user)
        theme = self.theme_repo.get_by_owner(billing.owner_type, billing.owner_id)
        if theme is not None:
            return theme

        # 3. If billing is owned by org, also check the org creator's user theme
        # (not implemented — hierarchy is billing -> owner -> default)

        return DEFAULT_THEME

    def create_or_update_theme(self, owner_type: str, owner_id: int, **fields) -> Theme:
        existing = self.theme_repo.get_by_owner(owner_type, owner_id)
        try:
            if existing:
                for key, value in fields.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                result = self.theme_repo.update(existing)
            else:
                theme = Theme(owner_type=owner_type, owner_id=owner_id, **fields)
                result = self.theme_repo.create(theme)
            if self.transactional:
                self._commit_transaction()
        except Exception:
            if self.transactional:
                self._rollback_transaction()
            raise
        return result

    def delete_theme(self, owner_type: str, owner_id: int) -> bool:
        theme = self.theme_repo.get_by_owner(owner_type, owner_id)
        if theme and theme.id:
            try:
                self.theme_repo.delete(theme.id)
                if self.transactional:
                    self._commit_transaction()
            except Exception:
                if self.transactional:
                    self._rollback_transaction()
                raise
            logger.info("Theme deleted for %s/%s", owner_type, owner_id)
            return True
        return False

    def get_by_uuid(self, uuid: str) -> Theme | None:
        return self.theme_repo.get_by_uuid(uuid)
