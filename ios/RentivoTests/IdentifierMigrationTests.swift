import Foundation
import Testing
@testable import RentivoCore

@Test func opaqueIdentifiersDoNotRequireUUIDParsing() {
  let billing = BillingID(rawValue: "01K0RENTIVO7QVK5R9H5G2Z0AB")
  let organization = OrganizationID(rawValue: "org_public_slug_like_value")
  #expect(billing.rawValue == "01K0RENTIVO7QVK5R9H5G2Z0AB")
  #expect(organization.rawValue == "org_public_slug_like_value")
}

@Test func fileUploadCarriesActualBytes() {
  let upload = FileUpload(
    data: Data([0x25, 0x50, 0x44, 0x46]),
    filename: "recibo.pdf",
    mediaType: "application/pdf"
  )
  #expect(upload.byteCount == 4)
}

@Test func personalAPIKeyGrantUsesLiteralPersonalWorkspace() {
  #expect(WorkspaceID.personal.rawValue == "personal")
}
