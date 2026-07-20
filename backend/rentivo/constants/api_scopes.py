from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class APIScope(StrEnum):
    PROFILE_READ = "profile:read"
    ACCOUNT_WRITE = "account:write"
    SECURITY_MANAGE = "security:manage"
    API_KEYS_MANAGE = "api_keys:manage"
    ORGANIZATIONS_READ = "organizations:read"
    ORGANIZATIONS_WRITE = "organizations:write"
    ORGANIZATIONS_MEMBERS = "organizations:members"
    BILLINGS_READ = "billings:read"
    BILLINGS_WRITE = "billings:write"
    BILLS_READ = "bills:read"
    BILLS_WRITE = "bills:write"
    EXPENSES_READ = "expenses:read"
    EXPENSES_WRITE = "expenses:write"
    FILES_READ = "files:read"
    FILES_WRITE = "files:write"
    COMMUNICATIONS_READ = "communications:read"
    COMMUNICATIONS_SEND = "communications:send"
    THEMES_READ = "themes:read"
    THEMES_WRITE = "themes:write"
    EXPORTS_CREATE = "exports:create"


ALL_FIRST_PARTY_SCOPES = frozenset(scope.value for scope in APIScope)

INTEGRATION_SCOPES = frozenset(
    {
        APIScope.PROFILE_READ.value,
        APIScope.ORGANIZATIONS_READ.value,
        APIScope.BILLINGS_READ.value,
        APIScope.BILLINGS_WRITE.value,
        APIScope.BILLS_READ.value,
        APIScope.BILLS_WRITE.value,
        APIScope.EXPENSES_READ.value,
        APIScope.EXPENSES_WRITE.value,
        APIScope.FILES_READ.value,
        APIScope.FILES_WRITE.value,
        APIScope.COMMUNICATIONS_READ.value,
        APIScope.COMMUNICATIONS_SEND.value,
        APIScope.THEMES_READ.value,
        APIScope.THEMES_WRITE.value,
        APIScope.EXPORTS_CREATE.value,
    }
)

DEPLOYED_API_SCOPES = INTEGRATION_SCOPES


def deployed_integration_scopes(deployed_scopes: Iterable[str]) -> frozenset[str]:
    return INTEGRATION_SCOPES.intersection(deployed_scopes)
