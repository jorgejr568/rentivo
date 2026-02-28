from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from rentivo.cli.bill_menu import generate_bill_menu, list_bills_menu
from rentivo.models import format_brl, parse_brl
from rentivo.models.audit_log import AuditEventType
from rentivo.models.billing import BillingItem, ItemType
from rentivo.services.audit_serializers import serialize_billing
from rentivo.services.audit_service import AuditService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService

console = Console()


def create_billing_menu(billing_service: BillingService, audit_service: AuditService) -> None:
    console.print()
    console.print("[bold]Nova Cobrança[/bold]", style="cyan")

    name = questionary.text("Nome da cobrança:").ask()
    if not name:
        console.print("[yellow]Operação cancelada.[/yellow]")
        return

    description = questionary.text("Descrição (opcional):").ask() or ""

    items: list[BillingItem] = []
    console.print()
    console.print("Adicione os itens da cobrança (aluguel, água, etc.):")

    while True:
        add = questionary.confirm("Adicionar item?", default=True).ask()
        if not add:
            break

        desc = questionary.text("  Descrição do item:").ask()
        if not desc:
            continue

        item_type_str = questionary.select("  Tipo:", choices=["Fixo", "Variável"]).ask()
        item_type = ItemType.FIXED if item_type_str == "Fixo" else ItemType.VARIABLE

        amount = 0
        if item_type == ItemType.FIXED:
            while True:
                amount_str = questionary.text("  Valor (ex: 2850.00):").ask()
                parsed = parse_brl(amount_str or "")
                if parsed is not None and parsed > 0:
                    amount = parsed
                    break
                console.print("[red]Valor inválido. Tente novamente.[/red]")

        items.append(BillingItem(description=desc, amount=amount, item_type=item_type))
        console.print(f"  [green]Item adicionado: {desc}[/green]")

    if not items:
        console.print("[yellow]Nenhum item adicionado. Cobrança não criada.[/yellow]")
        return

    # Optional PIX key override for this billing
    from rentivo.settings import settings as app_settings

    pix_key = ""
    if app_settings.pix_key:
        console.print(f"\n  [dim]Chave PIX padrão: {app_settings.pix_key}[/dim]")
        override = questionary.confirm("Usar uma chave PIX diferente para esta cobrança?", default=False).ask()
        if override:
            pix_key = questionary.text("  Chave PIX:").ask() or ""
    else:
        pix_key = questionary.text("Chave PIX para esta cobrança (opcional):").ask() or ""

    billing = billing_service.create_billing(name, description, items, pix_key=pix_key)

    audit_service.safe_log(
        AuditEventType.BILLING_CREATE,
        source="cli",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        new_state=serialize_billing(billing),
    )

    console.print()
    console.print(f"[green bold]Cobrança '{billing.name}' criada com sucesso![/green bold]")


def list_billings_menu(billing_service: BillingService, bill_service: BillService, audit_service: AuditService) -> None:
    billings = billing_service.list_billings()

    if not billings:
        console.print("[yellow]Nenhuma cobrança cadastrada.[/yellow]")
        return

    table = Table(title="Cobranças")
    table.add_column("#", style="dim")
    table.add_column("Nome", style="bold")
    table.add_column("Descrição")
    table.add_column("Itens", justify="right")

    for b in billings:
        table.add_row(str(b.id), b.name, b.description, str(len(b.items)))

    console.print()
    console.print(table)
    console.print()

    billing_choices = {f"{b.id} - {b.name}": b for b in billings}
    choices = list(billing_choices.keys()) + ["Voltar"]
    choice = questionary.select("Selecione uma cobrança:", choices=choices).ask()

    if choice is None or choice == "Voltar":
        return

    billing = billing_choices[choice]
    if not billing:  # pragma: no cover
        console.print("[red]Cobrança não encontrada.[/red]")
        return

    _billing_detail_menu(billing, billing_service, bill_service, audit_service)


