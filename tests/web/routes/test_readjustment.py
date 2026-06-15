from unittest.mock import AsyncMock, patch

import pytest

from rentivo.encryption.base64 import Base64Backend
from rentivo.models.billing import BillingItem, ItemType, ReadjustmentIndex
from rentivo.repositories.sqlalchemy import SQLAlchemyBillingRepository
from tests.web.conftest import create_billing_in_db, get_audit_logs


def _billing_with_index(test_engine, index=ReadjustmentIndex.IGPM):
    return create_billing_in_db(
        test_engine,
        name="Apt 1",
        items=[BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED)],
        readjustment_index=index,
        readjustment_month=6,
    )


class TestReadjustGet:
    def test_preview_shows_suggested_pct(self, auth_client, test_engine):
        billing = _billing_with_index(test_engine)
        with patch("web.routes.readjustment.BcbSgsClient") as cls:
            cls.return_value.fetch_accumulated = AsyncMock(return_value=5.0)
            resp = auth_client.get(f"/billings/{billing.uuid}/readjust")
        assert resp.status_code == 200
        assert "5.00%" in resp.text or "5,00" in resp.text

    def test_preview_bcb_failure_falls_back_to_manual(self, auth_client, test_engine):
        billing = _billing_with_index(test_engine)
        with patch("web.routes.readjustment.BcbSgsClient") as cls:
            cls.return_value.fetch_accumulated = AsyncMock(return_value=None)
            resp = auth_client.get(f"/billings/{billing.uuid}/readjust")
        assert resp.status_code == 200
        assert "manualmente" in resp.text

    def test_preview_not_found(self, auth_client):
        resp = auth_client.get("/billings/nonexistent/readjust", follow_redirects=False)
        assert resp.status_code in (302, 404)

    def test_preview_forbidden_other_user(self, auth_client, test_engine):
        from rentivo.models.user import User
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository

        with test_engine.connect() as conn:
            other = SQLAlchemyUserRepository(conn, Base64Backend()).create(User(email="x@y.com", password_hash="h"))
            conn.commit()
        billing = create_billing_in_db(test_engine, owner_type="user", owner_id=other.id)
        resp = auth_client.get(f"/billings/{billing.uuid}/readjust", follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_preview_no_fixed_items_redirects(self, auth_client, test_engine):
        billing = create_billing_in_db(
            test_engine,
            items=[BillingItem(description="Água", amount=0, item_type=ItemType.VARIABLE)],
            readjustment_index=ReadjustmentIndex.IGPM,
        )
        resp = auth_client.get(f"/billings/{billing.uuid}/readjust", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == f"/billings/{billing.uuid}"

    def test_preview_none_index_skips_bcb(self, auth_client, test_engine):
        billing = create_billing_in_db(
            test_engine,
            items=[BillingItem(description="Aluguel", amount=285000, item_type=ItemType.FIXED)],
        )  # default readjustment_index == none
        with patch("web.routes.readjustment.BcbSgsClient") as cls:
            resp = auth_client.get(f"/billings/{billing.uuid}/readjust")
        assert resp.status_code == 200
        assert "Nenhum" in resp.text
        cls.assert_not_called()


class TestReadjustDetailLink:
    def test_detail_shows_readjust_link_with_fixed_item(self, auth_client, test_engine):
        billing = _billing_with_index(test_engine)
        resp = auth_client.get(f"/billings/{billing.uuid}")
        assert resp.status_code == 200
        assert f"/billings/{billing.uuid}/readjust" in resp.text

    def test_detail_hides_readjust_link_without_fixed_item(self, auth_client, test_engine):
        billing = create_billing_in_db(
            test_engine,
            items=[BillingItem(description="Água", amount=0, item_type=ItemType.VARIABLE)],
        )
        resp = auth_client.get(f"/billings/{billing.uuid}")
        assert resp.status_code == 200
        assert f"/billings/{billing.uuid}/readjust" not in resp.text


class TestReadjustPost:
    def test_apply_with_override(self, auth_client, test_engine, csrf_token):
        billing = _billing_with_index(test_engine)
        resp = auth_client.post(
            f"/billings/{billing.uuid}/readjust",
            data={"csrf_token": csrf_token, "pct": "10,00"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillingRepository(conn, Base64Backend()).get_by_uuid(billing.uuid)
        assert reloaded.items[0].amount == 313500
        assert reloaded.last_readjustment_date is not None
        logs = get_audit_logs(test_engine, event_type="billing.readjusted")
        assert len(logs) == 1
        assert logs[0].metadata["index"] == "igpm"

    def test_apply_invalid_pct_redirects(self, auth_client, test_engine, csrf_token):
        billing = _billing_with_index(test_engine)
        resp = auth_client.post(
            f"/billings/{billing.uuid}/readjust",
            data={"csrf_token": csrf_token, "pct": "abc"},
            follow_redirects=False,
        )
        assert resp.status_code == 302  # flash + back to preview
        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillingRepository(conn, Base64Backend()).get_by_uuid(billing.uuid)
        assert reloaded.items[0].amount == 285000  # untouched

    def test_apply_empty_pct_redirects(self, auth_client, test_engine, csrf_token):
        billing = _billing_with_index(test_engine)
        resp = auth_client.post(
            f"/billings/{billing.uuid}/readjust",
            data={"csrf_token": csrf_token, "pct": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    @pytest.mark.parametrize("raw", ["inf", "nan", "-100", "5000"])
    def test_apply_non_finite_or_out_of_range_pct_redirects(self, auth_client, test_engine, csrf_token, raw):
        billing = _billing_with_index(test_engine)
        resp = auth_client.post(
            f"/billings/{billing.uuid}/readjust",
            data={"csrf_token": csrf_token, "pct": raw},
            follow_redirects=False,
        )
        assert resp.status_code == 302  # flash + back to preview, no mutation
        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillingRepository(conn, Base64Backend()).get_by_uuid(billing.uuid)
        assert reloaded.items[0].amount == 285000  # untouched

    @pytest.mark.parametrize("raw", ["10,5", "10.5"])
    def test_apply_valid_decimal_pct_applies(self, auth_client, test_engine, csrf_token, raw):
        billing = _billing_with_index(test_engine)
        resp = auth_client.post(
            f"/billings/{billing.uuid}/readjust",
            data={"csrf_token": csrf_token, "pct": raw},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with test_engine.connect() as conn:
            reloaded = SQLAlchemyBillingRepository(conn, Base64Backend()).get_by_uuid(billing.uuid)
        assert reloaded.items[0].amount == 314925  # 285000 * 1.105

    def test_apply_requires_csrf(self, auth_client, test_engine):
        billing = _billing_with_index(test_engine)
        resp = auth_client.post(
            f"/billings/{billing.uuid}/readjust",
            data={"pct": "10,00"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
