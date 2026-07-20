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
  targets: [
    .target(
      name: "RentivoCore",
      path: "Rentivo",
      sources: ["Domain", "Data"]
    ),
    .testTarget(
      name: "RentivoCoreTests",
      dependencies: ["RentivoCore"],
      path: "RentivoTests"
    ),
  ]
)
