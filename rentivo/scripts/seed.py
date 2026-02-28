"""Seed the database with demo data for local development.

Usage:
    python -m rentivo.scripts.seed
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from faker import Faker
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from rentivo.db import get_connection, initialize_db
from rentivo.models import format_brl
from rentivo.models.billing import Billing, BillingItem, ItemType
from rentivo.models.organization import OrgRole
from rentivo.repositories.factory import (
    get_bill_repository,
    get_billing_repository,
    get_invite_repository,
    get_organization_repository,
    get_receipt_repository,
    get_user_repository,
)
from rentivo.services.bill_service import BillService
from rentivo.services.billing_service import BillingService
from rentivo.services.invite_service import InviteService
from rentivo.services.organization_service import OrganizationService
from rentivo.services.user_service import UserService
from rentivo.storage.factory import get_storage

console = Console()
fake = Faker("pt_BR")

MAIN_USERNAME = "admin"
PASSWORD = "password"
NUM_EXTRA_USERS = 9
ORG_NAME = "Imobiliaria Horizonte"

TABLES_TO_TRUNCATE = [
    "audit_logs",
    "receipts",
    "bill_line_items",
    "bills",
    "billing_items",
    "billings",
    "invites",
    "organization_members",
    "organizations",
    "users",
]

# Realistic PT-BR billing templates: (name, description, items)
# Items: (description, amount_centavos, item_type)
BILLING_TEMPLATES = [
    (
        "Apt 101 - Edifício Aurora",
        "Apartamento 2 quartos, bloco A",
        [
            ("Aluguel", 180000, ItemType.FIXED),
            ("Condomínio", 65000, ItemType.FIXED),
            ("IPTU", 28000, ItemType.FIXED),
            ("Água", 0, ItemType.VARIABLE),
            ("Luz", 0, ItemType.VARIABLE),
        ],
    ),
    (
        "Apt 202 - Edifício Aurora",
        "Apartamento 3 quartos, bloco B",
        [
            ("Aluguel", 250000, ItemType.FIXED),
            ("Condomínio", 65000, ItemType.FIXED),
            ("IPTU", 35000, ItemType.FIXED),
            ("Água", 0, ItemType.VARIABLE),
            ("Luz", 0, ItemType.VARIABLE),
            ("Gás", 0, ItemType.VARIABLE),
        ],
    ),
    (
        "Apt 303 - Residencial Sol Nascente",
        "Studio mobiliado",
        [
            ("Aluguel", 120000, ItemType.FIXED),
            ("Condomínio", 45000, ItemType.FIXED),
            ("Internet", 10000, ItemType.FIXED),
            ("Água", 0, ItemType.VARIABLE),
        ],
    ),
    (
        "Casa 1 - Vila das Flores",
        "Casa 3 quartos com quintal",
        [
            ("Aluguel", 320000, ItemType.FIXED),
            ("IPTU", 42000, ItemType.FIXED),
            ("Água", 0, ItemType.VARIABLE),
            ("Luz", 0, ItemType.VARIABLE),
            ("Gás", 0, ItemType.VARIABLE),
        ],
    ),
    (
        "Apt 501 - Torre Norte",
        "Cobertura duplex",
        [
            ("Aluguel", 450000, ItemType.FIXED),
            ("Condomínio", 120000, ItemType.FIXED),
            ("IPTU", 58000, ItemType.FIXED),
            ("Água", 0, ItemType.VARIABLE),
            ("Luz", 0, ItemType.VARIABLE),
        ],
    ),
    (
        "Sala 12 - Centro Empresarial",
        "Sala comercial 40m²",
        [
            ("Aluguel", 200000, ItemType.FIXED),
            ("Condomínio", 35000, ItemType.FIXED),
            ("IPTU", 18000, ItemType.FIXED),
            ("Luz", 0, ItemType.VARIABLE),
        ],
    ),
    (
        "Apt 104 - Edifício Ipê",
        "Apartamento 1 quarto",
        [
            ("Aluguel", 95000, ItemType.FIXED),
            ("Condomínio", 38000, ItemType.FIXED),
            ("Água", 0, ItemType.VARIABLE),
            ("Luz", 0, ItemType.VARIABLE),
        ],
    ),
    (
        "Casa 5 - Condomínio Lago Azul",
        "Casa 4 quartos em condomínio fechado",
        [
            ("Aluguel", 500000, ItemType.FIXED),
            ("Condomínio", 85000, ItemType.FIXED),
            ("IPTU", 62000, ItemType.FIXED),
            ("Água", 0, ItemType.VARIABLE),
            ("Luz", 0, ItemType.VARIABLE),
            ("Gás", 0, ItemType.VARIABLE),
            ("Internet", 15000, ItemType.FIXED),
        ],
    ),
]

BILL_NOTES = [
    "",
    "",
    "",
    "Consumo de água acima da média neste mês.",
    "Reajuste do condomínio aplicado.",
    "",
    "Manutenção do elevador incluída no condomínio.",
    "",
    "",
    "Taxa extra de pintura da fachada.",
    "",
    "",
]


def _truncate_all(conn) -> None:
    """Truncate all tables, disabling FK checks for MariaDB/MySQL."""
    console.print("\n[yellow]Truncating all tables...[/yellow]")
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in TABLES_TO_TRUNCATE:
        conn.execute(text(f"TRUNCATE TABLE {table}"))  # noqa: S608
        console.print(f"  Truncated [dim]{table}[/dim]")
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    conn.commit()
    console.print("[green]All tables truncated.[/green]\n")


def _create_users(user_service: UserService) -> list:
    """Create the main user + extra users. Returns list of all User objects."""
    console.print("[cyan]Creating users...[/cyan]")

    main_user = user_service.create_user(MAIN_USERNAME, PASSWORD)
    console.print(f"  [bold green]Main user:[/bold green] {main_user.username} (id={main_user.id})")

    users = [main_user]
    usernames_seen = {MAIN_USERNAME}
    for _ in range(NUM_EXTRA_USERS):
        username = fake.user_name()
        while username in usernames_seen:
            username = fake.user_name()
        usernames_seen.add(username)

        user = user_service.create_user(username, PASSWORD)
        console.print(f"  Created user: {user.username} (id={user.id})")
        users.append(user)

    console.print(f"[green]{len(users)} users created.[/green]\n")
    return users


def _create_organization(org_service: OrganizationService, users: list):
    """Create one org owned by the main user, add all others as viewers."""
    console.print("[cyan]Creating organization...[/cyan]")

    main_user = users[0]
    assert main_user.id is not None
    org = org_service.create_organization(ORG_NAME, main_user.id)
    console.print(f"  Organization: {org.name} (id={org.id})")

    for user in users[1:]:
        assert user.id is not None
        assert org.id is not None
        org_service.add_member(org.id, user.id, OrgRole.VIEWER.value)
        console.print(f"  Added [dim]{user.username}[/dim] as viewer")

    console.print(f"[green]Organization created with {len(users)} members.[/green]\n")
    return org


def _create_invites(invite_service: InviteService, org, users: list) -> None:
    """Create a few historical invites (already accepted since users are members).

    We use send_invite for users NOT yet members, then accept/decline them.
    Since all users are already members, we create a couple of extra users
    just for invite history, or we create invites referencing the existing flow.

    Actually, since all users are already members, we'll create invites
    directly via the repo to avoid service-level validation.
    """
    console.print("[cyan]Creating invite history...[/cyan]")

    # The invite service checks membership, so we'll create invite records
    # directly via the repository for historical records.
    from rentivo.models.invite import Invite, InviteStatus
    from rentivo.repositories.factory import get_invite_repository

    invite_repo = get_invite_repository()
    main_user = users[0]
    assert org.id is not None
    assert main_user.id is not None

    # Create accepted invites for a few members (simulating history)
    for user in users[1:4]:
        assert user.id is not None
        invite = Invite(
            organization_id=org.id,
            invited_user_id=user.id,
            invited_by_user_id=main_user.id,
            role=OrgRole.VIEWER.value,
            status=InviteStatus.ACCEPTED.value,
        )
        created = invite_repo.create(invite)
        # Mark as accepted
        assert created.id is not None
        invite_repo.update_status(created.id, InviteStatus.ACCEPTED.value)
        console.print(f"  Invite (accepted): {user.username}")

    # Create a couple of declined invites
    for user in users[4:6]:
        assert user.id is not None
        invite = Invite(
            organization_id=org.id,
            invited_user_id=user.id,
            invited_by_user_id=main_user.id,
            role=OrgRole.MANAGER.value,
            status=InviteStatus.DECLINED.value,
        )
        created = invite_repo.create(invite)
        assert created.id is not None
        invite_repo.update_status(created.id, InviteStatus.DECLINED.value)
        console.print(f"  Invite (declined): {user.username}")

    console.print("[green]Invite history created.[/green]\n")


def _create_billings(billing_service: BillingService, main_user, org) -> list[Billing]:
    """Create billings — some user-owned, some org-owned."""
    console.print("[cyan]Creating billings...[/cyan]")

    billings = []
    assert main_user.id is not None
    assert org.id is not None

    for i, (name, description, item_defs) in enumerate(BILLING_TEMPLATES):
        items = []
        for sort_order, (desc, amount, item_type) in enumerate(item_defs):
            items.append(
                BillingItem(
                    description=desc,
                    amount=amount,
                    item_type=item_type,
                    sort_order=sort_order,
                )
            )

        # First 3 billings owned by user, rest by organization
        if i < 3:
            owner_type = "user"
            owner_id = main_user.id
        else:
            owner_type = "organization"
            owner_id = org.id

        pix_key = fake.cpf() if random.random() > 0.3 else ""

        billing = billing_service.create_billing(
            name=name,
            description=description,
            items=items,
            pix_key=pix_key,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        billings.append(billing)
        owner_label = "user" if owner_type == "user" else f"org ({org.name})"
        console.print(f"  [bold]{billing.name}[/bold] — {len(items)} items, owner: {owner_label}")

    console.print(f"[green]{len(billings)} billings created.[/green]\n")
    return billings


def _create_bills(bill_service: BillService, billings: list[Billing]) -> int:
    """Generate bills for each billing, spanning the last 12 months."""
    console.print("[cyan]Generating bills with PDFs...[/cyan]")

    today = datetime.now()
    total_bills = 0

    table = Table(title="Bills generated")
    table.add_column("Billing", style="bold")
    table.add_column("Month")
    table.add_column("Total", justify="right")
    table.add_column("Due Date")
    table.add_column("Status")

    for billing in billings:
        assert billing.id is not None
        # Generate 3-5 bills per billing
        num_bills = random.randint(3, 5)
        months_ago_start = random.randint(num_bills, 12)

        for j in range(num_bills):
            month_offset = months_ago_start - j
            ref_date = today - timedelta(days=30 * month_offset)
            reference_month = ref_date.strftime("%Y-%m")

            # Generate variable amounts (random between R$30-R$250)
            variable_amounts: dict[int, int] = {}
            for item in billing.items:
                if item.item_type == ItemType.VARIABLE and item.id is not None:
                    variable_amounts[item.id] = random.randint(3000, 25000)

            # Occasionally add extras
            extras: list[tuple[str, int]] = []
            if random.random() > 0.7:
                extra_descs = [
                    "Multa por atraso",
                    "Reparo hidráulico",
                    "Pintura",
                    "Dedetização",
                    "Taxa de limpeza",
                ]
                extras.append((random.choice(extra_descs), random.randint(5000, 30000)))

            notes = random.choice(BILL_NOTES)
            due_day = random.choice([5, 10, 15, 20])
            due_date = f"{due_day:02d}/{ref_date.month:02d}/{ref_date.year}"

            bill = bill_service.generate_bill(
                billing=billing,
                reference_month=reference_month,
                variable_amounts=variable_amounts,
                extras=extras,
                notes=notes,
                due_date=due_date,
            )

            # Mark some bills as paid (older ones more likely)
            if month_offset > 2 and random.random() > 0.2:
                bill_service.toggle_paid(bill)
                status = "[green]paid[/green]"
            elif month_offset <= 1:
                status = "[yellow]pending[/yellow]"
            else:
                # Some overdue
                if random.random() > 0.5:
                    status = "[red]overdue[/red]"
                else:
                    bill_service.toggle_paid(bill)
                    status = "[green]paid[/green]"

            table.add_row(
                billing.name,
                bill.reference_month,
                format_brl(bill.total_amount),
                bill.due_date or "-",
                status,
            )
            total_bills += 1

    console.print(table)
    console.print(f"\n[green]{total_bills} bills generated with PDFs.[/green]\n")
    return total_bills


def main() -> None:
    console.print("[bold magenta]Rentivo — Database Seeder[/bold magenta]")
    console.print("=" * 40)

    initialize_db()
    conn = get_connection()

    # --- Truncate ---
    _truncate_all(conn)

    # --- Repositories & Services ---
    user_repo = get_user_repository()
    billing_repo = get_billing_repository()
    bill_repo = get_bill_repository()
    org_repo = get_organization_repository()
    invite_repo = get_invite_repository()
    receipt_repo = get_receipt_repository()
    storage = get_storage()

    user_service = UserService(user_repo)
    billing_service = BillingService(billing_repo)
    bill_service = BillService(bill_repo, storage, receipt_repo)
    org_service = OrganizationService(org_repo)
    invite_service = InviteService(invite_repo, org_repo, user_repo)

    # --- Seed ---
    users = _create_users(user_service)
    org = _create_organization(org_service, users)
    _create_invites(invite_service, org, users)
    billings = _create_billings(billing_service, users[0], org)
    total_bills = _create_bills(bill_service, billings)

    # --- Summary ---
    console.print("[bold green]Seeding complete![/bold green]")
    console.print(f"  Users:        {len(users)}")
    console.print(f"  Organization: 1 ({org.name})")
    console.print(f"  Billings:     {len(billings)}")
    console.print(f"  Bills:        {total_bills}")
    console.print(f"\n  Login with: [bold]{MAIN_USERNAME}[/bold] / [bold]{PASSWORD}[/bold]")


if __name__ == "__main__":  # pragma: no cover
    main()
