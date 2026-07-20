import Foundation

public struct MockFixtures: Sendable {
  public let snapshot: StoreSnapshot

  public init(snapshot: StoreSnapshot) {
    self.snapshot = snapshot
  }

  public static let canonical = MockFixtures(snapshot: canonicalSnapshot())

  private static func canonicalSnapshot() -> StoreSnapshot {
    let personalPix = PixConfiguration(
      key: "ana@example.com",
      merchantName: "ANA SILVA",
      merchantCity: "SAO PAULO"
    )
    let organizationPix = PixConfiguration(
      key: "12345678000190",
      merchantName: "IMOB HORIZONTE",
      merchantCity: "SAO PAULO"
    )
    let profile = UserProfile(id: StableID.userAna, email: "ana@example.com", pix: personalPix)
    let personalOwner = BillingOwner.user(id: profile.id, name: "Pessoal")
    let organizationOwner = BillingOwner.organization(
      id: StableID.organizationHorizonte,
      name: "Imobiliária Horizonte"
    )

    let billings = [
      billing(
        id: StableID.billingAurora101,
        name: "Apt 101 - Edifício Aurora",
        description: "Apartamento 2 quartos, bloco A",
        owner: personalOwner,
        items: [
          ("Aluguel", 180_000, .fixed),
          ("Condomínio", 65_000, .fixed),
          ("IPTU", 28_000, .fixed),
          ("Água", 0, .variable),
          ("Luz", 0, .variable),
        ]
      ),
      billing(
        id: StableID.billingAurora202,
        name: "Apt 202 - Edifício Aurora",
        description: "Apartamento 3 quartos, bloco B",
        owner: personalOwner,
        items: [
          ("Aluguel", 250_000, .fixed),
          ("Condomínio", 65_000, .fixed),
          ("IPTU", 35_000, .fixed),
          ("Água", 0, .variable),
          ("Luz", 0, .variable),
          ("Gás", 0, .variable),
        ]
      ),
      billing(
        id: StableID.billingSolNascente303,
        name: "Apt 303 - Residencial Sol Nascente",
        description: "Studio mobiliado",
        owner: personalOwner,
        items: [
          ("Aluguel", 120_000, .fixed),
          ("Condomínio", 45_000, .fixed),
          ("Internet", 10_000, .fixed),
          ("Água", 0, .variable),
        ]
      ),
      billing(
        id: StableID.billingVilaFlores1,
        name: "Casa 1 - Vila das Flores",
        description: "Casa 3 quartos com quintal",
        owner: organizationOwner,
        items: [
          ("Aluguel", 320_000, .fixed),
          ("IPTU", 42_000, .fixed),
          ("Água", 0, .variable),
          ("Luz", 0, .variable),
        ]
      ),
      billing(
        id: StableID.billingTorreNorte501,
        name: "Apt 501 - Torre Norte",
        description: "Cobertura duplex",
        owner: organizationOwner,
        items: [
          ("Aluguel", 450_000, .fixed),
          ("Condomínio", 120_000, .fixed),
          ("IPTU", 58_000, .fixed),
          ("Água", 0, .variable),
        ]
      ),
      billing(
        id: StableID.billingCentro12,
        name: "Sala 12 - Centro Empresarial",
        description: "Sala comercial 40 m²",
        owner: organizationOwner,
        items: [
          ("Aluguel", 200_000, .fixed),
          ("Condomínio", 35_000, .fixed),
          ("IPTU", 18_000, .fixed),
          ("Luz", 0, .variable),
        ]
      ),
    ]

    let paidReceipt = Receipt(
      id: stableUUID(2_001),
      name: "comprovante-pix-junho.pdf",
      sortOrder: 0
    )
    let bills = [
      bill(
        id: StableID.billDraft,
        billingID: StableID.billingAurora101,
        month: 7,
        status: .draft,
        variableAmount: 12_300
      ),
      bill(
        id: StableID.billPublished,
        billingID: StableID.billingAurora101,
        month: 8,
        status: .published,
        variableAmount: 11_100
      ),
      bill(
        id: StableID.billSent,
        billingID: StableID.billingAurora202,
        month: 7,
        status: .sent,
        variableAmount: 18_500
      ),
      bill(
        id: StableID.billPaid,
        billingID: StableID.billingAurora101,
        month: 6,
        status: .paid,
        variableAmount: 14_340,
        paidAt: DateOnly(year: 2026, month: 6, day: 8),
        receipts: [paidReceipt]
      ),
      bill(
        id: StableID.billCancelled,
        billingID: StableID.billingSolNascente303,
        month: 6,
        status: .cancelled,
        variableAmount: 8_700
      ),
      bill(
        id: StableID.billDelayed,
        billingID: StableID.billingVilaFlores1,
        month: 6,
        status: .delayedPayment,
        variableAmount: 16_000
      ),
    ]

    let expenses = [
      Expense(
        id: stableUUID(5_001),
        billingID: StableID.billingAurora101,
        description: "Manutenção do interfone",
        amount: Money(centavos: 25_000),
        category: .maintenance,
        incurredOn: DateOnly(year: 2026, month: 5, day: 18)
      ),
      Expense(
        id: stableUUID(5_002),
        billingID: StableID.billingVilaFlores1,
        description: "Seguro residencial",
        amount: Money(centavos: 18_000),
        category: .insurance,
        incurredOn: DateOnly(year: 2026, month: 4, day: 10)
      ),
    ]

    let anaMember = OrganizationMember(userID: profile.id, email: profile.email, role: .owner)
    let organizations = [
      Organization(
        id: StableID.organizationHorizonte,
        name: "Imobiliária Horizonte",
        pix: organizationPix,
        members: [
          anaMember,
          OrganizationMember(userID: stableUUID(11), email: "bruno@example.com", role: .admin),
          OrganizationMember(userID: stableUUID(12), email: "carla@example.com", role: .manager),
          OrganizationMember(userID: stableUUID(13), email: "diego@example.com", role: .viewer),
        ],
        requiresMFA: true,
        currentUserRole: .owner
      ),
      Organization(
        id: stableUUID(20),
        name: "Condomínio Aurora",
        pix: nil,
        members: [
          OrganizationMember(userID: stableUUID(21), email: "sindico@aurora.com", role: .owner)
        ],
        requiresMFA: false,
        currentUserRole: .viewer
      ),
    ]

    let now = Date(timeIntervalSince1970: 1_768_521_600)
    let integrationKey = APIKeyMetadata(
      id: StableID.apiKeyDashboard,
      name: "Painel financeiro",
      hint: "rntv-v1-abcd••yz",
      scopes: [.profileRead, .billingsRead, .expensesRead],
      grants: [APIKeyGrant(resourceType: .user, resourceID: profile.id)],
      expiresAt: Date(timeIntervalSince1970: 1_798_761_600),
      lastUsedAt: now,
      createdAt: Date(timeIntervalSince1970: 1_752_796_800),
      revokedAt: nil
    )

    return StoreSnapshot(
      profile: profile,
      billings: billings,
      bills: bills,
      expenses: expenses,
      attachments: [
        StableID.billingAurora101: [
          Attachment(
            id: stableUUID(6_001),
            name: "contrato-locacao.pdf",
            mediaType: "application/pdf",
            byteCount: 184_320
          )
        ]
      ],
      organizations: organizations,
      invitations: [
        Invitation(
          id: StableID.invitationHorizonte,
          organizationID: stableUUID(20),
          organizationName: "Condomínio Aurora",
          email: profile.email,
          role: .manager,
          status: .pending
        )
      ],
      communications: [],
      security: SecuritySummary(
        totpEnabled: true,
        recoveryCodeCount: 6,
        passkeys: [
          Passkey(
            id: stableUUID(7_001),
            name: "Notebook pessoal",
            createdAt: Date(timeIntervalSince1970: 1_736_640_000),
            lastUsedAt: now
          )
        ]
      ),
      apiKeys: [integrationKey],
      themes: [
        .user: .rentivo,
        .organization(StableID.organizationHorizonte): .rentivo,
        .billing(StableID.billingTorreNorte501): .sunset,
      ],
      activities: [
        RecentActivity(
          id: stableUUID(8_001),
          kind: .bill,
          title: "Fatura paga",
          detail: "Apt 101 - Edifício Aurora · junho de 2026",
          occurredAt: now
        )
      ]
    )
  }

