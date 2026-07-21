// swift-tools-version: 6.0

import PackageDescription

let package = Package(
  name: "RentivoCore",
  platforms: [
    .macOS(.v14),
    .iOS(.v17),
  ],
  products: [
    .library(name: "RentivoCore", targets: ["RentivoCore"])
  ],
  dependencies: [
    .package(url: "https://github.com/apple/swift-openapi-generator", from: "1.13.0"),
    .package(url: "https://github.com/apple/swift-openapi-runtime", from: "1.12.0"),
    .package(url: "https://github.com/apple/swift-openapi-urlsession", from: "1.3.1"),
  ],
  targets: [
    .target(
      name: "RentivoCore",
      dependencies: [
        .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
        .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession"),
      ],
      path: "Rentivo",
      exclude: ["App", "DesignSystem", "Features", "Resources"],
      sources: ["Domain", "Data"],
      plugins: [.plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")]
    ),
    .testTarget(
      name: "RentivoCoreTests",
      dependencies: ["RentivoCore"],
      path: "RentivoTests"
    ),
  ]
)
