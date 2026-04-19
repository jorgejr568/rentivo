"""List all invoices and regenerate their PDFs with the current template.

Usage:
    python -m rentivo.scripts.regenerate_pdfs
    python -m rentivo.scripts.regenerate_pdfs --dry-run
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

from rentivo.db import initialize_db
from rentivo.logging import configure_logging
from rentivo.models import format_brl
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.repositories.factory import (
    get_bill_repository,
    get_billing_repository,
    get_organization_repository,
    get_receipt_repository,
    get_user_repository,
)
from rentivo.services.bill_service import BillService
from rentivo.services.pix_service import PixService
from rentivo.storage.factory import get_storage

console = Console()


def main() -> None:
    configure_logging(cli=True)
    dry_run = "--dry-run" in sys.argv

    initialize_db()

    billing_repo = get_billing_repository()
    bill_repo = get_bill_repository()
    receipt_repo = get_receipt_repository()
    user_repo = get_user_repository()
    org_repo = get_organization_repository()
    storage = get_storage()

    pix_service = PixService(user_repo, org_repo)
    bill_service = BillService(bill_repo, storage, receipt_repo, pix_service=pix_service)

    billings = billing_repo.list_all()

    if not billings:
        console.print("[yellow]Nenhuma cobranca encontrada.[/yellow]")
        return

    all_bills: list[tuple[Billing, Bill]] = []
    for billing in billings:
        assert billing.id is not None
        bills = bill_repo.list_by_billing(billing.id)
        for bill in bills:
            all_bills.append((billing, bill))

    if not all_bills:
        console.print("[yellow]Nenhuma fatura encontrada.[/yellow]")
        return

    table = Table(title="Faturas encontradas")
    table.add_column("#", style="dim")
    table.add_column("Cobranca", style="bold")
    table.add_column("Referencia")
    table.add_column("Total", justify="right")
    table.add_column("Link", style="dim")

    for billing, bill in all_bills:
        link = storage.get_url(bill.pdf_path) if bill.pdf_path else "-"
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

    regenerated = 0
    skipped: list[tuple[str, str, str]] = []
    for billing, bill in all_bills:
        try:
            bill_service.regenerate_pdf(bill, billing)
        except ValueError as e:
            skipped.append((billing.name, bill.reference_month, str(e)))
            console.print(f"  [yellow]\u2717[/yellow] {billing.name} - {bill.reference_month}: {e}")
            continue
        regenerated += 1
        url = storage.get_url(bill.pdf_path) if bill.pdf_path else "-"
        console.print(f"  [green]\u2713[/green] {billing.name} - {bill.reference_month} \u2192 {url}")

    console.print(f"\n[green bold]{regenerated} fatura(s) regenerada(s) com sucesso![/green bold]")
    if skipped:
        console.print(f"[yellow]{len(skipped)} fatura(s) ignorada(s) por falta de configuração de PIX.[/yellow]")


if __name__ == "__main__":  # pragma: no cover
    main()