def _billing_detail_menu(
    billing, billing_service: BillingService, bill_service: BillService, audit_service: AuditService
) -> None:
    while True:
        console.print()
        console.print(f"[bold cyan]Cobrança: {billing.name}[/bold cyan]")
        if billing.description:
            console.print(f"  {billing.description}")

        table = Table(title="Itens da Cobrança")
        table.add_column("Descrição")
        table.add_column("Tipo", justify="center")
        table.add_column("Valor", justify="right")

        for item in billing.items:
            tipo = "Fixo" if item.item_type == ItemType.FIXED else "Variável"
            valor = format_brl(item.amount) if item.item_type == ItemType.FIXED else "-"
            table.add_row(item.description, tipo, valor)

        console.print(table)
        console.print()

        choice = questionary.select(
            "Ações:",
            choices=[
                "Gerar Nova Fatura",
                "Ver Faturas Anteriores",
                "Editar Cobrança",
                "Excluir Cobrança",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            break
        elif choice == "Gerar Nova Fatura":
            generate_bill_menu(billing, bill_service, audit_service)
        elif choice == "Ver Faturas Anteriores":
            list_bills_menu(billing, bill_service, audit_service)
        elif choice == "Editar Cobrança":
            billing = _edit_billing_menu(billing, billing_service, audit_service)
        elif choice == "Excluir Cobrança":
            confirm = questionary.confirm(f"Tem certeza que deseja excluir '{billing.name}'?", default=False).ask()
            if confirm:
                previous_state = serialize_billing(billing)
                billing_service.delete_billing(billing.id)

                audit_service.safe_log(
                    AuditEventType.BILLING_DELETE,
                    source="cli",
                    entity_type="billing",
                    entity_id=billing.id,
                    entity_uuid=billing.uuid,
                    previous_state=previous_state,
                )

                console.print("[green]Cobrança excluída.[/green]")
                break


def _edit_billing_menu(billing, billing_service: BillingService, audit_service: AuditService):
    """Sub-menu for editing a billing's PIX key and items."""
    while True:
        choice = questionary.select(
            "Editar Cobrança:",
            choices=[
                "Editar Chave PIX",
                "Editar Item",
                "Adicionar Item",
                "Remover Item",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            break
        elif choice == "Editar Chave PIX":
            billing = _edit_pix_key(billing, billing_service, audit_service)
        elif choice == "Editar Item":
            billing = _edit_item(billing, billing_service, audit_service)
        elif choice == "Adicionar Item":
            billing = _add_item(billing, billing_service, audit_service)
        elif choice == "Remover Item":
            billing = _remove_item(billing, billing_service, audit_service)

    return billing


def _edit_pix_key(billing, billing_service: BillingService, audit_service: AuditService):
    current = billing.pix_key or "(nenhuma)"
    console.print(f"  Chave PIX atual: [bold]{current}[/bold]")
    new_key = questionary.text("  Nova chave PIX:", default=billing.pix_key).ask()
    if new_key is None:
        return billing
    previous_state = serialize_billing(billing)
    billing.pix_key = new_key
    billing = billing_service.update_billing(billing)

    audit_service.safe_log(
        AuditEventType.BILLING_UPDATE,
        source="cli",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(billing),
    )

    console.print("[green]Chave PIX atualizada.[/green]")
    return billing


def _edit_item(billing, billing_service: BillingService, audit_service: AuditService):
    if not billing.items:
        console.print("[yellow]Nenhum item para editar.[/yellow]")
        return billing

    choices = [
        f"{item.description} ({format_brl(item.amount) if item.item_type == ItemType.FIXED else 'Variável'})"
        for item in billing.items
    ] + ["Voltar"]

    choice = questionary.select("Selecione o item:", choices=choices).ask()
    if choice is None or choice == "Voltar":
        return billing

    idx = choices.index(choice)
    item = billing.items[idx]

    new_desc = questionary.text("  Descrição:", default=item.description).ask()
    if new_desc is None:
        return billing
    previous_state = serialize_billing(billing)
    item.description = new_desc

    item_type_str = questionary.select(
        "  Tipo:",
        choices=["Fixo", "Variável"],
        default="Fixo" if item.item_type == ItemType.FIXED else "Variável",
    ).ask()
    if item_type_str is None:
        return billing
    item.item_type = ItemType.FIXED if item_type_str == "Fixo" else ItemType.VARIABLE

    if item.item_type == ItemType.FIXED:
        while True:
            default_val = f"{item.amount / 100:.2f}" if item.amount else ""
            amount_str = questionary.text("  Valor (ex: 2850.00):", default=default_val).ask()
            if amount_str is None:
                return billing
            parsed = parse_brl(amount_str)
            if parsed is not None and parsed > 0:
                item.amount = parsed
                break
            console.print("[red]Valor inválido. Tente novamente.[/red]")
    else:
        item.amount = 0

    billing = billing_service.update_billing(billing)

    audit_service.safe_log(
        AuditEventType.BILLING_UPDATE,
        source="cli",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(billing),
    )

    console.print(f"[green]Item '{item.description}' atualizado.[/green]")
    return billing


def _add_item(billing, billing_service: BillingService, audit_service: AuditService):
    desc = questionary.text("  Descrição do item:").ask()
    if not desc:
        console.print("[yellow]Operação cancelada.[/yellow]")
        return billing

    item_type_str = questionary.select("  Tipo:", choices=["Fixo", "Variável"]).ask()
    if item_type_str is None:
        return billing
    item_type = ItemType.FIXED if item_type_str == "Fixo" else ItemType.VARIABLE

    amount = 0
    if item_type == ItemType.FIXED:
        while True:
            amount_str = questionary.text("  Valor (ex: 2850.00):").ask()
            if amount_str is None:
                return billing
            parsed = parse_brl(amount_str or "")
            if parsed is not None and parsed > 0:
                amount = parsed
                break
            console.print("[red]Valor inválido. Tente novamente.[/red]")

    previous_state = serialize_billing(billing)
    billing.items.append(BillingItem(description=desc, amount=amount, item_type=item_type))
    billing = billing_service.update_billing(billing)

    audit_service.safe_log(
        AuditEventType.BILLING_UPDATE,
        source="cli",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(billing),
    )

    console.print(f"[green]Item '{desc}' adicionado.[/green]")
    return billing


def _remove_item(billing, billing_service: BillingService, audit_service: AuditService):
    if not billing.items:
        console.print("[yellow]Nenhum item para remover.[/yellow]")
        return billing

    previous_state = serialize_billing(billing)

    choices = [
        f"{item.description} ({format_brl(item.amount) if item.item_type == ItemType.FIXED else 'Variável'})"
        for item in billing.items
    ] + ["Voltar"]

    choice = questionary.select("Selecione o item para remover:", choices=choices).ask()
    if choice is None or choice == "Voltar":
        return billing

    idx = choices.index(choice)
    removed = billing.items.pop(idx)

    if not billing.items:
        console.print("[red]Não é possível remover todos os itens. A cobrança precisa de pelo menos um item.[/red]")
        billing.items.insert(idx, removed)
        return billing

    confirm = questionary.confirm(f"Remover '{removed.description}'?", default=False).ask()
    if not confirm:
        billing.items.insert(idx, removed)
        return billing

    billing = billing_service.update_billing(billing)

    audit_service.safe_log(
        AuditEventType.BILLING_UPDATE,
        source="cli",
        entity_type="billing",
        entity_id=billing.id,
        entity_uuid=billing.uuid,
        previous_state=previous_state,
        new_state=serialize_billing(billing),
    )

    console.print(f"[green]Item '{removed.description}' removido.[/green]")
    return billing
