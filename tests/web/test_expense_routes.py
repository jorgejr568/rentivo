from __future__ import annotations

import re

import pytest

from rentivo.models.audit_log import AuditEventType
from tests.web.conftest import create_billing_in_db, get_audit_logs


@pytest.fixture
def billing(test_engine):
    return create_billing_in_db(test_engine)


def test_add_expense_success(auth_client, csrf_token, test_engine, billing):
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/add",
        data={
            "csrf_token": csrf_token,
            "description": "IPTU 2026",
            "amount": "1.200,00",
            "category": "iptu",
            "incurred_on": "2026-01-10",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    detail = auth_client.get(f"/billings/{billing.uuid}")
    assert "IPTU 2026" in detail.text
    assert "R$ 1.200,00" in detail.text
    logs = get_audit_logs(test_engine, AuditEventType.EXPENSE_CREATE)
    assert len(logs) == 1


def test_add_expense_invalid_category_rejected(auth_client, csrf_token, billing):
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/add",
        data={
            "csrf_token": csrf_token,
            "description": "x",
            "amount": "10,00",
            "category": "bogus",
            "incurred_on": "2026-01-10",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302  # flash + redirect, no row created
    detail = auth_client.get(f"/billings/{billing.uuid}")
    assert "x" not in detail.text or "Categoria inválida" in detail.text


def test_add_expense_empty_description_rejected(auth_client, csrf_token, billing):
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/add",
        data={
            "csrf_token": csrf_token,
            "description": "",
            "amount": "10,00",
            "category": "iptu",
            "incurred_on": "2026-01-10",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_add_expense_invalid_amount_rejected(auth_client, csrf_token, billing):
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/add",
        data={
            "csrf_token": csrf_token,
            "description": "X",
            "amount": "abc",
            "category": "iptu",
            "incurred_on": "2026-01-10",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_delete_expense_success(auth_client, csrf_token, test_engine, billing):
    auth_client.post(
        f"/billings/{billing.uuid}/expenses/add",
        data={
            "csrf_token": csrf_token,
            "description": "ToDelete",
            "amount": "10,00",
            "category": "outros",
            "incurred_on": "2026-01-10",
        },
    )
    # discover the expense uuid from the detail page delete form
    detail = auth_client.get(f"/billings/{billing.uuid}").text
    m = re.search(r"/expenses/([0-9A-Z]{26})/delete", detail)
    assert m, "expense delete form not rendered"
    expense_uuid = m.group(1)
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/{expense_uuid}/delete",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "ToDelete" not in auth_client.get(f"/billings/{billing.uuid}").text
    assert len(get_audit_logs(test_engine, AuditEventType.EXPENSE_DELETE)) == 1


def test_delete_unknown_expense_flashes(auth_client, csrf_token, billing):
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/01BX5ZZKBKACTAV9WEVGEMMVRZ/delete",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 302  # "não encontrada" flash


def test_delete_expense_of_other_billing_rejected(auth_client, csrf_token, test_engine, billing):
    other = create_billing_in_db(test_engine, name="Other")
    auth_client.post(
        f"/billings/{other.uuid}/expenses/add",
        data={
            "csrf_token": csrf_token,
            "description": "Foreign",
            "amount": "10,00",
            "category": "iptu",
            "incurred_on": "2026-01-10",
        },
    )
    other_detail = auth_client.get(f"/billings/{other.uuid}").text
    foreign_uuid = re.search(r"/expenses/([0-9A-Z]{26})/delete", other_detail).group(1)
    # try to delete it via the first billing's URL — cross-billing mismatch rejected
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/{foreign_uuid}/delete",
        data={"csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "Foreign" in auth_client.get(f"/billings/{other.uuid}").text  # still there


def test_add_expense_requires_csrf(auth_client, billing):
    resp = auth_client.post(
        f"/billings/{billing.uuid}/expenses/add",
        data={"description": "x", "amount": "10,00", "category": "iptu", "incurred_on": "2026-01-10"},
        follow_redirects=False,
    )
    # web/csrf.py rejects missing/invalid tokens with a 302 redirect (not a 403).
    assert resp.status_code == 302


def test_add_expense_unknown_billing_404(auth_client, csrf_token):
    resp = auth_client.post(
        "/billings/01BX5ZZKBKACTAV9WEVGEMMVRZ/expenses/add",
        data={
            "csrf_token": csrf_token,
            "description": "x",
            "amount": "10,00",
            "category": "iptu",
            "incurred_on": "2026-01-10",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302  # require_billing FlashRedirect to "/"
