from datetime import datetime

from rentivo.models.audit_log import AuditEventType, AuditLog


class TestAuditLogModel:
    def test_create_with_defaults(self):
        log = AuditLog(event_type="test.event")
        assert log.id is None
        assert log.uuid == ""
        assert log.event_type == "test.event"
        assert log.actor_id is None
        assert log.actor_username == ""
        assert log.source == ""
        assert log.entity_type == ""
        assert log.entity_id is None
        assert log.entity_uuid == ""
        assert log.previous_state is None
        assert log.new_state is None
        assert log.metadata == {}
        assert log.created_at is None

    def test_create_with_all_fields(self):
        now = datetime(2026, 2, 16, 12, 0, 0)
        log = AuditLog(
            id=1,
            uuid="01ABCDEFGH1234567890123456",
            event_type="billing.create",
            actor_id=42,
            actor_username="admin",
            source="web",
            entity_type="billing",
            entity_id=10,
            entity_uuid="01ABCDEFGH",
            previous_state=None,
            new_state={"name": "Apt 101"},
            metadata={"ip": "127.0.0.1"},
            created_at=now,
        )
        assert log.id == 1
        assert log.uuid == "01ABCDEFGH1234567890123456"
        assert log.event_type == "billing.create"
        assert log.actor_id == 42
        assert log.actor_username == "admin"
        assert log.source == "web"
        assert log.entity_type == "billing"
        assert log.entity_id == 10
        assert log.entity_uuid == "01ABCDEFGH"
        assert log.previous_state is None
        assert log.new_state == {"name": "Apt 101"}
        assert log.metadata == {"ip": "127.0.0.1"}
        assert log.created_at == now

    def test_state_fields_can_be_dict(self):
        log = AuditLog(
            event_type="billing.update",
            previous_state={"name": "old"},
            new_state={"name": "new"},
        )
        assert log.previous_state == {"name": "old"}
        assert log.new_state == {"name": "new"}


class TestAuditEventType:
    def test_user_events(self):
        assert AuditEventType.USER_LOGIN == "user.login"
        assert AuditEventType.USER_LOGIN_FAILED == "user.login_failed"
        assert AuditEventType.USER_SIGNUP == "user.signup"
        assert AuditEventType.USER_CREATE == "user.create"
        assert AuditEventType.USER_CHANGE_PASSWORD == "user.change_password"
        assert AuditEventType.USER_LOGOUT == "user.logout"

    def test_billing_events(self):
        assert AuditEventType.BILLING_CREATE == "billing.create"
        assert AuditEventType.BILLING_UPDATE == "billing.update"
        assert AuditEventType.BILLING_DELETE == "billing.delete"
        assert AuditEventType.BILLING_TRANSFER == "billing.transfer"

    def test_bill_events(self):
        assert AuditEventType.BILL_CREATE == "bill.create"
        assert AuditEventType.BILL_UPDATE == "bill.update"
        assert AuditEventType.BILL_DELETE == "bill.delete"
        assert AuditEventType.BILL_TOGGLE_PAID == "bill.toggle_paid"
        assert AuditEventType.BILL_REGENERATE_PDF == "bill.regenerate_pdf"

    def test_receipt_events(self):
        assert AuditEventType.RECEIPT_UPLOAD == "receipt.upload"
        assert AuditEventType.RECEIPT_DELETE == "receipt.delete"

    def test_organization_events(self):
        assert AuditEventType.ORGANIZATION_CREATE == "organization.create"
        assert AuditEventType.ORGANIZATION_UPDATE == "organization.update"
        assert AuditEventType.ORGANIZATION_DELETE == "organization.delete"
        assert AuditEventType.ORGANIZATION_ADD_MEMBER == "organization.add_member"
        assert AuditEventType.ORGANIZATION_REMOVE_MEMBER == "organization.remove_member"
        assert AuditEventType.ORGANIZATION_UPDATE_MEMBER_ROLE == "organization.update_member_role"

    def test_invite_events(self):
        assert AuditEventType.INVITE_SEND == "invite.send"
        assert AuditEventType.INVITE_ACCEPT == "invite.accept"
        assert AuditEventType.INVITE_DECLINE == "invite.decline"
