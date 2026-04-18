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
from rentivo.models import format_brl
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.services.container import ConnectionServices
from rentivo.storage.factory import get_storage

console = Console()


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    initialize_db()

    with ConnectionServices.open(storage_factory=get_storage) as services:
        billings = services.billing_repo.list_all()

        if not billings:
            console.print("[yellow]Nenhuma cobranca encontrada.[/yellow]")
            return

        all_bills: list[tuple[Billing, Bill]] = []
        for billing in billings:
            assert billing.id is not None
            bills = services.bill_repo.list_by_billing(billing.id)
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
            link = services.storage.get_url(bill.pdf_path) if bill.pdf_path else "-"
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
            services.bill_service.regenerate_pdf(bill, billing)
            url = services.storage.get_url(bill.pdf_path) if bill.pdf_path else "-"
            console.print(f"  [green]\u2713[/green] {billing.name} - {bill.reference_month} \u2192 {url}")

        console.print(f"\n[green bold]{len(all_bills)} fatura(s) regenerada(s) com sucesso![/green bold]")


if __name__ == "__main__":  # pragma: no cover
    main()
