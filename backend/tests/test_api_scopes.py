from rentivo.constants.api_scopes import (
    DEPLOYED_API_SCOPES,
    INTEGRATION_SCOPES,
    APIScope,
    deployed_integration_scopes,
)


def test_all_stable_integration_scopes_are_deployed() -> None:
    assert DEPLOYED_API_SCOPES == INTEGRATION_SCOPES


def test_login_only_scopes_are_never_selectable_for_integrations() -> None:
    assert DEPLOYED_API_SCOPES.isdisjoint(
        {
            APIScope.ACCOUNT_WRITE.value,
            APIScope.SECURITY_MANAGE.value,
            APIScope.API_KEYS_MANAGE.value,
            APIScope.ORGANIZATIONS_WRITE.value,
            APIScope.ORGANIZATIONS_MEMBERS.value,
        }
    )


def test_deployed_integration_scopes_excludes_first_party_only_values() -> None:
    assert deployed_integration_scopes(APIScope) == INTEGRATION_SCOPES
