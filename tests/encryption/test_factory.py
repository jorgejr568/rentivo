from __future__ import annotations

from unittest.mock import patch

import pytest

from rentivo.encryption.base64 import Base64Backend


class TestEncryptionFactory:
    @patch("rentivo.encryption.factory.settings")
    def test_returns_base64_backend_by_default(self, mock_settings):
        mock_settings.encryption_backend = "base64"
        mock_settings.encryption_cache_backend = "none"

        from rentivo.encryption.factory import get_encryption

        backend = get_encryption()
        assert isinstance(backend, Base64Backend)

    @patch("rentivo.encryption.factory.settings")
    def test_returns_kms_backend_when_configured(self, mock_settings):
        mock_settings.encryption_backend = "kms"
        mock_settings.encryption_cache_backend = "none"
        mock_settings.kms_key_id = "alias/rentivo"
        mock_settings.kms_region = "us-east-1"
        mock_settings.kms_access_key_id = "key"
        mock_settings.kms_secret_access_key = "secret"
        mock_settings.kms_endpoint_url = ""

        with patch("rentivo.encryption.kms.boto3"):
            from rentivo.encryption.factory import get_encryption
            from rentivo.encryption.kms import KMSBackend

            backend = get_encryption()
            assert isinstance(backend, KMSBackend)

    @patch("rentivo.encryption.factory.settings")
    def test_unsupported_backend(self, mock_settings):
        mock_settings.encryption_backend = "rot13"

        from rentivo.encryption.factory import get_encryption

        with pytest.raises(ValueError, match="Unsupported encryption backend"):
            get_encryption()


class TestEncryptionFactoryCache:
    @patch("rentivo.encryption.factory.settings")
    def test_none_cache_returns_inner_backend_directly(self, mock_settings):
        mock_settings.encryption_backend = "base64"
        mock_settings.encryption_cache_backend = "none"

        from rentivo.encryption.caching import CachingEncryptionBackend
        from rentivo.encryption.factory import get_encryption

        backend = get_encryption()
        assert isinstance(backend, Base64Backend)
        assert not isinstance(backend, CachingEncryptionBackend)

    @patch("rentivo.encryption.factory.settings")
    def test_memory_cache_wraps_inner_backend(self, mock_settings):
        mock_settings.encryption_backend = "base64"
        mock_settings.encryption_cache_backend = "memory"
        mock_settings.encryption_cache_ttl_seconds = 60
        mock_settings.encryption_cache_max_entries = 100

        from rentivo.cache.memory import MemoryKVCache
        from rentivo.encryption.caching import CachingEncryptionBackend
        from rentivo.encryption.factory import get_encryption

        backend = get_encryption()
        assert isinstance(backend, CachingEncryptionBackend)
        assert isinstance(backend.inner, Base64Backend)
        assert isinstance(backend.cache, MemoryKVCache)

    @patch("rentivo.encryption.factory.settings")
    def test_redis_cache_wraps_inner_backend(self, mock_settings):
        import fakeredis

        mock_settings.encryption_backend = "base64"
        mock_settings.encryption_cache_backend = "redis"
        mock_settings.encryption_cache_ttl_seconds = 60
        mock_settings.redis_url = "redis://ignored"

        from rentivo.cache.redis import RedisKVCache
        from rentivo.encryption.caching import CachingEncryptionBackend
        from rentivo.encryption.factory import get_encryption

        with patch("redis.from_url", return_value=fakeredis.FakeStrictRedis()):
            backend = get_encryption()
        assert isinstance(backend, CachingEncryptionBackend)
        assert isinstance(backend.cache, RedisKVCache)

    @patch("rentivo.encryption.factory.settings")
    def test_unsupported_cache_backend_raises(self, mock_settings):
        mock_settings.encryption_backend = "base64"
        mock_settings.encryption_cache_backend = "memcached"

        from rentivo.encryption.factory import get_encryption

        with pytest.raises(ValueError, match="Unsupported decrypt cache backend"):
            get_encryption()

    @patch("rentivo.encryption.factory.settings")
    def test_get_encryption_returns_cached_instance(self, mock_settings):
        mock_settings.encryption_backend = "base64"
        mock_settings.encryption_cache_backend = "none"

        from rentivo.encryption.factory import get_encryption

        first = get_encryption()
        second = get_encryption()
        assert first is second
