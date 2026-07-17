def test_legacy_request_services_reexports_shared_container():
    from legacy_web.services_container import RequestServices as LegacyRequestServices
    from rentivo.services.container import RequestServices

    assert LegacyRequestServices is RequestServices


def test_legacy_service_container_preserves_module_patch_points():
    import legacy_web.services_container as legacy_container
    import rentivo.services.container as shared_container

    assert legacy_container is shared_container


def test_api_key_service_is_lazily_cached(db_connection, fake_encryption):
    from rentivo.services.api_key_service import APIKeyService
    from rentivo.services.container import RequestServices

    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert isinstance(services.api_key, APIKeyService)
    assert services.api_key is services.api_key


def test_auth_challenge_service_is_lazily_cached(db_connection, fake_encryption):
    from rentivo.services.auth_challenge_service import AuthChallengeService
    from rentivo.services.container import RequestServices

    services = RequestServices(conn=db_connection, encryption=fake_encryption)

    assert isinstance(services.auth_challenge, AuthChallengeService)
    assert services.auth_challenge is services.auth_challenge
