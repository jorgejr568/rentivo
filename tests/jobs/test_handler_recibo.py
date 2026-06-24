from unittest.mock import MagicMock, patch

import pytest

from rentivo.jobs.base import PermanentJobError
from rentivo.models.bill import BillStatus


def _patches():
    """All collaborators the handler imports — so we can assert dispatch without DB."""
    return {
        "engine": patch("rentivo.jobs.handlers.recibo.get_engine"),
        "bill_repo": patch("rentivo.jobs.handlers.recibo.SQLAlchemyBillRepository"),
        "billing_repo": patch("rentivo.jobs.handlers.recibo.SQLAlchemyBillingRepository"),
        "user_repo": patch("rentivo.jobs.handlers.recibo.SQLAlchemyUserRepository"),
        "org_repo": patch("rentivo.jobs.handlers.recibo.SQLAlchemyOrganizationRepository"),
        "theme_repo": patch("rentivo.jobs.handlers.recibo.SQLAlchemyThemeRepository"),
        "storage": patch("rentivo.jobs.handlers.recibo.get_storage"),
        "service_cls": patch("rentivo.jobs.handlers.recibo.BillService"),
    }


def _wire(p, bill, billing):
    conn = MagicMock()
    p["engine_mock"].return_value.connect.return_value.__enter__.return_value = conn
    bill_repo = MagicMock()
    bill_repo.get_by_id.return_value = bill
    p["bill_repo_cls"].return_value = bill_repo
    billing_repo = MagicMock()
    billing_repo.get_by_id.return_value = billing
    p["billing_repo_cls"].return_value = billing_repo
    service = MagicMock()
    p["svc_cls"].return_value = service
    return bill_repo, billing_repo, service


def test_handler_renders_and_stores_recibo():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"] as svc_cls,
    ):
        bill = MagicMock(id=42, billing_id=7, status=BillStatus.PAID.value)
        billing = MagicMock(id=7)
        _, billing_repo, service = _wire(
            {
                "engine_mock": engine_mock,
                "bill_repo_cls": bill_repo_cls,
                "billing_repo_cls": billing_repo_cls,
                "svc_cls": svc_cls,
            },
            bill,
            billing,
        )

        from rentivo.jobs.handlers.recibo import handle_recibo_render

        handle_recibo_render({"bill_id": 42})

        billing_repo.get_by_id.assert_called_once_with(7)
        service.store_recibo.assert_called_once_with(bill, billing)


def test_handler_rejects_non_int_bill_id():
    from rentivo.jobs.handlers.recibo import handle_recibo_render

    with pytest.raises(PermanentJobError, match="bill_id"):
        handle_recibo_render({"bill_id": "42"})
    with pytest.raises(PermanentJobError, match="bill_id"):
        handle_recibo_render({})


def test_handler_dead_letters_when_bill_missing():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"],
        p["user_repo"],
        p["org_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"],
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = None
        bill_repo_cls.return_value = bill_repo

        from rentivo.jobs.handlers.recibo import handle_recibo_render

        with pytest.raises(PermanentJobError, match="bill .* not found"):
            handle_recibo_render({"bill_id": 42})


def test_handler_skips_when_bill_not_paid():
    """Status may revert to non-PAID before the job runs; the recibo must not be
    created in that case (no orphan quittance for an unpaid bill)."""
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"] as svc_cls,
    ):
        bill = MagicMock(id=42, billing_id=7, status=BillStatus.SENT.value)
        billing = MagicMock(id=7)
        _, billing_repo, service = _wire(
            {
                "engine_mock": engine_mock,
                "bill_repo_cls": bill_repo_cls,
                "billing_repo_cls": billing_repo_cls,
                "svc_cls": svc_cls,
            },
            bill,
            billing,
        )

        from rentivo.jobs.handlers.recibo import handle_recibo_render

        handle_recibo_render({"bill_id": 42})

        billing_repo.get_by_id.assert_not_called()
        service.store_recibo.assert_not_called()


def test_handler_dead_letters_when_billing_missing():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"],
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill = MagicMock(id=42, billing_id=7, status=BillStatus.PAID.value)
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = bill
        bill_repo_cls.return_value = bill_repo
        billing_repo = MagicMock()
        billing_repo.get_by_id.return_value = None
        billing_repo_cls.return_value = billing_repo

        from rentivo.jobs.handlers.recibo import handle_recibo_render

        with pytest.raises(PermanentJobError, match="billing .* not found"):
            handle_recibo_render({"bill_id": 42})


def test_handler_registers_under_recibo_render_key():
    from rentivo.jobs import registry
    from rentivo.jobs.handlers import recibo as _  # noqa: F401

    assert registry.get("recibo.render") is not None
