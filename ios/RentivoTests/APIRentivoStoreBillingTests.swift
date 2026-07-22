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
      body = #"{"items":[{"uuid":"billing-1","name":"Apartamento","description":"Aluguel","owner":{"type":"user","name":"Ana"},"capabilities":{"can_edit":true,"can_read_bills":true,"can_create_bills":true,"can_manage_bills":true,"can_read_expenses":true,"can_write_expenses":true,"can_create_exports":true,"can_read_attachments":true,"can_write_attachments":true,"can_read_theme":true,"can_manage_theme":true,"can_upload_bill_receipts":true,"can_delete":true,"can_transfer":true}}]}"#
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
