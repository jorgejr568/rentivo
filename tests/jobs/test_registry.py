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
