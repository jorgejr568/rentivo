import re
from ipaddress import IPv6Address, ip_address
from urllib.parse import urlsplit

DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.IGNORECASE)


def _parse_public_host(hostname: str, *, allow_localhost: bool) -> str | None:
    if hostname == "localhost":
        return hostname if allow_localhost else None
    if "%" in hostname:
        return None
    try:
        address = ip_address(hostname)
    except ValueError:
        if len(hostname) > 253 or not all(DNS_LABEL_PATTERN.fullmatch(label) for label in hostname.split(".")):
            return None
        return hostname.lower()
    if isinstance(address, IPv6Address):
        return f"[{address.compressed}]"
    return str(address)


def parse_public_origin(value: str, *, allow_localhost: bool) -> str | None:
    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    host = _parse_public_host(parsed.hostname, allow_localhost=allow_localhost)
    if host is None or parsed.netloc.endswith(":"):
        return None
    authority = host if port is None else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"
