"""Integration tests verifying audit log entries are created for web operations."""

from __future__ import annotations

from rentivo.models.audit_log import AuditEventType
from tests.web.conftest import create_billing_in_db, generate_bill_in_db, get_audit_logs


class TestAuthAuditLogs:
    def test_login_creates_audit_log(self, client, test_engine):
        """Successful login creates a user.login audit entry."""
        from rentivo.repositories.sqlalchemy import SQLAlchemyUserRepository
        from rentivo.services.user_service import UserService

        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            svc = UserService(user_repo)
            svc.create_user("audituser", "pass123")

        client.post("/login", data={"username": "audituser", "password": "pass123"})

        logs = get_audit_logs(test_engine, AuditEventType.USER_LOGIN)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "user"
        assert log.actor_username == "audituser"

    def test_failed_login_creates_audit_log(self, client, test_engine):
        """Failed login creates a user.login_failed audit entry."""
        client.post("/login", data={"username": "nobody", "password": "wrong"})

        logs = get_audit_logs(test_engine, AuditEventType.USER_LOGIN_FAILED)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.new_state.get("username") == "nobody"
        assert log.metadata.get("ip") is not None

    def test_change_password_creates_audit_log(self, auth_client, test_engine, csrf_token):
        """Password change creates a user.change_password audit entry."""
        auth_client.post(
            "/change-password",
            data={
                "csrf_token": csrf_token,
                "current_password": "testpass",
                "new_password": "newpass123",
                "confirm_password": "newpass123",
            },
        )

        logs = get_audit_logs(test_engine, AuditEventType.USER_CHANGE_PASSWORD)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "user"

    def test_logout_creates_audit_log(self, auth_client, test_engine):
        """Logout creates a user.logout audit entry."""
        auth_client.post("/logout", follow_redirects=False)

        logs = get_audit_logs(test_engine, AuditEventType.USER_LOGOUT)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "user"
        assert log.actor_username == "testuser"


