"""ReDoS budget smoke tests for every regex compiled in production code.

Catastrophic backtracking surfaces as super-linear runtime on adversarially long
input. We run each pattern against an adversarial near-match input under a 100 ms
wall-clock budget. A pattern that exceeds the budget must be reviewed for nested
quantifiers.

Why 100 ms? On the FastAPI event loop, a 100 ms regex match blocks every other
request handled by the same uvicorn worker. Hypothetical CVSS for the realistic
deployment (auth-gated routes, multi-worker uvicorn):

    AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L — base score 4.3 (MEDIUM)

Worst case if a regex were ever moved to a public, single-worker endpoint:

    AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H — base score 7.5 (HIGH)

Pinning the budget here prevents that class of bug from reaching production
regardless of which deployment shape the regex ends up in.
"""

from __future__ import annotations

import re
import time

import pytest

# Import every regex from its production site so this test fails the moment a
# new prod pattern is added without being registered below.
from rentivo.pix import _PIX_KEY_PATTERNS
from rentivo.settings import _GTM_RE

# (label, compiled pattern, adversarial input)
#
# Each input is sized to force the regex engine to traverse the full pattern
# (not be rejected by a constant-time length pre-check) and end with a
# disqualifying character that triggers backtracking before failure. This
# proves the patterns degrade gracefully under near-match adversarial input,
# not just oversized input.
PRODUCTION_REGEXES: list[tuple[str, re.Pattern[str], str]] = [
    # Variable-length: stress with a very long matching prefix + trailing bad char.
    ("settings._GTM_RE", _GTM_RE, "GTM-" + ("A" * 1000) + "!"),
    # Fixed length 11 digits: 11 valid digits + bad trailing char.
    ("pix.cpf", _PIX_KEY_PATTERNS["cpf"], ("9" * 11) + "!"),
    # Fixed length 14 digits: 14 valid digits + bad trailing char.
    ("pix.cnpj", _PIX_KEY_PATTERNS["cnpj"], ("9" * 14) + "!"),
    # Three negated-class segments separated by `@` and `.` — long matching segments
    # to maximize the work the engine does before failing on the final assertion.
    ("pix.email", _PIX_KEY_PATTERNS["email"], ("a" * 500) + "@" + ("b" * 500) + "."),
    # +55 + 10..11 digits: 11 valid digits + bad trailing char.
    ("pix.phone", _PIX_KEY_PATTERNS["phone"], "+55" + ("1" * 11) + "!"),
    # UUID with correct hyphen positions but bad trailing char.
    (
        "pix.evp",
        _PIX_KEY_PATTERNS["evp"],
        "a" * 8 + "-" + "a" * 4 + "-" + "a" * 4 + "-" + "a" * 4 + "-" + "a" * 12 + "!",
    ),
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
