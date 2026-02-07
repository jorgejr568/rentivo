import questionary
from rich.console import Console

from billing.cli.billing_menu import create_billing_menu, list_billings_menu
from billing.repositories.factory import get_bill_repository, get_billing_repository
from billing.services.bill_service import BillService
from billing.services.billing_service import BillingService
from billing.storage.factory import get_storage

console = Console()


def _build_services() -> tuple[BillingService, BillService]:
    billing_repo = get_billing_repository()
    bill_repo = get_bill_repository()
    storage = get_storage()
    return BillingService(billing_repo), BillService(bill_repo, storage)


def main_menu() -> None:
    billing_service, bill_service = _build_services()

    console.print()
    console.print("[bold]Gerador de Cobranças[/bold]", style="cyan")
    console.print()

    while True:
        choice = questionary.select(
            "Menu Principal",
            choices=[
                "Listar Cobranças",
                "Criar Nova Cobrança",
                "Sair",
            ],
        ).ask()

        if choice is None or choice == "Sair":
            console.print("[bold]Até logo![/bold]")
            break
        elif choice == "Listar Cobranças":
            list_billings_menu(billing_service, bill_service)
        elif choice == "Criar Nova Cobrança":
            create_billing_menu(billing_service)
