import pytest

from rentivo.jobs import registry


@pytest.fixture(autouse=True)
def _clear_registry():
    """Each test starts from an empty registry."""
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()


def test_register_adds_handler():
    @registry.register("foo.bar")
    def handler(payload: dict) -> None:
        return None

    assert registry.get("foo.bar") is handler


def test_register_returns_the_function_unchanged():
    def handler(payload: dict) -> None:
        return None

    decorated = registry.register("foo.bar")(handler)
    assert decorated is handler


def test_duplicate_register_raises():
    @registry.register("foo.bar")
    def first(payload: dict) -> None:
        return None

    with pytest.raises(ValueError, match="foo.bar"):

        @registry.register("foo.bar")
        def second(payload: dict) -> None:
            return None


def test_get_returns_none_for_unknown_type():
    assert registry.get("nope.never") is None


@pytest.fixture(autouse=True)
def _clear_fail_hooks():
    """Each test starts from an empty fail-hook registry."""
    registry._FAIL_HOOKS.clear()
    yield
    registry._FAIL_HOOKS.clear()


def test_register_on_fail_adds_hook():
    @registry.register_on_fail("foo.bar")
    def hook(payload: dict) -> None:
        return None

    assert registry.get_fail_hook("foo.bar") is hook


def test_register_on_fail_returns_function_unchanged():
    def hook(payload: dict) -> None:
        return None

    decorated = registry.register_on_fail("foo.bar")(hook)
    assert decorated is hook


def test_duplicate_register_on_fail_raises():
    @registry.register_on_fail("foo.bar")
    def first(payload: dict) -> None:
        return None

    with pytest.raises(ValueError, match="foo.bar"):

        @registry.register_on_fail("foo.bar")
        def second(payload: dict) -> None:
            return None


def test_get_fail_hook_returns_none_for_unknown_type():
    assert registry.get_fail_hook("nope.never") is None
