from __future__ import annotations

from unittest.mock import MagicMock

from web.services_container import RequestServices


class TestLazyProperties:
    def test_property_memoises(self):
        services = RequestServices(conn=MagicMock(), encryption=MagicMock())
        assert services.billing is services.billing


class TestNoLazyEncryptionImport:
    def test_module_imports_encryption_at_top_level(self):
        import web.services_container as sc

        with open(sc.__file__) as f:
            lines = f.read().splitlines()
        in_func = False
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith(("def ", "class ")):
                in_func = True
                continue
            if in_func and "from rentivo.encryption.factory" in line:
                raise AssertionError(f"Lazy encryption import at line {i}")
