"""Send automated payment reminders / dunning for unpaid bills (REN-6).

Usage:
    python -m rentivo.scripts.send_payment_reminders
    python -m rentivo.scripts.send_payment_reminders --dry-run
    python -m rentivo.scripts.send_payment_reminders --date 2026-06-24

Intended to run once a day on a scheduler (cron / k8s CronJob). For each
billing template with reminders enabled it scans issued-but-unpaid bills and,
on the configured offsets relative to the due date (D-3, due date, D+3 by
default — see ``payment_reminder_offset_days``), enqueues one reminder per
recipient. It is idempotent: re-running on the same day will not re-send a
reminder already queued/sent for that bill+offset.

``--date`` overrides "today" (ISO ``YYYY-MM-DD``) for catch-up runs or testing.
The actual email delivery is handled asynchronously by the worker via the
existing ``communication.send`` job; this script only enqueues.
"""

from __future__ import annotations

import sys
from datetime import date, datetime

from rich.console import Console

from rentivo.communications.channels import get_reminder_channel
from rentivo.communications.reminders import parse_offset_days
from rentivo.constants import SP_TZ
from rentivo.db import get_connection, initialize_db
from rentivo.jobs.factory import get_job_backend
from rentivo.logging import configure_logging
from rentivo.repositories.factory import (
    get_audit_log_repository,
    get_bill_repository,
    get_billing_repository,
    get_communication_repository,
    get_communication_template_repository,
    get_recipient_repository,
)
from rentivo.services.audit_service import AuditService
from rentivo.services.communication_service import CommunicationService
from rentivo.services.job_service import JobService
from rentivo.services.payment_reminder_service import PaymentReminderService
from rentivo.settings import settings

console = Console()


def _parse_args(argv: list[str]) -> tuple[bool, date]:
    dry_run = "--dry-run" in argv
    today = datetime.now(SP_TZ).date()
    for arg in argv:
        if arg.startswith("--date"):
            _, _, value = arg.partition("=")
            if not value and arg == "--date":
                idx = argv.index(arg)
                value = argv[idx + 1] if idx + 1 < len(argv) else ""
            today = date.fromisoformat(value)
    return dry_run, today


def main() -> None:
    configure_logging(cli=True)
    dry_run, today = _parse_args(sys.argv[1:])

    if not settings.payment_reminders_enabled:
        console.print("[yellow]payment_reminders_enabled=false — nada a fazer.[/yellow]")
        return

    offsets = parse_offset_days(settings.payment_reminder_offset_days)
    if not offsets:
        console.print("[yellow]Nenhum offset configurado (payment_reminder_offset_days vazio).[/yellow]")
        return

    initialize_db()
    conn = get_connection()

    audit_service = AuditService(get_audit_log_repository())
    job_service = JobService(get_job_backend(conn), audit_service)
    communication_service = CommunicationService(
        communication_repo=get_communication_repository(),
        template_repo=get_communication_template_repository(),
        job_service=job_service,
    )
    channel = get_reminder_channel(settings.payment_reminder_channel, communication_service=communication_service)

    service = PaymentReminderService(
        billing_repo=get_billing_repository(),
        bill_repo=get_bill_repository(),
        recipient_repo=get_recipient_repository(),
        communication_repo=get_communication_repository(),
        communication_service=communication_service,
        channel=channel,
        offset_days=offsets,
    )

    console.print(
        f"[cyan]Lembretes de pagamento[/cyan] — data={today.isoformat()} "
        f"offsets={offsets} canal={channel.name}{' (dry-run)' if dry_run else ''}\n"
    )

    result = service.run(today, dry_run=dry_run)

    for plan in result.planned:
        console.print(
            f"  [green]→[/green] bill={plan.bill_id} offset={plan.offset_days:+d} "
            f"({plan.comm_type}) destinatários={plan.recipient_count}"
        )

    console.print(
        "\n[bold]Resumo[/bold]: "
        f"faturas analisadas={result.bills_scanned}, "
        f"lembretes {'planejados' if dry_run else 'enfileirados'}={len(result.planned)}, "
        f"destinatários={result.recipients_notified}"
    )
    console.print(
        "[dim]Ignoradas: "
        f"template_desligado={result.skipped_template_disabled} (por template), "
        f"status_nao_elegivel={result.skipped_not_remindable_status}, "
        f"sem_vencimento={result.skipped_no_due_date}, "
        f"fora_do_offset={result.skipped_not_due_today}, "
        f"ja_enviado={result.skipped_already_sent}, "
        f"sem_destinatarios={result.skipped_no_recipients}, "
        f"sem_pdf={result.skipped_no_pdf}[/dim]"
    )
    if dry_run:
        console.print("\n[yellow]--dry-run: nenhum lembrete foi enfileirado.[/yellow]")


if __name__ == "__main__":  # pragma: no cover
    main()
