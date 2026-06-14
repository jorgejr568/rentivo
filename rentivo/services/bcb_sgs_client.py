from __future__ import annotations

from functools import reduce

import structlog

logger = structlog.get_logger(__name__)

# SGS monthly series codes (single source of truth).
IGPM_SERIES = 189
IPCA_SERIES = 433


def accumulated_factor(values: list[float]) -> float:
    """Compound a list of monthly percentage variations into an accumulated %.

    ``accumulated_pct = (prod(1 + v_i / 100) - 1) * 100``. An empty list is 0.0.
    Pure and unit-testable — no I/O.
    """
    product = reduce(lambda acc, v: acc * (1 + v / 100), values, 1.0)
    return (product - 1) * 100
