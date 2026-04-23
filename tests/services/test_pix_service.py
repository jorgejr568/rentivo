from unittest.mock import MagicMock

from rentivo.models.billing import Billing
from rentivo.models.organization import Organization
from rentivo.models.user import User
from rentivo.services.pix_service import PixConfig, PixService


def _make_service(user=None, org=None):
    user_repo = MagicMock()
    org_repo = MagicMock()
    user_repo.get_by_id.return_value = user
    org_repo.get_by_id.return_value = org
    return PixService(user_repo, org_repo)


class TestResolveForBilling:
    def test_returns_billing_override_when_complete(self):
        service = _make_service(
            user=User(
                id=1,
                username="u",
                pix_key="owner@pix",
                pix_merchant_name="Owner",
                pix_merchant_city="Sao Paulo",
            )
        )
        billing = Billing(
            id=10,
            name="Apt",
            owner_type="user",
            owner_id=1,
            pix_key="billing@pix",
            pix_merchant_name="Billing Co",
            pix_merchant_city="Campinas",
        )
        result = service.resolve_for_billing(billing)
        assert result == PixConfig("billing@pix", "Billing Co", "Campinas")

    def test_falls_back_to_user_owner(self):
        service = _make_service(
            user=User(
                id=1,
                username="u",
                pix_key="owner@pix",
                pix_merchant_name="Owner",
                pix_merchant_city="Sao Paulo",
            )
        )
        billing = Billing(id=10, name="Apt", owner_type="user", owner_id=1)
        result = service.resolve_for_billing(billing)
        assert result == PixConfig("owner@pix", "Owner", "Sao Paulo")

    def test_falls_back_to_organization_owner(self):
        service = _make_service(
            org=Organization(
                id=5,
                name="Org",
                pix_key="org@pix",
                pix_merchant_name="Org",
                pix_merchant_city="Campinas",
            )
        )
        billing = Billing(id=10, name="Apt", owner_type="organization", owner_id=5)
        result = service.resolve_for_billing(billing)
        assert result == PixConfig("org@pix", "Org", "Campinas")

    def test_returns_none_when_billing_partial_and_owner_empty(self):
        service = _make_service(user=User(id=1, username="u"))
        billing = Billing(
            id=10,
            name="Apt",
            owner_type="user",
            owner_id=1,
            pix_key="billing@pix",  # merchant fields missing
        )
        assert service.resolve_for_billing(billing) is None

    def test_partial_owner_not_used(self):
        service = _make_service(
            user=User(id=1, username="u", pix_key="owner@pix")  # missing merchant fields
        )
        billing = Billing(id=10, name="Apt", owner_type="user", owner_id=1)
        assert service.resolve_for_billing(billing) is None

    def test_owner_missing_returns_none(self):
        service = _make_service()
        billing = Billing(id=10, name="Apt", owner_type="user", owner_id=1)
        assert service.resolve_for_billing(billing) is None


class TestNeedsSetup:
    def test_billing_needs_setup_true_when_unresolvable(self):
        service = _make_service()
        billing = Billing(id=10, name="Apt", owner_type="user", owner_id=1)
        assert service.billing_needs_setup(billing) is True

    def test_billing_needs_setup_false_when_owner_has_pix(self):
        service = _make_service(
            user=User(
                id=1,
                username="u",
                pix_key="owner@pix",
                pix_merchant_name="Owner",
                pix_merchant_city="Sao Paulo",
            )
        )
        billing = Billing(id=10, name="Apt", owner_type="user", owner_id=1)
        assert service.billing_needs_setup(billing) is False

    def test_owner_needs_setup_checks_org(self):
        service = _make_service(org=Organization(id=5, name="Org"))
        assert service.owner_needs_setup("organization", 5) is True

    def test_organization_missing_returns_none(self):
        """owner_type=organization but repo returns None — guard must short-circuit."""
        service = _make_service()  # org defaults to None
        billing = Billing(id=10, name="Apt", owner_type="organization", owner_id=5)
        assert service.resolve_for_billing(billing) is None
