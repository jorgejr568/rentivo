from rentivo.cli.app import main_menu
from rentivo.db import initialize_db
from rentivo.logging import configure_logging


def main() -> None:
    configure_logging(cli=True)
    initialize_db()
    main_menu()


if __name__ == "__main__":
    main()
