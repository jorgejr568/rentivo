from __future__ import annotations

from sqlalchemy import Connection, text

from rentivo.observability import traced
from rentivo.repositories.base import PixWebhookEventRepository
from rentivo.repositories.sqlalchemy._common import _now


class SQLAlchemyPixWebhookEventRepository(PixWebhookEventRepository):
    """``pix_webhook_events`` ledger backing webhook idempotency / replay drop.

    The ``UNIQUE(provider, event_id)`` constraint (REN-25) is the dedup key.
    ``record_if_new`` relies on it via dialect-appropriate "insert, ignore on
    conflict" SQL and reports whether *this* delivery won the race — the single
    signal the route uses to decide between "process" and "replay no-op".
    """

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def _insert_ignore_prefix(self) -> str:
        # Portable "insert, skip on unique conflict": SQLite/PostgreSQL spell it
        # INSERT ... ON CONFLICT DO NOTHING; MySQL (prod, mysql+pymysql) has no
        # ON CONFLICT and uses INSERT IGNORE instead.
        return "INSERT IGNORE INTO" if self.conn.dialect.name == "mysql" else "INSERT INTO"

    def _conflict_suffix(self) -> str:
        return "" if self.conn.dialect.name == "mysql" else " ON CONFLICT (provider, event_id) DO NOTHING"

    @traced("pix_webhook_event_repo.record_if_new")
    def record_if_new(
        self,
        *,
        provider: str,
        event_id: str,
        event_type: str,
        status: str,
        charge_id: str | None = None,
        external_reference: str | None = None,
        e2eid: str | None = None,
        bill_id: int | None = None,
    ) -> bool:
        stmt = text(
            f"{self._insert_ignore_prefix()} pix_webhook_events "
            "(provider, event_id, charge_id, external_reference, e2eid, "
            "event_type, status, received_at, bill_id) "
            "VALUES (:provider, :event_id, :charge_id, :external_reference, :e2eid, "
            ":event_type, :status, :received_at, :bill_id)"
            f"{self._conflict_suffix()}"
        )
        result = self.conn.execute(
            stmt,
            {
                "provider": provider,
                "event_id": event_id,
                "charge_id": charge_id,
                "external_reference": external_reference,
                "e2eid": e2eid,
                "event_type": event_type,
                "status": status,
                "received_at": _now(),
                "bill_id": bill_id,
            },
        )
        self.conn.commit()
        # rowcount is 1 for a fresh insert, 0 when the unique conflict dropped it.
        return result.rowcount > 0

    @traced("pix_webhook_event_repo.set_bill_id")
    def set_bill_id(self, *, provider: str, event_id: str, bill_id: int) -> None:
        self.conn.execute(
            text(
                "UPDATE pix_webhook_events SET bill_id = :bill_id WHERE provider = :provider AND event_id = :event_id"
            ),
            {"bill_id": bill_id, "provider": provider, "event_id": event_id},
        )
        self.conn.commit()
