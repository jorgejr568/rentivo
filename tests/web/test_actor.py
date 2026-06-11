"""Tests for WebActor — the per-request actor context that replaces
hand-derived actor_id / actor_username / source triples at every audit
and job-enqueue site."""

from __future__ import annotations

import pytest

from web.context import ANON_ACTOR, WebActor, actor_for, actor_from_session


class TestWebActor:
    def test_dataclass_defaults_source_to_web(self):
        actor = WebActor(user_id=42, email="user@example.com")
        assert actor.user_id == 42
        assert actor.email == "user@example.com"
        assert actor.source == "web"

    def test_anon_actor_has_none_user_id_and_empty_email(self):
        assert ANON_ACTOR.user_id is None
        assert ANON_ACTOR.email == ""
        assert ANON_ACTOR.source == "web"

    def test_anon_actor_is_immutable(self):
        with pytest.raises((AttributeError, Exception)):
            ANON_ACTOR.user_id = 1

    def test_actor_from_session_returns_actor_when_logged_in(self):
        actor = actor_from_session({"user_id": 7, "email": "x@y.z"})
        assert actor == WebActor(user_id=7, email="x@y.z")

    def test_actor_from_session_returns_anon_when_no_user_id(self):
        assert actor_from_session({}) is ANON_ACTOR
        assert actor_from_session({"email": "stale@x.com"}) is ANON_ACTOR

    def test_actor_from_session_handles_missing_email(self):
        actor = actor_from_session({"user_id": 7})
        assert actor == WebActor(user_id=7, email="")


class TestActorOnRequestState:
    def test_logged_in_request_does_not_crash(self, auth_client):
        response = auth_client.get("/billings/")
        assert response.status_code in (200, 302)

    def test_anon_request_does_not_crash(self, client):
        # /login is public — AuthMiddleware short-circuits but still
        # attaches request.state.actor before doing so.
        response = client.get("/login")
        assert response.status_code in (200, 302)


class TestActorFor:
    def test_builds_web_actor_from_id_and_email(self):
        assert actor_for(7, "x@y.z") == WebActor(user_id=7, email="x@y.z")

    def test_none_email_collapses_to_empty_string(self):
        # mfa_pending_email can be absent from the session — the actor email
        # must still be a str (AuditService expects actor_username: str).
        assert actor_for(7, None) == WebActor(user_id=7, email="")

    def test_source_defaults_to_web(self):
        assert actor_for(7, "x@y.z").source == "web"
