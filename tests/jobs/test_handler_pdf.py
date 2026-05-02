from unittest.mock import MagicMock, patch

import pytest

from rentivo.jobs.base import PermanentJobError


def _patches():
    """All collaborators the handler imports — so we can assert dispatch without DB."""
    return {
        "engine": patch("rentivo.jobs.handlers.pdf.get_engine"),
        "bill_repo": patch("rentivo.jobs.handlers.pdf.SQLAlchemyBillRepository"),
        "billing_repo": patch("rentivo.jobs.handlers.pdf.SQLAlchemyBillingRepository"),
        "user_repo": patch("rentivo.jobs.handlers.pdf.SQLAlchemyUserRepository"),
        "org_repo": patch("rentivo.jobs.handlers.pdf.SQLAlchemyOrganizationRepository"),
        "receipt_repo": patch("rentivo.jobs.handlers.pdf.SQLAlchemyReceiptRepository"),
        "theme_repo": patch("rentivo.jobs.handlers.pdf.SQLAlchemyThemeRepository"),
        "storage": patch("rentivo.jobs.handlers.pdf.get_storage"),
        "service_cls": patch("rentivo.jobs.handlers.pdf.BillService"),
    }


def test_handler_renders_and_marks_succeeded():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"] as svc_cls,
    ):
        # Engine.connect() context-manager returns a connection.
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn

        bill = MagicMock(id=42, billing_id=7)
        billing = MagicMock(id=7)
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = bill
        bill_repo_cls.return_value = bill_repo
        billing_repo = MagicMock()
        billing_repo.get_by_id.return_value = billing
        billing_repo_cls.return_value = billing_repo

        service = MagicMock()
        svc_cls.return_value = service

        from rentivo.jobs.handlers.pdf import handle_pdf_render

        handle_pdf_render({"bill_id": 42})

        bill_repo.get_by_id.assert_called_once_with(42)
        billing_repo.get_by_id.assert_called_once_with(7)
        service._render_pdf_sync.assert_called_once_with(bill, billing)


def test_handler_rejects_non_int_bill_id():
    from rentivo.jobs.handlers.pdf import handle_pdf_render

    with pytest.raises(PermanentJobError, match="bill_id"):
        handle_pdf_render({"bill_id": "42"})
    with pytest.raises(PermanentJobError, match="bill_id"):
        handle_pdf_render({})


def test_handler_dead_letters_when_bill_missing():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"],
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"],
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = None
        bill_repo_cls.return_value = bill_repo

        from rentivo.jobs.handlers.pdf import handle_pdf_render

        with pytest.raises(PermanentJobError, match="bill .* not found"):
            handle_pdf_render({"bill_id": 42})


def test_handler_dead_letters_when_billing_missing():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"],
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill = MagicMock(id=42, billing_id=7)
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = bill
        bill_repo_cls.return_value = bill_repo
        billing_repo = MagicMock()
        billing_repo.get_by_id.return_value = None
        billing_repo_cls.return_value = billing_repo

        from rentivo.jobs.handlers.pdf import handle_pdf_render

        with pytest.raises(PermanentJobError, match="billing .* not found"):
            handle_pdf_render({"bill_id": 42})


def test_handler_translates_pix_not_configured_to_permanent_and_marks_failed():
    from rentivo.services.bill_service import PIX_NOT_CONFIGURED_MESSAGE

    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"] as svc_cls,
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill = MagicMock(id=42, billing_id=7)
        billing = MagicMock(id=7)
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = bill
        bill_repo_cls.return_value = bill_repo
        billing_repo = MagicMock()
        billing_repo.get_by_id.return_value = billing
        billing_repo_cls.return_value = billing_repo

        service = MagicMock()
        service._render_pdf_sync.side_effect = ValueError(PIX_NOT_CONFIGURED_MESSAGE)
        svc_cls.return_value = service

        from rentivo.jobs.handlers.pdf import handle_pdf_render

        with pytest.raises(PermanentJobError, match="Configure a chave PIX"):
            handle_pdf_render({"bill_id": 42})

        bill_repo.update_pdf_render_status.assert_called_once_with(42, "failed")


