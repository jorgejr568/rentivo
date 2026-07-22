import Foundation
import UniformTypeIdentifiers

public struct ResourceID<Tag>: RawRepresentable, Hashable, Codable, Sendable, Identifiable {
  public let rawValue: String

  public var id: String { rawValue }

  public init(rawValue: String) {
    self.rawValue = rawValue
  }
}

public enum BillingIDTag: Sendable {}
public typealias BillingID = ResourceID<BillingIDTag>
public enum BillIDTag: Sendable {}
public typealias BillID = ResourceID<BillIDTag>
public enum BillingItemIDTag: Sendable {}
public typealias BillingItemID = ResourceID<BillingItemIDTag>
public enum BillLineItemIDTag: Sendable {}
public typealias BillLineItemID = ResourceID<BillLineItemIDTag>
public enum ReceiptIDTag: Sendable {}
public typealias ReceiptID = ResourceID<ReceiptIDTag>
public enum ExpenseIDTag: Sendable {}
public typealias ExpenseID = ResourceID<ExpenseIDTag>
public enum AttachmentIDTag: Sendable {}
public typealias AttachmentID = ResourceID<AttachmentIDTag>
public enum OrganizationIDTag: Sendable {}
public typealias OrganizationID = ResourceID<OrganizationIDTag>
public enum InvitationIDTag: Sendable {}
public typealias InvitationID = ResourceID<InvitationIDTag>
public enum APIKeyIDTag: Sendable {}
public typealias APIKeyID = ResourceID<APIKeyIDTag>
public enum PasskeyIDTag: Sendable {}
public typealias PasskeyID = ResourceID<PasskeyIDTag>
public enum CommunicationIDTag: Sendable {}
public typealias CommunicationID = ResourceID<CommunicationIDTag>
public enum RecipientIDTag: Sendable {}
public typealias RecipientID = ResourceID<RecipientIDTag>
public enum WorkspaceIDTag: Sendable {}
public typealias WorkspaceID = ResourceID<WorkspaceIDTag>

public extension ResourceID where Tag == WorkspaceIDTag {
  static let personal = Self(rawValue: "personal")
}

public struct FileUpload: Hashable, Sendable {
  public let data: Data
  public let filename: String
  public let mediaType: String

  public init(data: Data, filename: String, mediaType: String) {
    self.data = data
    self.filename = filename
    self.mediaType = mediaType
  }

  public var byteCount: Int { data.count }

  public static func from(url: URL) throws -> Self {
    let filename = url.lastPathComponent
    let mediaType = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType
      ?? "application/octet-stream"
    return try Self(data: Data(contentsOf: url), filename: filename, mediaType: mediaType)
  }
}

public struct DownloadedFile: Hashable, Sendable {
  public let fileURL: URL
  public let filename: String
  public let mediaType: String

  public init(fileURL: URL, filename: String, mediaType: String) {
    self.fileURL = fileURL
    self.filename = filename
    self.mediaType = mediaType
  }
}

extension DownloadedFile: Identifiable {
  public var id: URL { fileURL }
}
