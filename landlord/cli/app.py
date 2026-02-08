import questionary
from rich.console import Console

from landlord.cli.billing_menu import create_billing_menu, list_billings_menu
from landlord.cli.user_menu import user_management_menu
from landlord.repositories.factory import (
    get_bill_repository,
    get_billing_repository,
    get_user_repository,
)
from landlord.services.bill_service import BillService
from landlord.services.billing_service import BillingService
from landlord.services.user_service import UserService
from landlord.storage.factory import get_storage

console = Console()


def _build_services() -> tuple[BillingService, BillService, UserService]:
    billing_repo = get_billing_repository()
    bill_repo = get_bill_repository()
    user_repo = get_user_repository()
    storage = get_storage()
    return (
        BillingService(billing_repo),
        BillService(bill_repo, storage),
        UserService(user_repo),
    )


def main_menu() -> None:
    billing_service, bill_service, user_service = _build_services()

    console.print()
    console.print("[bold]Gerador de Cobranças[/bold]", style="cyan")
    console.print()

    while True:
        choice = questionary.select(
            "Menu Principal",
            choices=[
                "Listar Cobranças",
                "Criar Nova Cobrança",
                "Gerenciar Usuários",
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
        elif choice == "Gerenciar Usuários":
            user_management_menu(user_service)
