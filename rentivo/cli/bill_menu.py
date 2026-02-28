from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from rentivo.constants import TYPE_LABELS, format_month
from rentivo.models import format_brl, parse_brl
from rentivo.models.audit_log import AuditEventType
from rentivo.models.bill import Bill, BillLineItem
from rentivo.models.billing import Billing, ItemType
from rentivo.services.audit_serializers import serialize_bill
from rentivo.services.audit_service import AuditService
from rentivo.services.bill_service import BillService

console = Console()


def _format_amount_input(centavos: int) -> str:
    """Format centavos for use as default input value: 8550 -> '85.50'"""
    return f"{centavos / 100:.2f}"


def _show_bill_detail(bill: Bill, bill_service: BillService) -> None:
    """Display a bill's line items and total."""
    detail_table = Table()
    detail_table.add_column("Descri\u00e7\u00e3o")
    detail_table.add_column("Tipo", justify="center")
    detail_table.add_column("Valor", justify="right")

    for item in bill.line_items:
        detail_table.add_row(
            item.description,
            TYPE_LABELS.get(item.item_type, item.item_type),
            format_brl(item.amount),
        )

    console.print(detail_table)
    console.print(f"  [bold]Total: {format_brl(bill.total_amount)}[/bold]")

    if bill.due_date:
        console.print(f"  Vencimento: {bill.due_date}")
    if bill.notes:
        console.print(f"  Observa\u00e7\u00f5es: {bill.notes}")
    if bill.pdf_path:
        url = bill_service.get_invoice_url(bill.pdf_path)
        console.print(f"  Link: {url}")


def generate_bill_menu(billing: Billing, bill_service: BillService, audit_service: AuditService) -> None:
    console.print()
    console.print("[bold]Gerar Nova Fatura[/bold]", style="cyan")

    # Reference month
    while True:
        month = questionary.text("M\u00eas de refer\u00eancia (AAAA-MM, ex: 2025-03):").ask()
        if month and len(month) == 7 and month[4] == "-":
            try:
                int(month[:4])
                int(month[5:])
                break
            except ValueError:
                pass
        console.print("[red]Formato inv\u00e1lido. Use AAAA-MM (ex: 2025-03).[/red]")

    # Show fixed items and prompt for variable items
    console.print()
    variable_amounts: dict[int, int] = {}

    for item in billing.items:
        if item.item_type == ItemType.FIXED:
            console.print(f"  [dim]Fixo:[/dim] {item.description} \u2192 {format_brl(item.amount)}")
        else:
            while True:
                val = questionary.text(f"  Valor para '{item.description}' (ex: 85.50):").ask()
                parsed = parse_brl(val or "")
                if parsed is not None and parsed >= 0:
                    if item.id is None:
                        raise ValueError("Variable billing item must have an id")
                    variable_amounts[item.id] = parsed
                    break
                console.print("[red]Valor inv\u00e1lido. Tente novamente.[/red]")

    # Extra expenses
    extras: list[tuple[str, int]] = []
    console.print()
    while True:
        add = questionary.confirm("Adicionar despesa extra?", default=False).ask()
        if not add:
            break

        desc = questionary.text("  Descri\u00e7\u00e3o da despesa:").ask()
        if not desc:
            continue

        while True:
            val = questionary.text("  Valor (ex: 50.00):").ask()
            parsed = parse_brl(val or "")
            if parsed is not None and parsed > 0:
                extras.append((desc, parsed))
                console.print(f"  [green]Despesa adicionada: {desc}[/green]")
                break
            console.print("[red]Valor inv\u00e1lido. Tente novamente.[/red]")

    # Due date
    due_date = questionary.text("Vencimento (ex: 10/03/2025, opcional):").ask() or ""

    # Notes
    notes = questionary.text("Observa\u00e7\u00f5es (opcional):").ask() or ""

    # Generate
    bill = bill_service.generate_bill(
        billing=billing,
        reference_month=month,
        variable_amounts=variable_amounts,
        extras=extras,
        notes=notes,
        due_date=due_date,
    )

    audit_service.safe_log(
        AuditEventType.BILL_CREATE,
        source="cli",
        entity_type="bill",
        entity_id=bill.id,
        entity_uuid=bill.uuid,
        new_state=serialize_bill(bill),
    )

    console.print()
    console.print("[green bold]Fatura gerada com sucesso![/green bold]")
    console.print(f"  Total: [bold]{format_brl(bill.total_amount)}[/bold]")
    url = bill_service.get_invoice_url(bill.pdf_path)
    console.print(f"  Link: {url}")


