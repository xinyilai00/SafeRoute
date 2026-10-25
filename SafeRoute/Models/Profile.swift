//
//  Profile.swift
//  SafeRoute
//

import Foundation

/// Driver / passenger profile. The raw value is the exact string the backend expects in `"profile"`.
nonisolated enum Profile: String, CaseIterable, Identifiable, Codable {
    case teen
    case elderly
    case sensitivePassenger = "sensitive_passenger"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .teen: "Teen"
        case .elderly: "Elderly"
        case .sensitivePassenger: "Sensitive Passenger"
        }
    }

    /// One line shown under the name in the profile menu.
    var summary: String {
        switch self {
        case .teen: "New driver. Avoids merges and fast left turns."
        case .elderly: "Fewer left turns and complex junctions."
        case .sensitivePassenger: "Smooth ride. Avoids sharp turns and rough roads."
        }
    }

    /// Short label (kept for compact layouts).
    var shortName: String {
        switch self {
        case .teen: "Teen"
        case .elderly: "Elderly"
        case .sensitivePassenger: "Sensitive"
        }
    }

    /// SF Symbol shown next to the profile.
    var symbolName: String {
        switch self {
        case .teen: "graduationcap.fill"
        case .elderly: "eyeglasses"
        case .sensitivePassenger: "heart.fill"
        }
    }
}
