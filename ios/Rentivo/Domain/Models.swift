import Foundation

public enum LoadState<Value: Sendable>: Sendable {
    case idle
    case loading
    case loaded(Value)
    case empty
    case failed(DemoError)

    public var value: Value? {
        guard case let .loaded(value) = self else { return nil }
        return value
    }
}

public struct DemoError: Error, Equatable, LocalizedError, Sendable {
    public let message: String

    public init(message: String) {
        self.message = message
    }

    public init(_ error: any Error) {
        if let demoError = error as? DemoError {
            self = demoError
        } else {
            self.init(message: "Não foi possível concluir esta ação de demonstração.")
        }
    }

    public var errorDescription: String? { message }

    public static let operationFailed = DemoError(
        message: "Não foi possível concluir esta ação de demonstração."
    )
}

public enum StableID {
    public static let userAna = uuid("00000000-0000-0000-0000-000000000001")
    public static let billingAurora101 = uuid("00000000-0000-0000-0000-000000000101")
    public static let billPaid = uuid("00000000-0000-0000-0000-000000001004")

    private static func uuid(_ value: String) -> UUID {
        guard let identifier = UUID(uuidString: value) else {
            preconditionFailure("Invalid stable UUID: \(value)")
        }
        return identifier
    }
}
