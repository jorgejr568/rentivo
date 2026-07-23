import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

// MARK: - Multipart body encoding (`APIRentivoStore.multipartBody`/`sanitizedFilename`)
//
// `multipartBody` and `sanitizedFilename` are private, so they're exercised indirectly through
// the two public upload entry points (`addReceipt`, `addAttachment`) with a capturing
// `URLProtocol`, following the same stubbed-session pattern as `APIRentivoStoreEncodingTests`.
// Each test gets its own dedicated `URLProtocol` subclass (rather than sharing one with mutable
// static capture state) so concurrently-running `@Test`s can't race on that state.

@MainActor
@Test func addReceiptSendsARentivoBoundaryAndSanitizesAFilenameCarryingHeaderInjectionCharacters() async throws {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [CapturingReceiptUploadURLProtocol.self]
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  let store = APIRentivoStore(client: client)
  _ = try #require(try await store.restoreSession())

  // A filename crafted to break out of the quoted `filename="..."` attribute (or the header line
  // entirely) if it were sent unsanitized: an embedded quote plus a CRLF.
  let upload = FileUpload(
    data: Data("%PDF-1.4".utf8),
    filename: "nota\r\ninjetada\".pdf",
    mediaType: "application/pdf"
  )

  _ = try await store.addReceipt(
    billingID: BillingID(rawValue: "billing-1"), billID: BillID(rawValue: "bill-1"), upload: upload
  )

  let contentTypeHeader = try #require(CapturingReceiptUploadURLProtocol.capturedContentTypeHeader)
  #expect(contentTypeHeader.hasPrefix("multipart/form-data; boundary=RentivoBoundary-"))
  let boundary = String(contentTypeHeader.dropFirst("multipart/form-data; boundary=".count))

  let body = try #require(CapturingReceiptUploadURLProtocol.capturedBody)
  let bodyString = try #require(String(data: body, encoding: .utf8))

  // Opens and closes with the exact boundary markers multipart/form-data requires.
  #expect(bodyString.hasPrefix("--\(boundary)\r\n"))
  #expect(bodyString.hasSuffix("--\(boundary)--\r\n"))

  // The dangerous characters never reach the header line...
  #expect(!bodyString.contains("nota\r\ninjetada\""))
  // ...but the sanitized filename (CRLF and quote stripped) is still present as the attribute
  // value, and the field name/content-type are set as the upload call requested.
  #expect(bodyString.contains(#"Content-Disposition: form-data; name="receipt_files"; filename="notainjetada.pdf""#))
  #expect(bodyString.contains("Content-Type: application/pdf"))
  #expect(bodyString.contains("%PDF-1.4"))
}

private final class CapturingReceiptUploadURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var capturedContentTypeHeader: String?
  nonisolated(unsafe) static var capturedBody: Data?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/billings/billing-1/bills/bill-1/receipts":
      Self.capturedContentTypeHeader = request.value(forHTTPHeaderField: "Content-Type")
      Self.capturedBody = Self.requestBody(from: request)
      body = #"{"items":[{"uuid":"receipt-1","filename":"notainjetada.pdf","content_type":"application/pdf","file_size":8,"sort_order":0}]}"#
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

@MainActor
@Test func addAttachmentSendsATopLevelNameFieldAlongsideTheSanitizedFilePart() async throws {
  let configuration = URLSessionConfiguration.ephemeral
  configuration.protocolClasses = [CapturingAttachmentUploadURLProtocol.self]
  let credentials = MemoryCredentialStore(token: "stored-token")
  let client = LiveAPIClient(session: URLSession(configuration: configuration), credentials: credentials)
  let store = APIRentivoStore(client: client)
  _ = try #require(try await store.restoreSession())

  let upload = FileUpload(
    data: Data("contrato".utf8), filename: "contrato-locacao.pdf", mediaType: "application/pdf"
  )

  _ = try await store.addAttachment(billingID: BillingID(rawValue: "billing-1"), upload: upload)

  let body = try #require(CapturingAttachmentUploadURLProtocol.capturedBody)
  let bodyString = try #require(String(data: body, encoding: .utf8))

  #expect(bodyString.contains(#"Content-Disposition: form-data; name="name""#))
  #expect(bodyString.contains("\r\n\r\ncontrato-locacao.pdf\r\n"))
  #expect(bodyString.contains(#"name="file"; filename="contrato-locacao.pdf""#))
}

private final class CapturingAttachmentUploadURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var capturedBody: Data?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let path = request.url?.path
    let body: String
    switch path {
    case "/api/v1/auth/session":
      body = #"{"status":"authenticated","bootstrap":{"user":{"id":7,"email":"ana@rentivo.com.br"}}}"#
    case "/api/v1/billings/billing-1/attachments":
      Self.capturedBody = Self.requestBody(from: request)
      body = #"{"uuid":"attachment-1","name":"contrato-locacao.pdf","content_type":"application/pdf","file_size":8}"#
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
