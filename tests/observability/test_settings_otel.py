import pytest

from rentivo.settings import Settings


def test_otel_defaults():
    # _env_file=None so a local .env (e.g. a dev tracing setup) can't override
    # the field defaults this test is asserting.
    s = Settings(_env_file=None)
    assert s.otel_enabled is False
    assert s.otel_service_name == "rentivo"
    assert s.otel_exporter_otlp_endpoint == "http://localhost:4318"
    assert s.otel_sample_ratio == 1.0


def test_otel_sample_ratio_out_of_range_rejected():
    with pytest.raises(ValueError, match="OTEL_SAMPLE_RATIO"):
        Settings(_env_file=None, otel_sample_ratio=1.5)


def test_otel_sample_ratio_bounds_accepted():
    assert Settings(_env_file=None, otel_sample_ratio=0.0).otel_sample_ratio == 0.0
    assert Settings(_env_file=None, otel_sample_ratio=1.0).otel_sample_ratio == 1.0
