from rentivo.models.organization import Organization, OrganizationMember, OrgRole


class TestOrgRole:
    def test_values(self):
        assert OrgRole.ADMIN.value == "admin"
        assert OrgRole.MANAGER.value == "manager"
        assert OrgRole.VIEWER.value == "viewer"

    def test_from_string(self):
        assert OrgRole("admin") is OrgRole.ADMIN

    def test_label_returns_pt_br_for_each_value(self):
        assert OrgRole.label("admin") == "Administrador"
        assert OrgRole.label("manager") == "Gerente"
        assert OrgRole.label("viewer") == "Visualizador"
        # forward-compat: "owner" is not a current OrgRole but the dict carries it
        assert OrgRole.label("owner") == "Dono"

    def test_label_falls_back_to_raw_value_for_unknown(self):
        assert OrgRole.label("unknown-role") == "unknown-role"


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
        assert m.email == ""
        assert m.role == "viewer"
        assert m.created_at is None

    def test_with_values(self):
        m = OrganizationMember(organization_id=1, user_id=2, role="admin", email="bob@example.com")
        assert m.organization_id == 1
        assert m.user_id == 2
        assert m.role == "admin"
        assert m.email == "bob@example.com"
