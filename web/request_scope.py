from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Request
from sqlalchemy.engine import Connection, Engine

from rentivo.services.container import ConnectionServices
from rentivo.storage.base import StorageBackend

logger = logging.getLogger(__name__)

_REQUEST_SCOPE_STATE_KEY = "_request_scope"


class RequestScope:
    def __init__(
        self,
        request: Request,
        *,
        engine_factory: Callable[[], Engine],
        storage_factory: Callable[[], StorageBackend],
    ) -> None:
        self.request = request
        self.engine_factory = engine_factory
        self.storage_factory = storage_factory
        self._conn: Connection | None = None
        self._services: ConnectionServices | None = None

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            logger.debug("Creating DB connection for %s %s", self.request.method, self.request.url.path)
            self._conn = self.engine_factory().connect()
        return self._conn

    @property
    def services(self) -> ConnectionServices:
        if self._services is None:
            self._services = ConnectionServices(self.conn, storage_factory=self.storage_factory)
        return self._services

    def count_pending_invites_for_user(self, user_id: int) -> int:
        return self.services.invite_repo.count_pending_for_user(user_id)

    def close(self) -> None:
        if self._conn is None:
            return
        self._conn.close()
        logger.debug("DB connection closed for %s %s", self.request.method, self.request.url.path)
        self._conn = None
        self._services = None


def get_request_scope(
    request: Request,
    *,
    engine_factory: Callable[[], Engine],
    storage_factory: Callable[[], StorageBackend],
) -> RequestScope:
    scope = getattr(request.state, _REQUEST_SCOPE_STATE_KEY, None)
    if scope is None:
        scope = RequestScope(
            request,
            engine_factory=engine_factory,
            storage_factory=storage_factory,
        )
        setattr(request.state, _REQUEST_SCOPE_STATE_KEY, scope)
    return scope


def get_request_services(
    request: Request,
    *,
    engine_factory: Callable[[], Engine],
    storage_factory: Callable[[], StorageBackend],
) -> ConnectionServices:
    return get_request_scope(
        request,
        engine_factory=engine_factory,
        storage_factory=storage_factory,
    ).services


def count_pending_invites_for_user(
    request: Request,
    user_id: int,
    *,
    engine_factory: Callable[[], Engine],
    storage_factory: Callable[[], StorageBackend],
) -> int:
    return get_request_scope(
        request,
        engine_factory=engine_factory,
        storage_factory=storage_factory,
    ).count_pending_invites_for_user(user_id)


def close_request_scope(request: Request) -> None:
    scope = getattr(request.state, _REQUEST_SCOPE_STATE_KEY, None)
    if scope is not None:
        scope.close()
        delattr(request.state, _REQUEST_SCOPE_STATE_KEY)
