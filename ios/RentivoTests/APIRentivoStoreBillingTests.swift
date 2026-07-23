import Foundation
import Testing
@testable import RentivoCore

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