def edit_bill_menu(bill: Bill, billing: Billing, bill_service: BillService, audit_service: AuditService) -> Bill:
    console.print()
    console.print("[bold]Editar Fatura[/bold]", style="cyan")
    console.print(f"  Refer\u00eancia: {format_month(bill.reference_month)}")
    console.print()

    previous_state = serialize_bill(bill)

    new_line_items: list[BillLineItem] = []
    sort = 0

    # Walk through existing line items by type
    # Fixed and variable items — let user update amounts
    for item in bill.line_items:
        if item.item_type in (ItemType.FIXED, ItemType.VARIABLE):
            default = _format_amount_input(item.amount)
            while True:
                val = questionary.text(
                    f"  {item.description} [{TYPE_LABELS[item.item_type]}] (atual: {format_brl(item.amount)}):",
                    default=default,
                ).ask()
                parsed = parse_brl(val or "")
                if parsed is not None and parsed >= 0:
                    new_line_items.append(
                        BillLineItem(
                            description=item.description,
                            amount=parsed,
                            item_type=item.item_type,
                            sort_order=sort,
                        )
                    )
                    sort += 1
                    break
                console.print("[red]Valor inv\u00e1lido. Tente novamente.[/red]")

    # Existing extras — let user keep, edit, or remove each
    existing_extras = [i for i in bill.line_items if i.item_type == ItemType.EXTRA]
    if existing_extras:
        console.print()
        console.print("  [dim]Despesas extras existentes:[/dim]")

    for item in existing_extras:
        action = questionary.select(
            f"  '{item.description}' ({format_brl(item.amount)}):",
            choices=["Manter", "Editar valor", "Remover"],
        ).ask()

        if action == "Manter":
            new_line_items.append(
                BillLineItem(
                    description=item.description,
                    amount=item.amount,
                    item_type=ItemType.EXTRA,
                    sort_order=sort,
                )
            )
            sort += 1
        elif action == "Editar valor":
            default = _format_amount_input(item.amount)
            while True:
                val = questionary.text(
                    f"    Novo valor para '{item.description}':",
                    default=default,
                ).ask()
                parsed = parse_brl(val or "")
                if parsed is not None and parsed > 0:
                    new_line_items.append(
                        BillLineItem(
                            description=item.description,
                            amount=parsed,
                            item_type=ItemType.EXTRA,
                            sort_order=sort,
                        )
                    )
                    sort += 1
                    break
                console.print("[red]Valor inv\u00e1lido. Tente novamente.[/red]")
        # "Remover" — just skip it

    # Add new extras
    console.print()
    while True:
        add = questionary.confirm("Adicionar nova despesa extra?", default=False).ask()
        if not add:
            break

        desc = questionary.text("  Descri\u00e7\u00e3o da despesa:").ask()
        if not desc:
            continue

        while True:
            val = questionary.text("  Valor (ex: 50.00):").ask()
            parsed = parse_brl(val or "")
            if parsed is not None and parsed > 0:
                new_line_items.append(
                    BillLineItem(
                        description=desc,
                        amount=parsed,
                        item_type=ItemType.EXTRA,
                        sort_order=sort,
                    )
                )
                sort += 1
                console.print(f"  [green]Despesa adicionada: {desc}[/green]")
                break
            console.print("[red]Valor inv\u00e1lido. Tente novamente.[/red]")

    # Due date
    due_date = (
        questionary.text(
            "Vencimento (ex: 10/03/2025, opcional):",
            default=bill.due_date or "",
        ).ask()
        or ""
    )

    # Notes
    notes = (
        questionary.text(
            "Observa\u00e7\u00f5es:",
            default=bill.notes,
        ).ask()
        or ""
    )

    # Update
    updated = bill_service.update_bill(
        bill=bill,
        billing=billing,
        line_items=new_line_items,
        notes=notes,
        due_date=due_date,
    )

    audit_service.safe_log(
        AuditEventType.BILL_UPDATE,
        source="cli",
        entity_type="bill",
        entity_id=updated.id,
        entity_uuid=updated.uuid,
        previous_state=previous_state,
        new_state=serialize_bill(updated),
    )

    console.print()
    console.print("[green bold]Fatura atualizada com sucesso![/green bold]")
    console.print(f"  Total: [bold]{format_brl(updated.total_amount)}[/bold]")
    url = bill_service.get_invoice_url(updated.pdf_path)
    console.print(f"  Link: {url}")

    return updated


