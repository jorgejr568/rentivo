import Foundation
import Testing
@testable import RentivoCore

@MainActor
@Test func liveCreateBillEncodesVariableAmountsForMatchingULIDsAndOmitsClientMintedIDs() async throws {
  // Regression test: createBill used to send only `extras`, silently dropping user-edited
  // variable line amounts. The server requires `variable_amounts` to be keyed by the billing's
  // own variable-item ULIDs; a freshly client-minted line item id must not be sent as a key.
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [CapturingBillCreateURLProtocol.self]
  CapturingBillCreateURLProtocol.capturedBody = nil
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  let store = APIRentivoStore(client: client)
  _ = try #require(try await store.restoreSession())

  let variableItemULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
  let clientMintedID = BillLineItemID(rawValue: UUID().uuidString)
  let draft = BillDraft(
    billingID: BillingID(rawValue: "billing-1"),
    referenceMonth: ReferenceMonth(year: 2026, month: 7),
    dueDate: DateOnly(year: 2026, month: 7, day: 10),
    notes: "",
    lineItems: [
      BillLineItem(id: BillLineItemID(rawValue: variableItemULID), description: "Água", amount: Money(centavos: 4_200), kind: .variable),
      BillLineItem(id: clientMintedID, description: "Taxa extra", amount: Money(centavos: 1_000), kind: .extra),
    ]
  )

  _ = try await store.createBill(draft)

  let body = try #require(CapturingBillCreateURLProtocol.capturedBody)
  let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
  let variableAmountsRaw = try #require(json["variable_amounts"] as? [String: Any])
  let variableAmounts = variableAmountsRaw.compactMapValues { $0 as? Int }
  #expect(variableAmounts == [variableItemULID: 4_200])
  let extras = try #require(json["extras"] as? [[String: Any]])
  #expect(extras.count == 1)
  #expect(extras.first?["amount"] as? Int == 1_000)
}

@MainActor
@Test func liveSendCommunicationPreservesExistingRecipientsAndResolvesTypedEmails() async throws {
  // Regression test: sendCommunication used to full-replace the billing's recipients with only
  // the ad-hoc emails typed for a single send, deleting every other configured recipient, and
  // fabricated the returned CommunicationRecord instead of using the server's response.
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [RecipientsPreservingURLProtocol.self]
  RecipientsPreservingURLProtocol.capturedPutBody = nil
  RecipientsPreservingURLProtocol.capturedSendBody = nil
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  let store = APIRentivoStore(client: client)
  _ = try #require(try await store.restoreSession())

  let record = try await store.sendCommunication(
    billingID: BillingID(rawValue: "billing-1"),
    billID: BillID(rawValue: "bill-1"),
    recipients: ["Maria@Example.com", "novo@example.com"],
    subject: "Fatura de julho",
    message: "Segue a fatura."
  )

  // The existing recipient must be resent with its original name (not overwritten), and only the
  // genuinely-new email gets appended (with a derived name, since the caller has no better one).
  let putBody = try #require(RecipientsPreservingURLProtocol.capturedPutBody)
  let putJSON = try #require(JSONSerialization.jsonObject(with: putBody) as? [String: Any])
  let putItems = try #require(putJSON["items"] as? [[String: String]])
  #expect(Set(putItems.compactMap { $0["email"] }) == Set(["maria@example.com", "novo@example.com"]))
  #expect(putItems.first { $0["email"] == "maria@example.com" }?["name"] == "Maria")
  #expect(putItems.first { $0["email"] == "novo@example.com" }?["name"] == "novo")

  // The send request must use the uuids the server just assigned, resolved by matching email.
  let sendBody = try #require(RecipientsPreservingURLProtocol.capturedSendBody)
  let sendJSON = try #require(JSONSerialization.jsonObject(with: sendBody) as? [String: Any])
  let recipientUUIDs = try #require(sendJSON["recipient_uuids"] as? [String])
  #expect(Set(recipientUUIDs) == Set(["contact-new-1", "contact-new-2"]))

  #expect(record.recipients == ["Maria@Example.com", "novo@example.com"])
  #expect(record.subject == "Fatura de julho")
}

// Dedicated to the createBill encoding test only, so its mutable capture state can't race with
// other tests.
private final class CapturingBillCreateURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var capturedBody: Data?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/billings/billing-1/bills":
      Self.capturedBody = Self.requestBody(from: request)
      body = #"{"uuid":"bill-1","reference_month":"2026-07","notes":"","status":"draft","due_date":"2026-07-10","status_updated_at": null,"line_items":[{"description":"Água","amount":4200,"item_type":"variable"},{"description":"Taxa extra","amount":1000,"item_type":"extra"}],"receipts":[]}"#
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

// Dedicated to the sendCommunication encoding test only, so its mutable capture state can't race
// with other tests.
private final class RecipientsPreservingURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var capturedPutBody: Data?
  nonisolated(unsafe) static var capturedSendBody: Data?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch (request.httpMethod, path) {
    case ("GET", "/api/v1/auth/session"):
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case ("GET", "/api/v1/billings/billing-1"):
      body = #"{"uuid":"billing-1","name":"Apartamento","description":"Aluguel","owner":{"type":"user","name":"Ana"},"items":[{"uuid":"item-1","description":"Aluguel","amount":12500,"item_type":"fixed"}],"pix_key":"","pix_merchant_name":"","pix_merchant_city":"","recipients":[{"uuid":"contact-old-1","name":"Maria","email":"maria@example.com"}],"reply_to":[],"capabilities":{"can_edit":true,"can_read_bills":true,"can_create_bills":true,"can_manage_bills":true,"can_read_expenses":true,"can_write_expenses":true,"can_create_exports":true,"can_read_attachments":true,"can_write_attachments":true,"can_read_theme":true,"can_manage_theme":true,"can_upload_bill_receipts":true,"can_delete":true,"can_transfer":true}}"#
    case ("PUT", "/api/v1/billings/billing-1/recipients"):
      Self.capturedPutBody = Self.requestBody(from: request)
      body = #"{"items":[{"uuid":"contact-new-1","name":"Maria","email":"maria@example.com"},{"uuid":"contact-new-2","name":"novo","email":"novo@example.com"}]}"#
    case ("POST", "/api/v1/billings/billing-1/communications/send"):
      Self.capturedSendBody = Self.requestBody(from: request)
      body = #"{"queued_count": 2}"#
    default:
      body = #"{"detail":"Endpoint inesperado: \#(request.httpMethod ?? "?") \#(path ?? "nil")"}"#
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
