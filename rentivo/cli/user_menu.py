from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from rentivo.models.audit_log import AuditEventType
from rentivo.services.audit_serializers import serialize_user
from rentivo.services.audit_service import AuditService
from rentivo.services.user_service import UserService

console = Console()


def user_management_menu(user_service: UserService, audit_service: AuditService) -> None:
    while True:
        choice = questionary.select(
            "Gerenciar Usuários",
            choices=[
                "Criar Usuário",
                "Alterar Senha",
                "Listar Usuários",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            break
        elif choice == "Criar Usuário":
            _create_user(user_service, audit_service)
        elif choice == "Alterar Senha":
            _change_password(user_service, audit_service)
        elif choice == "Listar Usuários":
            _list_users(user_service)


def _create_user(user_service: UserService, audit_service: AuditService) -> None:
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

        audit_service.safe_log(
            AuditEventType.USER_CREATE,
            source="cli",
            entity_type="user",
            entity_id=user.id,
            new_state=serialize_user(user),
        )

        console.print(f"[green bold]Usuário '{user.username}' criado com sucesso![/green bold]")
    except Exception as e:
        console.print(f"[red]Erro ao criar usuário: {e}[/red]")


def _change_password(user_service: UserService, audit_service: AuditService) -> None:
    console.print()
    console.print("[bold]Alterar Senha[/bold]", style="cyan")

    users = user_service.list_users()
    if not users:
        console.print("[yellow]Nenhum usuário cadastrado.[/yellow]")
        return

    choices = [u.username for u in users] + ["Voltar"]
    username = questionary.select("Selecione o usuário:", choices=choices).ask()
    if username is None or username == "Voltar":
        return

    password = questionary.password("Nova senha:").ask()
    if not password:
        console.print("[yellow]Operação cancelada.[/yellow]")
        return

    confirm = questionary.password("Confirmar nova senha:").ask()
    if password != confirm:
        console.print("[red]As senhas não coincidem.[/red]")
        return

    # Find the user object for audit logging
    target_user = next((u for u in users if u.username == username), None)

    user_service.change_password(username, password)

    if target_user:
        audit_service.safe_log(
            AuditEventType.USER_CHANGE_PASSWORD,
            source="cli",
            entity_type="user",
            entity_id=target_user.id,
            metadata={"username": username},
        )

    console.print(f"[green bold]Senha do usuário '{username}' alterada com sucesso![/green bold]")


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
