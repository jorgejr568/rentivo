import questionary
from rich.console import Console

from rentivo.cli.billing_menu import create_billing_menu, list_billings_menu
from rentivo.cli.user_menu import user_management_menu
from rentivo.repositories.factory import (
    get_audit_log_repository,
    get_bill_repository,
    get_billing_repository,
    get_user_repository,
)
from rentivo.services.audit_service import AuditService
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.user_service import UserService
from rentivo.storage.factory import get_storage

console = Console()


def _build_services() -> tuple[BillingService, BillService, UserService, AuditService]:
    billing_repo = get_billing_repository()
    bill_repo = get_bill_repository()
    user_repo = get_user_repository()
    audit_repo = get_audit_log_repository()
    storage = get_storage()
    return (
        BillingService(billing_repo),
        BillService(bill_repo, storage),
        UserService(user_repo),
        AuditService(audit_repo),
    )


def main_menu() -> None:
    billing_service, bill_service, user_service, audit_service = _build_services()

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
            list_billings_menu(billing_service, bill_service, audit_service)
        elif choice == "Criar Nova Cobrança":
            create_billing_menu(billing_service, audit_service)
        elif choice == "Gerenciar Usuários":
            user_management_menu(user_service, audit_service)
