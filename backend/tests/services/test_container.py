def test_legacy_request_services_reexports_shared_container():
    from legacy_web.services_container import RequestServices as LegacyRequestServices
    from rentivo.services.container import RequestServices

    assert LegacyRequestServices is RequestServices


def test_legacy_service_container_preserves_module_patch_points():
    import legacy_web.services_container as legacy_container
    import rentivo.services.container as shared_container

    assert legacy_container is shared_container
