import Foundation
import Testing

#if canImport(RentivoCore)
  @testable import RentivoCore
#else
  @testable import Rentivo
#endif

@Test func communicationPreviewRequestUsesTheAPIContractFieldNames() throws {
  let request = RemoteCommunicationPreviewRequest(
    subject: "Fatura disponível", body: "Olá, sua fatura está pronta."
  )

  let payload = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: String]

  #expect(payload == [
    "subject": "Fatura disponível",
    "body": "Olá, sua fatura está pronta.",
  ])
}
