import pytest

from rentivo.services.bcb_sgs_client import IGPM_SERIES, IPCA_SERIES, accumulated_factor


def test_series_codes():
    assert IGPM_SERIES == 189
    assert IPCA_SERIES == 433


def test_accumulated_factor_single_value():
    # one month of 1.00% -> 1.00% accumulated
    assert accumulated_factor([1.0]) == pytest.approx(1.0)


def test_accumulated_factor_compounds():
    # two months of 1% each -> (1.01 * 1.01 - 1) * 100 = 2.01%
    assert accumulated_factor([1.0, 1.0]) == pytest.approx(2.01)


def test_accumulated_factor_handles_negatives():
    # +2% then -1% -> (1.02 * 0.99 - 1) * 100 = 0.98%
    assert accumulated_factor([2.0, -1.0]) == pytest.approx(0.98)


def test_accumulated_factor_empty_is_zero():
    assert accumulated_factor([]) == 0.0
