from rentivo.cli.app import main_menu
from rentivo.db import initialize_db
from rentivo.logging import configure_logging
from rentivo.observability import configure_tracing


def main() -> None:
    configure_logging(cli=True)
    configure_tracing()
    initialize_db()
    main_menu()


if __name__ == "__main__":
    main()