  private static func billing(
    id: UUID,
    name: String,
    description: String,
    owner: BillingOwner,
    items: [(String, Int, BillingItemType)]
  ) -> Billing {
    Billing(
      id: id,
      name: name,
      description: description,
      owner: owner,
      items: items.enumerated().map { index, item in
        BillingItem(
          id: stableUUID(10_000 + index + Int(id.uuid.15)),
          description: item.0,
          amount: Money(centavos: item.1),
          type: item.2,
          sortOrder: index
        )
      },
      recipients: [
        BillingRecipient(
          id: stableUUID(20_000 + Int(id.uuid.15)),
          name: "Locatário",
          email: "locatario@example.com"
        )
      ],
      replyTo: "ana@example.com"
    )
  }

  private static func bill(
    id: UUID,
    billingID: UUID,
    month: Int,
    status: BillStatus,
    variableAmount: Int,
    paidAt: DateOnly? = nil,
    receipts: [Receipt] = []
  ) -> Bill {
    let fixedAmount: Int
    switch billingID {
    case StableID.billingAurora101: fixedAmount = 273_000
    case StableID.billingAurora202: fixedAmount = 350_000
    case StableID.billingSolNascente303: fixedAmount = 175_000
    case StableID.billingVilaFlores1: fixedAmount = 362_000
    case StableID.billingTorreNorte501: fixedAmount = 628_000
    default: fixedAmount = 253_000
    }
    return Bill(
      id: id,
      billingID: billingID,
      referenceMonth: ReferenceMonth(year: 2026, month: month),
      dueDate: DateOnly(year: 2026, month: month, day: 10),
      paidAt: paidAt,
      notes: status == .delayedPayment ? "Pagamento em acompanhamento." : "",
      status: status,
      lineItems: [
        BillLineItem(
          id: stableUUID(30_000 + Int(id.uuid.15)),
          description: "Itens fixos",
          amount: Money(centavos: fixedAmount),
          kind: .fixed
        ),
        BillLineItem(
          id: stableUUID(31_000 + Int(id.uuid.15)),
          description: "Consumo variável",
          amount: Money(centavos: variableAmount),
          kind: .variable
        ),
      ],
      receipts: receipts
    )
  }

  private static func stableUUID(_ value: Int) -> UUID {
    let suffix = String(format: "%012d", value)
    return UUID(uuidString: "00000000-0000-0000-0000-\(suffix)")!
  }
}
