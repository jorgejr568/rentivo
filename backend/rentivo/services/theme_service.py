from __future__ import annotations

from dataclasses import dataclass

import structlog

from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import ItemType
from rentivo.models.theme import DEFAULT_THEME, Theme
from rentivo.observability import traced
from rentivo.pdf.invoice import InvoicePDF
from rentivo.repositories.base import ThemeRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ResolvedTheme:
    """A resolved theme plus where in the precedence chain it came from."""

    theme: Theme
    source: str  # "billing" | "organization" | "user" | "default"


class ThemeService:
    def __init__(self, theme_repo: ThemeRepository) -> None:
        self.theme_repo = theme_repo

    @traced("theme.get_theme_for_owner")
    def get_theme_for_owner(self, owner_type: str, owner_id: int) -> Theme | None:
        return self.theme_repo.get_by_owner(owner_type, owner_id)

    @traced("theme.resolve_theme_with_source")
    def resolve_theme_with_source(self, billing) -> ResolvedTheme:
        """Resolve theme + source using hierarchy: billing -> owner -> DEFAULT_THEME.

        The billing object must have: id, owner_type, owner_id.
        """
        # 1. Check billing-level theme
        if billing.id is not None:
            theme = self.theme_repo.get_by_owner("billing", billing.id)
            if theme is not None:
                return ResolvedTheme(theme=theme, source="billing")

        # 2. Check owner-level theme (org or user)
        theme = self.theme_repo.get_by_owner(billing.owner_type, billing.owner_id)
        if theme is not None:
            return ResolvedTheme(theme=theme, source=billing.owner_type)

        return ResolvedTheme(theme=DEFAULT_THEME, source="default")

    @traced("theme.resolve_theme_for_billing")
    def resolve_theme_for_billing(self, billing) -> Theme:
        """Resolve theme using hierarchy: billing -> org -> user -> DEFAULT_THEME."""
        return self.resolve_theme_with_source(billing).theme

    @traced("theme.render_preview")
    def render_preview(self, theme: Theme) -> bytes:
        sample_bill = Bill(
            billing_id=0,
            reference_month="2026-01",
            total_amount=150000,
            line_items=[
                BillLineItem(description="Aluguel", amount=120000, item_type=ItemType.FIXED, sort_order=0),
                BillLineItem(description="Água", amount=15000, item_type=ItemType.VARIABLE, sort_order=1),
                BillLineItem(description="Luz", amount=15000, item_type=ItemType.VARIABLE, sort_order=2),
            ],
            notes="Exemplo de fatura para visualização do tema.",
            due_date="2026-01-15",
        )
        return bytes(InvoicePDF().generate(sample_bill, "Exemplo", theme=theme))

    @traced("theme.create_or_update_theme")
    def create_or_update_theme(self, owner_type: str, owner_id: int, **fields) -> Theme:
        existing = self.theme_repo.get_by_owner(owner_type, owner_id)
        if existing:
            for key, value in fields.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            return self.theme_repo.update(existing)
        theme = Theme(owner_type=owner_type, owner_id=owner_id, **fields)
        return self.theme_repo.create(theme)

    @traced("theme.delete_theme")
    def delete_theme(self, owner_type: str, owner_id: int) -> bool:
        theme = self.theme_repo.get_by_owner(owner_type, owner_id)
        if theme and theme.id:
            self.theme_repo.delete(theme.id)
            logger.info("theme_deleted", owner_type=owner_type, owner_id=owner_id)
            return True
        return False

    @traced("theme.get_by_uuid")
    def get_by_uuid(self, uuid: str) -> Theme | None:
        return self.theme_repo.get_by_uuid(uuid)
