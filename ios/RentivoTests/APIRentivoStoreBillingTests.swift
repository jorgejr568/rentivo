import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@MainActor
@Test func liveBillingListHydratesRecurringItemsForThePortfolioSubtotal() async throws {
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: billingSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let billing = try #require(try await store.listBillings().first)

  #expect(billing.fixedSubtotal == Money(centavos: 12_500))
}

@MainActor
@Test func liveDashboardSummaryMapsTheBillingListAggregateStats() async throws {
  // Regression test for the dashboard bug: it used to fan out ~3N per-billing bill/expense
  // requests and mis-derive the money figures instead of reading the server's own rollup.
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: billingSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)

  _ = try #require(try await store.restoreSession())
  let summary = try await store.dashboardSummary()

  #expect(summary.received == Money(centavos: 50_000))
  #expect(summary.expenses == Money(centavos: 8_000))
  #expect(summary.netIncome == Money(centavos: 42_000))
  #expect(summary.overdue == Money(centavos: 5_000))
  #expect(summary.upcoming == Money(centavos: 20_000))
  // paid_count / billed_count * 100, matching the mock's paid/non-cancelled integer-math formula.
  #expect(summary.collectionRatePercent == 60)
}

@MainActor
@Test func liveCreateBillingNullsClientMintedItemUUIDsButKeepsServerIssuedULIDs() async throws {
  // Regression test for the 422 bug: BillingItemInput.uuid only accepts a 26-char ULID or null,
  // but freshly-added items carry a 36-char client UUID. Uses its own dedicated URLProtocol
  // (rather than the shared BillingURLProtocol) so the captured body can't race with other tests.
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [CapturingBillingCreateURLProtocol.self]
  CapturingBillingCreateURLProtocol.capturedBody = nil
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  let store = APIRentivoStore(client: client)
  _ = try #require(try await store.restoreSession())

  let clientMintedID = BillingItemID(rawValue: UUID().uuidString)
  let serverULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
  let draft = BillingDraft(
    name: "Apartamento", description: "Aluguel", owner: .user(id: 1, name: "Ana"),
    items: [
      BillingItem(id: clientMintedID, description: "Aluguel", amount: Money(centavos: 1_000), type: .fixed, sortOrder: 0),
      BillingItem(id: BillingItemID(rawValue: serverULID), description: "Água", amount: Money(centavos: 500), type: .variable, sortOrder: 1),
    ]
  )

  _ = try await store.createBilling(draft)

  let body = try #require(CapturingBillingCreateURLProtocol.capturedBody)
  let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
  let items = try #require(json["items"] as? [[String: Any]])
  #expect(items.count == 2)
  #expect(items[0]["uuid"] == nil || items[0]["uuid"] is NSNull)
  #expect(items[1]["uuid"] as? String == serverULID)
}

@MainActor
@Test func liveBillDecodesServerAvailableTransitionsAndTotalAmount() async throws {
  // Regression test: `available_transitions`/`total_amount` from `BillResponse` weren't decoded
  // into `Bill.availableTransitions`/`Bill.serverTotal`, so the UI always fell back to the local
  // `BillStatus` state machine and the client-summed total instead of the server-authoritative
  // values this endpoint already returns.
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: billDetailSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)
  _ = try #require(try await store.restoreSession())

  let bill = try await store.bill(billingID: BillingID(rawValue: "billing-1"), id: BillID(rawValue: "bill-1"))

  #expect(bill.availableTransitions == [.paid, .delayedPayment])
  #expect(bill.serverTotal == Money(centavos: 10_000))
  #expect(bill.effectiveTotal == Money(centavos: 10_000))
  #expect(bill.effectiveTransitions == Set([.paid, .delayedPayment]))
}

@MainActor
@Test func liveBillWithMalformedReferenceMonthThrowsInsteadOfCrashing() async throws {
  // Regression test: `bill(from:)` used to build `ReferenceMonth`/`DateOnly` with their
  // precondition-enforcing initializers straight from unchecked server strings, so a malformed
  // `reference_month` would trap the process. Adopting the failable wire initializers must turn
  // this into an ordinary decode error instead.
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: malformedBillSession(), credentials: credentials)
  let store = APIRentivoStore(client: client)
  _ = try #require(try await store.restoreSession())

  do {
    _ = try await store.bill(billingID: BillingID(rawValue: "billing-1"), id: BillID(rawValue: "bill-1"))
    Issue.record("Expected the malformed reference_month to throw instead of crashing")
  } catch let error as LiveAPIError {
    guard case .invalidResponse = error else {
      Issue.record("Expected .invalidResponse, got \(error)")
      return
    }
  }
}

private func billingSession() -> URLSession {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [BillingURLProtocol.self]
  return URLSession(configuration: configuration)
}

