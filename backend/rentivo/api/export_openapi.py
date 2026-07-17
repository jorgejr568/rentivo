from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from rentivo.api.app import create_app


def export_openapi(output: Path) -> None:
    schema = create_app().openapi()
    content = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    export_openapi(args.output)


if __name__ == "__main__":
    main()
