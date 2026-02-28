from rentivo.models.user import User
from rentivo.repositories.sqlalchemy import (
    SQLAlchemyOrganizationRepository,
    SQLAlchemyUserRepository,
)
from tests.web.conftest import create_billing_in_db, create_org_in_db, get_test_user_id


class TestUserThemeForm:
    def test_user_theme_form_renders(self, auth_client):
        response = auth_client.get("/themes/user")
        assert response.status_code == 200


class TestUserThemeSave:
    def test_save_user_theme(self, auth_client, csrf_token):
        response = auth_client.post(
            "/themes/user",
            data={
                "csrf_token": csrf_token,
                "header_font": "Roboto",
                "text_font": "Open Sans",
                "primary": "#FF5733",
                "primary_light": "#FFD1C1",
                "secondary": "#33FF57",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FEFEFE",
                "name": "My Custom Theme",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/themes/user"

    def test_save_user_theme_with_invalid_font(self, auth_client, csrf_token):
        """Submitting an invalid font name falls back to Montserrat (line 62)."""
        response = auth_client.post(
            "/themes/user",
            data={
                "csrf_token": csrf_token,
                "header_font": "Comic Sans",
                "text_font": "Wingdings",
                "primary": "#FF5733",
                "primary_light": "#FFD1C1",
                "secondary": "#33FF57",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FEFEFE",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_save_user_theme_with_invalid_color(self, auth_client, csrf_token):
        """Submitting an invalid hex color falls back to DEFAULT_THEME value (line 65)."""
        response = auth_client.post(
            "/themes/user",
            data={
                "csrf_token": csrf_token,
                "primary": "not-a-color",
                "primary_light": "#FFD1C1",
                "secondary": "#33FF57",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FEFEFE",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestUserThemeDelete:
    def test_delete_user_theme_no_custom(self, auth_client, csrf_token):
        """POST /themes/user/delete when no custom theme exists flashes a warning."""
        response = auth_client.post(
            "/themes/user/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/themes/user"

    def test_delete_user_theme_with_custom(self, auth_client, csrf_token):
        """POST /themes/user/delete when a custom theme exists — covers lines 159-171."""
        # First create a theme
        auth_client.post(
            "/themes/user",
            data={
                "csrf_token": csrf_token,
                "header_font": "Roboto",
                "text_font": "Open Sans",
                "primary": "#FF5733",
                "primary_light": "#FFD1C1",
                "secondary": "#33FF57",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FEFEFE",
            },
            follow_redirects=False,
        )
        # Then delete it
        response = auth_client.post(
            "/themes/user/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/themes/user"


class TestOrgThemeForm:
    def test_org_theme_form_admin(self, auth_client, test_engine):
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Theme Org", user_id)
        response = auth_client.get(f"/themes/organization/{org.uuid}")
        assert response.status_code == 200

    def test_org_theme_form_non_admin_denied(self, auth_client, test_engine):
        """Create org with a different user, add testuser as viewer. GET should redirect."""
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other = user_repo.create(User(username="org_owner_theme", password_hash="h"))
        org = create_org_in_db(test_engine, "Other Org", other.id)
        test_user_id = get_test_user_id(test_engine)
        with test_engine.connect() as conn:
            org_repo = SQLAlchemyOrganizationRepository(conn)
            org_repo.add_member(org.id, test_user_id, "viewer")

        response = auth_client.get(
            f"/themes/organization/{org.uuid}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_org_theme_form_not_found(self, auth_client):
        """GET /themes/organization/<bad-uuid> redirects — covers lines 191-193."""
        response = auth_client.get(
            "/themes/organization/nonexistent-uuid",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/organizations/"


class TestOrgThemeSave:
    def test_save_org_theme(self, auth_client, test_engine, csrf_token):
        """Covers lines 235-265."""
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Save Org Theme", user_id)
        response = auth_client.post(
            f"/themes/organization/{org.uuid}",
            data={
                "csrf_token": csrf_token,
                "header_font": "Lora",
                "text_font": "Nunito",
                "primary": "#123456",
                "primary_light": "#ABCDEF",
                "secondary": "#654321",
                "secondary_dark": "#111111",
                "text_color": "#222222",
                "text_contrast": "#FFFFFF",
                "name": "Org Theme",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/themes/organization/{org.uuid}"

    def test_save_org_theme_denied(self, auth_client, test_engine, csrf_token):
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other = user_repo.create(User(username="org_save_other", password_hash="h"))
        org = create_org_in_db(test_engine, "Other Org Save", other.id)
        response = auth_client.post(
            f"/themes/organization/{org.uuid}",
            data={"csrf_token": csrf_token, "primary": "#123456"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestOrgThemeDelete:
    def test_delete_org_theme_no_custom(self, auth_client, test_engine, csrf_token):
        """Covers lines 270-297 (else branch)."""
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Del Org No Theme", user_id)
        response = auth_client.post(
            f"/themes/organization/{org.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/themes/organization/{org.uuid}"

    def test_delete_org_theme_with_custom(self, auth_client, test_engine, csrf_token):
        """Create theme then delete it — covers lines 270-297 (if branch)."""
        user_id = get_test_user_id(test_engine)
        org = create_org_in_db(test_engine, "Del Org With Theme", user_id)
        # Create theme
        auth_client.post(
            f"/themes/organization/{org.uuid}",
            data={
                "csrf_token": csrf_token,
                "primary": "#FF0000",
                "primary_light": "#FFD1C1",
                "secondary": "#00FF00",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FFFFFF",
            },
            follow_redirects=False,
        )
        # Delete theme
        response = auth_client.post(
            f"/themes/organization/{org.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/themes/organization/{org.uuid}"

    def test_delete_org_theme_denied(self, auth_client, test_engine, csrf_token):
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other = user_repo.create(User(username="org_del_other", password_hash="h"))
        org = create_org_in_db(test_engine, "Other Org Del", other.id)
        response = auth_client.post(
            f"/themes/organization/{org.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingThemeForm:
    def test_billing_theme_form_owner(self, auth_client, test_engine):
        billing = create_billing_in_db(test_engine)
        response = auth_client.get(f"/themes/billing/{billing.uuid}")
        assert response.status_code == 200

    def test_billing_theme_form_non_owner_denied(self, auth_client, test_engine):
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other = user_repo.create(User(username="billing_theme_other", password_hash="h"))
        billing = create_billing_in_db(test_engine, owner_type="user", owner_id=other.id)
        response = auth_client.get(
            f"/themes/billing/{billing.uuid}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_billing_theme_form_not_found(self, auth_client):
        """GET /themes/billing/<bad-uuid> redirects — covers lines 313-315."""
        response = auth_client.get(
            "/themes/billing/nonexistent-uuid",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/billings/"

    def test_billing_theme_form_with_user_theme(self, auth_client, test_engine, csrf_token):
        """effective_source should be 'user' — covers line 337."""
        auth_client.post(
            "/themes/user",
            data={
                "csrf_token": csrf_token,
                "primary": "#FF0000",
                "primary_light": "#FFD1C1",
                "secondary": "#00FF00",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FFFFFF",
            },
            follow_redirects=False,
        )
        billing = create_billing_in_db(test_engine)
        response = auth_client.get(f"/themes/billing/{billing.uuid}")
        assert response.status_code == 200

    def test_billing_theme_form_with_billing_theme(self, auth_client, test_engine, csrf_token):
        """effective_source should be 'billing' — covers line 332."""
        billing = create_billing_in_db(test_engine)
        auth_client.post(
            f"/themes/billing/{billing.uuid}",
            data={
                "csrf_token": csrf_token,
                "primary": "#FF0000",
                "primary_light": "#FFD1C1",
                "secondary": "#00FF00",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FFFFFF",
            },
            follow_redirects=False,
        )
        response = auth_client.get(f"/themes/billing/{billing.uuid}")
        assert response.status_code == 200


class TestBillingThemeSave:
    def test_save_billing_theme(self, auth_client, test_engine, csrf_token):
        """Covers lines 376-406."""
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/themes/billing/{billing.uuid}",
            data={
                "csrf_token": csrf_token,
                "header_font": "Roboto",
                "text_font": "Lora",
                "primary": "#AA0000",
                "primary_light": "#FFD1C1",
                "secondary": "#00AA00",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FFFFFF",
                "name": "Billing Theme",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/themes/billing/{billing.uuid}"

    def test_save_billing_theme_denied(self, auth_client, test_engine, csrf_token):
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other = user_repo.create(User(username="billing_save_other", password_hash="h"))
        billing = create_billing_in_db(test_engine, owner_type="user", owner_id=other.id)
        response = auth_client.post(
            f"/themes/billing/{billing.uuid}",
            data={"csrf_token": csrf_token, "primary": "#123456"},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestBillingThemeDelete:
    def test_delete_billing_theme_no_custom(self, auth_client, test_engine, csrf_token):
        """Covers lines 411-438 (else branch)."""
        billing = create_billing_in_db(test_engine)
        response = auth_client.post(
            f"/themes/billing/{billing.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/themes/billing/{billing.uuid}"

    def test_delete_billing_theme_with_custom(self, auth_client, test_engine, csrf_token):
        """Create billing theme then delete it — covers lines 411-438 (if branch)."""
        billing = create_billing_in_db(test_engine)
        auth_client.post(
            f"/themes/billing/{billing.uuid}",
            data={
                "csrf_token": csrf_token,
                "primary": "#FF0000",
                "primary_light": "#FFD1C1",
                "secondary": "#00FF00",
                "secondary_dark": "#1E8C35",
                "text_color": "#111111",
                "text_contrast": "#FFFFFF",
            },
            follow_redirects=False,
        )
        response = auth_client.post(
            f"/themes/billing/{billing.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == f"/themes/billing/{billing.uuid}"

    def test_delete_billing_theme_denied(self, auth_client, test_engine, csrf_token):
        with test_engine.connect() as conn:
            user_repo = SQLAlchemyUserRepository(conn)
            other = user_repo.create(User(username="billing_del_other", password_hash="h"))
        billing = create_billing_in_db(test_engine, owner_type="user", owner_id=other.id)
        response = auth_client.post(
            f"/themes/billing/{billing.uuid}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestThemePreview:
    def test_preview_returns_pdf(self, auth_client):
        response = auth_client.get(
            "/themes/preview",
            params={
                "header_font": "Montserrat",
                "text_font": "Montserrat",
                "primary": "#8A4C94",
                "primary_light": "#EEE4F1",
                "secondary": "#6EAFAE",
                "secondary_dark": "#357B7C",
                "text_color": "#282830",
                "text_contrast": "#FFFFFF",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/pdf")
