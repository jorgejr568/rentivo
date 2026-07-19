"""List all invoices and enqueue a `pdf.render` job for each one.

Usage:
    python -m rentivo.scripts.regenerate_pdfs
    python -m rentivo.scripts.regenerate_pdfs --dry-run

Behavior:
- Walks every billing and every bill.
- Skips bills whose billing has no PIX configured (the worker would only
  dead-letter them after 5 retries).
- For every remaining bill, enqueues a single ``pdf.render`` job and
  prints the resulting ULID.
- Prints a final summary: how many were enqueued, plus how many
  ``pdf.render`` jobs are still pending or running. The script does NOT
  wait for the worker to drain.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table
from ulid import ULID

from rentivo.db import get_connection, initialize_db
from rentivo.jobs.factory import get_job_backend
from rentivo.logging import configure_logging
from rentivo.models import format_brl
from rentivo.models.bill import Bill
from rentivo.models.billing import Billing
from rentivo.repositories.factory import (
    get_audit_log_repository,
    get_bill_repository,
    get_billing_repository,
    get_job_repository,
    get_organization_repository,
    get_receipt_repository,  # noqa: F401 — kept so existing test mocks still bind cleanly
    get_user_repository,
)
from rentivo.services.audit_service import AuditService
from rentivo.services.job_service import JobService
from rentivo.services.pix_service import PixService
from rentivo.storage.factory import get_storage

console = Console()


def main() -> None:
    configure_logging(cli=True)
    dry_run = "--dry-run" in sys.argv

    initialize_db()

    billing_repo = get_billing_repository()
    bill_repo = get_bill_repository()
    user_repo = get_user_repository()
    org_repo = get_organization_repository()
    audit_repo = get_audit_log_repository()
    job_repo = get_job_repository()
    storage = get_storage()

    pix_service = PixService(user_repo, org_repo)
    audit_service = AuditService(audit_repo)
    job_service = JobService(get_job_backend(get_connection()), audit_service)

    billings = billing_repo.list_all()

    if not billings:
        console.print("[yellow]Nenhuma cobranca encontrada.[/yellow]")
        return

    all_bills: list[tuple[Billing, Bill]] = []
    for billing in billings:
        assert billing.id is not None
        for bill in bill_repo.list_by_billing(billing.id):
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
        console.print("\n[yellow]--dry-run: nenhuma fatura foi enfileirada.[/yellow]")
        return

    console.print("\n[cyan]Enfileirando jobs pdf.render...[/cyan]\n")

    enqueued = 0
    skipped = 0
    for billing, bill in all_bills:
        # Pre-flight PIX check — bills without PIX would just dead-letter
        # in the worker after 5 retries, so we filter them here.
        if pix_service.resolve_for_billing(billing) is None:
            skipped += 1
            console.print(f"  [yellow]✗[/yellow] {billing.name} - {bill.reference_month}: PIX não configurado")
            continue

        assert bill.id is not None
        previous_render_status = bill.pdf_render_status
        render_operation_id = str(ULID())
        bill_repo.begin_pdf_render(bill.id, render_operation_id)
        bill.pdf_render_status = "pending"
        try:
            job = job_service.enqueue(
                "pdf.render",
                {"bill_id": bill.id, "render_operation_id": render_operation_id},
                source="cli",
            )
        except Exception:
            if bill_repo.finish_pdf_render(bill.id, render_operation_id, previous_render_status):
                bill.pdf_render_status = previous_render_status
            raise
        enqueued += 1
        console.print(f"  [green]✓[/green] {billing.name} - {bill.reference_month} → enqueued ulid={job.ulid}")

    pending_or_running = job_repo.count_by_type_and_statuses("pdf.render", ("pending", "running"))
    console.print(f"\n[green bold]{enqueued} fatura(s) enfileirada(s) com sucesso![/green bold]")
    console.print(f"[dim]{pending_or_running} job(s) pdf.render aguardando o worker (pending+running).[/dim]")
    if skipped:
        console.print(f"[yellow]{skipped} fatura(s) ignorada(s) por falta de configuração de PIX.[/yellow]")


if __name__ == "__main__":  # pragma: no cover
    main()
