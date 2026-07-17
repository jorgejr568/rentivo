from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: int | None
    email: str
    source: str
    api_key_uuid: str | None = None
    is_login_token: bool | None = None


ANON_ACTOR = Actor(user_id=None, email="", source="anonymous")