private final class BillingURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/billings":
      body = #"{"items":[{"uuid":"billing-1","name":"Apartamento","description":"Aluguel","owner":{"type":"user","name":"Ana"},"capabilities":{"can_edit":true,"can_read_bills":true,"can_create_bills":true,"can_manage_bills":true,"can_read_expenses":true,"can_write_expenses":true,"can_create_exports":true,"can_read_attachments":true,"can_write_attachments":true,"can_read_theme":true,"can_manage_theme":true,"can_upload_bill_receipts":true,"can_delete":true,"can_transfer":true}}],"user_pix_incomplete":false,"stats":{"year":2026,"expected":75000,"received":50000,"pending":20000,"overdue":5000,"paid_count":3,"pending_count":1,"overdue_count":1,"active_count":2,"billed_count":5,"total_expenses":8000,"net_income":42000}}"#
    case "/api/v1/billings/billing-1":
      body = #"{"uuid":"billing-1","name":"Apartamento","description":"Aluguel","owner":{"type":"user","name":"Ana"},"items":[{"uuid":"item-1","description":"Aluguel","amount":12500,"item_type":"fixed"}],"pix_key":"","pix_merchant_name":"","pix_merchant_city":"","recipients":[],"reply_to":[],"capabilities":{"can_edit":true,"can_read_bills":true,"can_create_bills":true,"can_manage_bills":true,"can_read_expenses":true,"can_write_expenses":true,"can_create_exports":true,"can_read_attachments":true,"can_write_attachments":true,"can_read_theme":true,"can_manage_theme":true,"can_upload_bill_receipts":true,"can_delete":true,"can_transfer":true}}"#
    default:
      body = #"{"detail":"Endpoint inesperado: \#(path ?? "nil")"}"#
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

// Dedicated to `liveCreateBillingNullsClientMintedItemUUIDsButKeepsServerIssuedULIDs` only, so its
// mutable capture state can't race with the other tests in this file.
private final class CapturingBillingCreateURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var capturedBody: Data?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/billings":
      Self.capturedBody = Self.requestBody(from: request)
      body = #"{"uuid":"billing-new","name":"Apartamento","description":"Aluguel","owner":{"type":"user","name":"Ana"},"items":[],"pix_key":"","pix_merchant_name":"","pix_merchant_city":"","recipients":[],"reply_to":[],"capabilities":{"can_edit":true,"can_read_bills":true,"can_create_bills":true,"can_manage_bills":true,"can_read_expenses":true,"can_write_expenses":true,"can_create_exports":true,"can_read_attachments":true,"can_write_attachments":true,"can_read_theme":true,"can_manage_theme":true,"can_upload_bill_receipts":true,"can_delete":true,"can_transfer":true}}"#
    default:
      body = #"{"detail":"Endpoint inesperado: \#(path ?? "nil")"}"#
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  static func requestBody(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let bufferSize = 4096
    var buffer = [UInt8](repeating: 0, count: bufferSize)
    while stream.hasBytesAvailable {
      let read = stream.read(&buffer, maxLength: bufferSize)
      if read <= 0 { break }
      data.append(buffer, count: read)
    }
    return data
  }
}

private func billDetailSession() -> URLSession {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [BillDetailURLProtocol.self]
  return URLSession(configuration: configuration)
}

private final class BillDetailURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/billings/billing-1/bills/bill-1":
      body = #"{"uuid":"bill-1","reference_month":"2026-07","notes":"","status":"sent","due_date":"2026-07-10","status_updated_at": null,"line_items":[{"description":"Aluguel","amount":10000,"item_type":"fixed"}],"receipts":[],"total_amount":10000,"available_transitions":[{"target":"paid","label":"Marcar como paga","style":"primary","requires_confirmation":false},{"target":"delayed_payment","label":"Marcar como atrasada","style":"secondary","requires_confirmation":true}]}"#
    default:
      body = #"{"detail":"Endpoint inesperado: \#(path ?? "nil")"}"#
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

private func malformedBillSession() -> URLSession {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [MalformedBillURLProtocol.self]
  return URLSession(configuration: configuration)
}

private final class MalformedBillURLProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/billings/billing-1/bills/bill-1":
      // Out-of-range month (13): with the raw precondition initializer this used to trap the
      // process instead of throwing a decode error.
      body = #"{"uuid":"bill-1","reference_month":"2026-13","notes":"","status":"draft","due_date":"2026-07-10","status_updated_at": null,"line_items":[],"receipts":[],"total_amount":0,"available_transitions":[]}"#
    default:
      body = #"{"detail":"Endpoint inesperado: \#(path ?? "nil")"}"#
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(body.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}