def list_bills_menu(billing: Billing, bill_service: BillService, audit_service: AuditService) -> None:
    if billing.id is None:
        console.print("[red]Cobrança inválida.[/red]")
        return
    bills = bill_service.list_bills(billing.id)

    if not bills:
        console.print("[yellow]Nenhuma fatura gerada para esta cobran\u00e7a.[/yellow]")
        return

    table = Table(title=f"Faturas - {billing.name}")
    table.add_column("#", style="dim")
    table.add_column("Refer\u00eancia")
    table.add_column("Total", justify="right")
    table.add_column("Link", style="dim")

    for b in bills:
        url = bill_service.get_invoice_url(b.pdf_path) if b.pdf_path else "-"
        table.add_row(
            str(b.id),
            format_month(b.reference_month),
            format_brl(b.total_amount),
            url,
        )

    console.print()
    console.print(table)

    bill_choices = {f"{b.id} - {format_month(b.reference_month)}": b for b in bills}
    choices = list(bill_choices.keys()) + ["Voltar"]
    choice = questionary.select("Selecione uma fatura:", choices=choices).ask()

    if choice is None or choice == "Voltar":
        return

    selected = bill_choices[choice]
    bill = bill_service.get_bill(selected.id)
    if not bill:
        console.print("[red]Fatura n\u00e3o encontrada.[/red]")
        return

    _bill_detail_menu(bill, billing, bill_service, audit_service)


def _bill_detail_menu(bill: Bill, billing: Billing, bill_service: BillService, audit_service: AuditService) -> None:
    while True:
        console.print()
        console.print(f"[bold cyan]Fatura {format_month(bill.reference_month)}[/bold cyan]")
        _show_bill_detail(bill, bill_service)
        if bill.paid_at:
            console.print(f"  [green]Pago em: {bill.paid_at.strftime('%d/%m/%Y %H:%M')}[/green]")
        console.print()

        paid_label = "Desmarcar Pagamento" if bill.paid_at else "Marcar como Pago"
        action = questionary.select(
            "A\u00e7\u00f5es:",
            choices=[
                "Editar Fatura",
                paid_label,
                "Regenerar PDF",
                "Excluir Fatura",
                "Voltar",
            ],
        ).ask()

        if action is None or action == "Voltar":
            break
        elif action == "Editar Fatura":
            bill = edit_bill_menu(bill, billing, bill_service, audit_service)
        elif action == paid_label:
            previous_state = serialize_bill(bill)
            bill = bill_service.toggle_paid(bill)

            audit_service.safe_log(
                AuditEventType.BILL_TOGGLE_PAID,
                source="cli",
                entity_type="bill",
                entity_id=bill.id,
                entity_uuid=bill.uuid,
                previous_state=previous_state,
                new_state=serialize_bill(bill),
            )

            if bill.paid_at:
                console.print("[green]Fatura marcada como paga![/green]")
            else:
                console.print("[yellow]Pagamento desmarcado.[/yellow]")
        elif action == "Regenerar PDF":
            previous_state = serialize_bill(bill)
            bill = bill_service.regenerate_pdf(bill, billing)

            audit_service.safe_log(
                AuditEventType.BILL_REGENERATE_PDF,
                source="cli",
                entity_type="bill",
                entity_id=bill.id,
                entity_uuid=bill.uuid,
                previous_state=previous_state,
                new_state=serialize_bill(bill),
            )

            url = bill_service.get_invoice_url(bill.pdf_path)
            console.print("[green]PDF regenerado![/green]")
            console.print(f"  Link: {url}")
        elif action == "Excluir Fatura":
            confirm = questionary.confirm("Tem certeza que deseja excluir esta fatura?", default=False).ask()
            if confirm:
                if bill.id is None:
                    console.print("[red]Fatura inválida.[/red]")
                    break
                previous_state = serialize_bill(bill)
                bill_service.delete_bill(bill.id)

                audit_service.safe_log(
                    AuditEventType.BILL_DELETE,
                    source="cli",
                    entity_type="bill",
                    entity_id=bill.id,
                    entity_uuid=bill.uuid,
                    previous_state=previous_state,
                )

                console.print("[green]Fatura exclu\u00edda.[/green]")
                break
