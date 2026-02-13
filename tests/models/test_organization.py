from landlord.models.organization import OrgRole, Organization, OrganizationMember


class TestOrgRole:
    def test_values(self):
        assert OrgRole.ADMIN.value == "admin"
        assert OrgRole.MANAGER.value == "manager"
        assert OrgRole.VIEWER.value == "viewer"

    def test_from_string(self):
        assert OrgRole("admin") is OrgRole.ADMIN


class TestOrganization:
    def test_defaults(self):
        org = Organization(name="Test Org")
        assert org.id is None
        assert org.uuid == ""
        assert org.created_by == 0
        assert org.created_at is None
        assert org.deleted_at is None

    def test_with_values(self):
        org = Organization(name="Test Org", id=1, created_by=5)
        assert org.id == 1
        assert org.created_by == 5


class TestOrganizationMember:
    def test_defaults(self):
        m = OrganizationMember()
        assert m.id is None
        assert m.organization_id == 0
        assert m.user_id == 0
        assert m.username == ""
        assert m.role == "viewer"
        assert m.created_at is None

    def test_with_values(self):
        m = OrganizationMember(organization_id=1, user_id=2, role="admin", username="bob")
        assert m.organization_id == 1
        assert m.user_id == 2
        assert m.role == "admin"
        assert m.username == "bob"
