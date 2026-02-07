from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from billing.cli.bill_menu import generate_bill_menu, list_bills_menu
from billing.models import format_brl
from billing.models.billing import BillingItem, ItemType
from billing.services.bill_service import BillService
from billing.services.billing_service import BillingService

console = Console()


def _parse_amount(text: str) -> int | None:
    """Parse a user-entered amount like '2850' or '2850.00' into centavos."""
    text = text.strip().replace(",", ".")
    try:
        return int(round(float(text) * 100))
    except ValueError:
        return None


def create_billing_menu(billing_service: BillingService) -> None:
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

        item_type_str = questionary.select(
            "  Tipo:", choices=["Fixo", "Variável"]
        ).ask()
        item_type = ItemType.FIXED if item_type_str == "Fixo" else ItemType.VARIABLE

        amount = 0
        if item_type == ItemType.FIXED:
            while True:
                amount_str = questionary.text("  Valor (ex: 2850.00):").ask()
                parsed = _parse_amount(amount_str or "")
                if parsed is not None and parsed > 0:
                    amount = parsed
                    break
                console.print("[red]Valor inválido. Tente novamente.[/red]")

        items.append(
            BillingItem(description=desc, amount=amount, item_type=item_type)
        )
        console.print(f"  [green]Item adicionado: {desc}[/green]")

    if not items:
        console.print("[yellow]Nenhum item adicionado. Cobrança não criada.[/yellow]")
        return

    # Optional PIX key override for this billing
    from billing.settings import settings as app_settings

    pix_key = ""
    if app_settings.pix_key:
        console.print(f"\n  [dim]Chave PIX padrão: {app_settings.pix_key}[/dim]")
        override = questionary.confirm(
            "Usar uma chave PIX diferente para esta cobrança?", default=False
        ).ask()
        if override:
            pix_key = questionary.text("  Chave PIX:").ask() or ""
    else:
        pix_key = questionary.text(
            "Chave PIX para esta cobrança (opcional):"
        ).ask() or ""

    billing = billing_service.create_billing(name, description, items, pix_key=pix_key)
    console.print()
    console.print(f"[green bold]Cobrança '{billing.name}' criada com sucesso![/green bold]")


def list_billings_menu(
    billing_service: BillingService, bill_service: BillService
) -> None:
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

    choices = [f"{b.id} - {b.name}" for b in billings] + ["Voltar"]
    choice = questionary.select("Selecione uma cobrança:", choices=choices).ask()

    if choice is None or choice == "Voltar":
        return

    billing_id = int(choice.split(" - ")[0])
    billing = billing_service.get_billing(billing_id)
    if not billing:
        console.print("[red]Cobrança não encontrada.[/red]")
        return

    _billing_detail_menu(billing, billing_service, bill_service)


def _billing_detail_menu(
    billing, billing_service: BillingService, bill_service: BillService
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
                "Excluir Cobrança",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            break
        elif choice == "Gerar Nova Fatura":
            generate_bill_menu(billing, bill_service)
        elif choice == "Ver Faturas Anteriores":
            list_bills_menu(billing, bill_service)
        elif choice == "Excluir Cobrança":
            confirm = questionary.confirm(
                f"Tem certeza que deseja excluir '{billing.name}'?", default=False
            ).ask()
            if confirm:
                billing_service.delete_billing(billing.id)
                console.print("[green]Cobrança excluída.[/green]")
                break
