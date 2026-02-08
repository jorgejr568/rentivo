from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from landlord.services.user_service import UserService

console = Console()


def user_management_menu(user_service: UserService) -> None:
    while True:
        choice = questionary.select(
            "Gerenciar Usuários",
            choices=[
                "Criar Usuário",
                "Listar Usuários",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            break
        elif choice == "Criar Usuário":
            _create_user(user_service)
        elif choice == "Listar Usuários":
            _list_users(user_service)


def _create_user(user_service: UserService) -> None:
    console.print()
    console.print("[bold]Novo Usuário[/bold]", style="cyan")

    username = questionary.text("Nome de usuário:").ask()
    if not username:
        console.print("[yellow]Operação cancelada.[/yellow]")
        return

    password = questionary.password("Senha:").ask()
    if not password:
        console.print("[yellow]Operação cancelada.[/yellow]")
        return

    confirm = questionary.password("Confirmar senha:").ask()
    if password != confirm:
        console.print("[red]As senhas não coincidem.[/red]")
        return

    try:
        user = user_service.create_user(username, password)
        console.print(f"[green bold]Usuário '{user.username}' criado com sucesso![/green bold]")
    except Exception as e:
        console.print(f"[red]Erro ao criar usuário: {e}[/red]")


def _list_users(user_service: UserService) -> None:
    users = user_service.list_users()

    if not users:
        console.print("[yellow]Nenhum usuário cadastrado.[/yellow]")
        return

    table = Table(title="Usuários")
    table.add_column("#", style="dim")
    table.add_column("Usuário", style="bold")
    table.add_column("Criado em")

    for u in users:
        created = u.created_at.strftime("%d/%m/%Y %H:%M") if u.created_at else "-"
        table.add_row(str(u.id), u.username, created)

    console.print()
    console.print(table)
    console.print()