def test_handler_propagates_other_exceptions_for_retry():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"] as svc_cls,
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill = MagicMock(id=42, billing_id=7)
        billing = MagicMock(id=7)
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = bill
        bill_repo_cls.return_value = bill_repo
        billing_repo = MagicMock()
        billing_repo.get_by_id.return_value = billing
        billing_repo_cls.return_value = billing_repo

        service = MagicMock()
        service._render_pdf_sync.side_effect = RuntimeError("S3 throttled")
        svc_cls.return_value = service

        from rentivo.jobs.handlers.pdf import handle_pdf_render

        with pytest.raises(RuntimeError, match="S3 throttled"):
            handle_pdf_render({"bill_id": 42})


def test_handler_unrelated_value_error_propagates_for_retry():
    """Only the PIX message is permanent. Other ValueErrors retry."""
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"] as svc_cls,
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill = MagicMock(id=42, billing_id=7)
        billing = MagicMock(id=7)
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = bill
        bill_repo_cls.return_value = bill_repo
        billing_repo = MagicMock()
        billing_repo.get_by_id.return_value = billing
        billing_repo_cls.return_value = billing_repo

        service = MagicMock()
        service._render_pdf_sync.side_effect = ValueError("Cannot update pdf_path for bill without an id")
        svc_cls.return_value = service

        from rentivo.jobs.handlers.pdf import handle_pdf_render

        with pytest.raises(ValueError, match="pdf_path"):
            handle_pdf_render({"bill_id": 42})


def test_handler_marks_succeeded_on_success():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"] as billing_repo_cls,
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"] as svc_cls,
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill = MagicMock(id=42, billing_id=7)
        billing = MagicMock(id=7)
        bill_repo = MagicMock()
        bill_repo.get_by_id.return_value = bill
        bill_repo_cls.return_value = bill_repo
        billing_repo = MagicMock()
        billing_repo.get_by_id.return_value = billing
        billing_repo_cls.return_value = billing_repo

        service = MagicMock()
        svc_cls.return_value = service

        from rentivo.jobs.handlers.pdf import handle_pdf_render

        handle_pdf_render({"bill_id": 42})

        # _render_pdf_sync sets status="succeeded" itself, but the handler also
        # explicitly sets it as a guard against partial implementations.
        bill_repo.update_pdf_render_status.assert_called_with(42, "succeeded")


def test_on_pdf_render_failed_sets_status_failed():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"] as bill_repo_cls,
        p["billing_repo"],
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"],
    ):
        conn = MagicMock()
        engine_mock.return_value.connect.return_value.__enter__.return_value = conn
        bill_repo = MagicMock()
        bill_repo_cls.return_value = bill_repo

        from rentivo.jobs.handlers.pdf import _on_pdf_render_failed

        _on_pdf_render_failed({"bill_id": 42})

        bill_repo.update_pdf_render_status.assert_called_once_with(42, "failed")


def test_on_pdf_render_failed_ignores_missing_bill_id():
    p = _patches()
    with (
        p["engine"] as engine_mock,
        p["bill_repo"],
        p["billing_repo"],
        p["user_repo"],
        p["org_repo"],
        p["receipt_repo"],
        p["theme_repo"],
        p["storage"],
        p["service_cls"],
    ):
        from rentivo.jobs.handlers.pdf import _on_pdf_render_failed

        _on_pdf_render_failed({})  # missing bill_id
        _on_pdf_render_failed({"bill_id": "not-int"})

        # Engine should not even be touched on bad payload.
        engine_mock.assert_not_called()


def test_handler_registers_under_pdf_render_key():
    """Importing the module side-effects-registers the handler."""
    from rentivo.jobs import registry
    from rentivo.jobs.handlers import pdf as _  # noqa: F401

    handler = registry.get("pdf.render")
    assert handler is not None
    fail_hook = registry.get_fail_hook("pdf.render")
    assert fail_hook is not None
