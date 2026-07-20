from dataclasses import dataclass

from ulid import ULID

MAX_REQUEST_ID_LEN = 128


def new_request_id() -> str:
    return str(ULID())


def accept_inbound_request_id(value: str | None) -> str | None:
    if not value:
        return None
    request_id = value.strip()
    if not request_id or len(request_id) > MAX_REQUEST_ID_LEN:
        return None
    if not all(32 <= ord(character) < 127 for character in request_id):
        return None
    return request_id


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: int | None
    email: str
    source: str
    api_key_uuid: str | None = None
    is_login_token: bool | None = None


ANON_ACTOR = Actor(user_id=None, email="", source="anonymous")
