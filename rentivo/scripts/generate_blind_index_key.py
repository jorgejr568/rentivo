"""Generate a KMS-sealed HMAC key for the email blind index.

Usage:
    python -m rentivo.scripts.generate_blind_index_key

Output:
    base64-encoded KMS ciphertext blob to set as
    ``RENTIVO_EMAIL_BLIND_INDEX_KEY_CIPHERTEXT``.

WARNING: every run generates a NEW key. Running it after the system is in
production invalidates every ``users.email_hash`` row and forces a backfill.
"""

from __future__ import annotations

import base64
import secrets
import sys

from rich.console import Console

from rentivo.logging import configure_logging
from rentivo.settings import settings

console = Console()


def _get_kms_client():  # pragma: no cover - stubbed in tests
    import boto3

    kwargs: dict[str, str] = {"region_name": settings.kms_region}
    if settings.kms_access_key_id:
        kwargs["aws_access_key_id"] = settings.kms_access_key_id
    if settings.kms_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.kms_secret_access_key
    if settings.kms_endpoint_url:
        kwargs["endpoint_url"] = settings.kms_endpoint_url
    return boto3.client("kms", **kwargs)


def main() -> None:
    configure_logging(cli=True)
    if not settings.kms_key_id:
        console.print("[red]RENTIVO_KMS_KEY_ID is not set.[/red]")
        sys.exit(2)

    plaintext = secrets.token_bytes(32)
    client = _get_kms_client()
    response = client.encrypt(KeyId=settings.kms_key_id, Plaintext=plaintext)
    ciphertext_b64 = base64.b64encode(response["CiphertextBlob"]).decode()

    console.print("[bold yellow]New blind-index key generated.[/bold yellow]")
    console.print(
        "[red]This invalidates every existing users.email_hash row. "
        "Run `make backfill-encryption` after deploying.[/red]\n"
    )
    console.print("Set this in your environment:\n")
    console.print(
        f"  RENTIVO_EMAIL_BLIND_INDEX_KEY_CIPHERTEXT={ciphertext_b64}\n",
        soft_wrap=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
