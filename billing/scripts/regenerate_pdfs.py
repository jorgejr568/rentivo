"""List all invoices and regenerate their PDFs with the current template.

Usage:
    python -m billing.scripts.regenerate_pdfs
    python -m billing.scripts.regenerate_pdfs --dry-run
"""
from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

from billing.db import initialize_db
from billing.models import format_brl
from billing.models.billing import Billing
from billing.pdf.invoice import InvoicePDF
from billing.pix import generate_pix_payload, generate_pix_qrcode_png
from billing.repositories.factory import get_bill_repository, get_billing_repository
from billing.settings import settings
from billing.storage.factory import get_storage

console = Console()


def _get_pix_data(billing: Billing, total_centavos: int) -> tuple[bytes | None, str, str]:
    pix_key = billing.pix_key or settings.pix_key
    if not pix_key or not settings.pix_merchant_name or not settings.pix_merchant_city:
        return None, "", ""
    amount = total_centavos / 100
    payload = generate_pix_payload(
        pix_key=pix_key,
        merchant_name=settings.pix_merchant_name,
        merchant_city=settings.pix_merchant_city,
        amount=amount,
    )
    png = generate_pix_qrcode_png(
        pix_key=pix_key,
        merchant_name=settings.pix_merchant_name,
        merchant_city=settings.pix_merchant_city,
        amount=amount,
    )
    return png, pix_key, payload


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    initialize_db()

    billing_repo = get_billing_repository()
    bill_repo = get_bill_repository()
    storage = get_storage()
    pdf_generator = InvoicePDF()

    billings = billing_repo.list_all()

    if not billings:
        console.print("[yellow]Nenhuma cobrança encontrada.[/yellow]")
        return

    all_bills: list[tuple[Billing, object]] = []
    for billing in billings:
        bills = bill_repo.list_by_billing(billing.id)  # type: ignore[arg-type]
        for bill in bills:
            all_bills.append((billing, bill))

    if not all_bills:
        console.print("[yellow]Nenhuma fatura encontrada.[/yellow]")
        return

    table = Table(title="Faturas encontradas")
    table.add_column("#", style="dim")
    table.add_column("Cobrança", style="bold")
    table.add_column("Referência")
    table.add_column("Total", justify="right")
    table.add_column("Link", style="dim")

    for billing, bill in all_bills:
        link = storage.get_presigned_url(bill.pdf_path) if bill.pdf_path else "-"
        table.add_row(
            str(bill.id),
            billing.name,
            bill.reference_month,
            format_brl(bill.total_amount),
            link,
        )

    console.print(table)
    console.print(f"\nTotal de faturas: [bold]{len(all_bills)}[/bold]")

    if dry_run:
        console.print("\n[yellow]--dry-run: nenhum PDF foi regenerado.[/yellow]")
        return

    console.print("\n[cyan]Regenerando PDFs...[/cyan]\n")

    for billing, bill in all_bills:
        pix_png, pix_key, pix_payload = _get_pix_data(billing, bill.total_amount)
        pdf_bytes = pdf_generator.generate(
            bill, billing.name,
            pix_qrcode_png=pix_png, pix_key=pix_key, pix_payload=pix_payload,
        )
        key = f"{billing.uuid}/{bill.uuid}.pdf"
        path = storage.save(key, pdf_bytes)
        bill_repo.update_pdf_path(bill.id, path)  # type: ignore[arg-type]
        url = storage.get_presigned_url(path)
        console.print(f"  [green]\u2713[/green] {billing.name} - {bill.reference_month} \u2192 {url}")

    console.print(f"\n[green bold]{len(all_bills)} fatura(s) regenerada(s) com sucesso![/green bold]")


if __name__ == "__main__":
    main()
