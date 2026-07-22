import Foundation
import Testing
@testable import RentivoCore

@Test func passwordChangeRequestUsesTheAPIContractFieldNames() throws {
  let request = RemotePasswordChange(
    currentPassword: "old-password", newPassword: "new-password", confirmPassword: "new-password"
  )

  let payload = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: String]

  #expect(payload == [
    "current_password": "old-password",
    "new_password": "new-password",
    "confirm_password": "new-password",
  ])
}