class TestBillingAuditLogs:
    def test_create_billing_creates_audit_log(self, auth_client, test_engine, csrf_token):
        """Creating a billing creates a billing.create audit entry."""
        auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Audit Test Billing",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "1000,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )

        logs = get_audit_logs(test_engine, AuditEventType.BILLING_CREATE)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "billing"
        assert log.new_state is not None
        assert log.new_state["name"] == "Audit Test Billing"

    def test_edit_billing_creates_audit_log(self, auth_client, test_engine, csrf_token):
        """Editing a billing creates a billing.update audit entry with previous_state."""
        billing = create_billing_in_db(test_engine)

        auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "Updated Name",
                "description": "Updated",
                "pix_key": "new@pix",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "2850,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )

        logs = get_audit_logs(test_engine, AuditEventType.BILLING_UPDATE)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "billing"
        assert log.previous_state is not None
        assert log.new_state is not None
        assert log.previous_state["name"] == "Apt 101"
        assert log.new_state["name"] == "Updated Name"

    def test_delete_billing_creates_audit_log(self, auth_client, test_engine, csrf_token):
        """Deleting a billing creates a billing.delete audit entry with previous_state."""
        billing = create_billing_in_db(test_engine)

        auth_client.post(
            f"/billings/{billing.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        logs = get_audit_logs(test_engine, AuditEventType.BILLING_DELETE)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "billing"
        assert log.previous_state is not None
        assert log.new_state is None


class TestBillAuditLogs:
    def test_generate_bill_creates_audit_log(self, auth_client, test_engine, csrf_token, tmp_path):
        """Generating a bill creates a bill.create audit entry."""
        from unittest.mock import patch

        billing = create_billing_in_db(test_engine)

        with patch("web.deps.get_storage") as mock_storage:
            from rentivo.storage.local import LocalStorage

            mock_storage.return_value = LocalStorage(str(tmp_path))

            auth_client.post(
                f"/billings/{billing.uuid}/bills/generate",
                data={
                    "csrf_token": csrf_token,
                    "reference_month": "2025-03",
                    "due_date": "10/04/2025",
                    "notes": "test",
                },
                follow_redirects=False,
            )

        logs = get_audit_logs(test_engine, AuditEventType.BILL_CREATE)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "bill"
        assert log.new_state is not None

    def test_toggle_paid_creates_audit_log(self, auth_client, test_engine, csrf_token, tmp_path):
        """Toggling paid creates a bill.toggle_paid audit entry."""
        from unittest.mock import patch

        billing = create_billing_in_db(test_engine)

        with patch("web.deps.get_storage") as mock_storage:
            from rentivo.storage.local import LocalStorage

            mock_storage.return_value = LocalStorage(str(tmp_path))
            bill = generate_bill_in_db(test_engine, billing, tmp_path)

            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/toggle-paid",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        logs = get_audit_logs(test_engine, AuditEventType.BILL_TOGGLE_PAID)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "bill"
        assert log.previous_state is not None
        assert log.new_state is not None

    def test_delete_bill_creates_audit_log(self, auth_client, test_engine, csrf_token, tmp_path):
        """Deleting a bill creates a bill.delete audit entry."""
        from unittest.mock import patch

        billing = create_billing_in_db(test_engine)

        with patch("web.deps.get_storage") as mock_storage:
            from rentivo.storage.local import LocalStorage

            mock_storage.return_value = LocalStorage(str(tmp_path))
            bill = generate_bill_in_db(test_engine, billing, tmp_path)

            auth_client.post(
                f"/billings/{billing.uuid}/bills/{bill.uuid}/delete",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        logs = get_audit_logs(test_engine, AuditEventType.BILL_DELETE)
        assert len(logs) >= 1
        log = logs[0]
        assert log.source == "web"
        assert log.entity_type == "bill"
        assert log.previous_state is not None
        assert log.new_state is None


class TestAuditLogStateCapture:
    def test_previous_state_captured_before_edit(self, auth_client, test_engine, csrf_token):
        """Verify that previous_state reflects the state BEFORE the edit was applied."""
        billing = create_billing_in_db(test_engine, name="Original Name", description="Original Desc")

        auth_client.post(
            f"/billings/{billing.uuid}/edit",
            data={
                "csrf_token": csrf_token,
                "name": "New Name",
                "description": "New Desc",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "2850,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )

        logs = get_audit_logs(test_engine, AuditEventType.BILLING_UPDATE)
        assert len(logs) >= 1
        log = logs[0]
        # previous_state should reflect ORIGINAL values
        assert log.previous_state["name"] == "Original Name"
        assert log.previous_state["description"] == "Original Desc"
        # new_state should reflect UPDATED values
        assert log.new_state["name"] == "New Name"
        assert log.new_state["description"] == "New Desc"

    def test_audit_log_contains_actor_info(self, auth_client, test_engine, csrf_token):
        """Verify actor information is captured in audit entries."""
        auth_client.post(
            "/billings/create",
            data={
                "csrf_token": csrf_token,
                "name": "Actor Test",
                "description": "",
                "pix_key": "",
                "items-TOTAL_FORMS": "1",
                "items-0-description": "Rent",
                "items-0-amount": "500,00",
                "items-0-item_type": "fixed",
            },
            follow_redirects=False,
        )

        logs = get_audit_logs(test_engine, AuditEventType.BILLING_CREATE)
        assert len(logs) >= 1
        log = logs[0]
        assert log.actor_username == "testuser"
        assert log.actor_id is not None

    def test_audit_log_entity_uuid_captured(self, auth_client, test_engine, csrf_token):
        """Verify entity_uuid is captured in audit entries."""
        billing = create_billing_in_db(test_engine)

        auth_client.post(
            f"/billings/{billing.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

        logs = get_audit_logs(test_engine, AuditEventType.BILLING_DELETE)
        assert len(logs) >= 1
        log = logs[0]
        assert log.entity_uuid == billing.uuid
        assert log.entity_id == billing.id
