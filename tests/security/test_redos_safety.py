"""ReDoS budget smoke tests for every regex compiled in production code.

Catastrophic backtracking surfaces as super-linear runtime on adversarially long
input. We run each pattern against a length-1000 worst-case string under a 100 ms
wall-clock budget. A pattern that exceeds the budget must be reviewed for nested
quantifiers.

Why 100 ms? On the FastAPI event loop, a 100 ms regex match blocks every other
request handled by the same uvicorn worker. Any production regex slower than that
is an availability hazard with hypothetical CVSS:

    AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H — base score 7.5 (HIGH)

Pinning the budget here prevents that class of bug from reaching production.
"""

from __future__ import annotations

import re
import time

import pytest

# Import every regex from its production site so this test fails the moment a
# new prod pattern is added without being registered below.
from rentivo.pix import _PIX_KEY_PATTERNS
from rentivo.settings import _GTM_RE
from web.routes.theme import _HEX_COLOR_RE

# (label, compiled pattern, adversarial input)
PRODUCTION_REGEXES: list[tuple[str, re.Pattern[str], str]] = [
    ("settings._GTM_RE", _GTM_RE, "GTM-" + ("A" * 1000) + "!"),
    ("theme._HEX_COLOR_RE", _HEX_COLOR_RE, "#" + ("a" * 1000)),
    ("pix.cpf", _PIX_KEY_PATTERNS["cpf"], "9" * 1000),
    ("pix.cnpj", _PIX_KEY_PATTERNS["cnpj"], "9" * 1000),
    ("pix.email", _PIX_KEY_PATTERNS["email"], ("a" * 500) + "@" + ("b" * 500)),
    ("pix.phone", _PIX_KEY_PATTERNS["phone"], "+55" + ("1" * 1000)),
    ("pix.evp", _PIX_KEY_PATTERNS["evp"], "a" * 1000),
]

REDOS_BUDGET_SECONDS = 0.1


@pytest.mark.parametrize(
    "label,pattern,adversarial_input",
    PRODUCTION_REGEXES,
    ids=[item[0] for item in PRODUCTION_REGEXES],
)
def test_regex_is_linear_time_on_adversarial_input(
    label: str, pattern: re.Pattern[str], adversarial_input: str
) -> None:
    start = time.perf_counter()
    pattern.match(adversarial_input)
    elapsed = time.perf_counter() - start
    assert elapsed < REDOS_BUDGET_SECONDS, (
        f"{label} took {elapsed * 1000:.1f} ms on a length-{len(adversarial_input)} input "
        f"(budget: {REDOS_BUDGET_SECONDS * 1000:.0f} ms). Likely catastrophic backtracking — "
        f"review for nested quantifiers."
    )
