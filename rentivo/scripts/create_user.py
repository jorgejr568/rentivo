"""Create a web user interactively.

Usage:
    python -m rentivo.scripts.create_user
"""

from __future__ import annotations

import getpass

from rentivo.db import initialize_db
from rentivo.services.container import ConnectionServices


def main() -> None:
    initialize_db()

    with ConnectionServices.open() as services:
        service = services.user_service
        username = input("Username: ")
        password = getpass.getpass("Password: ")
        service.create_user(username, password)
        print(f"User {username} created.")


if __name__ == "__main__":  # pragma: no cover
    main()
